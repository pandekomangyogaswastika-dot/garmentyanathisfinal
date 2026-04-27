"""
Production Flow Audit Script
Tests the end-to-end production flow and edge cases:
  1. Happy path: PO → Shipment → Inspection → Job → Progress → Buyer Shipment
  2. Missing items (inspection qty < sent qty)
  3. Material defects (defect report during production)
  4. Production returns (retur from buyer)
  5. Variances (over/under production)
"""
import requests
import json
import sys
from datetime import datetime, timedelta

BASE = "http://localhost:8001/api"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}

findings = []  # List of (severity, category, title, detail)


def add_finding(sev, cat, title, detail):
    findings.append({"severity": sev, "category": cat, "title": title, "detail": detail})
    print(f"  [{sev}] {cat} :: {title}")
    if detail:
        print(f"       → {detail}")


def login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["token"]


def post(token, path, payload, expected=(200, 201)):
    r = requests.post(f"{BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}"})
    return r


def put(token, path, payload):
    return requests.put(f"{BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}"})


def get(token, path):
    return requests.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"})


def dump(label, data):
    print(f"\n===== {label} =====")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, default=str)[:2500])
    else:
        print(data)


def main():
    print("=" * 70)
    print("PRODUCTION FLOW AUDIT — Garment ERP v8.0")
    print("=" * 70)
    token = login(**ADMIN)
    print("✔  admin logged in")

    # ─────────── SEED MASTER DATA ────────────
    print("\n[STEP 1] Seeding master data (garment, buyer, product, variants)")
    g = post(token, "/garments", {
        "garment_code": "GM-A01", "garment_name": "Audit Vendor",
        "contact_person": "Test", "email": "v@audit.com", "phone": "08100000"
    })
    if g.status_code not in (200, 201):
        add_finding("HIGH", "Seed", "Cannot create garment",
                    f"{g.status_code}: {g.text}")
        # Try fetching existing to reuse
        existing = get(token, "/garments").json()
        if existing:
            vendor = existing[0]
        else:
            sys.exit("No vendor available to test with")
    else:
        vendor = g.json()
    print(f"  vendor: {vendor['garment_name']} ({vendor['id']})")

    b = post(token, "/buyers", {
        "buyer_name": "Audit Buyer Co.", "contact_person": "Tony", "email": "tony@buyer.com"
    })
    buyer = b.json() if b.ok else (get(token, "/buyers").json() or [{}])[0]
    print(f"  buyer: {buyer.get('buyer_name')} ({buyer.get('id')})")

    p = post(token, "/products", {
        "product_name": "Audit T-Shirt", "selling_price": 100000, "cmt_price": 25000
    })
    product = p.json() if p.ok else (get(token, "/products").json() or [{}])[0]
    print(f"  product: {product.get('product_name')} ({product.get('id')})")

    v1 = post(token, "/product-variants", {
        "product_id": product["id"], "sku": "AUD-S-BLK", "size": "S", "color": "Black"
    })
    v2 = post(token, "/product-variants", {
        "product_id": product["id"], "sku": "AUD-M-BLK", "size": "M", "color": "Black"
    })
    variant1 = v1.json() if v1.ok else None
    variant2 = v2.json() if v2.ok else None
    print(f"  variants: {variant1.get('sku')}, {variant2.get('sku')}")

    # ─────────── CREATE PRODUCTION PO ────────────
    print("\n[STEP 2] Create Production PO with 2 items (100 S, 80 M)")
    po_number = f"AUDIT-PO-{int(datetime.now().timestamp())}"
    po_body = {
        "po_number": po_number,
        "buyer_id": buyer["id"], "vendor_id": vendor["id"],
        "po_date": datetime.now().isoformat(),
        "deadline": (datetime.now() + timedelta(days=30)).isoformat(),
        "delivery_deadline": (datetime.now() + timedelta(days=45)).isoformat(),
        "status": "Confirmed",
        "items": [
            {"product_id": product["id"], "variant_id": variant1["id"],
             "qty": 100, "sku": variant1["sku"], "size": "S", "color": "Black",
             "serial_number": "SN-001",
             "selling_price_snapshot": 100000, "cmt_price_snapshot": 25000},
            {"product_id": product["id"], "variant_id": variant2["id"],
             "qty": 80, "sku": variant2["sku"], "size": "M", "color": "Black",
             "serial_number": "SN-002",
             "selling_price_snapshot": 100000, "cmt_price_snapshot": 25000},
        ]
    }
    r = post(token, "/production-pos", po_body)
    if not r.ok:
        add_finding("CRITICAL", "PO", "Cannot create PO", f"{r.status_code}: {r.text}")
        sys.exit()
    po = r.json()
    po_items = po["items"]
    print(f"  PO created: {po['po_number']} with {len(po_items)} items")
    print(f"  PO status: {po['status']}")

    # ─────────── VENDOR SHIPMENT (MATERIALS → VENDOR) ────────────
    print("\n[STEP 3] Admin ships materials to vendor (100 S + 80 M)")
    ship_body = {
        "shipment_number": f"SJ-{po_number}",
        "delivery_note_number": f"DN-{po_number}",
        "vendor_id": vendor["id"],
        "shipment_date": datetime.now().isoformat(),
        "shipment_type": "NORMAL",
        "items": [
            {"po_id": po["id"], "po_number": po["po_number"], "po_item_id": po_items[0]["id"],
             "qty_sent": 100},
            {"po_id": po["id"], "po_number": po["po_number"], "po_item_id": po_items[1]["id"],
             "qty_sent": 80},
        ]
    }
    r = post(token, "/vendor-shipments", ship_body)
    if not r.ok:
        add_finding("CRITICAL", "Shipment", "Cannot create shipment", f"{r.status_code}: {r.text}")
        sys.exit()
    shipment = r.json()
    print(f"  shipment: {shipment['shipment_number']} status={shipment['status']}")
    ship_items = shipment["items"]

    # ─── Mark shipment as Received (simulating vendor acknowledgement) ───
    put(token, f"/vendor-shipments/{shipment['id']}", {"status": "Received"})
    print(f"  shipment marked as Received")

    # ─────────── SCENARIO A: INSPECTION WITH MISSING ITEMS ────────────
    print("\n[STEP 4] SCENARIO A — Inspection: Size S fully received (100), Size M received 75 (5 missing)")
    insp_body = {
        "shipment_id": shipment["id"],
        "inspection_date": datetime.now().isoformat(),
        "overall_notes": "Paket M rusak, 5 pcs hilang",
        "items": [
            {"shipment_item_id": ship_items[0]["id"], "sku": variant1["sku"],
             "product_name": product["product_name"], "size": "S", "color": "Black",
             "ordered_qty": 100, "received_qty": 100, "missing_qty": 0,
             "condition_notes": "OK"},
            {"shipment_item_id": ship_items[1]["id"], "sku": variant2["sku"],
             "product_name": product["product_name"], "size": "M", "color": "Black",
             "ordered_qty": 80, "received_qty": 75, "missing_qty": 5,
             "condition_notes": "5 pcs hilang di paket"},
        ]
    }
    r = post(token, "/vendor-material-inspections", insp_body)
    if not r.ok:
        add_finding("CRITICAL", "Inspection", "Cannot create inspection", f"{r.status_code}: {r.text}")
        sys.exit()
    insp = r.json()
    print(f"  inspection created: recv={insp['total_received']} miss={insp['total_missing']}")

    # ── Check: Does missing materials auto-generate a material request? ──
    reqs = get(token, "/material-requests").json()
    has_missing_material_req = any(
        r.get("original_shipment_id") == shipment["id"] and
        r.get("category") != "accessories"
        for r in reqs
    )
    if not has_missing_material_req:
        add_finding("HIGH", "Inspection",
                    "No auto material request generated for missing MATERIAL items",
                    "Missing 5 pcs of size M during inspection; backend auto-creates "
                    "a request only for missing ACCESSORIES (line 1001). For missing MATERIAL, "
                    "the vendor must manually file a REPLACEMENT request.")

    # ─────────── CREATE PRODUCTION JOB ────────────
    print("\n[STEP 5] Create Production Job from shipment")
    r = post(token, "/production-jobs", {
        "vendor_id": vendor["id"],
        "vendor_shipment_id": shipment["id"],
        "po_id": po["id"],
        "notes": "Job audit"
    })
    if not r.ok:
        add_finding("CRITICAL", "Job", "Cannot create job", f"{r.status_code}: {r.text}")
        sys.exit()
    job = r.json()
    job_items = job["items"]
    print(f"  job: {job['job_number']}, items:")
    for ji in job_items:
        print(f"    - {ji['sku']} shipment_qty={ji['shipment_qty']} available_qty={ji['available_qty']}")

    # ── Check: available_qty should reflect INSPECTED received_qty, not qty_sent ──
    m_item = next(i for i in job_items if i["sku"] == variant2["sku"])
    if m_item["available_qty"] != 75:
        add_finding("HIGH", "Job", "Job item available_qty not adjusted for missing items",
                    f"Expected 75 (inspected qty) but got {m_item['available_qty']}. "
                    "This would allow vendor to produce more than physically received.")
    else:
        print(f"  ✔ available_qty correctly reflects inspected qty (75 vs 80 sent)")

    # ─────────── SCENARIO B: DEFECT REPORT ────────────
    print("\n[STEP 6] SCENARIO B — Report material defect: 3 pcs S damaged during cutting")
    s_job_item = next(i for i in job_items if i["sku"] == variant1["sku"])
    r = post(token, "/material-defect-reports", {
        "job_id": job["id"],
        "job_item_id": s_job_item["id"],
        "po_id": po["id"],
        "po_item_id": s_job_item["po_item_id"],
        "sku": variant1["sku"], "size": "S", "color": "Black",
        "product_name": product["product_name"],
        "defect_qty": 3, "defect_type": "Material Cacat",
        "description": "3 pcs material sobek saat cutting",
        "shipment_id": shipment["id"],
    })
    if not r.ok:
        add_finding("HIGH", "Defect", "Cannot create defect report", f"{r.status_code}: {r.text}")
    else:
        defect = r.json()
        print(f"  defect reported: {defect['defect_qty']} pcs, id={defect['id'][:8]}…")

    # ── Verify defect is reflected in job detail ──
    r = get(token, f"/production-jobs/{job['id']}")
    job_detail = r.json()
    s_ji_detail = next((i for i in job_detail["items"] if i["sku"] == variant1["sku"]), None)
    if s_ji_detail:
        expected_effective = 100 - 3
        if s_ji_detail.get("effective_available_qty") != expected_effective:
            add_finding("MED", "Defect", "effective_available_qty not reduced by defect qty",
                        f"Expected {expected_effective} but got {s_ji_detail.get('effective_available_qty')}.")
        else:
            print(f"  ✔ effective_available_qty reduced: {s_ji_detail['effective_available_qty']}")

    # ── Attempt to produce MORE THAN effective_available_qty ──
    # The backend check uses 'available_qty' NOT 'effective_available_qty', so defects are ignored in validation.
    print("\n[STEP 7] SCENARIO B2 — Attempt to record progress ABOVE defect-adjusted capacity")
    r = post(token, "/production-progress", {
        "job_item_id": s_job_item["id"],
        "completed_quantity": 100,  # produce all 100, ignoring that 3 are defect
        "progress_date": datetime.now().isoformat(),
        "notes": "Should this be blocked?"
    })
    if r.ok:
        add_finding("MED", "Defect", "Progress validation ignores defect-adjusted capacity",
                    f"Vendor could record 100 pcs produced even though 3 pcs are defect. "
                    "The 'available_qty' cap (100) is used, not 'effective_available_qty' (97). "
                    "This lets vendor over-claim production beyond what material can yield.")
        print(f"  ⚠ progress 100 accepted despite defect of 3")
    else:
        print(f"  ✔ progress 100 correctly rejected: {r.status_code}: {r.json().get('error')}")
        # Reduce to valid qty
        r = post(token, "/production-progress", {
            "job_item_id": s_job_item["id"], "completed_quantity": 97,
            "progress_date": datetime.now().isoformat(), "notes": "Adjusted for defects"
        })
        if not r.ok:
            add_finding("CRITICAL", "Progress", "Cannot record progress", r.text)

    # Record M size partial production
    m_job_item = next(i for i in job_items if i["sku"] == variant2["sku"])
    post(token, "/production-progress", {
        "job_item_id": m_job_item["id"], "completed_quantity": 70,
        "progress_date": datetime.now().isoformat(), "notes": "M almost done"
    })

    # ─── Fetch PO quantity summary ───
    r = get(token, f"/production-pos/{po['id']}/quantity-summary")
    if r.ok:
        summary = r.json()
        print(f"\n[STEP 8] PO quantity summary: {json.dumps(summary, indent=2, default=str)[:600]}")

    # ─────────── SCENARIO C: BUYER SHIPMENT ────────────
    print("\n[STEP 9] Vendor ships finished goods to buyer")
    r = post(token, "/buyer-shipments", {
        "vendor_id": vendor["id"],
        "po_id": po["id"],
        "po_number": po["po_number"],
        "customer_name": buyer["buyer_name"],
        "job_id": job["id"],
        "shipment_date": datetime.now().isoformat(),
        "items": [
            {"po_item_id": s_job_item["po_item_id"], "job_item_id": s_job_item["id"],
             "ordered_qty": 100, "qty_shipped": 97},
            {"po_item_id": m_job_item["po_item_id"], "job_item_id": m_job_item["id"],
             "ordered_qty": 80, "qty_shipped": 70},
        ]
    })
    if not r.ok:
        add_finding("HIGH", "BuyerShipment", "Cannot create buyer shipment", r.text)
        sys.exit()
    bs = r.json()
    print(f"  buyer shipment: {bs['shipment_number']} status={bs['ship_status']}")

    # ── Check: is over-shipping blocked? ──
    print("\n[STEP 10] SCENARIO C2 — Try to OVER-SHIP to buyer (ship 500 when only 97 produced)")
    r = post(token, "/buyer-shipments", {
        "vendor_id": vendor["id"], "po_id": po["id"], "job_id": job["id"],
        "shipment_date": datetime.now().isoformat(),
        "items": [
            {"po_item_id": s_job_item["po_item_id"], "job_item_id": s_job_item["id"],
             "ordered_qty": 100, "qty_shipped": 500}
        ]
    })
    if r.ok:
        add_finding("HIGH", "BuyerShipment", "Over-ship validation missing",
                    "Vendor shipped 500 pcs while only 97 were produced. "
                    "Backend does not validate that qty_shipped <= produced_qty - already_shipped.")
        print(f"  ⚠ over-ship of 500 accepted!")
    else:
        print(f"  ✔ over-ship blocked: {r.status_code}")

    # ─────────── SCENARIO D: PRODUCTION RETURN ────────────
    print("\n[STEP 11] SCENARIO D — Buyer returns 2 pcs S for repair")
    r = post(token, "/production-returns", {
        "customer_name": buyer["buyer_name"],
        "reference_po_id": po["id"],
        "return_date": datetime.now().isoformat(),
        "return_reason": "Produk Cacat",
        "notes": "Jahitan longgar",
        "items": [
            {"po_item_id": s_job_item["po_item_id"], "sku": variant1["sku"],
             "product_name": product["product_name"], "serial_number": "SN-001",
             "size": "S", "color": "Black", "return_qty": 2,
             "defect_type": "Jahitan Longgar", "repair_notes": "Jahit ulang kerah"}
        ]
    })
    if not r.ok:
        add_finding("HIGH", "Return", "Cannot create return", r.text)
    else:
        ret = r.json()
        print(f"  return created: {ret['return_number']} qty={ret['total_return_qty']}")

    # ── Try: Return more than shipped to buyer ──
    print("\n[STEP 12] SCENARIO D2 — Try to RETURN 999 pcs (more than 97 shipped)")
    r = post(token, "/production-returns", {
        "customer_name": buyer["buyer_name"],
        "reference_po_id": po["id"],
        "return_date": datetime.now().isoformat(),
        "return_reason": "Produk Cacat",
        "items": [
            {"po_item_id": s_job_item["po_item_id"], "sku": variant1["sku"],
             "size": "S", "color": "Black", "return_qty": 999,
             "defect_type": "Lainnya"}
        ]
    })
    if r.ok:
        add_finding("HIGH", "Return", "Over-return validation missing",
                    "Return for 999 pcs accepted but only 97 were shipped to buyer. "
                    "Backend `create_return` does not validate return_qty vs max_returnable.")
        print(f"  ⚠ 999 pcs return accepted!")
    else:
        print(f"  ✔ over-return blocked: {r.status_code}")

    # ── Validate: po-items-produced endpoint ──
    print("\n[STEP 13] Check po-items-produced endpoint for return accounting")
    r = get(token, f"/po-items-produced?po_id={po['id']}")
    if r.ok:
        for it in r.json():
            print(f"    {it['sku']}: produced={it['total_produced']} shipped={it['total_shipped']} "
                  f"returned={it['total_returned']} max_returnable={it['max_returnable']}")

    # ─────────── SCENARIO E: PRODUCTION VARIANCE ────────────
    print("\n[STEP 14] SCENARIO E — Vendor reports OVERPRODUCTION of 2 pcs")
    r = post(token, "/production-variances", {
        "vendor_id": vendor["id"],
        "job_id": job["id"], "po_id": po["id"],
        "variance_type": "OVERPRODUCTION",
        "reason": "Operator produced extras",
        "items": [{
            "job_item_id": s_job_item["id"], "sku": variant1["sku"],
            "product_name": product["product_name"],
            "ordered_qty": 100, "produced_qty": 102, "variance_qty": 2
        }]
    })
    if not r.ok:
        add_finding("MED", "Variance", "Cannot create variance", r.text)
    else:
        var = r.json()
        print(f"  variance reported: {var['variance_type']} qty={var['total_variance_qty']}")

    # ── Check: negative qty / zero qty ──
    print("\n[STEP 15] NEGATIVE TESTS — Zero/negative qty validation")
    tests = [
        ("inspection with negative received_qty",
         lambda: post(token, "/vendor-material-inspections", {
             "shipment_id": shipment["id"],
             "items": [{"sku": "X", "received_qty": -10, "missing_qty": 0}]})),
        ("progress with 0 qty",
         lambda: post(token, "/production-progress", {
             "job_item_id": s_job_item["id"], "completed_quantity": 0})),
        ("progress with negative qty",
         lambda: post(token, "/production-progress", {
             "job_item_id": s_job_item["id"], "completed_quantity": -5})),
        ("return with negative qty",
         lambda: post(token, "/production-returns", {
             "customer_name": "X", "reference_po_id": po["id"],
             "items": [{"sku": "AUD-S-BLK", "return_qty": -5}]})),
    ]
    for label, fn in tests:
        r = fn()
        if r.ok:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
            add_finding("MED", "Validation", f"No validation: {label}",
                        f"Accepted with {r.status_code}. Response: {str(body)[:120]}")
            print(f"  ⚠ {label}: accepted ({r.status_code})")
        else:
            print(f"  ✔ {label}: rejected ({r.status_code})")

    # ── Double inspection guard ──
    print("\n[STEP 16] Try to inspect the same shipment twice")
    r = post(token, "/vendor-material-inspections", {
        "shipment_id": shipment["id"],
        "items": [{"sku": variant1["sku"], "received_qty": 50}]})
    if r.ok:
        add_finding("HIGH", "Inspection", "Duplicate inspection allowed", "")
    else:
        print(f"  ✔ duplicate inspection blocked ({r.status_code})")

    # ─────────── SUMMARY ────────────
    print("\n" + "=" * 70)
    print("AUDIT FINDINGS SUMMARY")
    print("=" * 70)
    by_sev = {}
    for f in findings:
        by_sev.setdefault(f["severity"], []).append(f)

    for sev in ("CRITICAL", "HIGH", "MED", "LOW"):
        if sev in by_sev:
            print(f"\n{sev} ({len(by_sev[sev])})")
            for f in by_sev[sev]:
                print(f"  • [{f['category']}] {f['title']}")
                if f["detail"]:
                    print(f"        {f['detail']}")

    print(f"\nTotal issues: {len(findings)}")

    with open("/app/tests/audit_production_findings.json", "w") as f:
        json.dump(findings, f, indent=2)
    print("  → /app/tests/audit_production_findings.json written")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nFATAL: {e}")
        sys.exit(1)
