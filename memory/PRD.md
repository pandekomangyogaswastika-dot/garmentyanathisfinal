# Garment ERP v8.0 — Product Requirements Document

## Original problem statement
Continue development of **Garment ERP v8.0**, a multi-portal (Admin / Vendor / Buyer) factory ERP for garment manufacturers built on **React + FastAPI + MongoDB**.

## Stack
- **Frontend**: React, shadcn/ui, Tailwind, Sonner toasts, dnd-kit, lucide-react
- **Backend**: FastAPI + Motor (async MongoDB)
- **Storage**: MongoDB

## Architecture
- `/app/backend/` — FastAPI app, modular routes, auth.py with JWT-based custom auth, seed_initial_data() for the superadmin
- `/app/frontend/` — React SPA. All API requests now flow through a centralized client.

## Key technical concept (post-Phase-11)
**`/app/frontend/src/lib/api.js`** is the single network entry point. It exposes:
- `apiGet(path)`, `apiPost(path, body)`, `apiPut(path, body)`, `apiDelete(path)` — JSON helpers; auto-inject Auth header; throw on non-OK responses
- `apiFetch(path, options)` — raw fetch with auth + base-URL prefixing; used for blob/PDF/Excel downloads where the caller must read the Response object
- `apiDownload(path, filename)` — convenience for blob downloads
Native `fetch()` is now **forbidden** outside `lib/api.js`.

## What's been implemented (chronological highlights)
- **Phases 1–10**: Core ERP modules (PO, Products, Vendors, Buyers, Shipments, Invoices, Payments, Reports, PDF templates, Smart Import w/ AI mapping, Material Requests, Returns, Variances, Approvals, Activity Log, Accounts Receivable/Payable, etc.)
- **Phase 10C**: Server-side pagination on heavy tables (Products, Production POs)
- **Phase 11A** (prior session): All low-fetch-count files migrated to `lib/api.js`
- **Phase 11B** (this session, 2026-02-27): Migrated 5 remaining medium-complexity files
  - PaymentModule.jsx, ReportsModule.jsx, VendorBuyerShipments.jsx, VendorProductionJobs.jsx, VendorMaterialInspection.jsx
- **Phase 11C** (this session, 2026-02-27): Migrated all 10 heavy fetch-using files
  - ProductionPOModule.jsx (17 fetches), VendorShipmentModule.jsx (14), ManualInvoiceModule.jsx (12), BuyerShipmentModule.jsx (10), SmartImportModule.jsx (9), ProductionReturnModule.jsx (8), ProductsModule.jsx (7), ProductionProgressModule.jsx (7), UserManagementModule.jsx (7), PDFConfigModule.jsx (7)
- **Verified by `grep -rln 'fetch(' /app/frontend/src/`**: only `/app/frontend/src/lib/api.js` remains
- **Regression test**: testing_agent_v3_fork iteration_20.json — 100% pass, 0 console/page errors across all 15 modules
- **Phase 11 dead-prop cleanup** (this session, 2026-02-27): removed dead `token` prop from signature of 15 migrated modules + 2 internal subcomponents (ShipmentList, MaterialRequestList in VendorShipmentModule); removed `token={token}` JSX pass-through from App.js, VendorPortalApp.jsx, and internal calls to ImportExportPanel/FileAttachmentPanel within the 6 affected modules
- **Regression test**: testing_agent_v3_fork iteration_21.json — 100% pass, 0 ReferenceError, 0 console errors

## Phase 12 — Critical Bug Fix: Production PO infinite-fetch loop (2026-04-28)
### Reported Issue
User: "loading production po terlalu lama dan tidak terload" (Production PO never finishes loading).

