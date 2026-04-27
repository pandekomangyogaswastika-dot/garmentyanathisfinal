# Garment ERP v8.0 — Delivery Plan (Updated)

## Objectives
- ✅ **Completed:** PDF export enhancement program (presets, column selection & order, header/footer/title overrides, orientation, RBAC) across all 17 PDF types.
- ✅ **Completed:** Production Flow Audit remediation (AUDIT-A + AUDIT-B) — data integrity guardrails + workflow completeness + UX polish.
- ✅ **Completed:** Smart Import Feature (Tier 1–3, all data types) — Upload → Map → Preview/Edit → Confirm → Import.
- ✅ **Completed:** Comprehensive E2E validation for delivered features; critical RBAC security bug fixed.
- ✅ **Completed:** Phase 8 enhancement sprint (shipment safety guards, PO edit guardrails, system-wide sorting persistence, Smart Import add-ons, product variants, hook cleanup).
- ✅ **Completed:** Phase 9 critical bug fix sprint (Login JSON error, Smart Import error-path stability, buyer portal authenticated PDF download, missing frontend deps).
- ✅ **Completed (P0):** **Performance tuning — backend pagination** (backward compatible) added to major list endpoints + added missing MongoDB indexes + eliminated worst N+1 patterns.
- ✅ **Completed (P0/P1):** Phase 10B + 10E — additional N+1 query reductions across reports + dashboard + serial endpoints and PDF paths.
- ✅ **Completed (refactor):** Extracted PDF logic from `backend/server.py` into `backend/routes/pdf_exports.py`.
- ✅ **Completed (refactor):** Split monolithic `VendorPortalApp.jsx` into modular Vendor components; created centralized API client `frontend/src/lib/api.js`.
- ✅ **Completed:** Removed **“Made with Emergent”** badge (HTML anchor + external script injection) and restarted frontend.
- ✅ **Verified (iteration_19):** Full regression test suite passed — **Backend 100% (21/21)**, **Frontend 100%** including badge removal.
- 🎯 **Current Focus (P1):** Frontend API standardization — migrate remaining inline network calls to centralized `frontend/src/lib/api.js` to standardize auth headers, error handling, and downloads.

---

## Implementation Steps

### Phase 1 — Core Flow POC (Isolation): Prove preset → PDF rendering works reliably
**Status: ✅ COMPLETED**

**What we verified**
1. All PDF export endpoints work with seeded data; buyer shipment summary + per-dispatch both export correctly.
2. PDF Config CRUD works (create/read/update/delete/set default).
3. Column filtering via `config_id` and default preset auto-apply both work.
4. Confirmed critical branding bug: Company Settings fields were saved but not rendered.
5. Confirmed validation gap: unknown `pdf_type` accepted by preset creation.

**Confirmed bugs from Phase 1**
- **CRITICAL:** Company Settings branding fields were not rendered in PDFs.
- **LOW:** `POST /api/pdf-export-configs` accepted unknown `pdf_type`.

---

### Phase 2 — Bug Fixes: Company branding + validation hardening
**Status: ✅ COMPLETED**

**User stories delivered**
1. Company Settings branding is always reflected in exported PDFs.
2. System rejects invalid presets (unknown `pdf_type`).
3. PDF generation remains stable even if logo URL is invalid/unreachable.

---

### Phase 3 — Enhancements: Full preset power (columns/order/header-footer/orientation) + RBAC
**Status: ✅ COMPLETED (Backend + Frontend)**

**User stories delivered**
1. Admin can configure presets for all 17 PDF types.
2. Admin can drag & drop columns to set ordering.
3. Admin can select additional DB-backed columns beyond the original minimal set.
4. Admin can override title/header/footer per preset with a clear precedence model.
5. Admin can set page orientation per preset (auto/portrait/landscape).
6. Non-admin users can view presets and export PDFs but cannot modify presets (RBAC).

---

### Phase 4 — End-to-End Testing & Validation (PDF Export)
**Status: ✅ COMPLETED (per `test_reports/iteration_6.json`)**

---

### Phase 5 — Productionization (optional)
**Status: ⏳ OPTIONAL / FUTURE**

---

## Phase AUDIT-A — Production Flow Data-Integrity Guardrails
**Status: ✅ COMPLETED (2026-04-24)**

---

## Phase AUDIT-B — Workflow Completeness & UX Polish
**Status: ✅ COMPLETED (2026-04-24)**

---

## Phase 6 — Smart Import Feature (All tiers + all data types)
**Status: ✅ COMPLETED (implementation) (2026-04-24)**

---

## Phase 7 — End-to-End Testing & Validation (All recent features)
**Status: ✅ COMPLETED (2026-04-24)**

