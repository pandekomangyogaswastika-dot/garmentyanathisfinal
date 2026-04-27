"""
POC: PO Accessories Flow Test
Verifies that PO accessories propagate to:
1. PO detail response
2. Vendor shipment creation (po_id stored at shipment level)
3. Vendor shipment detail response
"""
import requests
import json
import sys

BASE = "http://localhost:8001/api"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASS = "Admin@123"
PASS_COUNT = 0
FAIL_COUNT = 0

def test(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  ✅ PASS: {name}")
    else:
        FAIL_COUNT += 1
        print(f"  ❌ FAIL: {name} — {detail}")

def main():
    global PASS_COUNT, FAIL_COUNT

    # 1. Login
    print("\n=== 1. Login ===")
    r = requests.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    test("Login successful", r.status_code == 200, f"Status: {r.status_code}")
    token = r.json().get("token", "")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 2. Create Vendor
    print("\n=== 2. Create Vendor ===")
    vendor_data = {"garment_name": "Test Vendor POC", "garment_code": "VPOC01", "status": "active",
                   "contact_person": "Test", "phone": "123456", "address": "Test Address"}
    r = requests.post(f"{BASE}/garments", json=vendor_data, headers=headers)
    test("Vendor created", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:200]}")
    vendor_id = r.json().get("id", "")

    # 3. Create Product + Variant
    print("\n=== 3. Create Product ===")
    product_data = {"product_name": "T-Shirt POC", "product_code": "TSPOC01", "category": "Garment",
                    "cmt_price": 35000, "selling_price": 85000, "status": "active"}
    r = requests.post(f"{BASE}/products", json=product_data, headers=headers)
    test("Product created", r.status_code == 201, f"Status: {r.status_code}")
    product_id = r.json().get("id", "")

    variant_data = {"product_id": product_id, "size": "L", "color": "Black", "sku": "TS-BLK-L-POC"}
    r = requests.post(f"{BASE}/product-variants", json=variant_data, headers=headers)
    test("Variant created", r.status_code == 201, f"Status: {r.status_code}")
    variant_id = r.json().get("id", "")

    # 4. Create Accessories
    print("\n=== 4. Create Accessories ===")
    acc1_data = {"name": "Button Silver", "code": "BTN-SLV", "category": "Button", "unit": "pcs", "status": "active"}
    r1 = requests.post(f"{BASE}/accessories", json=acc1_data, headers=headers)
    test("Accessory 1 created", r1.status_code == 201, f"Status: {r1.status_code}")
    acc1_id = r1.json().get("id", "")

    acc2_data = {"name": "Zipper Black 20cm", "code": "ZIP-BLK-20", "category": "Zipper", "unit": "pcs", "status": "active"}
    r2 = requests.post(f"{BASE}/accessories", json=acc2_data, headers=headers)
    test("Accessory 2 created", r2.status_code == 201, f"Status: {r2.status_code}")
    acc2_id = r2.json().get("id", "")

    # 5. Create PO with items
    print("\n=== 5. Create PO ===")
    po_data = {
        "po_number": "PO-ACC-TEST-001", "customer_name": "Test Buyer",
        "vendor_id": vendor_id, "po_date": "2026-04-14",
        "deadline": "2026-05-14", "delivery_deadline": "2026-05-21",
        "notes": "PO for accessories flow test",
        "items": [
            {"product_id": product_id, "product_name": "T-Shirt POC", "variant_id": variant_id,
             "size": "L", "color": "Black", "sku": "TS-BLK-L-POC", "qty": 500,
             "serial_number": "SN-ACC-001", "selling_price_snapshot": 85000, "cmt_price_snapshot": 35000}
        ]
    }
    r = requests.post(f"{BASE}/production-pos", json=po_data, headers=headers)
    test("PO created", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:200]}")
    po_id = r.json().get("id", "")

    # 6. Add accessories to PO
    print("\n=== 6. Add Accessories to PO ===")
    acc_attach_data = {
        "po_id": po_id,
        "items": [
            {"accessory_id": acc1_id, "accessory_name": "Button Silver", "accessory_code": "BTN-SLV",
             "qty_needed": 2000, "unit": "pcs", "notes": "4 per shirt"},
            {"accessory_id": acc2_id, "accessory_name": "Zipper Black 20cm", "accessory_code": "ZIP-BLK-20",
             "qty_needed": 500, "unit": "pcs", "notes": "1 per shirt"}
        ]
    }
    r = requests.post(f"{BASE}/po-accessories", json=acc_attach_data, headers=headers)
    test("PO accessories attached", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:200]}")

    # 7. Verify GET /api/po-accessories returns them
    print("\n=== 7. Verify GET /api/po-accessories ===")
    r = requests.get(f"{BASE}/po-accessories?po_id={po_id}", headers=headers)
    test("GET po-accessories returns data", r.status_code == 200 and len(r.json()) == 2,
         f"Status: {r.status_code}, Count: {len(r.json())}")

    # 8. Verify PO detail includes accessories
    print("\n=== 8. Verify PO Detail includes accessories ===")
    r = requests.get(f"{BASE}/production-pos/{po_id}", headers=headers)
    po_detail = r.json()
    test("PO detail has po_accessories field", 'po_accessories' in po_detail,
         f"Keys: {list(po_detail.keys())}")
    test("PO detail has 2 accessories", len(po_detail.get('po_accessories', [])) == 2,
         f"Count: {len(po_detail.get('po_accessories', []))}")
    if po_detail.get('po_accessories'):
        acc_names = [a['accessory_name'] for a in po_detail['po_accessories']]
        test("Accessories have correct names", 'Button Silver' in acc_names and 'Zipper Black 20cm' in acc_names,
             f"Names: {acc_names}")

    # 9. Verify PO list includes accessories count
    print("\n=== 9. Verify PO List includes accessories count ===")
    r = requests.get(f"{BASE}/production-pos", headers=headers)
    po_list = r.json()
    test_po = next((p for p in po_list if p['id'] == po_id), None)
    test("PO in list found", test_po is not None)
    if test_po:
        test("PO list has po_accessories_count", test_po.get('po_accessories_count') == 2,
             f"Count: {test_po.get('po_accessories_count')}")

    # 10. Create Vendor Shipment for this PO
    print("\n=== 10. Create Vendor Shipment ===")
    ship_data = {
        "shipment_number": "SHP-ACC-TEST-001",
        "delivery_note_number": "DN-ACC-001",
        "vendor_id": vendor_id,
        "shipment_date": "2026-04-14",
        "shipment_type": "NORMAL",
        "notes": "Test shipment with accessories",
        "items": [
            {"po_id": po_id, "po_number": "PO-ACC-TEST-001",
             "po_item_id": po_detail['items'][0]['id'] if po_detail.get('items') else '',
             "product_name": "T-Shirt POC", "size": "L", "color": "Black",
             "sku": "TS-BLK-L-POC", "serial_number": "SN-ACC-001", "qty_sent": 500}
        ]
    }
    r = requests.post(f"{BASE}/vendor-shipments", json=ship_data, headers=headers)
    test("Vendor shipment created", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:200]}")
    ship_id = r.json().get("id", "")

    # 11. Verify shipment has po_id stored at shipment level
    print("\n=== 11. Verify Shipment has po_id ===")
    r = requests.get(f"{BASE}/vendor-shipments/{ship_id}", headers=headers)
    ship_detail = r.json()
    test("Shipment has po_id at shipment level", ship_detail.get('po_id') == po_id,
         f"po_id: {ship_detail.get('po_id')}, expected: {po_id}")
    test("Shipment has po_number at shipment level", ship_detail.get('po_number') == "PO-ACC-TEST-001",
         f"po_number: {ship_detail.get('po_number')}")

    # 12. Verify shipment detail includes PO accessories
    print("\n=== 12. Verify Shipment Detail includes PO accessories ===")
    test("Shipment detail has po_accessories field", 'po_accessories' in ship_detail,
         f"Keys: {list(ship_detail.keys())}")
    test("Shipment detail has 2 PO accessories", len(ship_detail.get('po_accessories', [])) == 2,
         f"Count: {len(ship_detail.get('po_accessories', []))}")
    if ship_detail.get('po_accessories'):
        acc_names = [a['accessory_name'] for a in ship_detail['po_accessories']]
        test("Shipment accessories have correct names", 'Button Silver' in acc_names and 'Zipper Black 20cm' in acc_names,
             f"Names: {acc_names}")
        # Check po_number is included
        test("Accessories include po_number", all(a.get('po_number') == 'PO-ACC-TEST-001' for a in ship_detail['po_accessories']),
             f"po_numbers: {[a.get('po_number') for a in ship_detail['po_accessories']]}")

    # 13. Verify vendor shipments list includes accessories count
    print("\n=== 13. Verify Vendor Shipments List ===")
    r = requests.get(f"{BASE}/vendor-shipments", headers=headers)
    ships_list = r.json()
    test_ship = next((s for s in ships_list if s['id'] == ship_id), None)
    test("Shipment in list found", test_ship is not None)
    if test_ship:
        test("Shipment list has po_accessories_count", test_ship.get('po_accessories_count') == 2,
             f"Count: {test_ship.get('po_accessories_count')}")

    # Cleanup
    print("\n=== Cleanup ===")
    requests.delete(f"{BASE}/vendor-shipments/{ship_id}", headers=headers)
    requests.delete(f"{BASE}/production-pos/{po_id}", headers=headers)
    requests.delete(f"{BASE}/products/{product_id}", headers=headers)
    requests.delete(f"{BASE}/garments/{vendor_id}", headers=headers)
    for acc_id in [acc1_id, acc2_id]:
        requests.delete(f"{BASE}/accessories/{acc_id}", headers=headers)
    print("  Cleanup done")

    # Summary
    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print(f"{'='*50}")
    return FAIL_COUNT == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
