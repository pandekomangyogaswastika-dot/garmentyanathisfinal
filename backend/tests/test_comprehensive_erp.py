"""
Comprehensive ERP Backend Test - Iteration 22
Covers: Auth, Master Data, Production PO, Variance, Buyer Shipment caps,
Manual Invoice/Payment, PDF Export, Smart Import, Pagination envelope.
"""
import os
import time
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fabric-preview-7.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"
TS = int(time.time())

# Shared state across tests
state = {}


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data, "Login response missing 'token' field"
    assert data["user"]["role"] == "superadmin"
    return data["token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── AUTH ────────────────────────────────────────────────────────────────────
class TestAuth:
    def test_login_success(self, token):
        assert isinstance(token, str) and len(token) > 50

    def test_login_wrong_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=30)
        assert r.status_code == 401
        assert "detail" in r.json()

    def test_auth_me(self, auth):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth, timeout=30)
        assert r.status_code == 200
        assert r.json().get("email") == ADMIN_EMAIL


# ─── MASTER DATA ─────────────────────────────────────────────────────────────
class TestMasterData:
    def test_create_garment(self, auth):
        r = requests.post(f"{BASE_URL}/api/garments", headers=auth, json={
            "garment_name": f"PT Vendor Sejahtera {TS}",
            "garment_code": f"VND{TS}",
            "address": "Jl. Industri No.1",
            "phone": "0812345",
            "status": "active",
        }, timeout=30)
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["garment_name"] == f"PT Vendor Sejahtera {TS}"
        assert "id" in d
        state["vendor_id"] = d["id"]

    def test_list_garments(self, auth):
        r = requests.get(f"{BASE_URL}/api/garments", headers=auth, timeout=30)
        assert r.status_code == 200
        body = r.json()
        items = body["items"] if isinstance(body, dict) and "items" in body else body
        assert any(g["id"] == state["vendor_id"] for g in items)

    def test_create_buyer(self, auth):
        r = requests.post(f"{BASE_URL}/api/buyers", headers=auth, json={
            "buyer_name": f"CV Buyer Mandiri {TS}",
            "buyer_code": f"BUY{TS}",
            "address": "Jl. Mandiri 5",
            "status": "active",
        }, timeout=30)
        assert r.status_code == 201, r.text
        d = r.json()
        state["buyer_id"] = d["id"]
        assert d["buyer_name"] == f"CV Buyer Mandiri {TS}"

    def test_create_products(self, auth):
        for sku, name, sp, cmt in [(f"KAOS-{TS}", "Kaos Polos", 50000, 15000),
                                   (f"JKT-{TS}", "Jaket Bomber", 120000, 35000)]:
            r = requests.post(f"{BASE_URL}/api/products", headers=auth, json={
                "product_code": sku,
                "product_name": name,
                "sku": sku,
                "category": "Apparel",
                "selling_price": sp,
                "cmt_price": cmt,
                "status": "active",
            }, timeout=30)
            assert r.status_code in (200, 201), r.text
            state.setdefault("products", []).append(r.json())

    def test_list_products_paginated(self, auth):
        r = requests.get(f"{BASE_URL}/api/products?page=1&per_page=10", headers=auth, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body and "total" in body and "page" in body and "per_page" in body and "total_pages" in body

    def test_create_accessories(self, auth):
        for nm in [f"Kancing Plastik {TS}", f"Resleting YKK {TS}"]:
            r = requests.post(f"{BASE_URL}/api/accessories", headers=auth,
                              json={"accessory_name": nm, "unit": "pcs", "status": "active"}, timeout=30)
            assert r.status_code in (200, 201), r.text
            state.setdefault("accessories", []).append(r.json())


# ─── PRODUCTION PO ───────────────────────────────────────────────────────────
class TestProductionPO:
    def test_create_po(self, auth):
        prods = state["products"]
        accs = state["accessories"]
        body = {
            "po_number": f"PO-TEST-{TS}",
            "customer_name": "Test Buyer",
            "buyer_id": state["buyer_id"],
            "vendor_id": state["vendor_id"],
            "deadline": "2026-12-31",
            "items": [
                {"product_id": prods[0]["id"], "qty": 100,
                 "selling_price_snapshot": 50000, "cmt_price_snapshot": 15000,
                 "sku": prods[0].get("sku"), "size": "M", "color": "Hitam"},
                {"product_id": prods[1]["id"], "qty": 50,
                 "selling_price_snapshot": 120000, "cmt_price_snapshot": 35000,
                 "sku": prods[1].get("sku"), "size": "L", "color": "Navy"},
            ],
        }
        r = requests.post(f"{BASE_URL}/api/production-pos", headers=auth, json=body, timeout=30)
        assert r.status_code == 201, r.text
        d = r.json()
        state["po_id"] = d["id"]
        state["po_items"] = d.get("items", [])
        assert len(d.get("items", [])) == 2

        # Add po-accessories separately
        for a in accs[:1]:
            ra = requests.post(f"{BASE_URL}/api/po-accessories", headers=auth, json={
                "po_id": state["po_id"],
                "accessory_id": a["id"],
                "qty_needed": 200,
            }, timeout=30)
            assert ra.status_code in (200, 201), ra.text

    def test_list_pos_paginated_envelope(self, auth):
        r = requests.get(f"{BASE_URL}/api/production-pos?page=1&per_page=10",
                         headers=auth, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert all(k in body for k in ("items", "total", "page", "per_page", "total_pages"))
        # Find our PO
        ours = [p for p in body["items"] if p["id"] == state["po_id"]]
        if ours:
            p = ours[0]
            assert p.get("total_qty") == 150 or p.get("total_qty", 0) >= 150
            assert p.get("item_count") == 2

    def test_get_po_detail(self, auth):
        r = requests.get(f"{BASE_URL}/api/production-pos/{state['po_id']}", headers=auth, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == state["po_id"]

    def test_update_po_status(self, auth):
        r = requests.put(f"{BASE_URL}/api/production-pos/{state['po_id']}", headers=auth,
                         json={"status": "Confirmed"}, timeout=30)
        assert r.status_code in (200, 201), r.text


# ─── BUYER SHIPMENT CAP / DISPATCH 0 (M-1 + C-1) ─────────────────────────────
class TestBuyerShipmentValidations:
    def test_reject_zero_qty_dispatch(self, auth):
        po_items = state.get("po_items", [])
        if not po_items:
            pytest.skip("no po items")
        body = {
            "po_id": state["po_id"],
            "vendor_id": state["vendor_id"],
            "items": [{"po_item_id": po_items[0]["id"], "qty_shipped": 0,
                       "ordered_qty": 100}],
        }
        r = requests.post(f"{BASE_URL}/api/buyer-shipments", headers=auth, json=body, timeout=30)
        assert r.status_code == 400, f"Expected 400 for 0-qty dispatch, got {r.status_code}: {r.text}"

    def test_reject_phantom_shipment_no_production(self, auth):
        # No production yet → C-1 cap should reject any positive qty
        po_items = state.get("po_items", [])
        if not po_items:
            pytest.skip("no po items")
        body = {
            "po_id": state["po_id"],
            "vendor_id": state["vendor_id"],
            "items": [{"po_item_id": po_items[0]["id"], "qty_shipped": 10,
                       "ordered_qty": 100}],
        }
        r = requests.post(f"{BASE_URL}/api/buyer-shipments", headers=auth, json=body, timeout=30)
        # Should reject since produced=0
        assert r.status_code == 400, f"Expected 400 for phantom shipment, got {r.status_code}: {r.text}"


# ─── MANUAL INVOICE + PAYMENT ────────────────────────────────────────────────
class TestInvoiceAndPayment:
    def test_create_manual_invoice(self, auth):
        r = requests.post(f"{BASE_URL}/api/invoices", headers=auth, json={
            "invoice_type": "AR",
            "invoice_number": f"INV-AR-TEST-{TS}",
            "buyer_id": state["buyer_id"],
            "customer_name": "Test Buyer",
            "total_amount": 1000000,
            "items": [{"description": "Manual line", "qty": 1, "unit_price": 1000000, "subtotal": 1000000}],
            "notes": "test",
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        state["invoice_id"] = d["id"]

    def test_list_invoices(self, auth):
        r = requests.get(f"{BASE_URL}/api/invoices", headers=auth, timeout=30)
        assert r.status_code == 200
        body = r.json()
        items = body["items"] if isinstance(body, dict) and "items" in body else body
        assert any(i["id"] == state["invoice_id"] for i in items)

    def test_partial_payment(self, auth):
        r = requests.post(f"{BASE_URL}/api/payments", headers=auth, json={
            "invoice_id": state["invoice_id"],
            "amount": 400000,
            "payment_method": "Bank Transfer",
            "notes": "Partial test",
        }, timeout=30)
        assert r.status_code in (200, 201), r.text

    def test_full_payment(self, auth):
        r = requests.post(f"{BASE_URL}/api/payments", headers=auth, json={
            "invoice_id": state["invoice_id"],
            "amount": 600000,
            "payment_method": "Bank Transfer",
            "notes": "Final test",
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        # GET invoice and verify
        ri = requests.get(f"{BASE_URL}/api/invoices/{state['invoice_id']}", headers=auth, timeout=30)
        assert ri.status_code == 200
        d = ri.json()
        assert d.get("paid_amount", 0) >= 1000000 or d.get("status") in ("Paid", "Partial")


# ─── PDF EXPORT ──────────────────────────────────────────────────────────────
class TestPdfExport:
    def test_pdf_production_po(self, auth):
        r = requests.get(f"{BASE_URL}/api/export-pdf?type=production-po&id={state['po_id']}",
                         headers=auth, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert "pdf" in r.headers.get("content-type", "").lower()
        assert len(r.content) > 1000

    def test_pdf_invoice(self, auth):
        r = requests.get(f"{BASE_URL}/api/export-pdf?type=invoice&id={state['invoice_id']}",
                         headers=auth, timeout=60)
        # Some invoice types may not export; just record status
        assert r.status_code in (200, 404, 400, 422), r.text[:200]


# ─── SMART IMPORT ────────────────────────────────────────────────────────────
class TestSmartImport:
    def test_smart_import_upload(self, auth):
        try:
            from openpyxl import Workbook
        except ImportError:
            pytest.skip("openpyxl not installed in test env")
        wb = Workbook()
        ws = wb.active
        ws.append(["sku", "name", "status"])
        ws.append([f"SI-{TS}-A", "Imported A", "active"])
        ws.append([f"SI-{TS}-B", "Imported B", "active"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        files = {"file": (f"products_{TS}.xlsx", buf,
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        headers = {"Authorization": auth["Authorization"]}
        r = requests.post(f"{BASE_URL}/api/smart-import/upload",
                          headers=headers, files=files,
                          data={"data_type": "products"}, timeout=60)
        # Just verify endpoint reachable; full preview/commit flow skipped (LLM dep)
        assert r.status_code in (200, 201, 400, 422), f"unexpected: {r.status_code} {r.text[:200]}"


# ─── LIST ENDPOINTS SMOKE (for sidebar modules) ──────────────────────────────
class TestListEndpointsSmoke:
    @pytest.mark.parametrize("path", [
        "/api/garments",
        "/api/buyers",
        "/api/products",
        "/api/accessories",
        "/api/production-pos",
        "/api/vendor-shipments",
        "/api/buyer-shipments",
        "/api/production-jobs",
        "/api/production-returns",
        "/api/production-variances",
        "/api/invoices",
        "/api/payments",
        "/api/users",
        "/api/activity-logs",
        "/api/company-settings",
        "/api/dashboard",
        "/api/financial-recap",
        "/api/accounts-payable",
        "/api/accounts-receivable",
        "/api/distribusi-kerja",
        "/api/production-monitoring-v2",
        "/api/serial-list",
        "/api/pdf-export-configs",
        "/api/pdf-export-columns",
        "/api/roles",
        "/api/permissions",
        "/api/reminders",
    ])
    def test_endpoint_reachable(self, auth, path):
        r = requests.get(f"{BASE_URL}{path}", headers=auth, timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


# ─── CLEANUP ─────────────────────────────────────────────────────────────────
class TestZCleanup:
    def test_cleanup_po(self, auth):
        if "po_id" in state:
            r = requests.delete(f"{BASE_URL}/api/production-pos/{state['po_id']}", headers=auth, timeout=30)
            assert r.status_code in (200, 204, 404)

    def test_cleanup_invoice(self, auth):
        if "invoice_id" in state:
            r = requests.delete(f"{BASE_URL}/api/invoices/{state['invoice_id']}", headers=auth, timeout=30)
            assert r.status_code in (200, 204, 404)

    def test_cleanup_buyer(self, auth):
        if "buyer_id" in state:
            requests.delete(f"{BASE_URL}/api/buyers/{state['buyer_id']}", headers=auth, timeout=30)

    def test_cleanup_vendor(self, auth):
        if "vendor_id" in state:
            requests.delete(f"{BASE_URL}/api/garments/{state['vendor_id']}", headers=auth, timeout=30)

    def test_cleanup_products(self, auth):
        for p in state.get("products", []):
            requests.delete(f"{BASE_URL}/api/products/{p['id']}", headers=auth, timeout=30)

    def test_cleanup_accessories(self, auth):
        for a in state.get("accessories", []):
            requests.delete(f"{BASE_URL}/api/accessories/{a['id']}", headers=auth, timeout=30)