---

## Phase 8 — Multi-Issue Enhancement Sprint (Execution Approved)
**Status: ✅ COMPLETED (Implementation + Verification)**

---

## Phase 9 — Critical Bug Fixes (Login / Smart Import / PDF Export)
**Status: ✅ COMPLETED (2026-04-27)**

### Context
User reported three bugs:
1. Login bug — `Failed to execute 'json' on 'Response': body stream already read`
2. Smart Import bug (same root cause on error responses)
3. Suspected PDF export bug

### Root Cause
Emergent preview logger wraps `window.fetch` and calls `response.text()` on non-OK responses without cloning, consuming the body stream and breaking later `res.json()` calls.

### Fixes Delivered
1. `frontend/public/index.html` — preserve native fetch and install clone-safe wrapper.
2. `frontend/src/components/erp/Login.jsx` — use `detail` and defensive JSON parsing.
3. `frontend/src/components/erp/BuyerPortalApp.jsx` — authenticated PDF download via fetch+blob.
4. Installed missing deps: `xlsx`, `jspdf`, `jspdf-autotable`.

### Follow-up change (2026-04-27)
- Removed “Made with Emergent” badge:
  - Deleted `#emergent-badge` anchor block.
  - Removed `https://assets.emergent.sh/scripts/emergent-main.js` which injected the badge.

### Verification
- Full regression suite re-run: **iteration_19** indicates backend and frontend both 100% pass.

---

## Phase 10 — Performance Tuning (P0-first)
**Status: ✅ Phase 10A COMPLETED (2026-04-27); ✅ 10B COMPLETED; ✅ 10C COMPLETED; ✅ 10D COMPLETED; ✅ 10E COMPLETED**

### Context / Problem
Current UI used to rely on **client-side pagination** (`DataTable.jsx` slices arrays), but backend previously returned full datasets for many list endpoints (frequent `.to_list(None)`), which will not scale. Several endpoints also contained **N+1 query patterns** that multiplied DB calls per request.

### High-level Strategy
- **10A (P0)**: Add **backend pagination** first with **backward compatibility** so frontend remains functional during rollout.
- **10B/10E (P0/P1)**: Reduce worst N+1 patterns via batch fetches or aggregation.
- **10C/10D (P1/P2)**: Update frontend tables to true server-side pagination and virtualization.

---

### Phase 10A — Backend Pagination (Backward-Compat) + Missing Indexes
**Status: ✅ COMPLETED (2026-04-27)**

(Details unchanged; see prior sections in plan.)

---

### Phase 10B — N+1 Query Reduction (Heaviest list endpoints)
**Status: ✅ FULLY COMPLETED (2026-04-27)**

---

### Phase 10C — Frontend tuning: True server-side pagination rollout
**Status: ✅ COMPLETED (2026-04-27)**

---

### Phase 10D — Virtualized rows
**Status: ✅ COMPLETED (2026-04-27)**

---

### Phase 10E — Additional N+1 reductions
**Status: ✅ COMPLETED (2026-04-27)**

---

## Phase 11 — P1 Frontend API Standardization: Migrate inline network calls → `frontend/src/lib/api.js`
**Status: 🟡 IN PROGRESS (P1)**

### Context / Problem
Frontend previously contained **~200+ inline `fetch()` calls across ~43 files**. This caused:
- Inconsistent auth header injection (manual `Bearer` usage in many places)
- Inconsistent error handling (`res.ok` checks vary; JSON parse errors differ)
- Repeated boilerplate (headers/body parsing) across modules
- Harder-to-maintain download logic (PDF/Excel) and 401 handling

A centralized API client already exists:
- `frontend/src/lib/api.js` provides: `apiFetch`, `apiGet`, `apiPost`, `apiPut`, `apiDelete`, `apiDownload`
- Includes: automatic token header, 401 auto-logout, JSON error normalization

### High-level Strategy
Migrate in 3 phases **from simplest to heaviest**, and **test after each phase**.

#### Phase 11A — Low-risk / core/shared (1–3 calls per file)
**Status: ✅ COMPLETED**

**Result / Current state**
- All core/shared modules now have **0 inline `fetch()`** and use `api.js`.
- Current scan shows: `App.js:0`, and many modules at `0` (Phase 11A target satisfied).

**Notes**
- Any remaining Emergent badge injection must remain removed via `frontend/public/index.html` (ensure this file stays in sync with repo changes).

**Phase 11A test checklist (smoke)**
- Login success + failed login shows correct error
- Sidebar loads current user
- Dashboard loads analytics + reminders
- Vendor dashboard loads for vendor role (smoke)

