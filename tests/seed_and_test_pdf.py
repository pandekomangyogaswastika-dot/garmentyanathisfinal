#!/usr/bin/env python3
"""Seed test data and test ALL PDF export types."""
import requests
import json
import os
import sys
import time

BASE = "http://localhost:8001/api"
TS = str(int(time.time()))[-6:]  # Unique suffix

# Login
login_res = requests.post(f"{BASE}/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
TOKEN = login_res.json().get('token', '')
if not TOKEN:
    print("FAIL: Could not login")
    sys.exit(1)
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
print(f"Logged in as superadmin")

# ─── SEED DATA ───────────────────────────────────────────────────────────────
def seed_data():
    # Product
    p = requests.post(f"{BASE}/products", headers=H, json={
        "product_name": f"T-Shirt Basic {TS}", "product_code": f"TSB-{TS}", "category": "Tops", "status": "active"
    })
    pid = p.json().get('id', '')
    print(f"  Product: {pid}")

    # Variant
    v = requests.post(f"{BASE}/product-variants", headers=H, json={
        "product_id": pid, "sku": f"TSB-{TS}-M-BLK", "size": "M", "color": "Black",
        "selling_price": 50000, "cmt_price": 15000
    })
    vid = v.json().get('id', '')
    print(f"  Variant: {vid}")

    # Vendor
    g = requests.post(f"{BASE}/garments", headers=H, json={
        "garment_name": f"PT Vendor {TS}", "garment_code": f"VJ{TS}", "location": "Bandung",
        "contact_person": "Budi", "phone": "081234567890", "status": "active"
    })
    gid = g.json().get('id', '')
    print(f"  Vendor: {gid} (status {g.status_code})")

    # Buyer
    b = requests.post(f"{BASE}/buyers", headers=H, json={
        "buyer_name": f"Fashion Corp {TS}", "buyer_code": f"FC{TS}", "contact_person": "Alice",
        "phone": "087654321000", "address": "Jakarta", "status": "active"
    })
    bid = b.json().get('id', '')
    print(f"  Buyer: {bid}")

    # PO with items
    po = requests.post(f"{BASE}/production-pos", headers=H, json={
        "po_number": f"PO-PDF-{TS}", "customer_name": f"Fashion Corp {TS}", "buyer_id": bid,
        "vendor_id": gid, "vendor_name": f"PT Vendor {TS}", "po_date": "2026-04-01",
        "deadline": "2026-05-01", "delivery_deadline": "2026-05-15", "status": "Confirmed",
        "items": [
            {"product_id": pid, "variant_id": vid, "product_name": f"T-Shirt {TS}", "sku": f"TSB-{TS}-M-BLK",
             "serial_number": f"SN-{TS}-001", "size": "M", "color": "Black", "qty": 100,
             "selling_price_snapshot": 50000, "cmt_price_snapshot": 15000},
            {"product_id": pid, "variant_id": vid, "product_name": f"T-Shirt {TS}", "sku": f"TSB-{TS}-L-WHT",
             "serial_number": f"SN-{TS}-002", "size": "L", "color": "White", "qty": 200,
             "selling_price_snapshot": 55000, "cmt_price_snapshot": 16000},
        ]
    })
    po_data = po.json()
    po_id = po_data.get('id', '')
    print(f"  PO: {po_id} (status {po.status_code})")

    # Get PO items
    items_res = requests.get(f"{BASE}/po-items?po_id={po_id}", headers=H)
    po_items = items_res.json()
    print(f"  PO Items: {len(po_items)}")
    if len(po_items) < 2:
        print("  WARNING: Less than 2 PO items created")
        return None

    # Vendor shipment
    ship = requests.post(f"{BASE}/vendor-shipments", headers=H, json={
        "shipment_number": f"SHP-{TS}", "po_id": po_id, "po_number": f"PO-PDF-{TS}",
        "vendor_id": gid, "vendor_name": f"PT Vendor {TS}",
        "shipment_date": "2026-04-05", "shipment_type": "NORMAL",
        "items": [
            {"po_item_id": po_items[0]['id'], "po_id": po_id, "po_number": f"PO-PDF-{TS}", "serial_number": f"SN-{TS}-001",
             "product_name": f"T-Shirt {TS}", "sku": f"TSB-{TS}-M-BLK", "size": "M", "color": "Black", "qty_sent": 100},
            {"po_item_id": po_items[1]['id'], "po_id": po_id, "po_number": f"PO-PDF-{TS}", "serial_number": f"SN-{TS}-002",
             "product_name": f"T-Shirt {TS}", "sku": f"TSB-{TS}-L-WHT", "size": "L", "color": "White", "qty_sent": 200},
        ]
    })
    ship_id = ship.json().get('id', '')
    print(f"  Vendor Shipment: {ship_id} (status {ship.status_code})")

    # Buyer shipment with dispatch
    bship = requests.post(f"{BASE}/buyer-shipments", headers=H, json={
        "po_id": po_id, "po_number": f"PO-PDF-{TS}", "customer_name": f"Fashion Corp {TS}",
        "vendor_id": gid, "vendor_name": f"PT Vendor {TS}",
        "items": [
            {"po_item_id": po_items[0]['id'], "serial_number": f"SN-{TS}-001", "product_name": f"T-Shirt {TS}",
             "sku": f"TSB-{TS}-M-BLK", "size": "M", "color": "Black", "ordered_qty": 100, "qty_shipped": 50,
             "dispatch_seq": 1, "dispatch_date": "2026-04-10"},
            {"po_item_id": po_items[1]['id'], "serial_number": f"SN-{TS}-002", "product_name": f"T-Shirt {TS}",
             "sku": f"TSB-{TS}-L-WHT", "size": "L", "color": "White", "ordered_qty": 200, "qty_shipped": 100,
             "dispatch_seq": 1, "dispatch_date": "2026-04-10"},
        ]
    })
    bship_id = bship.json().get('id', '')
    print(f"  Buyer Shipment: {bship_id} (status {bship.status_code})")

    # Production return
    ret = requests.post(f"{BASE}/production-returns", headers=H, json={
        "reference_po_id": po_id, "reference_po_number": f"PO-PDF-{TS}",
        "customer_name": f"Fashion Corp {TS}", "return_date": "2026-04-12",
        "return_reason": "Color mismatch", "status": "Pending",
        "items": [
            {"po_item_id": po_items[0]['id'], "serial_number": f"SN-{TS}-001", "product_name": f"T-Shirt {TS}",
             "sku": f"TSB-{TS}-M-BLK", "size": "M", "color": "Black", "return_qty": 5, "notes": "Wrong shade"}
        ]
    })
    ret_id = ret.json().get('id', '')
    print(f"  Return: {ret_id} (status {ret.status_code})")

    # Material request (ADDITIONAL) - requires original_shipment_id
    mreq = requests.post(f"{BASE}/material-requests", headers=H, json={
        "po_id": po_id, "po_number": f"PO-PDF-{TS}", "vendor_id": gid, "vendor_name": f"PT Vendor {TS}",
        "original_shipment_id": ship_id,
        "request_type": "ADDITIONAL", "reason": "Short 10 pcs",
        "total_requested_qty": 10, "status": "Pending",
        "items": [
            {"po_item_id": po_items[0]['id'], "serial_number": f"SN-{TS}-001", "product_name": f"T-Shirt {TS}",
             "sku": f"TSB-{TS}-M-BLK", "size": "M", "color": "Black", "requested_qty": 10}
        ]
    })
    mreq_id = mreq.json().get('id', '')
    print(f"  Material Request: {mreq_id} (status {mreq.status_code})")

    # Invoice
    inv = requests.post(f"{BASE}/invoices", headers=H, json={
        "invoice_number": f"INV-{TS}", "invoice_category": "AP",
        "po_id": po_id, "po_number": f"PO-PDF-{TS}", "vendor_name": f"PT Vendor {TS}",
        "amount": 5000000, "paid_amount": 2000000, "remaining_amount": 3000000,
        "invoice_date": "2026-04-10", "status": "Partial"
    })
    print(f"  Invoice: (status {inv.status_code})")

    return {
        'po_id': po_id, 'ship_id': ship_id, 'bship_id': bship_id,
        'ret_id': ret_id, 'mreq_id': mreq_id, 'po_items': po_items,
    }

# ─── TEST PDF EXPORTS ────────────────────────────────────────────────────────
def test_pdf(name, params, expect_status=200, min_size=500):
    url = f"{BASE}/export-pdf"
    res = requests.get(url, params=params, headers=H)
    size = len(res.content)
    ok = res.status_code == expect_status and (size >= min_size or expect_status != 200)
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: HTTP {res.status_code}, size={size} bytes"
          + (f" (expected {expect_status})" if not ok else ""))
    if not ok and res.status_code != 200:
        try:
            print(f"    Error: {res.json()}")
        except:
            print(f"    Body: {res.text[:200]}")
    return ok

