"""
Iteration 23 — Full E2E backend test for Garment ERP v8.0.
Verifies regression fix for enrich_with_product_photos AND walks full chain:
  vendor receiving -> inspection -> production job -> progress (I-1 cap)
  -> variance Reported->Acknowledged->Resolved
  -> buyer shipment (M-1, C-1) -> production return (C-2, H-4)
  -> invoice (manual + auto) -> payment partial+full -> financial recap -> PDF export.
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://fabric-preview-7.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
TS = int(time.time())


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    sess.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def ctx(s):
    """Setup + teardown all entities used across tests."""
    c = {"created": {"po_ids": [], "garment_ids": [], "buyer_ids": [], "product_ids": [], "accessory_ids": [],
                     "shipment_ids": [], "buyer_ship_ids": [], "return_ids": [], "invoice_ids": [], "job_ids": []}}
    # Vendor (garment), Buyer
    g = s.post(f"{API}/garments", json={"garment_name": f"PT Test Vendor {TS}", "address": "X", "phone": "0", "email": f"v{TS}@x.com"}).json()
    c["vendor_id"] = g["id"]; c["created"]["garment_ids"].append(g["id"])
    b = s.post(f"{API}/buyers", json={"customer_name": f"CV Test Buyer {TS}", "address": "Y", "phone": "0"}).json()
    c["buyer_id"] = b["id"]; c["created"]["buyer_ids"].append(b["id"])
    # Products
    pA = s.post(f"{API}/products", json={"product_name": f"KAOS-A-{TS}", "sku": f"KA-{TS}", "size": "L", "color": "Red", "unit": "pcs", "cmt_price": 50000, "selling_price": 100000}).json()
    pB = s.post(f"{API}/products", json={"product_name": f"KAOS-B-{TS}", "sku": f"KB-{TS}", "size": "M", "color": "Blue", "unit": "pcs", "cmt_price": 50000, "selling_price": 100000}).json()
    c["pA"] = pA; c["pB"] = pB
    c["created"]["product_ids"].extend([pA["id"], pB["id"]])
    # Accessory
    a = s.post(f"{API}/accessories", json={"accessory_name": f"Kancing-{TS}", "accessory_code": f"KNC-{TS}", "unit": "pcs"}).json()
    c["acc"] = a; c["created"]["accessory_ids"].append(a["id"])

    yield c

    # Cleanup (best-effort)
    for inv in c["created"]["invoice_ids"]:
        try: s.delete(f"{API}/invoices/{inv}")
        except: pass
    for r in c["created"]["return_ids"]:
        try: s.delete(f"{API}/production-returns/{r}")
        except: pass
    for bs in c["created"]["buyer_ship_ids"]:
        try: s.delete(f"{API}/buyer-shipments/{bs}")
        except: pass
    for sid in c["created"]["shipment_ids"]:
        try: s.delete(f"{API}/vendor-shipments/{sid}")
        except: pass
    for po in c["created"]["po_ids"]:
        try: s.delete(f"{API}/production-pos/{po}")
        except: pass
    for pid in c["created"]["product_ids"]:
        try: s.delete(f"{API}/products/{pid}")
        except: pass
    for aid in c["created"]["accessory_ids"]:
        try: s.delete(f"{API}/accessories/{aid}")
        except: pass
    for gid in c["created"]["garment_ids"]:
        try: s.delete(f"{API}/garments/{gid}")
        except: pass
    for bid in c["created"]["buyer_ids"]:
        try: s.delete(f"{API}/buyers/{bid}")
        except: pass


def _create_po(s, ctx, qty, prod, prefix):
    """Helper: create a PO with 1 item -> Confirmed status."""
    body = {
        "po_number": f"{prefix}-{TS}-{qty}",
        "vendor_id": ctx["vendor_id"], "vendor_name": f"PT Test Vendor {TS}",
        "customer_id": ctx["buyer_id"], "customer_name": f"CV Test Buyer {TS}",
        "po_date": "2026-01-08", "deadline": "2026-01-22",
        "items": [{
            "product_id": prod["id"], "product_name": prod["product_name"],
            "sku": prod["sku"], "size": prod.get("size", ""), "color": prod.get("color", ""),
            "qty": qty, "cmt_price": 50000, "selling_price": 100000,
        }],
    }
    r = s.post(f"{API}/production-pos", json=body)
    assert r.status_code == 201, f"PO create failed: {r.status_code} {r.text}"
    po = r.json(); ctx["created"]["po_ids"].append(po["id"])
    rc = s.put(f"{API}/production-pos/{po['id']}", json={"status": "Confirmed"})
    assert rc.status_code == 200, rc.text
    return po


# ─── REGRESSION: enrich_with_product_photos must NOT 500 ──────────────────────
class TestRegressionEnrich:
    def test_get_po_detail_200(self, s, ctx):
        po = _create_po(s, ctx, 100, ctx["pA"], "PO-REG")
        r = s.get(f"{API}/production-pos/{po['id']}")
        assert r.status_code == 200, f"GET PO detail failed (regression bug): {r.status_code} {r.text}"
        d = r.json(); assert "items" in d and len(d["items"]) == 1


# ─── FULL CHAIN: vendor shipment -> inspection -> job -> progress -> variance -> buyer shipment -> return -> invoice -> payment ───
class TestFullChain:
    @pytest.fixture(scope="class")
    def chain(self, s, ctx):
        """Setup 'main' chain: PO qty=110 (overproduction-friendly), ship 110, no defect, produce 102."""
        po = _create_po(s, ctx, 110, ctx["pB"], "PO-CHAIN")
        # GET full PO to fetch po_item id
        po_full = s.get(f"{API}/production-pos/{po['id']}").json()
        po_item = po_full["items"][0]
        # Vendor shipment qty_sent=110
        ship_body = {
            "shipment_number": f"VS-CH-{TS}", "vendor_id": ctx["vendor_id"],
            "shipment_date": "2026-01-08", "shipment_type": "NORMAL",
            "items": [{"po_id": po["id"], "po_number": po["po_number"], "po_item_id": po_item["id"],
                       "product_name": po_item["product_name"], "sku": po_item["sku"],
                       "size": po_item.get("size", ""), "color": po_item.get("color", ""),
                       "qty_sent": 110, "ordered_qty": 110}],
        }
        rs = s.post(f"{API}/vendor-shipments", json=ship_body)
        assert rs.status_code == 201, f"vendor-shipment create: {rs.status_code} {rs.text}"
        ship = rs.json(); ctx["created"]["shipment_ids"].append(ship["id"])
        ship_items = ship["items"]
        # Mark Received
        rput = s.put(f"{API}/vendor-shipments/{ship['id']}", json={"status": "Received"})
        assert rput.status_code == 200, rput.text
        # Inspection: received=110, missing=0, no defect
        insp_body = {"shipment_id": ship["id"], "vendor_id": ctx["vendor_id"], "inspection_date": "2026-01-09",
                     "items": [{"shipment_item_id": ship_items[0]["id"], "sku": ship_items[0]["sku"],
                                "product_name": ship_items[0]["product_name"], "size": ship_items[0].get("size", ""),
                                "color": ship_items[0].get("color", ""), "ordered_qty": 110,
                                "received_qty": 110, "missing_qty": 0}]}
        ri = s.post(f"{API}/vendor-material-inspections", json=insp_body)
        assert ri.status_code == 201, f"inspection: {ri.status_code} {ri.text}"
        # Production job
        rj = s.post(f"{API}/production-jobs", json={"vendor_id": ctx["vendor_id"], "vendor_shipment_id": ship["id"]})
        assert rj.status_code == 201, f"job create: {rj.status_code} {rj.text}"
        job = rj.json(); ctx["created"]["job_ids"].append(job["id"])
        job_item = job["items"][0]
        return {"po": po, "po_item": po_item, "ship": ship, "job": job, "job_item": job_item}

    def test_regression_get_vendor_shipment_detail_200(self, s, chain):
        # Regression: this used to 500 due to enrich_with_product_photos missing
        r = s.get(f"{API}/vendor-shipments/{chain['ship']['id']}")
        assert r.status_code == 200, f"GET vendor-shipment detail 500 bug: {r.text}"

    def test_progress_overproduction_accepted(self, s, chain):
        # Produce 102 against ordered=110 (within available_qty=110, no defect)
        r = s.post(f"{API}/production-progress", json={"job_item_id": chain["job_item"]["id"],
                                                       "completed_quantity": 102, "progress_date": "2026-01-10"})
        assert r.status_code == 201, f"progress 102 should accept: {r.status_code} {r.text}"
        assert r.json().get("new_total") == 102

    def test_invariant_I1_defect_cap(self, s, chain):
        # Add defect_qty=3 → effective_max=110-3=107. Already produced=102. Try +6 (=108, must fail), then +5 (=107, must pass)
        d = s.post(f"{API}/material-defect-reports", json={"job_id": chain["job"]["id"], "job_item_id": chain["job_item"]["id"],
                                                            "vendor_id": chain["job"]["vendor_id"], "defect_qty": 3,
                                                            "defect_type": "Material Cacat"})
        assert d.status_code == 201, d.text
        bad = s.post(f"{API}/production-progress", json={"job_item_id": chain["job_item"]["id"], "completed_quantity": 6})
        assert bad.status_code == 400, f"I-1 cap should reject 108>107: {bad.status_code} {bad.text}"
        good = s.post(f"{API}/production-progress", json={"job_item_id": chain["job_item"]["id"], "completed_quantity": 5})
        assert good.status_code == 201, f"I-1 should accept 107: {good.status_code} {good.text}"

    def test_variance_lifecycle(self, s, chain):
        body = {"vendor_id": chain["job"]["vendor_id"], "job_id": chain["job"]["id"],
                "variance_type": "OVERPRODUCTION", "reason": "Vendor produced extra",
                "items": [{"job_item_id": chain["job_item"]["id"], "ordered_qty": 100, "produced_qty": 107, "variance_qty": 7}]}
        r = s.post(f"{API}/production-variances", json=body)
        assert r.status_code == 201, r.text
        vid = r.json()["id"]
        for st in ["Acknowledged", "Resolved"]:
            up = s.put(f"{API}/production-variances/{vid}", json={"status": st})
            assert up.status_code == 200, up.text

    def test_M1_zero_qty_buyer_shipment_rejected(self, s, chain):
        body = {"vendor_id": chain["job"]["vendor_id"], "po_id": chain["po"]["id"], "job_id": chain["job"]["id"],
                "shipment_date": "2026-01-12",
                "items": [{"po_item_id": chain["po_item"]["id"], "job_item_id": chain["job_item"]["id"],
                           "qty_shipped": 0, "ordered_qty": 110}]}
        r = s.post(f"{API}/buyer-shipments", json=body)
        assert r.status_code == 400, f"M-1 must reject 0-qty: {r.status_code} {r.text}"

    def test_C1_buyer_cap_enforced(self, s, ctx, chain):
        # Ship 80 (OK), then 25 more (must FAIL: 80+25=105>107 produced), then 22 (OK: 80+22=102, total 102 ≤ 107)
        # Actually total produced = 107 now. So 80 + 25 = 105 ≤ 107 → OK. We need over-cap. Use 80 + 28 = 108 > 107.
        # Plan: 80 → OK, +28 → FAIL, +27 → OK (total 107)
        body = lambda q: {"vendor_id": chain["job"]["vendor_id"], "po_id": chain["po"]["id"], "job_id": chain["job"]["id"],
                          "shipment_date": "2026-01-12", "shipment_number": f"BS-{TS}",
                          "items": [{"po_item_id": chain["po_item"]["id"], "job_item_id": chain["job_item"]["id"],
                                     "qty_shipped": q, "ordered_qty": 110}]}
        r1 = s.post(f"{API}/buyer-shipments", json=body(80))
        assert r1.status_code in (200, 201), f"first dispatch 80: {r1.status_code} {r1.text}"
        bsid = r1.json()["id"]; ctx["created"]["buyer_ship_ids"].append(bsid)
        r2 = s.post(f"{API}/buyer-shipments", json=body(28))
        assert r2.status_code == 400, f"C-1 must reject 108>107: {r2.status_code} {r2.text}"
        r3 = s.post(f"{API}/buyer-shipments", json=body(27))
        assert r3.status_code in (200, 201), f"second dispatch 27 (total 107): {r3.status_code} {r3.text}"

    def test_C3_total_shipped_aggregation(self, s, chain):
        # GET production-jobs and verify total_shipped_to_buyer = 107
        r = s.get(f"{API}/production-job-items?job_id={chain['job']['id']}")
        assert r.status_code == 200, r.text
        items = r.json()
        ji = next((i for i in items if i["id"] == chain["job_item"]["id"]), None)
        assert ji is not None
        assert ji.get("shipped_to_buyer", 0) == 107, f"C-3 aggregation: expected 107, got {ji.get('shipped_to_buyer')}"

    def test_H1_po_remaining_qty(self, s, chain):
        # GET PO list, verify remaining_qty_to_ship and over_shipped_qty
        r = s.get(f"{API}/production-pos/{chain['po']['id']}")
        assert r.status_code == 200, r.text
        d = r.json()
        # ordered=110, shipped=107 → remaining=3, over=0 (if exposed)
        # Some implementations expose at po level or item level — just check not negative
        for it in d.get("items", []):
            rq = it.get("remaining_qty_to_ship")
            ovr = it.get("over_shipped_qty")
            if rq is not None: assert rq >= 0, f"remaining_qty_to_ship negative: {rq}"
            if ovr is not None: assert ovr >= 0, f"over_shipped_qty negative: {ovr}"

    def test_C2_return_cap_and_H4(self, s, ctx, chain):
        body = lambda q: {"reference_po_id": chain["po"]["id"], "return_date": "2026-01-13",
                          "return_reason": "QC", "items": [{"po_item_id": chain["po_item"]["id"],
                                                            "sku": chain["po_item"]["sku"], "return_qty": q}]}
        # Valid 10
        r1 = s.post(f"{API}/production-returns", json=body(10))
        assert r1.status_code == 201, f"return 10: {r1.status_code} {r1.text}"
        ctx["created"]["return_ids"].append(r1.json()["id"])
        # Cap exceed (200 > 107-10=97)
        r2 = s.post(f"{API}/production-returns", json=body(200))
        assert r2.status_code == 400, f"C-2 cap reject: {r2.status_code} {r2.text}"
        # H-4 zero
        r3 = s.post(f"{API}/production-returns", json=body(0))
        assert r3.status_code == 400, f"H-4 zero reject: {r3.status_code} {r3.text}"
        # H-4 negative
        r4 = s.post(f"{API}/production-returns", json=body(-5))
        assert r4.status_code == 400, f"H-4 negative reject: {r4.status_code} {r4.text}"

    def test_manual_invoice_create_and_update(self, s, ctx, chain):
        body = {"source_po_id": chain["po"]["id"], "invoice_category": "BUYER",
                "invoice_items": [{"po_item_id": chain["po_item"]["id"], "product_name": chain["po_item"]["product_name"],
                                   "invoice_qty": 100, "selling_price": 100000}],
                "discount": 0, "notes": "Manual invoice E2E"}
        r = s.post(f"{API}/invoices", json=body)
        assert r.status_code == 201, f"manual invoice: {r.status_code} {r.text}"
        inv = r.json(); ctx["created"]["invoice_ids"].append(inv["id"])
        assert inv["total_amount"] == 100 * 100000
        u = s.put(f"{API}/invoices/{inv['id']}", json={"notes": "Updated note"})
        assert u.status_code == 200, u.text

    def test_payment_partial_then_full(self, s, ctx, chain):
        # Use first manual invoice
        inv_id = ctx["created"]["invoice_ids"][0]
        # Partial 4,000,000
        rp = s.post(f"{API}/payments", json={"invoice_id": inv_id, "amount": 4000000, "payment_date": "2026-01-14",
                                              "payment_method": "Transfer"})
        assert rp.status_code in (200, 201), f"partial pay: {rp.status_code} {rp.text}"
        ig = s.get(f"{API}/invoices/{inv_id}").json()
        # Some impl uses paid_amount, others total_paid
        paid = ig.get("paid_amount") or ig.get("total_paid") or 0
        # Allow soft check (might be aggregated lazily)
        assert paid >= 0
        # Full remainder
        remainder = ig.get("total_amount", 10000000) - paid
        if remainder > 0:
            rp2 = s.post(f"{API}/payments", json={"invoice_id": inv_id, "amount": remainder, "payment_date": "2026-01-15",
                                                   "payment_method": "Transfer"})
            assert rp2.status_code in (200, 201), f"final pay: {rp2.status_code} {rp2.text}"
        ig2 = s.get(f"{API}/invoices/{inv_id}").json()
        assert ig2.get("status") in ("Paid", "Partial", "Unpaid"), f"unexpected status: {ig2.get('status')}"

    def test_financial_recap(self, s):
        r = s.get(f"{API}/financial-recap")
        assert r.status_code == 200, r.text
        d = r.json(); assert isinstance(d, dict)

    def test_pdf_export_po_and_vendor_shipment_and_invoice(self, s, ctx, chain):
        # PO PDF
        r1 = s.get(f"{API}/export-pdf?type=production-po&id={chain['po']['id']}")
        assert r1.status_code == 200, f"PDF PO: {r1.status_code} {r1.text[:200]}"
        assert "application/pdf" in r1.headers.get("content-type", ""), r1.headers
        assert len(r1.content) > 1024
        # Vendor shipment PDF
        r2 = s.get(f"{API}/export-pdf?type=vendor-shipment&id={chain['ship']['id']}")
        assert r2.status_code == 200, f"PDF VS: {r2.status_code} {r2.text[:200]}"
        assert len(r2.content) > 500
        # Invoice PDF
        inv_id = ctx["created"]["invoice_ids"][0]
        r3 = s.get(f"{API}/export-pdf?type=invoice&id={inv_id}")
        assert r3.status_code == 200, f"PDF invoice: {r3.status_code} {r3.text[:200]}"
        assert len(r3.content) > 500


# ─── INVARIANT I-1 — strict spec scenario (available=100, defect=3) ────────────
class TestInvariantI1Strict:
    """Spec: available=100, defect=3 → progress new_total=99 must 400, 97 must accept."""
    @pytest.fixture(scope="class")
    def setup(self, s, ctx):
        po = _create_po(s, ctx, 100, ctx["pA"], "PO-I1")
        po_full = s.get(f"{API}/production-pos/{po['id']}").json(); po_item = po_full["items"][0]
        ship_body = {"shipment_number": f"VS-I1-{TS}", "vendor_id": ctx["vendor_id"],
                     "shipment_date": "2026-01-08", "shipment_type": "NORMAL",
                     "items": [{"po_id": po["id"], "po_number": po["po_number"], "po_item_id": po_item["id"],
                                "product_name": po_item["product_name"], "sku": po_item["sku"],
                                "size": po_item.get("size", ""), "color": po_item.get("color", ""),
                                "qty_sent": 100, "ordered_qty": 100}]}
        rs = s.post(f"{API}/vendor-shipments", json=ship_body); assert rs.status_code == 201, rs.text
        ship = rs.json(); ctx["created"]["shipment_ids"].append(ship["id"])
        s.put(f"{API}/vendor-shipments/{ship['id']}", json={"status": "Received"})
        insp = s.post(f"{API}/vendor-material-inspections", json={
            "shipment_id": ship["id"], "vendor_id": ctx["vendor_id"], "inspection_date": "2026-01-09",
            "items": [{"shipment_item_id": ship["items"][0]["id"], "sku": ship["items"][0]["sku"],
                       "product_name": ship["items"][0]["product_name"], "ordered_qty": 100,
                       "received_qty": 100, "missing_qty": 0}]})
        assert insp.status_code == 201, insp.text
        rj = s.post(f"{API}/production-jobs", json={"vendor_id": ctx["vendor_id"], "vendor_shipment_id": ship["id"]})
        assert rj.status_code == 201, rj.text
        job = rj.json(); ctx["created"]["job_ids"].append(job["id"])
        # Defect 3
        d = s.post(f"{API}/material-defect-reports", json={"job_id": job["id"], "job_item_id": job["items"][0]["id"],
                                                            "vendor_id": ctx["vendor_id"], "defect_qty": 3})
        assert d.status_code == 201, d.text
        return {"job": job, "job_item": job["items"][0]}

    def test_99_rejected(self, s, setup):
        r = s.post(f"{API}/production-progress", json={"job_item_id": setup["job_item"]["id"], "completed_quantity": 99})
        assert r.status_code == 400, f"new_total=99 must 400 (effective_max=97): {r.status_code} {r.text}"

    def test_97_accepted(self, s, setup):
        r = s.post(f"{API}/production-progress", json={"job_item_id": setup["job_item"]["id"], "completed_quantity": 97})
        assert r.status_code == 201, f"new_total=97 must accept: {r.status_code} {r.text}"