#### Phase 11B — Medium complexity (4–6 calls per file)
**Status: 🟡 NEXT**

**Goal**
Convert mid-sized modules that usually combine list + CRUD operations.

**Remaining target files (per current scan)**
- 4 calls each:
  - `frontend/src/components/erp/ActivityLogModule.jsx`
  - `frontend/src/components/erp/GarmentsModule.jsx`
  - `frontend/src/components/erp/OverproductionModule.jsx`
  - `frontend/src/components/erp/RoleManagementModule.jsx`
  - `frontend/src/components/erp/VendorProgress.jsx`
  - `frontend/src/components/erp/VendorVarianceReport.jsx`
- 5 calls each:
  - `frontend/src/components/erp/PaymentModule.jsx`
  - `frontend/src/components/erp/ReportsModule.jsx`
  - `frontend/src/components/erp/VendorBuyerShipments.jsx`
  - `frontend/src/components/erp/VendorProductionJobs.jsx`
- 6 calls each:
  - `frontend/src/components/erp/InvoiceModule.jsx`
  - `frontend/src/components/erp/VendorDefectReports.jsx`
  - `frontend/src/components/erp/VendorMaterialInspection.jsx`

**Phase 11B implementation rules**
- Introduce helper functions inside module: `loadX`, `saveY`, `deleteZ` using `api*` methods.
- Replace repeated header creation with client calls.
- Normalize error handling into `try/catch` with user-friendly message.
- Prefer `apiDownload()` for PDF/Excel exports; use `apiFetch()` when custom headers/filenames are required.

**Phase 11B test checklist**
- CRUD happy path per module (create/edit/delete where applicable)
- Filters + server-side pagination still functioning
- Vendor role access still restricted properly (401/403 behaviors preserved)

#### Phase 11C — Heaviest modules (7+ calls per file)
**Status: 🟡 UPCOMING (after 11B)**

**Goal**
Convert the largest screens last, after patterns are proven.

**Remaining target files (per current scan)**
- 7 calls each:
  - `frontend/src/components/erp/PDFConfigModule.jsx`
  - `frontend/src/components/erp/ProductionProgressModule.jsx`
  - `frontend/src/components/erp/ProductsModule.jsx`
  - `frontend/src/components/erp/UserManagementModule.jsx`
- 8 calls:
  - `frontend/src/components/erp/ProductionReturnModule.jsx`
- 9 calls:
  - `frontend/src/components/erp/SmartImportModule.jsx`
- 10 calls:
  - `frontend/src/components/erp/BuyerShipmentModule.jsx`
- 12 calls:
  - `frontend/src/components/erp/ManualInvoiceModule.jsx`
- 14 calls:
  - `frontend/src/components/erp/VendorShipmentModule.jsx`
- 17 calls:
  - `frontend/src/components/erp/ProductionPOModule.jsx`

**Phase 11C implementation rules**
- Prefer small, mechanical changes per commit chunk to reduce merge risk.
- Convert list fetches first, then CRUD actions, then special cases (download/export).
- Keep existing response-shape handling to avoid UI regressions.

**Phase 11C test checklist**
- Production PO end-to-end flows (create/update, add items, status changes)
- Shipment flows (vendor shipment create, buyer shipment, dispatch)
- Smart Import end-to-end
- PDF config and exports still working

### Exit Criteria (Phase 11)
- No inline `fetch()` remains in `frontend/src` (except where explicitly justified, e.g. very specialized streaming scenarios).
- All API calls go through `frontend/src/lib/api.js` (or thin wrappers built on top of it).
- Consistent handling of:
  - `Authorization` headers
  - `Content-Type` and FormData
  - Error messages (`detail` surfaced consistently)
  - 401 auto-logout behavior
- Regression suite passes after Phase 11C.

---

## Next Actions (Immediate)
1. **Phase 11B:** Migrate the remaining 4–6 call modules listed above to `frontend/src/lib/api.js`.
2. Run smoke tests after Phase 11B.
3. **Phase 11C:** Migrate heavy modules (7+ calls) listed above and validate complex workflows.
4. Run full regression suite (same coverage as iteration_19) after Phase 11C.

## Success Criteria
- ✅ P0: Backend supports safe pagination and avoids unbounded reads.
- ✅ P0: Heaviest list endpoints no longer have catastrophic N+1 query behaviour.
- ✅ Verified: Badge removed and full regression suite passes (iteration_19).
- 🎯 P1: Frontend uses centralized API client; auth + errors + downloads are standardized.
- 🎯 P1: Reduced duplicated networking code and fewer auth-related bugs (401 handling consistent).