print("\n=== SEEDING TEST DATA ===")
ids = seed_data()
if not ids:
    print("FAIL: Could not seed data")
    sys.exit(1)

print("\n=== TESTING PDF EXPORTS ===")
results = []

# Document PDFs
results.append(test_pdf("production-po (SPP)", {"type": "production-po", "id": ids['po_id']}))
results.append(test_pdf("vendor-shipment", {"type": "vendor-shipment", "id": ids['ship_id']}))
results.append(test_pdf("buyer-shipment (summary)", {"type": "buyer-shipment", "id": ids['bship_id']}))
results.append(test_pdf("buyer-shipment-dispatch", {"type": "buyer-shipment-dispatch", "shipment_id": ids['bship_id'], "dispatch_seq": 1}))
results.append(test_pdf("production-return", {"type": "production-return", "id": ids['ret_id']}))
results.append(test_pdf("material-request", {"type": "material-request", "id": ids['mreq_id']}))
results.append(test_pdf("production-report", {"type": "production-report"}))

# Report PDFs
for rt in ['production', 'progress', 'financial', 'shipment', 'return', 'missing-material', 'replacement']:
    results.append(test_pdf(f"report-{rt}", {"type": f"report-{rt}"}))

# Unknown type should fail gracefully
results.append(test_pdf("unknown-type (should 400)", {"type": "nonexistent"}, expect_status=400, min_size=0))

# Missing ID should fail gracefully
results.append(test_pdf("production-po no id (should 400)", {"type": "production-po"}, expect_status=400, min_size=0))

passed = sum(results)
total = len(results)
print(f"\n=== RESULTS: {passed}/{total} passed ===")
if passed < total:
    sys.exit(1)
