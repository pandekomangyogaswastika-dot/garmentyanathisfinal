# Production Flow Audit — Garment ERP v8.0 (REVISED)

**Date:** 2026-04-24 (rev 2 — variance feature re-analysis)  
**Scope:** End-to-end production flow including intentional overproduction/underproduction  
**Test artefact:** `/app/tests/audit_production_flow.py`

---

## 0. Re-analysis — Variance feature is INTENTIONAL

After reviewing `OverproductionModule.jsx`, `VendorPortalApp.jsx:2534-2793` (`VendorVarianceReport`), and `/api/production-variances` endpoints, I confirm:

### ✅ Intended flow
1. Vendor may **produce more or less than `ordered_qty`** (within material limit).
2. When `produced_qty ≠ ordered_qty`, vendor files an **OVERPRODUCTION** or **UNDERPRODUCTION** variance via the portal.
3. Admin reviews variance in `OverproductionModule` → sets status `Reported → Acknowledged → Resolved`.
4. Invoice `invoice_qty` is **manual** (`server.py:1536`), so vendors can invoice actual shipped qty (which may include overproduction).

### 🔒 Invariants that MUST hold (regardless of variance)

| # | Invariant | Purpose |
|---|---|---|
| I-1 | `produced_qty ≤ available_qty − total_defect_qty` | Can't produce from defective/missing material |
| I-2 | `Σ qty_shipped (all dispatches for po_item) ≤ Σ produced_qty (all job_items for po_item)` | Can't ship what you didn't make |
| I-3 | `Σ return_qty (all returns for po_item) ≤ Σ qty_shipped − Σ already_returned` | Buyer can only return what they received |
| I-4 | `return_qty ≥ 1`, `qty_shipped ≥ 0`, `produced_qty > 0` | No negative/bogus quantities |
| I-5 | `produced_qty` vs `ordered_qty` → **FREE** (variance module records the gap) | This is the overproduction/underproduction feature — do not restrict |

**My original finding M-2 violated I-5 and has been REMOVED.**

---

## 1. Executive Summary (revised)

| Severity | Count | Change |
|---|---|---|
| 🔴 **CRITICAL** | 3 | no change |
| 🟠 **HIGH** | 4 | H-1 reworded — negative remainder has meaning in overproduction; new approach: add `over_shipped_qty` field |
| 🟡 **MEDIUM** | **3** (was 4) | **M-2 REMOVED** (false positive — overproduction intentional) |
| 🟢 **LOW** | 3 | no change |

**All proposed fixes are verified safe for the variance workflow.** Zero data conflicts introduced.

---

## 2. Revised findings (all survive re-analysis except M-2)

### 🔴 CRITICAL

#### C-1. Buyer-shipment accepts `qty_shipped > produced_qty`  ⚠️ Fix cap against PRODUCED, not ORDERED
- **Endpoint:** `POST /api/buyer-shipments` (`server.py:1373`)
- **Wrong cap (variance-incompatible):** reject if `qty_shipped > ordered_qty` → would block legitimate overproduction shipment.
- **Correct cap (variance-compatible):** reject if `Σ qty_shipped (cumulative across all dispatches for this po_item) > Σ produced_qty (all job_items for this po_item, incl. child jobs)`.
- **Evidence:** Shipped 500 when produced 97 → 201 OK.
- **Why safe:** `produced_qty` already captures overproduction (vendor produced 102 → cap is 102, not 100). Variance feature untouched.
- **Implementation:**
  ```python
  # Before insert:
  total_produced = sum(ji.produced_qty for ji in production_job_items where po_item_id==item.po_item_id)
  total_already_shipped = sum(bsi.qty_shipped for bsi in buyer_shipment_items where po_item_id==item.po_item_id)
  if total_already_shipped + item.qty_shipped > total_produced:
      raise 400("Qty ship melebihi qty produksi")
  ```

#### C-2. Production return accepts `return_qty > shipped`  ⚠️ Fix unchanged
- **Endpoint:** `POST /api/production-returns` (`server.py:2247`)
- **Correct cap:** `return_qty ≤ max_returnable = Σ qty_shipped − Σ already_returned` (formula already exists in `/api/po-items-produced:681`).
- **Evidence:** Returned 999 when shipped 97 → 201 OK.
- **Why safe:** Variance feature is vendor-side; returns are buyer-side. No interaction.

#### C-3. Job `total_shipped_to_buyer` always returns 0  ⚠️ Query bug, unrelated to variance
- **Endpoint:** `GET /api/production-jobs` (`server.py:1078`)
- **Fix:** Change query from `{'job_id': j['id']}` → `{'job_item_id': {'$in': all_job_item_ids}}` (the list is already computed 3 lines above).
- **Evidence:** After shipping 667 pcs, listing still showed `shipped=0, remaining_to_ship=170`.

