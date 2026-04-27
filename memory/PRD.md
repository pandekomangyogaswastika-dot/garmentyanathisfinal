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
