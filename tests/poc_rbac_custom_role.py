"""
POC: RBAC Custom Role Fix Test
Creates a custom role with all permissions, assigns to a user, and verifies they can create PO and shipment.
"""
import requests
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

    # 1. Login as superadmin
    print("\n=== 1. Login as Superadmin ===")
    r = requests.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    test("Superadmin login", r.status_code == 200)
    admin_token = r.json()['token']
    admin_h = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    # 2. Get all permission keys
    print("\n=== 2. Get All Permissions ===")
    r = requests.get(f"{BASE}/permissions", headers=admin_h)
    test("Get permissions", r.status_code == 200, f"Status: {r.status_code}")
    all_perms = [p['key'] for p in r.json()]
    test("Has permission keys", len(all_perms) > 0, f"Count: {len(all_perms)}")
    print(f"    Available permissions: {all_perms}")

    # 3. Create a custom role with ALL permissions
    print("\n=== 3. Create Custom Role with All Access ===")
    role_data = {
        "name": "Full Access Test Role",
        "description": "Role with all permissions for testing",
        "permissions": all_perms
    }
    r = requests.post(f"{BASE}/roles", json=role_data, headers=admin_h)
    test("Custom role created", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:200]}")
    role_id = r.json().get('id', '')

    # 4. Create a user with the custom role
    print("\n=== 4. Create User with Custom Role ===")
    user_data = {
        "name": "Test Custom User",
        "email": "testcustom@garment.com",
        "password": "Test@123",
        "role": "Full Access Test Role",
        "status": "active"
    }
    r = requests.post(f"{BASE}/users", json=user_data, headers=admin_h)
    test("Custom role user created", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:200]}")
    user_id = r.json().get('id', '')

    # 5. Login as custom role user
    print("\n=== 5. Login as Custom Role User ===")
    r = requests.post(f"{BASE}/auth/login", json={"email": "testcustom@garment.com", "password": "Test@123"})
    test("Custom user login", r.status_code == 200, f"Status: {r.status_code}, Body: {r.text[:200]}")
    custom_token = r.json()['token']
    custom_h = {"Authorization": f"Bearer {custom_token}", "Content-Type": "application/json"}

    # 6. Check /auth/me returns permissions
    print("\n=== 6. Verify Auth Me Returns Permissions ===")
    r = requests.get(f"{BASE}/auth/me", headers=custom_h)
    test("Auth me returns permissions", r.status_code == 200)
    me_data = r.json()
    test("Permissions list is populated", len(me_data.get('permissions', [])) > 0,
         f"Permissions: {me_data.get('permissions', [])}")

    # 7. Test: Custom role user can VIEW products
    print("\n=== 7. Test: View Products ===")
    r = requests.get(f"{BASE}/products", headers=custom_h)
    test("Can view products", r.status_code == 200, f"Status: {r.status_code}")

    # 8. Test: Custom role user can CREATE vendor
    print("\n=== 8. Test: Create Vendor ===")
    vendor_data = {"garment_name": "RBAC Test Vendor", "garment_code": "RBV01", "status": "active",
                   "contact_person": "Test", "phone": "123", "address": "Test"}
    r = requests.post(f"{BASE}/garments", json=vendor_data, headers=custom_h)
    test("Can create vendor", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:200]}")
    vendor_id = r.json().get('id', '') if r.status_code == 201 else ''

    # 9. Test: Custom role user can CREATE product
    print("\n=== 9. Test: Create Product ===")
    product_data = {"product_name": "RBAC Test Product", "product_code": "RBP01", "category": "Garment",
                    "cmt_price": 25000, "selling_price": 75000, "status": "active"}
    r = requests.post(f"{BASE}/products", json=product_data, headers=custom_h)
    test("Can create product", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:200]}")
    product_id = r.json().get('id', '') if r.status_code == 201 else ''

    # Create variant
    variant_data = {"product_id": product_id, "size": "M", "color": "Red", "sku": "RBP-RED-M"}
    r = requests.post(f"{BASE}/product-variants", json=variant_data, headers=custom_h)
    test("Can create variant", r.status_code == 201, f"Status: {r.status_code}")
    variant_id = r.json().get('id', '') if r.status_code == 201 else ''

    # 10. Test: Custom role user can CREATE PO (the critical test!)
    print("\n=== 10. Test: Create PO (CRITICAL) ===")
    po_data = {
        "po_number": "PO-RBAC-TEST-001", "customer_name": "RBAC Buyer",
        "vendor_id": vendor_id, "po_date": "2026-04-14",
        "deadline": "2026-05-14", "delivery_deadline": "2026-05-21",
        "items": [
            {"product_id": product_id, "product_name": "RBAC Test Product", "variant_id": variant_id,
             "size": "M", "color": "Red", "sku": "RBP-RED-M", "qty": 100,
             "serial_number": "SN-RBAC-001", "selling_price_snapshot": 75000, "cmt_price_snapshot": 25000}
        ]
    }
    r = requests.post(f"{BASE}/production-pos", json=po_data, headers=custom_h)
    test("Can CREATE PO", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:300]}")
    po_id = r.json().get('id', '') if r.status_code == 201 else ''

    # 11. Test: Custom role user can CREATE vendor shipment (the other critical test!)
    print("\n=== 11. Test: Create Vendor Shipment (CRITICAL) ===")
    if po_id:
        # Get PO items
        r = requests.get(f"{BASE}/production-pos/{po_id}", headers=custom_h)
        po_detail = r.json()
        po_item_id = po_detail['items'][0]['id'] if po_detail.get('items') else ''
        
        ship_data = {
            "shipment_number": "SHP-RBAC-TEST-001",
            "vendor_id": vendor_id,
            "shipment_date": "2026-04-14",
            "items": [
                {"po_id": po_id, "po_number": "PO-RBAC-TEST-001",
                 "po_item_id": po_item_id,
                 "product_name": "RBAC Test Product", "size": "M", "color": "Red",
                 "sku": "RBP-RED-M", "serial_number": "SN-RBAC-001", "qty_sent": 100}
            ]
        }
        r = requests.post(f"{BASE}/vendor-shipments", json=ship_data, headers=custom_h)
        test("Can CREATE shipment", r.status_code == 201, f"Status: {r.status_code}, Body: {r.text[:300]}")
        ship_id = r.json().get('id', '') if r.status_code == 201 else ''
    else:
        test("Can CREATE shipment", False, "PO creation failed, skipping")
        ship_id = ''

    # 12. Test: Custom role can view shipments
    print("\n=== 12. Test: View Shipments ===")
    r = requests.get(f"{BASE}/vendor-shipments", headers=custom_h)
    test("Can view shipments", r.status_code == 200, f"Status: {r.status_code}")

    # 13. Test: Custom role can view POs
    print("\n=== 13. Test: View POs ===")
    r = requests.get(f"{BASE}/production-pos", headers=custom_h)
    test("Can view POs", r.status_code == 200, f"Status: {r.status_code}")

    # Cleanup
    print("\n=== Cleanup ===")
    if ship_id: requests.delete(f"{BASE}/vendor-shipments/{ship_id}", headers=admin_h)
    if po_id: requests.delete(f"{BASE}/production-pos/{po_id}", headers=admin_h)
    if product_id: requests.delete(f"{BASE}/products/{product_id}", headers=admin_h)
    if vendor_id: requests.delete(f"{BASE}/garments/{vendor_id}", headers=admin_h)
    if user_id: requests.delete(f"{BASE}/users/{user_id}", headers=admin_h)
    if role_id: requests.delete(f"{BASE}/roles/{role_id}", headers=admin_h)
    print("  Cleanup done")

    # Summary
    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print(f"{'='*50}")
    return FAIL_COUNT == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