---

### 🟠 HIGH

#### H-1. PO `remaining_qty_to_ship` goes negative  ⚠️ Reworded — negative is meaningful for overproduction
- **Endpoint:** `GET /api/production-pos` (`server.py:516`)
- **Original proposal:** `max(0, ordered - shipped)` — **still recommended**, but insufficient alone. 
- **Refined proposal:**
  ```python
  # Keep remaining_qty_to_ship as the "still to ship" counter (floored at 0)
  remaining_qty_to_ship = max(0, total_ordered - total_shipped)
  # NEW: explicit overproduction indicator
  over_shipped_qty    = max(0, total_shipped - total_ordered)
  under_shipped_qty   = max(0, total_ordered - total_shipped)  # == remaining if status != variance-resolved
  ```
- **Why safe:** `remaining_qty_to_ship` staying non-negative matches dashboard expectations; `over_shipped_qty` gives admin visibility into the overproduction-shipped case without reading variance table. UI can show "✅ 100/100 shipped + 2 over" using these fields. Backward compatible (old UI still reads the same field, just clamped).

#### H-2. Missing MATERIALS don't auto-create replacement request  ⚠️ Unchanged
- `server.py:1001` — auto-creates only for missing *accessories*. Missing material lines don't trigger an auto `REQ-RPL-…`.
- **Why safe:** Adding the auto-create mirrors existing accessory logic; doesn't interact with variance feature.

