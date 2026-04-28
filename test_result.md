#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================
# (Standard testing protocol preserved as in original repo)
#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

user_problem_statement: |
  Continue development from https://github.com/pandekomangyogaswastika-dot/garmentyanathisfinal.
  User reported: "loading production po terlalu lama dan tidak terload" (Production PO never finishes loading).
  Then: "do full comprehensive testing using real input data case & scenario".

  Root cause already fixed:
  - Missing frontend deps (@tanstack/react-virtual, @dnd-kit/{core,sortable,utilities}) caused full compile failure → red CRA overlay hid every page.
  - DataTable.jsx had `serverPagination` (inline object prop) inside runFetch's useCallback dep array → infinite re-fetch loop in ProductionPOModule.
  Fix applied at /app/frontend/src/components/erp/DataTable.jsx (fetcherRef + dep cleanup).
  See PRD.md "Phase 12" for full RCA.

  Now we need comprehensive E2E regression covering all major ERP flows.

backend:
  - task: "Auth — JWT login/logout, role-based access"
    implemented: true
    working: "NA"
    file: "/app/backend/auth.py, /app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true

  - task: "Production PO — CRUD + items + accessories + close + variance"
    implemented: true
    working: "NA"
    file: "/app/backend/server.py (lines 655-992)"
    stuck_count: 0
    priority: "high"
    needs_retesting: true

  - task: "Vendor flow — receiving / inspection / progress / defect / variance / shipment"
    implemented: true
    working: "NA"
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true

  - task: "Buyer Shipment + Production Return + invariants (C-1, C-2, C-3, H-1)"
    implemented: true
    working: "NA"
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true

  - task: "Invoices (auto AP/AR + manual) + Payments"
    implemented: true
    working: "NA"
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true

  - task: "PDF Export (17 types) + presets RBAC"
    implemented: true
    working: "NA"
    file: "/app/backend/routes/pdf_exports.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true

  - task: "Smart Import (Excel/PDF, all data types)"
    implemented: true
    working: "NA"
    file: "/app/backend/routes/smart_import.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true

frontend:
  - task: "Production PO infinite-loop fix verification"
    implemented: true
    working: "NA"
    file: "/app/frontend/src/components/erp/DataTable.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true

  - task: "Full sidebar nav + each module renders without console/page errors"
    implemented: true
    working: "NA"
    file: "/app/frontend/src/components/erp/*"
    stuck_count: 0
    priority: "high"
    needs_retesting: true

  - task: "End-to-end PO → vendor distribute → progress → variance → shipment → invoice → payment"
    implemented: true
    working: "NA"
    file: "Multiple modules"
    stuck_count: 0
    priority: "high"
    needs_retesting: true

metadata:
  created_by: main_agent
  version: "12.0"
  test_sequence: 22
  run_ui: true

test_plan:
  current_focus:
    - "Production PO infinite-loop fix verification"
    - "Auth — JWT login/logout, role-based access"
    - "Production PO — CRUD + items + accessories + close + variance"
    - "Vendor flow — receiving / inspection / progress / defect / variance / shipment"
    - "Buyer Shipment + Production Return + invariants"
    - "Invoices (auto AP/AR + manual) + Payments"
    - "End-to-end PO → vendor distribute → progress → variance → shipment → invoice → payment"
    - "Full sidebar nav + each module renders without console/page errors"
  stuck_tasks: []
  test_all: true
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Phase 12 fix shipped: DataTable.jsx infinite-loop bug + missing deps installed (rapidfuzz, react-virtual, dnd-kit/*).
      Re-verified manually: ProductionPO now triggers exactly 2 calls (StrictMode double-mount) instead of 20+ infinite loop.
      Need comprehensive E2E across all major ERP flows with realistic data scenarios:
        - Master data seeding (vendor + buyer + products + accessories)
        - PO creation with multi-item + variants + accessories
        - Vendor receiving + inspection (defect + missing) + progress (overproduction/underproduction)
        - Variance reporting + admin acknowledge
        - Vendor shipment → buyer dispatch (partial + over-ship caps)
        - Production returns (cap on shipped-returned)
        - Invoice (auto + manual) + Payment workflow
        - PDF export of key types
      Test_credentials.md is up to date: admin@garment.com / Admin@123 (superadmin).
