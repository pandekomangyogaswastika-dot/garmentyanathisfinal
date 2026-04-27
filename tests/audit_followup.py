"""Follow-up targeted test for defect flow + remaining_to_ship accuracy.

Creates a fresh PO and tests:
- Properly passing vendor_id so defect record is created
- Whether effective_available_qty is reduced
- Whether progress validation uses effective (not raw) available qty
- The state of PO remaining_qty_to_ship after over-shipping (negative?)
"""
import requests, json, sys
from datetime import datetime, timedelta

BASE = "http://localhost:8001/api"
t = requests.post(f"{BASE}/auth/login", json={"email":"admin@garment.com","password":"Admin@123"}).json()["token"]
H = {"Authorization": f"Bearer {t}"}

# Reuse last PO
pos = requests.get(f"{BASE}/production-pos", headers=H).json()
po = pos[0]
print(f"Using PO: {po['po_number']} status={po['status']}")
print(f"  total_qty={po.get('total_qty')}, total_shipped_to_buyer={po.get('total_shipped_to_buyer')}, remaining_qty_to_ship={po.get('remaining_qty_to_ship')}")

# Fetch job
jobs = requests.get(f"{BASE}/production-jobs", headers=H).json()
job = next((j for j in jobs if j["po_number"] == po["po_number"]), None)
print(f"\nJob: {job['job_number']} produced={job['total_produced']} shipped={job['total_shipped_to_buyer']} remaining_to_ship={job.get('remaining_to_ship')}")

# Fetch detailed job
detail = requests.get(f"{BASE}/production-jobs/{job['id']}", headers=H).json()
for it in detail["items"]:
    print(f"  {it['sku']}: ordered={it.get('ordered_qty')} shipment={it.get('shipment_qty')} available={it.get('available_qty')} produced={it.get('produced_qty')} defect_total={it.get('total_defect_qty')} effective={it.get('effective_available_qty')}")

# Now create defect WITH vendor_id (admin flow)
vendor_id = job["vendor_id"]
s_ji = next(i for i in detail["items"] if i["sku"] == "AUD-S-BLK")
print(f"\nCreating defect via admin (vendor_id={vendor_id[:8]}...)")
r = requests.post(f"{BASE}/material-defect-reports", headers=H, json={
    "vendor_id": vendor_id,
    "job_id": job["id"], "job_item_id": s_ji["id"],
    "po_id": po["id"], "po_item_id": s_ji.get("po_item_id"),
    "sku": "AUD-S-BLK", "size": "S", "color": "Black",
    "defect_qty": 3, "defect_type": "Material Cacat", "description": "Test defect"
})
print(f"  defect POST -> {r.status_code}: {str(r.json())[:200]}")

# Refresh and check effective_available_qty reduction
detail = requests.get(f"{BASE}/production-jobs/{job['id']}", headers=H).json()
for it in detail["items"]:
    if it['sku'] == "AUD-S-BLK":
        print(f"\nAfter defect: available={it.get('available_qty')} produced={it.get('produced_qty')} defect_total={it.get('total_defect_qty')} effective={it.get('effective_available_qty')}")

# Test progress beyond "effective" — admin records for vendor
# NOTE: progress endpoint doesn't require vendor_id from admin
print("\nAttempt to record more progress to exceed effective capacity:")
r = requests.post(f"{BASE}/production-progress", headers=H, json={
    "job_item_id": s_ji["id"], "completed_quantity": 5,  # already 97; +5 = 102 > 97 effective
    "progress_date": datetime.now().isoformat(), "notes": "Over effective"
})
print(f"  progress +5 -> {r.status_code}: {str(r.json())[:200]}")

# Check over-shipping wasn't blocked — look at current state
print("\nCurrent PO state with over-shipments:")
pos = requests.get(f"{BASE}/production-pos", headers=H).json()
po = pos[0]
print(f"  total_qty={po.get('total_qty')}, total_shipped_to_buyer={po.get('total_shipped_to_buyer')}, remaining_qty_to_ship={po.get('remaining_qty_to_ship')}")
print(f"  (If remaining_qty_to_ship is negative → dashboard shows nonsense)")

# Ship same job twice (duplicate dispatch) at qty_shipped=0 to test
print("\nCreate 0-qty dispatch (is it allowed?):")
r = requests.post(f"{BASE}/buyer-shipments", headers=H, json={
    "vendor_id": vendor_id, "po_id": po["id"], "job_id": job["id"],
    "shipment_date": datetime.now().isoformat(),
    "items": [{"po_item_id": s_ji.get("po_item_id"), "qty_shipped": 0, "ordered_qty": 100}]
})
print(f"  -> {r.status_code}: has_dispatch_seq={r.json().get('dispatch_seq') if r.ok else 'N/A'}")
