# DESIGN & TECHNICAL DOCUMENT
## Garment ERP System v8.0

**Tanggal Update Terakhir:** 14 April 2026  
**Versi Aplikasi:** 8.0  
**Stack Teknologi:** React + FastAPI + MongoDB

---

## 📋 DAFTAR ISI

1. [Gambaran Umum Sistem](#gambaran-umum-sistem)
2. [Arsitektur Aplikasi](#arsitektur-aplikasi)
3. [Model Data & Database](#model-data--database)
4. [API Endpoints](#api-endpoints)
5. [Fitur-Fitur Utama](#fitur-fitur-utama)
6. [Autentikasi & RBAC](#autentikasi--rbac)
7. [Testing & Quality Assurance](#testing--quality-assurance)
8. [Deployment & Environment](#deployment--environment)

---

## 🎯 GAMBARAN UMUM SISTEM

### Tujuan
Sistem ERP Garment adalah platform manajemen produksi garmen end-to-end yang menghubungkan Admin ERP, Vendor (Garment), dan Buyer dalam satu ekosistem terintegrasi.

### Portal Akses
1. **Portal Admin ERP** - Dashboard utama untuk mengelola seluruh operasi
2. **Portal Vendor** - Interface khusus untuk vendor/garment melakukan operasi terkait production
3. **Portal Buyer** - Interface untuk buyer memantau order dan shipment

### Key Capabilities
- Production Order (PO) Management dengan aksesoris
- Vendor Shipment & Material Inspection (termasuk aksesoris)
- Production Job Management dengan serial tracking
- Buyer Shipment Management dengan per-dispatch PDF export
- Dashboard Analytics dengan date range filter
- Real-time Serial Number Tracking
- Product Master Data dengan photo upload
- Auto-creation Material Request untuk missing accessories
- Multi-level RBAC (Role-Based Access Control)
- Comprehensive PDF & Excel reporting

---

## 🏗️ ARSITEKTUR APLIKASI

### Tech Stack

#### Frontend
- **Framework:** React (Create React App)
- **Styling:** Tailwind CSS + Shadcn/ui components
- **Icons:** Lucide React
- **Charts:** Recharts
- **HTTP Client:** Fetch API
- **State Management:** React Hooks (useState, useEffect, useCallback)

#### Backend
- **Framework:** FastAPI (Python 3.11+)
- **Database Driver:** Motor (Async MongoDB driver)
- **Authentication:** PyJWT
- **PDF Generation:** ReportLab
- **Excel Generation:** openpyxl
- **File Upload:** Python Multipart
- **CORS:** FastAPI CORS Middleware

#### Database
- **Type:** MongoDB (Document-based NoSQL)
- **ID Strategy:** UUID v4 (bukan ObjectId)
- **Timezone:** UTC untuk semua datetime fields

### Struktur Direktori

```
/app/
├── backend/
│   ├── server.py              # Main FastAPI app (~4928 lines, monolithic)
│   ├── database.py            # MongoDB connection setup
│   ├── auth.py                # JWT & RBAC utilities
│   ├── requirements.txt       # Python dependencies
│   └── .env                   # Backend environment variables (MONGO_URL)
├── frontend/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── App.js             # Main router & layout
│   │   ├── index.js           # React entry point
│   │   ├── index.css          # Global styles
│   │   ├── App.css            # App-specific styles
│   │   └── components/
│   │       ├── ui/            # Shadcn/ui components (Button, Card, etc.)
│   │       └── erp/           # Business logic components
│   │           ├── Login.jsx
│   │           ├── Dashboard.jsx
│   │           ├── ProductionPOModule.jsx
│   │           ├── VendorShipmentModule.jsx
│   │           ├── BuyerShipmentModule.jsx
│   │           ├── ProductsModule.jsx
│   │           ├── SerialTrackingModule.jsx
│   │           ├── VendorPortalApp.jsx
│   │           └── ... (30+ modules)
│   ├── package.json
│   └── .env                   # REACT_APP_BACKEND_URL
├── tests/
│   ├── poc_po_accessories_flow.py
│   ├── poc_rbac_custom_role.py
│   └── backend_test_iteration*.py
├── test_reports/
│   ├── iteration_1.json
│   ├── iteration_2.json
│   └── iteration_3.json
└── plan.md                    # Development plan & progress tracking
```

### Service Architecture

- **Frontend:** React Dev Server (Port 3000)
- **Backend:** Uvicorn ASGI Server (Port 8001, bind 0.0.0.0)
- **Database:** MongoDB (managed service, connected via MONGO_URL)
- **Supervisor:** Process manager untuk frontend & backend services
- **Nginx Ingress:** 
  - `/api/*` → Backend (port 8001)
  - `/*` → Frontend (port 3000)

### Environment Variables

#### Backend (.env)
```bash
MONGO_URL=<MongoDB connection string>
SECRET_KEY=<JWT secret key>
EMERGENT_LLM_KEY=<Optional: for file storage>
```

#### Frontend (.env)
```bash
REACT_APP_BACKEND_URL=https://erp-production-track.preview.emergentagent.com
```

**⚠️ CRITICAL:** Jangan pernah memodifikasi `REACT_APP_BACKEND_URL` dan `MONGO_URL` karena sudah dikonfigurasi oleh platform.

---

## 🗄️ MODEL DATA & DATABASE

### Prinsip Desain Database
1. **UUID sebagai Primary Key** - Semua collection menggunakan field `id` bertipe UUID string
2. **No ObjectId** - Tidak menggunakan MongoDB ObjectId untuk portabilitas data
3. **Timezone UTC** - Semua datetime disimpan dalam UTC dengan `datetime.now(timezone.utc)`
4. **Denormalization** - Duplikasi data seperti `po_number`, `vendor_name` untuk performa query
5. **Soft References** - Foreign key sebagai string UUID, bukan DBRef

### Core Collections

#### 1. users
```javascript
{
  id: UUID,
  email: String,
  password: String (hashed),
  name: String,
  role: 'superadmin' | 'admin' | 'vendor' | 'buyer',
  vendor_id?: UUID,     // jika role=vendor
  buyer_id?: UUID,      // jika role=buyer
  role_id?: UUID,       // custom role ID
  status: 'active' | 'inactive',
  created_at: DateTime,
  updated_at: DateTime
}
```

#### 2. roles & role_permissions
```javascript
// roles collection
{
  id: UUID,
  role_name: String,
  description: String,
  created_at: DateTime
}

// role_permissions collection
{
  id: UUID,
  role_id: UUID,
  permission_key: String,  // e.g., 'production_po.create'
  created_at: DateTime
}
```

**Permission Keys:**
- `production_po.create`, `production_po.read`, `production_po.update`, `production_po.delete`
- `vendor_shipment.create`, `vendor_shipment.read`, etc.
- `buyer_shipment.create`, `buyer_shipment.read`, etc.
- `products.create`, `products.read`, etc.
- (dan seterusnya untuk semua module)

#### 3. production_pos (Production Orders)
```javascript
{
  id: UUID,
  po_number: String,            // Auto-generated: PO-YYYYMMDD-XXXX
  customer_name: String,
  buyer_id?: UUID,
  buyer_name?: String,
  vendor_id: UUID,
  vendor_name: String,
  po_date: DateTime,
  deadline: DateTime,
  delivery_deadline?: DateTime,
  total_qty: Number,
  total_value: Number,
  status: 'Draft' | 'Active' | 'Distributed' | 'In Progress' | 'Completed' | 'Closed',
  notes?: String,
  created_by: String,
  created_at: DateTime,
  updated_at: DateTime
}
```

#### 4. po_items
```javascript
{
  id: UUID,
  po_id: UUID,
  po_number: String,
  product_id: UUID,
  product_name: String,
  variant_id?: UUID,
  sku: String,
  size: String,
  color: String,
  serial_number?: String,       // Serial tracking
  qty: Number,
  unit_price: Number,
  total_price: Number,
  notes?: String,
  created_at: DateTime
}
```

#### 5. po_accessories (BARU di v8.0)
```javascript
{
  id: UUID,
  po_id: UUID,
  po_number: String,
  accessory_id: UUID,
  accessory_name: String,
  accessory_code: String,
  qty_needed: Number,
  unit: String,               // 'pcs', 'roll', 'meter', dll
  notes?: String,
  created_at: DateTime
}
```

#### 6. vendor_shipments
```javascript
{
  id: UUID,
  shipment_number: String,      // SHP-VENDOR-XXXX
  delivery_note_number: String,
  vendor_id: UUID,
  vendor_name: String,
  po_id?: UUID,                 // Linked PO (jika single-PO shipment)
  po_number?: String,
  shipment_date: DateTime,
  shipment_type: 'REGULAR' | 'ADDITIONAL' | 'REPLACEMENT',
  parent_shipment_id?: UUID,    // For ADDITIONAL/REPLACEMENT
  total_qty: Number,
  status: 'Sent' | 'In Transit' | 'Received' | 'Inspected',
  inspection_status: 'Pending' | 'Inspected',
  total_received?: Number,
  total_missing?: Number,
  notes?: String,
  created_at: DateTime,
  updated_at: DateTime
}
```

#### 7. vendor_shipment_items
```javascript
{
  id: UUID,
  shipment_id: UUID,
  po_id: UUID,
  po_number: String,
  po_item_id?: UUID,
  product_name: String,
  sku: String,
  size: String,
  color: String,
  serial_number?: String,
  qty_sent: Number,
  unit: String,
  notes?: String,
  created_at: DateTime
}
```

#### 8. vendor_material_inspections (ENHANCED di v8.0)
```javascript
{
  id: UUID,
  shipment_id: UUID,
  shipment_number: String,
  vendor_id: UUID,
  vendor_name: String,
  inspection_date: DateTime,
  total_received: Number,       // Material items
  total_missing: Number,        // Material items
  total_acc_received: Number,   // NEW: Accessory items
  total_acc_missing: Number,    // NEW: Accessory items
  overall_notes?: String,
  status: 'Submitted' | 'Reviewed',
  submitted_by: String,
  created_at: DateTime,
  updated_at: DateTime
}
```

#### 9. vendor_material_inspection_items (ENHANCED di v8.0)
```javascript
{
  id: UUID,
  inspection_id: UUID,
  item_type: 'material' | 'accessory',   // NEW: type discriminator
  
  // For material type:
  shipment_item_id?: UUID,
  sku?: String,
  product_name?: String,
  size?: String,
  color?: String,
  
  // For accessory type:
  accessory_id?: UUID,
  accessory_name?: String,
  accessory_code?: String,
  unit?: String,
  
  // Common fields:
  ordered_qty: Number,
  received_qty: Number,
  missing_qty: Number,
  condition_notes?: String,
  created_at: DateTime
}
```

#### 10. material_requests (ENHANCED di v8.0 - Auto-creation)
```javascript
{
  id: UUID,
  request_number: String,       // REQ-ADD-X-{po_number} or REQ-ACC-X-{po_number}
  request_type: 'ADDITIONAL' | 'REPLACEMENT',
  category?: 'accessories',     // NEW: untuk accessory requests
  vendor_id: UUID,
  vendor_name: String,
  original_shipment_id: UUID,   // Shipment yang memicu request
  original_shipment_number: String,
  po_id: UUID,
  po_number: String,
  reason: String,
  vendor_notes?: String,
  total_requested_qty: Number,
  items: [                      // Array of requested items
    {
      accessory_name?: String,
      accessory_code?: String,
      product_name?: String,
      sku?: String,
      requested_qty: Number,
      unit: String
    }
  ],
  status: 'Pending' | 'Approved' | 'Rejected',
  admin_notes?: String,
  created_by: String,
  created_at: DateTime,
  updated_at: DateTime
}
```

**Auto-creation Logic (v8.0):**
Saat vendor melakukan material inspection dan ada `accessory_items` dengan `missing_qty > 0`, sistem secara otomatis membuat material request dengan:
- `request_type: 'ADDITIONAL'`
- `category: 'accessories'`
- `reason: "Aksesoris kurang saat inspeksi: {detail}"`
- `status: 'Pending'`

#### 11. products (ENHANCED di v8.0 - Photo Upload)
```javascript
{
  id: UUID,
  product_code: String,
  product_name: String,
  category: String,
  cmt_price: Number,
  selling_price: Number,
  photo_url: String,            // NEW: base64 data URL atau URL eksternal
  status: 'active' | 'inactive',
  created_at: DateTime,
  updated_at: DateTime
}
```

#### 12. buyer_shipments
```javascript
{
  id: UUID,
  shipment_number: String,      // SJ-BYR-{po_number} (v8.0)
  po_id: UUID,
  po_number: String,
  buyer_id: UUID,
  buyer_name: String,
  shipment_date: DateTime,
  total_qty: Number,
  status: 'Pending' | 'Sent' | 'Received',
  notes?: String,
  created_at: DateTime,
  updated_at: DateTime
}
```

#### 13. buyer_shipment_dispatches (BARU di v8.0)
```javascript
{
  id: UUID,
  shipment_id: UUID,
  dispatch_number: String,      // Dispatch 1, Dispatch 2, etc.
  dispatch_date: DateTime,
  courier?: String,
  tracking_number?: String,
  notes?: String,
  created_at: DateTime
}
```

#### 14. buyer_shipment_dispatch_items (BARU di v8.0)
```javascript
{
  id: UUID,
  dispatch_id: UUID,
  shipment_id: UUID,
  po_item_id: UUID,
  product_name: String,
  sku: String,
  size: String,
  color: String,
  serial_number?: String,
  qty_shipped: Number,
  created_at: DateTime
}
```

### Relasi Antar Collection

```
production_pos (1) ─→ (N) po_items
                  └─→ (N) po_accessories
                  └─→ (N) vendor_shipments
                  └─→ (N) buyer_shipments

vendor_shipments (1) ─→ (N) vendor_shipment_items
                     └─→ (1) vendor_material_inspections
                     └─→ (N) material_requests (auto-created)

vendor_material_inspections (1) ─→ (N) vendor_material_inspection_items

buyer_shipments (1) ─→ (N) buyer_shipment_dispatches
                   └─→ (N) buyer_shipment_items

buyer_shipment_dispatches (1) ─→ (N) buyer_shipment_dispatch_items

products (1) ─→ (N) product_variants
         └─→ (N) po_items (via product_id)
```

---

## 🔌 API ENDPOINTS

### Autentikasi

#### POST /api/auth/login
Login user dan mendapatkan JWT token.

**Request:**
```json
{
  "email": "admin@garment.com",
  "password": "Admin@123"
}
```

**Response:**
```json
{
  "token": "eyJhbGc...",
  "user": {
    "id": "uuid",
    "email": "admin@garment.com",
    "name": "Admin",
    "role": "superadmin"
  }
}
```

#### POST /api/auth/register
Register user baru (hanya superadmin).

---

### Production PO

#### GET /api/production-pos
List semua PO dengan accessories count.

**Query Params:**
- `vendor_id` (optional)
- `status` (optional)
- `search` (optional)

**Response:**
```json
[
  {
    "id": "uuid",
    "po_number": "PO-20260414-0001",
    "customer_name": "PT ABC",
    "vendor_name": "Garment XYZ",
    "total_qty": 1000,
    "status": "Active",
    "po_accessories_count": 5,    // NEW in v8.0
    "created_at": "2026-04-14T10:00:00+00:00"
  }
]
```

#### GET /api/production-pos/{po_id}
Detail PO dengan items, accessories, dan variants.

**Response:**
```json
{
  "id": "uuid",
  "po_number": "PO-20260414-0001",
  "items": [...],
  "po_accessories": [            // NEW in v8.0
    {
      "id": "uuid",
      "accessory_name": "Kancing Plastik",
      "accessory_code": "ACC-001",
      "qty_needed": 5000,
      "unit": "pcs"
    }
  ],
  "variants": [...]
}
```

#### POST /api/production-pos
Create PO baru.

#### PUT /api/production-pos/{po_id}
Update PO.

#### DELETE /api/production-pos/{po_id}
Delete PO (hanya superadmin).

---

### PO Accessories (BARU di v8.0)

#### GET /api/po-accessories?po_id={po_id}
List accessories untuk PO tertentu.

#### POST /api/po-accessories
Tambah accessory ke PO.

**Request:**
```json
{
  "po_id": "uuid",
  "accessory_id": "uuid",
  "qty_needed": 5000,
  "notes": "Untuk semua varian"
}
```

#### DELETE /api/po-accessories/{acc_id}
Hapus accessory dari PO.

---

### Products (ENHANCED di v8.0)

#### POST /api/products/{pid}/photo
Upload photo untuk product (max 5MB).

**Request:**
- `Content-Type: multipart/form-data`
- `file`: Image file (jpg, jpeg, png, webp, gif)

**Response:**
```json
{
  "success": true,
  "photo_url": "data:image/jpeg;base64,/9j/4AAQSkZJ..."
}
```

**Notes:**
- Photo disimpan sebagai base64 data URL di field `photo_url`
- Max file size: 5MB
- Supported formats: jpg, jpeg, png, webp, gif

---

### Vendor Shipments (ENHANCED di v8.0)

#### GET /api/vendor-shipments
List semua vendor shipments dengan accessories count.

**Response:**
```json
[
  {
    "id": "uuid",
    "shipment_number": "SHP-VENDOR-0001",
    "vendor_name": "Garment XYZ",
    "po_number": "PO-20260414-0001",
    "total_qty": 500,
    "status": "Sent",
    "po_accessories_count": 3,    // NEW: aggregated from linked PO
    "created_at": "2026-04-14T10:00:00+00:00"
  }
]
```

#### GET /api/vendor-shipments/{sid}
Detail shipment dengan items dan PO accessories.

**Response:**
```json
{
  "id": "uuid",
  "shipment_number": "SHP-VENDOR-0001",
  "items": [...],
  "po_accessories": [             // NEW: aggregated dari PO
    {
      "id": "uuid",
      "accessory_name": "Kancing Plastik",
      "qty_needed": 5000,
      "unit": "pcs"
    }
  ]
}
```

---

### Vendor Material Inspections (ENHANCED di v8.0)

#### POST /api/vendor-material-inspections
Create inspection dengan material items DAN accessory items.

**Request:**
```json
{
  "shipment_id": "uuid",
  "inspection_date": "2026-04-14",
  "items": [                      // Material items
    {
      "shipment_item_id": "uuid",
      "sku": "SKU-001",
      "product_name": "T-Shirt Basic",
      "ordered_qty": 100,
      "received_qty": 95,
      "missing_qty": 5,
      "condition_notes": "5 pcs cacat jahitan"
    }
  ],
  "accessory_items": [            // NEW: Accessory items
    {
      "accessory_id": "uuid",
      "accessory_name": "Kancing Plastik",
      "accessory_code": "ACC-001",
      "unit": "pcs",
      "ordered_qty": 5000,
      "received_qty": 4800,
      "missing_qty": 200,
      "condition_notes": "Kurang 200 pcs"
    }
  ],
  "overall_notes": "Pengiriman cukup baik"
}
```

**Response:**
```json
{
  "id": "uuid",
  "shipment_id": "uuid",
  "total_received": 95,
  "total_missing": 5,
  "total_acc_received": 4800,     // NEW
  "total_acc_missing": 200,       // NEW
  "items": [...],
  "accessory_items": [...]        // NEW
}
```

**Auto-creation Material Request:**
Jika `accessory_items` ada yang `missing_qty > 0`, sistem akan otomatis membuat entry di collection `material_requests` dengan:
- `request_type: 'ADDITIONAL'`
- `category: 'accessories'`
- `status: 'Pending'`

---

### Material Requests (ENHANCED di v8.0)

#### GET /api/material-requests
List material requests (termasuk auto-created accessory requests).

**Query Params:**
- `vendor_id` (optional)
- `status` (optional)
- `category` (optional) - filter by 'accessories'

#### POST /api/material-requests
Manual create material request.

**Request:**
```json
{
  "vendor_id": "uuid",
  "original_shipment_id": "uuid",
  "request_type": "ADDITIONAL",
  "po_id": "uuid",
  "reason": "Kekurangan material",
  "items": [
    {
      "product_name": "T-Shirt Basic",
      "sku": "SKU-001",
      "requested_qty": 50,
      "unit": "pcs"
    }
  ]
}
```

---

### Buyer Shipments (ENHANCED di v8.0)

#### GET /api/buyer-shipments/{sid}
Detail buyer shipment dengan dispatches.

**Response:**
```json
{
  "id": "uuid",
  "shipment_number": "SJ-BYR-PO-20260414-0001",
  "po_number": "PO-20260414-0001",
  "buyer_name": "PT ABC",
  "total_qty": 1000,
  "dispatches": [                 // NEW: dispatch breakdown
    {
      "id": "uuid",
      "dispatch_number": "Dispatch 1",
      "dispatch_date": "2026-04-15T10:00:00+00:00",
      "qty_shipped": 500,
      "items": [...]
    }
  ],
  "items": [...]
}
```

#### GET /api/export-pdf?type=buyer-dispatch&id={dispatch_id}
**NEW in v8.0:** Export PDF untuk single dispatch.

**Response:** PDF file download

---

### Dashboard Analytics (BARU di v8.0)

#### GET /api/dashboard/analytics
Advanced analytics dengan date range filter.

**Query Params:**
- `from` - Start date (YYYY-MM-DD)
- `to` - End date (YYYY-MM-DD)

**Response:**
```json
{
  "weekly_throughput": [
    {
      "week": "2026-W15",
      "pos_created": 5,
      "jobs_completed": 3,
      "shipments_sent": 8
    }
  ],
  "deadline_distribution": {
    "overdue": 2,
    "this_week": 5,
    "this_month": 10,
    "later": 15
  },
  "shipment_status_breakdown": {
    "Sent": 10,
    "In Transit": 5,
    "Received": 20,
    "Inspected": 15
  },
  "vendor_lead_time": [
    {
      "vendor_name": "Garment XYZ",
      "avg_days": 7.5
    }
  ],
  "missing_rate_per_vendor": [
    {
      "vendor_name": "Garment XYZ",
      "total_inspected": 1000,
      "total_missing": 50,
      "missing_rate_pct": 5.0
    }
  ],
  "product_completion_rates": [
    {
      "product_name": "T-Shirt Basic",
      "total_ordered": 1000,
      "total_produced": 950,
      "completion_pct": 95.0
    }
  ]
}
```

---

### Serial Tracking (BARU di v8.0)

#### GET /api/serial-list
List serial numbers dengan status dan search.

**Query Params:**
- `status` - 'ongoing' | 'completed' | 'pending' | 'all' (default: 'all')
- `search` - Search by serial number, PO number, product name

**Response:**
```json
[
  {
    "serial_number": "SN-001",
    "po_number": "PO-20260414-0001",
    "product_name": "T-Shirt Basic",
    "vendor_name": "Garment XYZ",
    "total_qty": 100,
    "produced_qty": 80,
    "status": "ongoing",
    "timeline": [
      {
        "stage": "PO Created",
        "date": "2026-04-01T10:00:00+00:00",
        "details": "PO dibuat oleh Admin"
      },
      {
        "stage": "Material Shipped",
        "date": "2026-04-05T10:00:00+00:00",
        "details": "Shipment SHP-VENDOR-0001"
      }
    ]
  }
]
```

#### GET /api/serial-trace/{serial_number}
Full trace timeline untuk serial number tertentu.

---

### PDF Export Endpoints

#### GET /api/export-pdf
Multi-purpose PDF export endpoint.

**Query Params:**
- `type` - 'production-po' | 'vendor-shipment' | 'buyer-shipment' | 'buyer-dispatch' | 'vendor-inspection' | 'invoice' | 'production-job' | 'material-request'
- `id` - Entity ID to export

**Examples:**
```
GET /api/export-pdf?type=production-po&id={po_id}
GET /api/export-pdf?type=buyer-dispatch&id={dispatch_id}    // NEW in v8.0
GET /api/export-pdf?type=vendor-inspection&id={inspection_id}  // ENHANCED: includes accessories
```

---

## ✨ FITUR-FITUR UTAMA

### 1. PO Accessories Flow (v8.0)
**Problem Solved:** Aksesoris yang didefinisikan di PO tidak terlihat di vendor shipment flow.

**Solution:**
- Collection `po_accessories` untuk menyimpan aksesoris per PO
- Endpoint GET PO include `po_accessories` array
- Endpoint GET Vendor Shipment include `po_accessories` aggregated dari linked PO
- Frontend menampilkan aksesoris di:
  - PO detail modal
  - Vendor shipment creation form
  - Vendor shipment detail modal
  - Vendor portal shipment cards

**User Journey:**
1. Admin membuat PO dan menambahkan aksesoris (Kancing, Label, dll)
2. Admin membuat Vendor Shipment linked ke PO → Aksesoris otomatis muncul
3. Vendor melihat shipment di portal → Aksesoris terlihat
4. Vendor melakukan inspeksi material → Bisa inspect aksesoris juga

---

### 2. RBAC Custom Roles (v8.0)
**Problem Solved:** User dengan custom role tidak bisa create PO/Shipment karena frontend hardcode check `isSuperAdmin`.

**Solution Backend:**
- `require_auth` function di-refactor jadi `async def` untuk load permissions dari DB
- `user['_permissions']` array berisi permission keys untuk role tersebut
- `check_role` function updated untuk support custom roles

**Solution Frontend:**
- Replace hardcoded `isSuperAdmin` checks dengan `hasPerm(userPermissions, 'permission.key')`
- `App.js` pass `userPermissions` as props ke child components
- Modules (ProductionPOModule, VendorShipmentModule, BuyerShipmentModule) gunakan `hasPerm` utility

**Permission Model:**
```javascript
// Example permission keys:
'production_po.create'
'production_po.read'
'production_po.update'
'production_po.delete'
'vendor_shipment.create'
// ... dst
```

**User Journey:**
1. Superadmin membuat custom role "Production Manager" di Role Management
2. Assign permissions: `production_po.*`, `vendor_shipment.*`
3. Superadmin create user dan assign ke role "Production Manager"
4. User login → Tombol "Buat PO" dan "Buat Shipment" terlihat sesuai permissions

---

### 3. Material & Accessories Inspection (v8.0)
**Problem Solved:** Vendor hanya bisa inspect material, tidak bisa inspect aksesoris.

**Solution:**
- Inspection items punya field `item_type: 'material' | 'accessory'`
- POST endpoint accept 2 arrays: `items[]` (material) dan `accessory_items[]`
- Inspection header track: `total_received`, `total_missing`, `total_acc_received`, `total_acc_missing`
- PDF export include accessories section

**User Journey:**
1. Vendor terima shipment material + aksesoris
2. Vendor buka portal → Inspeksi Material
3. Form inspeksi ada 2 section:
   - Material Items (produk garmen)
   - Accessory Items (kancing, label, dll)
4. Vendor input qty received/missing untuk masing-masing
5. Submit inspection → Backend simpan dengan item_type berbeda
6. Admin bisa lihat hasil inspeksi dengan breakdown material vs aksesoris

---

### 4. Auto-create Material Request untuk Missing Accessories (v8.0)
**Problem Solved:** Saat inspeksi, jika aksesoris kurang, harus manual create material request.

**Solution:**
- Di endpoint POST `/api/vendor-material-inspections`, setelah save inspection items
- Check jika ada `accessory_items` dengan `missing_qty > 0`
- Otomatis create entry di `material_requests` collection dengan:
  - `request_type: 'ADDITIONAL'`
  - `category: 'accessories'`
  - `reason: "Aksesoris kurang saat inspeksi: {details}"`
  - `items: [{accessory_name, requested_qty, unit}]`
  - `status: 'Pending'`

**User Journey:**
1. Vendor inspect shipment, input missing accessories (misal: Kancing kurang 200 pcs)
2. Submit inspection
3. Backend auto-create Material Request "REQ-ACC-1-PO-xxx" dengan status Pending
4. Admin bisa review di module Material Request → Approve/Reject

---

### 5. Product Photo Upload (v8.0)
**Problem Solved:** Tidak ada visualisasi produk di sistem.

**Solution:**
- Field `photo_url` di collection `products` (initialized as empty string)
- Endpoint `POST /api/products/{pid}/photo` untuk upload
- Photo disimpan sebagai base64 data URL (max 5MB)
- Frontend ProductsModule menampilkan:
  - Photo column di table
  - Upload button di expanded row
  - Large preview image

**Future Enhancement:**
- Backend enrichment menambahkan `photo_url` ke PO items dan shipment items
- Thumbnails muncul di semua list view

**User Journey:**
1. Admin buka Products module
2. Expand product row → Click camera icon
3. Upload photo (jpg/png/webp)
4. Photo tersimpan dan langsung terlihat di table

---

### 6. Dashboard Analytics dengan Date Filter (v8.0)
**Problem Solved:** Dashboard hanya menampilkan metrics all-time, tidak bisa filter by date range.

**Solution:**
- Endpoint baru: `GET /api/dashboard/analytics?from=YYYY-MM-DD&to=YYYY-MM-DD`
- Return 6 kategori analytics:
  1. **Weekly Throughput** - PO created, jobs completed, shipments per week
  2. **Deadline Distribution** - Overdue, this week, this month, later
  3. **Shipment Status Breakdown** - Pie chart data
  4. **Vendor Lead Time** - Average days per vendor
  5. **Missing Rate per Vendor** - Percentage missing items
  6. **Product Completion Rates** - Percentage produced vs ordered

**Frontend:**
- Modern KPI grid (3 rows)
- Date range filter inputs
- Drilldown modals untuk detail
- Recharts untuk visualizations (Bar, Pie, Line)

**User Journey:**
1. Admin buka Dashboard
2. Set date range: 01 Apr 2026 - 14 Apr 2026
3. Click "Terapkan Filter"
4. Dashboard refresh dengan data filtered
5. Click KPI card untuk drilldown detail

---

### 7. Serial Tracking List Module (v8.0)
**Problem Solved:** Susah tracking ongoing serials, harus trace satu-satu.

**Solution:**
- Endpoint `GET /api/serial-list` dengan filter status & search
- Frontend SerialTrackingModule dengan 2 tabs:
  1. **Daftar Serial** - List view dengan status cards, expandable rows
  2. **Trace Timeline** - Full timeline untuk single serial

**Features:**
- Status filter: Ongoing, Completed, Pending, All
- Search by serial number, PO number, product name
- Expandable rows dengan mini timeline
- Progress bar per serial

**User Journey:**
1. Admin buka Serial Tracking module
2. Filter "Ongoing Serials"
3. Lihat list 50 serials yang sedang berjalan
4. Expand serial "SN-001" → Lihat mini timeline
5. Switch tab ke "Trace Timeline"
6. Input serial number → Lihat full detailed timeline

---

### 8. Per-Dispatch PDF Export (v8.0)
**Problem Solved:** Buyer shipment PDF selalu export semua dispatches, tidak bisa per-dispatch.

**Solution:**
- Setiap dispatch di Buyer Shipment detail punya PDF export button
- Endpoint: `GET /api/export-pdf?type=buyer-dispatch&id={dispatch_id}`
- PDF hanya include items dari dispatch tersebut

**Format Buyer Shipment Number:**
- Sebelumnya: `SJ-BYR-XXXX`
- Sekarang: `SJ-BYR-{po_number}` (lebih deskriptif)

**User Journey:**
1. Admin buka Buyer Shipment detail "SJ-BYR-PO-20260414-0001"
2. Lihat 3 dispatches: Dispatch 1, Dispatch 2, Dispatch 3
3. Click PDF button di Dispatch 1
4. Download PDF hanya untuk Dispatch 1 (tidak include Dispatch 2 & 3)

---

### 9. Vendor Inspection PDF Export (v8.0)
**Problem Solved:** Vendor tidak bisa export PDF hasil inspeksi material.

**Solution:**
- Endpoint: `GET /api/export-pdf?type=vendor-inspection&id={inspection_id}`
- PDF include:
  - Header: PO number, Invoice number, Vendor name, Inspection date
  - Material Items table: Product, Size, Color, SKU, Qty Sent/Received/Missing
  - Accessories table: Accessory name/code, Unit, Qty Sent/Received/Missing
  - Footer: Overall notes, Submitted by

**Authentication:**
- Frontend menggunakan authenticated fetch (include Authorization header)
- Sebelumnya: unauthorized fetch menyebabkan 401 error

**User Journey:**
1. Vendor login ke portal
2. Buka tab "Inspeksi Material"
3. Click detail inspection "INS-001"
4. Click button "Export PDF"
5. Download PDF dengan detail inspection materials + accessories

---

## 🔐 AUTENTIKASI & RBAC

### JWT Authentication

**Token Generation:**
```python
import jwt
from datetime import datetime, timedelta

payload = {
    'user_id': user['id'],
    'email': user['email'],
    'role': user['role'],
    'exp': datetime.utcnow() + timedelta(hours=24)
}
token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
```

**Token Validation:**
```python
from auth import require_auth

@api.get("/protected-endpoint")
async def protected(request: Request):
    user = await require_auth(request)  # Raises 401 if invalid
    # user dict contains: id, email, name, role, vendor_id, buyer_id, _permissions
```

### Permission Checking

**Backend:**
```python
from auth import require_auth, check_role

@api.post("/production-pos")
async def create_po(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    # Permission 'production_po.create' required
```

**Frontend:**
```javascript
// App.js passes userPermissions to children
const hasPerm = (permissions, key) => {
  return permissions?.some(p => p === key || p === key.split('.')[0] + '.*');
};

// In component:
const canCreate = hasPerm(userPermissions, 'production_po.create');

{canCreate && (
  <button onClick={openCreateForm}>Buat PO</button>
)}
```

### Role Hierarchy
1. **superadmin** - Full access, tidak dibatasi permissions
2. **admin** - Access via custom role permissions
3. **vendor** - Limited to vendor portal + vendor-specific data
4. **buyer** - Limited to buyer portal + buyer-specific data

### Custom Roles
Admin dapat membuat custom role di Role Management module:
- Define role name & description
- Assign granular permissions (CRUD per module)
- Assign users to custom role

---

## 🧪 TESTING & QUALITY ASSURANCE

### Testing Structure

#### 1. POC Test Scripts (Python)
Located in `/app/tests/`

**poc_po_accessories_flow.py:**
- Tests PO accessories CRUD
- Tests vendor shipment accessories aggregation
- Verifies PO → Shipment → Accessories data flow
- **Result:** 23/23 tests passed

**poc_rbac_custom_role.py:**
- Tests custom role creation
- Tests user assignment to custom role
- Tests permission loading and enforcement
- Verifies user can create PO/shipment with custom role

#### 2. Testing Agent Reports
Located in `/app/test_reports/`

**iteration_1.json:**
- Focus: PO accessories flow
- Backend: 100% (13/13 passed)
- Frontend: 100% (8/8 verified)

**iteration_2.json:**
- Focus: RBAC, Dashboard, Product Photo, Serial Tracking
- Backend: 93.3% (14/15 passed)
- Frontend: 70% (core features verified, session timeout issues)
- Issues found: vendor_id inference flaky → Fixed

**iteration_3.json:**
- Focus: Comprehensive testing all v8.0 features
- Backend: 86.7% (13/15 passed)
- Frontend: 95% (all major features verified)
- Issues found: 
  - Product photo_url field missing → Fixed
  - Material request auto-creation validation → Fixed

### Manual Testing Checklist

**Authentication:**
- [ ] Login as superadmin
- [ ] Login as custom role user
- [ ] Login as vendor
- [ ] Login as buyer
- [ ] Verify JWT token expiration

**RBAC:**
- [ ] Custom role can see permitted modules
- [ ] Custom role create buttons visible when has permission
- [ ] Unauthorized access returns 403

**PO Flow:**
- [ ] Create PO with accessories
- [ ] View PO detail shows accessories
- [ ] Create vendor shipment from PO shows accessories
- [ ] Vendor portal shows shipment accessories

**Inspection Flow:**
- [ ] Vendor can inspect materials
- [ ] Vendor can inspect accessories
- [ ] Missing accessories auto-create material request
- [ ] Inspection PDF export includes accessories

**Product Photo:**
- [ ] Upload photo to product
- [ ] Photo appears in product list
- [ ] Photo saved as base64 data URL

**Dashboard:**
- [ ] Date filter affects analytics data
- [ ] KPI cards clickable
- [ ] Charts render correctly

**Serial Tracking:**
- [ ] List serials with status filter
- [ ] Search serials
- [ ] Expand row shows mini timeline
- [ ] Trace timeline shows full history

**Buyer Shipment:**
- [ ] Shipment number format SJ-BYR-{po_number}
- [ ] Per-dispatch PDF export works
- [ ] PDF only includes selected dispatch items

### Known Issues & Limitations

**Session Timeout:**
- JWT expires after 24 hours
- Long testing sessions may encounter logout
- **Workaround:** Implement refresh token or extend TTL

**Photo Storage:**
- Currently stores as base64 in MongoDB
- Large photos increase document size
- **Future:** Migrate to object storage (EMERGENT_LLM_KEY)

**Monolithic server.py:**
- Single file ~4928 lines
- **Recommendation:** Split into domain routers (`/routes/po.py`, `/routes/shipment.py`, etc.)

---

## 🚀 DEPLOYMENT & ENVIRONMENT

### Development Environment

**Services:**
- Frontend: `yarn start` on port 3000
- Backend: `uvicorn server:app --reload --host 0.0.0.0 --port 8001`
- MongoDB: Managed service (connected via MONGO_URL)

**Process Management:**
```bash
supervisorctl status
supervisorctl restart backend
supervisorctl restart frontend
supervisorctl restart all
```

**Logs:**
```bash
tail -f /var/log/supervisor/backend.err.log
tail -f /var/log/supervisor/frontend.err.log
```

### Environment Configuration

**Backend `.env`:**
```bash
MONGO_URL=mongodb+srv://...
SECRET_KEY=your-secret-key-here
EMERGENT_LLM_KEY=optional-for-storage
```

**Frontend `.env`:**
```bash
REACT_APP_BACKEND_URL=https://erp-production-track.preview.emergentagent.com
```

### Database Indexes

**Recommended Indexes (created at startup in server.py):**
```python
# users
await db.users.create_index('email', unique=True)
await db.users.create_index('role')

# production_pos
await db.production_pos.create_index('po_number', unique=True)
await db.production_pos.create_index('vendor_id')
await db.production_pos.create_index('status')

# vendor_shipments
await db.vendor_shipments.create_index('shipment_number', unique=True)
await db.vendor_shipments.create_index('vendor_id')
await db.vendor_shipments.create_index('po_id')

# vendor_material_inspections
await db.vendor_material_inspections.create_index('shipment_id', unique=True)

# po_items
await db.po_items.create_index('po_id')
await db.po_items.create_index('serial_number')

# po_accessories
await db.po_accessories.create_index('po_id')
```

### Production Deployment Checklist

- [ ] Set strong SECRET_KEY
- [ ] Configure MongoDB backup strategy
- [ ] Enable HTTPS/SSL
- [ ] Set JWT expiration appropriate for use case
- [ ] Implement rate limiting
- [ ] Set up monitoring (CPU, Memory, DB connections)
- [ ] Configure log rotation
- [ ] Enable CORS only for trusted origins
- [ ] Implement proper error handling & logging
- [ ] Set up CI/CD pipeline
- [ ] Document API with OpenAPI/Swagger
- [ ] Perform load testing
- [ ] Set up disaster recovery plan

---

## 📚 APPENDIX

### Tech Debt & Future Improvements

1. **Backend Modularization:**
   - Split `server.py` (~4928 lines) into domain routers
   - Example structure: `/routes/po.py`, `/routes/shipment.py`, `/routes/inspection.py`

2. **Object Storage Migration:**
   - Move product photos from base64 → object storage
   - Use EMERGENT_LLM_KEY for file upload API

3. **Server-side Pagination:**
   - Implement pagination for heavy endpoints (PO list, Shipment list)
   - Return `{data: [], total: N, page: 1, per_page: 50}`

4. **Real-time Updates:**
   - WebSocket for production monitoring updates
   - Notify admin when vendor submits inspection

5. **Excel Import:**
   - Bulk import PO items from Excel file
   - Bulk import products from Excel

6. **Session Management:**
   - Implement refresh token mechanism
   - Extend session on user activity

7. **Full-text Search:**
   - MongoDB text indexes for faster search
   - Elasticsearch integration for advanced search

8. **Audit Trail:**
   - Track all changes with before/after snapshots
   - Who changed what when

9. **Email Notifications:**
   - Email vendor when PO created
   - Email admin when inspection submitted

10. **Mobile Responsiveness:**
    - Optimize UI for tablet and mobile screens
    - Vendor portal mobile app (React Native)

### Version History

**v8.0 (April 2026):**
- ✅ PO Accessories Flow
- ✅ RBAC Custom Roles Frontend Fix
- ✅ Material + Accessories Inspection
- ✅ Auto-create Material Request for Missing Accessories
- ✅ Product Photo Upload
- ✅ Dashboard Analytics with Date Filter
- ✅ Serial Tracking List Module
- ✅ Per-Dispatch PDF Export (Buyer Shipment)
- ✅ Vendor Inspection PDF Export
- ✅ Buyer Shipment Number Format (SJ-BYR-{po_number})
- ✅ Frontend Compile Bug Fixes

**v7.x (March 2026):**
- Production Monitoring
- Work Order Distribution
- Material Request workflow
- Buyer Shipment multi-dispatch
- Activity Log module

**v6.x (February 2026):**
- Initial Buyer Portal
- Invoice Management
- Accounts Payable/Receivable

**v5.x (January 2026):**
- Production Job Management
- Serial Number Tracking
- Defect & Return Management

**v4.x (December 2025):**
- Vendor Portal
- Vendor Material Inspection

**v3.x (November 2025):**
- Vendor Shipment Management
- PDF Export basic

**v2.x (October 2025):**
- Production PO Management
- Product & Variant Master

**v1.x (September 2025):**
- Authentication & Authorization
- User Management
- Role Management (basic)

### Contact & Support

**Development Team:** Emergent AI Platform  
**Documentation Maintained By:** AI Agent Neo (Full-Stack Engineer)  
**Last Updated:** 14 April 2026  
**Version:** 8.0

---

*Dokumen ini adalah living document dan akan diupdate seiring perkembangan sistem.*