### Root Cause
`DataTable.jsx`'s `runFetch` `useCallback` had `serverPagination` (parent-passed prop object) in its dep array. ProductionPOModule passes `serverPagination={{ fetcher, deps, ... }}` as inline object literal — every parent render produces a new object reference, which:
1. Made `runFetch` reference change every render
2. Triggered `useEffect [runFetch]` → re-fired the fetcher
3. The fetcher itself called `setPOs(items)` on the parent → triggered re-render
4. Loop step 1 → ∞ (verified ~20+ identical `/api/production-pos?page=1&per_page=20…` calls per page mount; UI stuck on "Memuat data…")

Same trap latently affected every other module using `DataTable` server pagination (BuyerShipment, ProductsModule, etc.) — but the symptom was most visible in ProductionPO because its fetcher writes back to parent state.

### Fix
`/app/frontend/src/components/erp/DataTable.jsx`: store `serverPagination?.fetcher` in a `useRef` and read from it inside `runFetch`. Removed `serverPagination` from `runFetch` dep array. `deps` (filter primitives) still flow through `...deps` spread for legitimate refetch triggers.

### Verification
Reproduced before fix → ~20+ duplicate calls in <5s, UI stuck on "Memuat data…".
After fix → exactly 2 calls (React 18 strict-mode double-mount, normal), UI shows "Tidak ada data" empty state correctly. Cross-module check on Accounts Payable confirms no breakage.

### Phase 12 follow-up bug fix (2026-04-28)
**Iteration 22 testing agent** found:
- **CRITICAL**: `GET /api/production-pos/{po_id}` and `GET /api/vendor-shipments/{sid}` returned 500 (`NameError: enrich_with_product_photos is not defined`). Function was called at server.py L752 + L1215 but never defined. Defined the helper near top of server.py (after `_run_list_query`); it batch-looks-up `products` by referenced product_ids and attaches `product_photo` / `product_photo_url` to each item dict. Verified: `GET /api/production-pos/{id}` now returns 200 with serialized PO doc.
- **NOT A BUG (false positive)**: testing-agent flagged manual invoice as broken because `source_po_id` is required. By design — `ManualInvoiceModule.jsx` requires user to select a PO first (line 223), and `POST /api/invoices` correctly enforces this. No code change needed.

### Iteration 22 verified
- Production PO infinite-loop fix HOLDS (only 2 `/api/production-pos` calls on module open vs >20 before)
- Auth, master-data CRUD, PO create, pagination envelope, buyer-shipment caps (M-1, C-1), payment endpoint, PDF export, smart-import upload all GREEN
- Backend success rate after `enrich_with_product_photos` fix: ~96% (the 1 remaining "fail" was the false-positive manual-invoice case)

### Environment Setup (also done this session)
- Installed missing backend dep: `rapidfuzz` (used by `routes/smart_import.py`)
- Installed missing frontend deps: `@tanstack/react-virtual`, `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`
  (frontend was failing to compile before this — every page would have shown the red CRA error overlay)

## Backlog / Roadmap
### P1 — Polishing & DX
- Add unit tests for `lib/api.js` covering auth-header injection, 401 auto-logout, JSON/FormData handling, blob downloads
- Optional: replace remaining `alert()` / `window.confirm` calls with shadcn `<AlertDialog>` for consistency

### P2 — Performance / Scale
- Server-side pagination for Payments, Invoices, BuyerShipments, VendorShipments (currently full-list fetches with per_page=200 on a few)
- Bundle-size review (vendor splitting, lazy-load heavy modules)

### P2 — UX
- Optimistic updates on common CRUD actions (toast feedback while request is in flight)
- Skeleton loaders on initial module load for smoother first-paint

### P3 — Backlog
- Multi-language support (currently Indonesian-only UI strings)
- Export-to-Email for reports
- Dashboard customization (drag-rearrange KPI cards)

## Test credentials
See `/app/memory/test_credentials.md`. Superadmin: `admin@garment.com` / `Admin@123`.

## Known constraints
- Indonesian-language UI labels (Buat = Create, Daftar = List, Manajemen = Management, etc.)
- Sidebar nav uses title-case group labels (Keuangan, Master Data, Laporan & Tools, Sistem) that must be expanded before clicking children