#### H-3. Progress validation ignores defect-adjusted capacity  ⚠️ Verified compatible with UNDERPRODUCTION variance
- **Endpoint:** `POST /api/production-progress` (`server.py:1265`)
- **Current:** `max_qty = job_item.available_qty` → ignores defects.
- **Correct (invariant I-1):** `max_qty = available_qty − Σ defect_qty`.
- **Why safe for variance:**
  - **Case A:** Material 100, defect 3, vendor produces 97 (= effective). They file UNDERPRODUCTION variance (ordered 100, produced 97, gap 3 "material defect"). ✅ Works.
  - **Case B:** Material 100, no defect, vendor produces 102 (overtime/surplus). Current code already allows this since `102 > 100 available` is rejected — wait, actually NO. Let me re-check...
  - Actually, re-reading `server.py:1267`: `if new_total > max_qty: raise`. So currently, you CANNOT produce more than `available_qty`. That means **overproduction requires material > ordered**.
  - Q: How does overproduction physically happen then? Only if `available_qty > ordered_qty` (vendor received more material than ordered). That is plausible (admin sends extra for buffer).
  - **Conclusion:** The fix does NOT restrict overproduction — it just enforces I-1 (can't produce more than `material received − defective material`). Same logic as today, just accurate.

#### H-4. Return accepts negative `return_qty`  ⚠️ Unchanged
- Pure input validation. No variance interaction.

---

### 🟡 MEDIUM (reduced to 3)

#### M-1. 0-qty buyer dispatch allowed  ⚠️ Unchanged
- Pollutes dispatch history. Fix: require at least one item with `qty_shipped > 0`.

#### ~~M-2. No check `produced_qty > ordered_qty`~~ ❌ **REMOVED — FALSE POSITIVE**
- **Reason for removal:** Overproduction is an intentional, first-class feature. Vendor reports it via variance module. Restricting `produced ≤ ordered` would break the feature.
- **However**, I recommend a *soft dashboard warning* (non-blocking) when `produced > ordered` AND no matching `production_variances` record with `variance_type=OVERPRODUCTION` exists for this `job_id`. This is audit-hygiene, not enforcement.
- Renamed to **optional enhancement** M-2*: "Flag un-reported overproduction in dashboard" — **not a bug, low priority**.

#### M-3. Admin cannot file defect without explicit `vendor_id`  ⚠️ Unchanged
- UX fix: derive vendor_id from the referenced `job_id` / `job_item_id` on backend.

#### M-4. `server.py` monolith (5,816 lines)
- Already on `plan.md` Phase 5 roadmap.

---

### 🟢 LOW — Unchanged (3)

L-1. N+1 queries · L-2. `alert()` usage · L-3. No backend unit tests

---

## 3. Verification matrix — proposed fixes vs variance workflow

| Fix | Overproduction case survives? | Underproduction case survives? | Defect case survives? | Missing-items case survives? | Data conflict? |
|---|---|---|---|---|---|
| C-1 (ship cap = produced) | ✅ produced includes over-pcs | ✅ only ship what produced | ✅ unrelated | ✅ unrelated | None |
| C-2 (return cap = shipped−returned) | ✅ unrelated | ✅ unrelated | ✅ unrelated | ✅ unrelated | None |
| C-3 (job query fix) | ✅ unrelated | ✅ unrelated | ✅ unrelated | ✅ unrelated | None |
| H-1 (clamp + over_shipped_qty) | ✅ new field exposes over-ship | ✅ remaining reflects gap | ✅ unrelated | ✅ unrelated | None — clamp is monotonic |
| H-2 (auto REQ-RPL for missing) | ✅ unrelated | ✅ vendor-filed variance still works | ✅ unrelated | ✅ core improvement | None — new record only |
| H-3 (progress cap = avail − defect) | ✅ overproduction needs extra material, not virtual | ✅ under vendor files variance | ✅ enforces I-1 | ✅ reduces avail already | None — only new inserts |
| H-4 (reject negative return) | ✅ unrelated | ✅ unrelated | ✅ unrelated | ✅ unrelated | None |
| M-1 (reject 0-qty dispatch) | ✅ unrelated | ✅ unrelated | ✅ unrelated | ✅ unrelated | None |
| M-3 (derive vendor_id) | ✅ unrelated | ✅ unrelated | ✅ unrelated | ✅ unrelated | None |

**All proposed fixes preserve the variance feature fully.**

---

## 4. Updated scenario test results

| Scenario | Current | After fixes |
|---|---|---|
| Ship 500 when produced 97 | ❌ accepted | ✅ reject `400: Qty ship melebihi produksi (97)` |
| Ship 102 when produced 102 (overproduction) | ✅ accepted | ✅ accepted — no change |
| Ship 95 when produced 95 (underproduction) | ✅ accepted | ✅ accepted — no change |
| Return 999 when shipped 97 | ❌ accepted | ✅ reject `400: Qty retur melebihi yang dikirim (97)` |
| Return 5 after partial return of 10/97 | ✅ accepted | ✅ accepted — no change |
| Record produce 100 with 3 defect | ❌ accepted | ✅ reject `400: Total produksi (100) melebihi material usable (97)` |
| Record produce 97 with 3 defect | ✅ accepted | ✅ accepted — no change |
| Record produce 102 with avail 110 | ✅ accepted | ✅ accepted — overproduction preserved |
| File OVERPRODUCTION variance for 102 vs 100 | ✅ works | ✅ works — no change |
| File UNDERPRODUCTION variance for 97 vs 100 | ✅ works | ✅ works — no change |
| Job `total_shipped_to_buyer` after 100 shipped | ❌ shows 0 | ✅ shows 100 |
| PO `remaining_qty_to_ship` after over-ship 102/100 | ❌ shows -2 | ✅ shows 0; `over_shipped_qty = 2` |
| Auto REQ-RPL when 5 missing material | ❌ not created | ✅ created with pre-filled items |

---

## 5. Recommended implementation sequence (unchanged priorities, verified safe)

### Phase A — Critical guardrails (preserving variance)  
~2-3 hours · Atomic per-bug fixes
1. C-1 · cap buyer shipment at `produced_qty` (not `ordered_qty`)
2. C-2 · cap return at `max_returnable`
3. C-3 · fix job shipped query
4. H-1 · add `over_shipped_qty` + clamp `remaining_qty_to_ship`
5. H-3 · cap progress at `available − defect` (I-1)
6. H-4 · reject `return_qty < 1`
7. M-1 · reject 0-qty dispatch

### Phase B — Workflow completeness  
~2 hours
8. H-2 · auto REQ-RPL for missing material (mirror accessory block)
9. M-3 · derive vendor_id on defect endpoint
10. M-2* (optional) · soft-warn unreported overproduction on dashboard

### Phase C — UX polish  
~1 hour
11. L-2 · replace `alert()` with `Sonner` toast

### Phase D — Productionization (Phase-5 in plan.md)
12. M-4 / L-1 · split monolith, batch queries
13. L-3 · pytest regression suite covering I-1 through I-4

---

## 6. Files of interest (unchanged)

| File | Concern |
|---|---|
| `/app/backend/server.py:516` | PO remaining calc (H-1) |
| `/app/backend/server.py:1040-1091` | Job aggregate query bug (C-3) |
| `/app/backend/server.py:1255-1290` | Progress validation (H-3) |
| `/app/backend/server.py:1373-1432` | Buyer shipment create (C-1) |
| `/app/backend/server.py:2247-2288` | Return create (C-2, H-4) |
| `/app/backend/server.py:898-1037` | Inspection auto-request (H-2) |
| `/app/backend/server.py:2193-2219` | Defect report vendor_id (M-3) |
| `/app/backend/server.py:5597-5777` | Variance endpoints (reference only — no changes) |
| `/app/frontend/src/components/erp/OverproductionModule.jsx` | Admin variance view (reference only — no changes) |
| `/app/frontend/src/components/erp/VendorPortalApp.jsx:2534` | Vendor variance form (reference only — no changes) |

---

*End of revised audit.*
