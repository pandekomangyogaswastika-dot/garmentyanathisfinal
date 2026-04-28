from fastapi import FastAPI, APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from database import get_db, client
from auth import (verify_token, require_auth, check_role, hash_password, verify_password,
                  create_token, log_activity, seed_initial_data, serialize_doc, generate_password)
from cascade_delete import cascade_delete_po
import uuid
import os
import logging
from datetime import datetime, timezone, timedelta
from io import BytesIO
import json

app = FastAPI()
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── STARTUP ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await seed_initial_data()
    await create_indexes()
    # Init persistent storage
    try:
        from storage import init_storage
        init_storage()
    except Exception as e:
        logger.warning(f"Storage init: {e}")
    logger.info("Garment ERP API started")

async def create_indexes():
    """Create MongoDB indexes for performance."""
    db = get_db()
    try:
        await db.po_items.create_index("po_id")
        await db.po_items.create_index("id", unique=True)
        await db.vendor_shipment_items.create_index("shipment_id")
        await db.vendor_shipment_items.create_index("po_item_id")
        await db.production_job_items.create_index("job_id")
        await db.production_job_items.create_index("po_item_id")
        await db.production_job_items.create_index("vendor_shipment_item_id")
        await db.production_progress.create_index("job_item_id")
        await db.production_progress.create_index([("job_id", 1), ("job_item_id", 1)])
        await db.buyer_shipment_items.create_index("shipment_id")
        await db.buyer_shipment_items.create_index("po_item_id")
        await db.invoices.create_index("po_id")
        await db.invoices.create_index("invoice_category")
        await db.activity_logs.create_index([("timestamp", -1)])
        await db.production_jobs.create_index("vendor_id")
        await db.production_jobs.create_index("parent_job_id")
        await db.production_jobs.create_index("vendor_shipment_id")
        
        # Production variances (overproduction/underproduction tracking)
        await db.production_variances.create_index("vendor_id")
        await db.production_variances.create_index("job_id")
        await db.production_variances.create_index("po_id")
        await db.production_variances.create_index("variance_type")
        await db.production_variances.create_index("created_at")
        
        await db.vendor_shipments.create_index("vendor_id")
        await db.vendor_shipments.create_index("parent_shipment_id")
        await db.vendor_material_inspections.create_index("shipment_id")
        await db.vendor_material_inspection_items.create_index("inspection_id")
        await db.material_requests.create_index("vendor_id")
        await db.material_defect_reports.create_index("vendor_id")
        await db.buyer_shipments.create_index("po_id")
        await db.buyer_shipments.create_index("vendor_id")
        # Accessory indexes
        await db.accessories.create_index("status")
        await db.accessory_shipments.create_index("po_id")
        await db.accessory_shipment_items.create_index("shipment_id")
        # RBAC indexes
        await db.roles.create_index("name", unique=True)
        await db.permissions.create_index("key", unique=True)
        # Invoice edit approval indexes
        await db.invoice_edit_requests.create_index("invoice_id")
        await db.invoice_edit_requests.create_index("status")
        await db.invoice_edit_requests.create_index("requested_at")
        await db.invoice_change_history.create_index("invoice_id")
        await db.invoice_change_history.create_index("changed_at")
        # ── Phase 10A missing indexes (fill gaps for common query fields) ──
        await db.po_accessories.create_index("po_id")
        await db.production_return_items.create_index("return_id")
        await db.production_return_items.create_index("po_item_id")
        await db.invoice_adjustments.create_index("invoice_id")
        await db.po_items.create_index("serial_number")
        await db.work_orders.create_index("po_id")
        await db.production_progress.create_index("work_order_id")
        await db.material_requests.create_index("request_type")
        await db.material_requests.create_index("status")
        await db.payments.create_index("invoice_id")
        await db.production_pos.create_index("status")
        await db.production_pos.create_index("vendor_id")
        await db.production_pos.create_index([("created_at", -1)])
        await db.invoices.create_index("status")
        await db.invoices.create_index([("created_at", -1)])
        await db.payments.create_index([("created_at", -1)])
        await db.production_returns.create_index("status")
        await db.production_returns.create_index([("created_at", -1)])
        await db.buyer_shipments.create_index([("created_at", -1)])
        await db.vendor_shipments.create_index([("created_at", -1)])
        await db.work_orders.create_index([("created_at", -1)])
        await db.production_jobs.create_index([("created_at", -1)])
        # ── Phase 10E: additional indexes for batch-query patterns ──
        await db.vendor_material_inspection_items.create_index("shipment_item_id")
        await db.buyer_shipment_items.create_index("job_item_id")
        await db.material_defect_reports.create_index("job_item_id")
        await db.material_defect_reports.create_index("po_item_id")
        await db.production_jobs.create_index("id")
        await db.production_returns.create_index("id")
        await db.buyer_shipments.create_index("id")
        await db.vendor_shipments.create_index("id")
        await db.vendor_shipment_items.create_index("id")
        await db.vendor_material_inspections.create_index("id")
        await db.production_pos.create_index("deadline")
        await db.production_pos.create_index([("status", 1), ("deadline", 1)])
        await db.production_progress.create_index("progress_date")
        await db.role_permissions.create_index("role_id")
        await db.accessory_shipments.create_index("vendor_id")
        await db.accessory_shipment_items.create_index("po_id")
        logger.info("MongoDB indexes created")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")

# Valid PO statuses (staged lifecycle)
PO_STATUSES = [
    "Draft", "Confirmed", "Distributed", "In Production", 
    "Production Complete", "Variance Review", "Return Review",
    "Ready to Close", "Closed"
]

@app.on_event("shutdown")
async def shutdown():
    client.close()

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def new_id():
    return str(uuid.uuid4())

def now():
    return datetime.now(timezone.utc)

def parse_date(d):
    if not d: return None
    if isinstance(d, datetime): return d
    try: return datetime.fromisoformat(str(d).replace('Z', '+00:00'))
    except: return None

def to_end_of_day(d):
    if isinstance(d, str):
        d = parse_date(d)
    if d:
        return d.replace(hour=23, minute=59, second=59, microsecond=999999)
    return None

# ─── PAGINATION HELPERS (Phase 10A) ──────────────────────────────────────────
# Backward-compatible pagination:
#   • If the request includes `page` OR `per_page`, the endpoint returns a
#     paginated envelope: {"items": [...], "total": N, "page": P,
#     "per_page": M, "total_pages": T}.
#   • Otherwise, the endpoint returns the legacy array response — but with a
#     safety cap applied to the underlying Mongo query so no request can load
#     unbounded data by accident.
LEGACY_DEFAULT_CAP = 1000   # hard cap when no pagination requested
PAGE_DEFAULT_SIZE = 20
PAGE_MAX_SIZE = 200

def _paginate_params(sp):
    """Parse `page` / `per_page` from query params.

    Returns (page, per_page, skip, wants_paginated)
    where `wants_paginated` is True only when the caller explicitly asked.
    """
    page_raw = sp.get('page')
    per_page_raw = sp.get('per_page')
    wants = page_raw is not None or per_page_raw is not None
    try:
        page = max(1, int(page_raw)) if page_raw is not None else 1
    except Exception:
        page = 1
    try:
        per_page = int(per_page_raw) if per_page_raw is not None else PAGE_DEFAULT_SIZE
    except Exception:
        per_page = PAGE_DEFAULT_SIZE
    per_page = max(1, min(per_page, PAGE_MAX_SIZE))
    skip = (page - 1) * per_page
    return page, per_page, skip, wants

def _paginated_envelope(items, total, page, per_page):
    total_pages = (total + per_page - 1) // per_page if per_page else 1
    return {
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
    }

def _sort_params(sp, default_by='created_at', default_dir='desc', allowed=None):
    """Parse `sort_by` / `sort_dir` query params. Returns list suitable for Mongo .sort().
    `allowed` is an optional whitelist of sortable field names.
    """
    by = sp.get('sort_by') or default_by
    if allowed is not None and by not in allowed:
        by = default_by
    dir_raw = (sp.get('sort_dir') or default_dir).lower()
    direction = 1 if dir_raw == 'asc' else -1
    return [(by, direction)]

async def _run_list_query(cursor_factory, sp, default_sort_by='created_at',
                           default_sort_dir='desc', allowed_sort=None,
                           legacy_cap=LEGACY_DEFAULT_CAP, count_query=None):
    """Generic pagination runner.

    cursor_factory(sort, skip, limit) -> async cursor of docs.
    count_query: callable returning the total count when paginated=True
                 (separate from cursor_factory to avoid extra work legacy-mode).

    Returns (docs, page, per_page, total, wants_paginated).
    In legacy mode, `total` and `wants_paginated` are still returned
    (total being len(docs), which may be capped by legacy_cap).
    """
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, default_sort_by, default_sort_dir, allowed_sort)
    if wants:
        total = await count_query() if count_query else 0
        cursor = cursor_factory(sort=sort, skip=skip, limit=per_page)
        docs = await cursor.to_list(per_page)
        return docs, page, per_page, total, True
    # Legacy mode
    cursor = cursor_factory(sort=sort, skip=0, limit=legacy_cap)
    docs = await cursor.to_list(legacy_cap)
    return docs, 1, len(docs), len(docs), False

async def enrich_with_product_photos(items, db):
    """Attach product photo (if any) to each item dict.

    Looks up `products` by the unique product_ids referenced in `items` and
    adds `product_photo` and `product_photo_url` keys (None when missing).
    Items without a product_id are returned unchanged. Safe on empty input.
    """
    if not items:
        return items
    product_ids = list({it.get('product_id') for it in items if it.get('product_id')})
    if not product_ids:
        return items
    photo_docs = await db.products.find(
        {'id': {'$in': product_ids}},
        {'_id': 0, 'id': 1, 'photo': 1, 'photo_url': 1}
    ).to_list(None)
    photo_map = {d['id']: d for d in photo_docs}
    for it in items:
        pid = it.get('product_id')
        meta = photo_map.get(pid) if pid else None
        if meta:
            if 'photo' in meta and meta.get('photo') is not None:
                it.setdefault('product_photo', meta['photo'])
            if 'photo_url' in meta and meta.get('photo_url') is not None:
                it.setdefault('product_photo_url', meta['photo_url'])
    return items

# ─── AUTH ────────────────────────────────────────────────────────────────────
@api.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    db = get_db()
    email = body.get('email', '')
    password = body.get('password', '')
    u = await db.users.find_one({'email': email})
    if not u or not verify_password(password, u['password']):
        raise HTTPException(401, 'Email atau password salah')
    if u.get('status') != 'active':
        raise HTTPException(403, 'Akun tidak aktif')
    
    # Get user permissions for immediate use (without /auth/me call)
    user_perms = []
    role = u.get('role', '')
    if role == 'superadmin':
        user_perms = ['*']
    elif role == 'vendor':
        user_perms = ['dashboard.view', 'shipment.view', 'jobs.view', 'jobs.create', 'progress.view', 'progress.create']
    elif role == 'buyer':
        user_perms = ['dashboard.view', 'po.view', 'shipment.view']
    else:
        # Check custom role
        if u.get('role_id'):
            role_perms = await db.role_permissions.find({'role_id': u['role_id']}, {'_id': 0}).to_list(None)
            user_perms = [rp.get('permission_key') for rp in role_perms]
        else:
            custom_role = await db.roles.find_one({'name': role})
            if custom_role:
                role_perms = await db.role_permissions.find({'role_id': custom_role['id']}, {'_id': 0}).to_list(None)
                user_perms = [rp.get('permission_key') for rp in role_perms]
    
    token = create_token(u)
    await log_activity(u['id'], u['name'], 'Login', 'Auth', f"User {u['email']} logged in")
    return {'token': token, 'user': {'id': u['id'], 'name': u['name'], 'email': u['email'], 'role': u['role'],
            'vendor_id': u.get('vendor_id'), 'buyer_id': u.get('buyer_id'),
            'customer_name': u.get('customer_name', u.get('buyer_company', '')),
            'permissions': user_perms}}

@api.get("/auth/me")
async def auth_me(request: Request):
    user = await require_auth(request)
    db = get_db()
    u = await db.users.find_one({'id': user['id']}, {'password': 0, '_id': 0})
    # Include user permissions for RBAC
    user_perms = []
    role = u.get('role', '') if u else ''
    
    if role == 'superadmin':
        user_perms = ['*']  # Full access
    elif role == 'vendor':
        user_perms = ['dashboard.view', 'shipment.view', 'jobs.view', 'jobs.create', 'progress.view', 'progress.create']
    elif role == 'buyer':
        user_perms = ['dashboard.view', 'po.view', 'shipment.view']
    else:
        # Check if this is a custom role
        if u.get('role_id'):
            # User has custom role assigned via role_id
            role_perms = await db.role_permissions.find({'role_id': u['role_id']}, {'_id': 0}).to_list(None)
            user_perms = [rp.get('permission_key') for rp in role_perms]
        else:
            # Try to find role by name (legacy)
            custom_role = await db.roles.find_one({'name': role})
            if custom_role:
                role_perms = await db.role_permissions.find({'role_id': custom_role['id']}, {'_id': 0}).to_list(None)
                user_perms = [rp.get('permission_key') for rp in role_perms]
    
    result = serialize_doc(u) if u else {}
    result['permissions'] = user_perms
    return result

# ─── GARMENTS ────────────────────────────────────────────────────────────────
@api.get("/garments")
async def get_garments(request: Request):
    user = await require_auth(request)
    db = get_db()
    query = {}
    sp = request.query_params
    search = sp.get('search')
    status = sp.get('status')
    if search:
        query['$or'] = [{'garment_name': {'$regex': search, '$options': 'i'}}, {'garment_code': {'$regex': search, '$options': 'i'}}]
    if status: query['status'] = status
    if user.get('role') == 'vendor': query['id'] = user.get('vendor_id')
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'garment_name', 'garment_code', 'status'})
    total = await db.garments.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.garments.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.get("/garments/{gid}")
async def get_garment(gid: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.garments.find_one({'id': gid}, {'_id': 0})
    if not doc: raise HTTPException(404, 'Not found')
    return serialize_doc(doc)

@api.post("/garments")
async def create_garment(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    garment_id = new_id()
    code_slug = (body.get('garment_code', garment_id)).lower()
    code_slug = ''.join(c for c in code_slug if c.isalnum())
    vendor_email = f"vendor.{code_slug}@garment.com"
    raw_password = generate_password(10)
    hashed = hash_password(raw_password)
    await db.users.insert_one({
        'id': new_id(), 'name': body.get('garment_name', ''), 'email': vendor_email,
        'password': hashed, 'role': 'vendor', 'vendor_id': garment_id,
        'status': 'active', 'created_at': now(), 'updated_at': now()
    })
    garment = {'id': garment_id, **body, 'status': body.get('status', 'active'),
               'login_email': vendor_email, 'vendor_password_plain': raw_password,
               'created_at': now(), 'updated_at': now()}
    await db.garments.insert_one(garment)
    await log_activity(user['id'], user['name'], 'Create', 'Garments', f"Created garment: {garment.get('garment_name')}")
    result = serialize_doc(garment)
    result['vendor_account'] = {'email': vendor_email, 'password': raw_password}
    return JSONResponse(result, status_code=201)

@api.put("/garments/{gid}")
async def update_garment(gid: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None); body.pop('vendor_account', None)
    await db.garments.update_one({'id': gid}, {'$set': {**body, 'updated_at': now()}})
    if body.get('garment_name'):
        await db.users.update_one({'vendor_id': gid}, {'$set': {'name': body['garment_name'], 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Update', 'Garments', f"Updated garment: {gid}")
    doc = await db.garments.find_one({'id': gid}, {'_id': 0})
    return serialize_doc(doc)

@api.delete("/garments/{gid}")
async def delete_garment(gid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden: Only Superadmin can delete')
    db = get_db()
    doc = await db.garments.find_one({'id': gid})
    if not doc: raise HTTPException(404, 'Not found')
    vendor_pos = await db.production_pos.find({'vendor_id': gid}).to_list(None)
    for po in vendor_pos:
        await cascade_delete_po(po['id'])
    await db.material_requests.delete_many({'vendor_id': gid})
    await db.material_defect_reports.delete_many({'vendor_id': gid})
    await db.users.delete_many({'vendor_id': gid})
    await db.garments.delete_one({'id': gid})
    await log_activity(user['id'], user['name'], 'Delete', 'Garments', f"Cascade deleted garment: {doc.get('garment_name')}")
    return {'success': True, 'deleted_pos': len(vendor_pos)}

# ─── BUYERS (Master Data) ────────────────────────────────────────────────────
@api.get("/buyers")
async def get_buyers(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    search = sp.get('search')
    if search:
        query['$or'] = [{'buyer_name': {'$regex': search, '$options': 'i'}}, {'buyer_code': {'$regex': search, '$options': 'i'}}]
    if sp.get('status'): query['status'] = sp['status']
    # Phase 10A: support both new (page/per_page → envelope) and legacy (page/limit + paginated=true → {data,total,page,limit})
    page_p, per_page, skip_p, wants_new = _paginate_params(sp)
    legacy_paginated = sp.get('paginated') and not wants_new
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'buyer_name', 'buyer_code', 'status'})
    if wants_new or legacy_paginated:
        if legacy_paginated:
            page_p = int(sp.get('page', 1) or 1)
            per_page = int(sp.get('limit', 100) or 100)
            per_page = max(1, min(per_page, PAGE_MAX_SIZE))
            skip_p = (page_p - 1) * per_page
        total = await db.buyers.count_documents(query)
        docs = await db.buyers.find(query, {'_id': 0}).sort(sort).skip(skip_p).limit(per_page).to_list(per_page)
        if wants_new:
            return _paginated_envelope(serialize_doc(docs), total, page_p, per_page)
        # legacy shape kept for callers using paginated=true
        return {'data': serialize_doc(docs), 'total': total, 'page': page_p, 'limit': per_page}
    # No pagination params → legacy array response with safety cap
    docs = await db.buyers.find(query, {'_id': 0}).sort(sort).limit(LEGACY_DEFAULT_CAP).to_list(LEGACY_DEFAULT_CAP)
    return serialize_doc(docs)

@api.get("/buyers/{bid}")
async def get_buyer(bid: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.buyers.find_one({'id': bid}, {'_id': 0})
    if not doc: raise HTTPException(404, 'Not found')
    return serialize_doc(doc)

@api.post("/buyers")
async def create_buyer(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    buyer_id = new_id()
    code_slug = (body.get('buyer_code', buyer_id)).lower()
    code_slug = ''.join(c for c in code_slug if c.isalnum())
    buyer_email = f"buyer.{code_slug}@garment.com"
    raw_password = generate_password(10)
    hashed = hash_password(raw_password)
    # Auto-create buyer portal account
    await db.users.insert_one({
        'id': new_id(), 'name': body.get('buyer_name', ''), 'email': buyer_email,
        'password': hashed, 'role': 'buyer', 'buyer_id': buyer_id,
        'customer_name': body.get('buyer_name', ''),
        'buyer_company': body.get('buyer_name', ''),
        'status': 'active', 'created_at': now(), 'updated_at': now()
    })
    buyer = {
        'id': buyer_id, **body, 'status': body.get('status', 'active'),
        'login_email': buyer_email, 'buyer_password_plain': raw_password,
        'created_at': now(), 'updated_at': now()
    }
    await db.buyers.insert_one(buyer)
    await log_activity(user['id'], user['name'], 'Create', 'Buyers', f"Created buyer: {body.get('buyer_name')}, account: {buyer_email}")
    result = serialize_doc(buyer)
    result['buyer_account'] = {'email': buyer_email, 'password': raw_password}
    return JSONResponse(result, status_code=201)

@api.put("/buyers/{bid}")
async def update_buyer(bid: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None); body.pop('buyer_account', None)
    await db.buyers.update_one({'id': bid}, {'$set': {**body, 'updated_at': now()}})
    if body.get('buyer_name'):
        await db.users.update_one({'buyer_id': bid}, {'$set': {'name': body['buyer_name'], 'customer_name': body['buyer_name'], 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Update', 'Buyers', f"Updated buyer: {bid}")
    return serialize_doc(await db.buyers.find_one({'id': bid}, {'_id': 0}))

@api.delete("/buyers/{bid}")
async def delete_buyer(bid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.buyers.find_one({'id': bid})
    if not doc: raise HTTPException(404, 'Not found')
    await db.users.delete_many({'buyer_id': bid})
    await db.buyers.delete_one({'id': bid})
    await log_activity(user['id'], user['name'], 'Delete', 'Buyers', f"Deleted buyer: {doc.get('buyer_name')}")
    return {'success': True}

# ─── PRODUCTS ────────────────────────────────────────────────────────────────
@api.get("/products")
async def get_products(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    search = sp.get('search')
    if search:
        query['$or'] = [{'product_name': {'$regex': search, '$options': 'i'}}, {'product_code': {'$regex': search, '$options': 'i'}}]
    if sp.get('category'): query['category'] = sp['category']
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'product_name', 'product_code', 'category'})
    total = await db.products.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.products.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.get("/products/{pid}")
async def get_product(pid: str, request: Request):
    await require_auth(request)
    db = get_db()
    p = await db.products.find_one({'id': pid}, {'_id': 0})
    if not p: raise HTTPException(404, 'Not found')
    variants = await db.product_variants.find({'product_id': pid}, {'_id': 0}).sort('created_at', 1).to_list(None)
    result = serialize_doc(p)
    result['variants'] = serialize_doc(variants)
    return result

@api.post("/products")
async def create_product(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    product = {'id': new_id(), **body, 'status': body.get('status', 'active'), 'photo_url': '', 'created_at': now(), 'updated_at': now()}
    await db.products.insert_one(product)
    await log_activity(user['id'], user['name'], 'Create', 'Products', f"Created product: {product.get('product_name')}")
    return JSONResponse(serialize_doc(product), status_code=201)

@api.put("/products/{pid}")
async def update_product(pid: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None)
    await db.products.update_one({'id': pid}, {'$set': {**body, 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Update', 'Products', f"Updated product: {pid}")
    return serialize_doc(await db.products.find_one({'id': pid}, {'_id': 0}))

@api.delete("/products/{pid}")
async def delete_product(pid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.products.find_one({'id': pid})
    if not doc: raise HTTPException(404, 'Not found')
    await db.products.delete_one({'id': pid})
    await db.product_variants.delete_many({'product_id': pid})
    await log_activity(user['id'], user['name'], 'Delete', 'Products', f"Deleted product: {doc.get('product_name')}")
    return {'success': True}

@api.post("/products/{pid}/photo")
async def upload_product_photo(pid: str, request: Request, file: UploadFile = File(...)):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    product = await db.products.find_one({'id': pid})
    if not product: raise HTTPException(404, 'Product not found')
    import base64
    content = await file.read()
    if len(content) > 5 * 1024 * 1024: raise HTTPException(400, 'File terlalu besar (maks 5MB)')
    ext = (file.filename or '').rsplit('.', 1)[-1].lower() if file.filename else 'jpg'
    if ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif'): raise HTTPException(400, 'Format tidak didukung')
    content_type = file.content_type or f'image/{ext}'
    b64 = base64.b64encode(content).decode('utf-8')
    photo_url = f"data:{content_type};base64,{b64}"
    await db.products.update_one({'id': pid}, {'$set': {'photo_url': photo_url, 'updated_at': now()}})
    return {'success': True, 'photo_url': photo_url}

# ─── PRODUCT VARIANTS ────────────────────────────────────────────────────────
@api.get("/product-variants")
async def get_variants(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    pid = sp.get('product_id')
    if pid: query['product_id'] = pid
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'sku': {'$regex': search, '$options': 'i'}},
            {'size': {'$regex': search, '$options': 'i'}},
            {'color': {'$regex': search, '$options': 'i'}},
        ]
    # Pagination (Phase 10A) — default asc by created_at for variants
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'asc',
                        allowed={'created_at', 'sku', 'size', 'color'})
    total = await db.product_variants.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.product_variants.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.get("/product-variants/{vid}")
async def get_variant(vid: str, request: Request):
    await require_auth(request)
    db = get_db()
    v = await db.product_variants.find_one({'id': vid}, {'_id': 0})
    if not v: raise HTTPException(404, 'Not found')
    return serialize_doc(v)

@api.post("/product-variants")
async def create_variant(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    product = await db.products.find_one({'id': body.get('product_id')})
    if not product: raise HTTPException(404, 'Product not found')
    variant = {
        'id': new_id(), 'product_id': body['product_id'],
        'product_code': product.get('product_code', ''), 'product_name': product.get('product_name', ''),
        'size': body.get('size', ''), 'color': body.get('color', ''), 'sku': body.get('sku', ''),
        'status': 'active', 'created_at': now()
    }
    await db.product_variants.insert_one(variant)
    await log_activity(user['id'], user['name'], 'Create', 'Product Variants', f"Added variant SKU: {body.get('sku')}")
    return JSONResponse(serialize_doc(variant), status_code=201)

@api.put("/product-variants/{vid}")
async def update_variant(vid: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None)
    await db.product_variants.update_one({'id': vid}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.product_variants.find_one({'id': vid}, {'_id': 0}))

@api.delete("/product-variants/{vid}")
async def delete_variant(vid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.product_variants.find_one({'id': vid})
    if not doc: raise HTTPException(404, 'Not found')
    await db.product_variants.delete_one({'id': vid})
    await log_activity(user['id'], user['name'], 'Delete', 'Product Variants', f"Deleted variant: {doc.get('sku', vid)}")
    return {'success': True}

# ─── PRODUCTION POs ──────────────────────────────────────────────────────────
@api.get("/production-pos")
async def get_pos(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    search = sp.get('search'); status = sp.get('status'); vendor_id = sp.get('vendor_id')
    if search: query['$or'] = [{'po_number': {'$regex': search, '$options': 'i'}}, {'customer_name': {'$regex': search, '$options': 'i'}}]
    if status: query['status'] = status
    if vendor_id: query['vendor_id'] = vendor_id

    # Paginate the parent PO query (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'po_number', 'customer_name', 'vendor_name',
                                 'status', 'deadline', 'delivery_deadline'})
    total = await db.production_pos.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    cursor = db.production_pos.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit)
    pos = await cursor.to_list(limit)

    # ── Phase 10B: eliminate N+1 by batch-fetching all related rows once ──
    po_ids = [po['id'] for po in pos]
    if po_ids:
        items_all = await db.po_items.find({'po_id': {'$in': po_ids}}, {'_id': 0}).to_list(None)
        accs_all = await db.po_accessories.find({'po_id': {'$in': po_ids}}, {'_id': 0}).to_list(None)
        item_ids = [i['id'] for i in items_all]
        # Aggregate shipment totals per po_item_id in a single query each
        buyer_agg = await db.buyer_shipment_items.aggregate([
            {'$match': {'po_item_id': {'$in': item_ids}}},
            {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_shipped'}}},
        ]).to_list(None) if item_ids else []
        vendor_agg = await db.vendor_shipment_items.aggregate([
            {'$match': {'po_item_id': {'$in': item_ids}}},
            {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_sent'}}},
        ]).to_list(None) if item_ids else []
    else:
        items_all, accs_all, buyer_agg, vendor_agg = [], [], [], []

    # Build maps
    items_by_po = {}
    for it in items_all:
        items_by_po.setdefault(it['po_id'], []).append(it)
    accs_by_po = {}
    for a in accs_all:
        accs_by_po.setdefault(a['po_id'], []).append(a)
    buyer_by_item = {b['_id']: b['qty'] for b in buyer_agg}
    vendor_by_item = {v['_id']: v['qty'] for v in vendor_agg}

    result = []
    for po in pos:
        items = items_by_po.get(po['id'], [])
        po_accessories = accs_by_po.get(po['id'], [])
        serial_numbers = list({i.get('serial_number', '') for i in items if i.get('serial_number')})
        created = po.get('created_at')
        date_str = ''
        if created:
            if isinstance(created, datetime):
                date_str = created.strftime('%d/%m/%Y')
            else:
                date_str = str(created)[:10]
        composite_label = f"{po.get('po_number', '')} | {po.get('vendor_name', '')} | {date_str}"

        total_ordered = sum(i.get('qty', 0) for i in items)
        total_shipped = sum(buyer_by_item.get(i['id'], 0) for i in items)
        total_sent_to_vendor = sum(vendor_by_item.get(i['id'], 0) for i in items)
        # ─── H-1 FIX: clamp remaining at 0 (preserves dashboard semantics),
        # expose over_shipped_qty separately so overproduction shipping is visible.
        remaining_qty_to_ship = max(0, total_ordered - total_shipped)
        over_shipped_qty = max(0, total_shipped - total_ordered)
        # Phase 8.5: remaining qty the vendor still needs to receive (NORMAL shipment capacity)
        remaining_qty_to_vendor = max(0, total_ordered - total_sent_to_vendor)

        result.append({**serialize_doc(po), 'items': serialize_doc(items), 'item_count': len(items),
                       'total_qty': total_ordered,
                       'total_shipped_to_buyer': total_shipped,
                       'remaining_qty_to_ship': remaining_qty_to_ship,
                       'over_shipped_qty': over_shipped_qty,
                       'total_sent_to_vendor': total_sent_to_vendor,
                       'remaining_qty_to_vendor': remaining_qty_to_vendor,
                       'serial_numbers': serial_numbers, 'composite_label': composite_label,
                       'po_accessories': serialize_doc(po_accessories),
                       'po_accessories_count': len(po_accessories)})

    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result

@api.get("/production-pos/{po_id}")
async def get_po(po_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
    if not po: raise HTTPException(404, 'Not found')
    items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    wos = await db.work_orders.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    po_accessories = await db.po_accessories.find({'po_id': po_id}, {'_id': 0}).sort('created_at', 1).to_list(None)
    items = await enrich_with_product_photos(items, db)
    result = serialize_doc(po)
    result['items'] = serialize_doc(items)
    result['distributions'] = serialize_doc(wos)
    result['po_accessories'] = serialize_doc(po_accessories)
    return result

@api.post("/production-pos")
async def create_po(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    if not body.get('po_number'): raise HTTPException(400, 'Nomor PO wajib diisi')
    vendor_name = ''
    if body.get('vendor_id'):
        vendor_doc = await db.garments.find_one({'id': body['vendor_id']})
        vendor_name = vendor_doc.get('garment_name', '') if vendor_doc else ''
    po_id = new_id()
    initial_status = 'Confirmed' if body.get('status') == 'Confirmed' else 'Draft'
    # Resolve buyer name from buyer_id if provided
    customer_name = body.get('customer_name', '')
    buyer_id = body.get('buyer_id')
    if buyer_id:
        buyer_doc = await db.buyers.find_one({'id': buyer_id})
        if buyer_doc:
            customer_name = buyer_doc.get('buyer_name', customer_name)
    po = {
        'id': po_id, 'po_number': body['po_number'], 'customer_name': customer_name,
        'buyer_id': buyer_id,
        'vendor_id': body.get('vendor_id'), 'vendor_name': vendor_name,
        'po_date': parse_date(body.get('po_date')) or now(),
        'deadline': parse_date(body.get('deadline')),
        'delivery_deadline': parse_date(body.get('delivery_deadline')),
        'status': initial_status, 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.production_pos.insert_one(po)
    items_data = body.get('items', [])
    inserted_items = []
    for item in items_data:
        variant = await db.product_variants.find_one({'id': item.get('variant_id')}) if item.get('variant_id') else None
        product = await db.products.find_one({'id': item.get('product_id')}) if item.get('product_id') else None
        po_item = {
            'id': new_id(), 'po_id': po_id, 'po_number': body['po_number'],
            'product_id': item.get('product_id'), 'product_name': (product or {}).get('product_name', ''),
            'variant_id': item.get('variant_id'), 'size': (variant or {}).get('size', item.get('size', '')),
            'color': (variant or {}).get('color', item.get('color', '')),
            'sku': (variant or {}).get('sku', item.get('sku', '')),
            'qty': int(item.get('qty', 0) or 0), 'serial_number': item.get('serial_number', ''),
            'selling_price_snapshot': float(item.get('selling_price_snapshot', 0) or (product or {}).get('selling_price', 0) or 0),
            'cmt_price_snapshot': float(item.get('cmt_price_snapshot', 0) or (product or {}).get('cmt_price', 0) or 0),
            'created_at': now()
        }
        await db.po_items.insert_one(po_item)
        inserted_items.append(po_item)
    await log_activity(user['id'], user['name'], 'Create', 'Production PO', f"Created PO: {po['po_number']} with {len(items_data)} items")
    result = serialize_doc(po)
    result['items'] = serialize_doc(inserted_items)
    return JSONResponse(result, status_code=201)

@api.post("/production-pos/{po_id}/close")
async def close_po(po_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    po = await db.production_pos.find_one({'id': po_id})
    if not po: raise HTTPException(404, 'PO not found')
    await db.production_pos.update_one({'id': po_id}, {'$set': {
        'status': 'Closed', 'close_reason': body.get('close_reason'),
        'close_notes': body.get('close_notes', ''), 'closed_by': user['name'],
        'closed_at': now(), 'updated_at': now()
    }})
    await log_activity(user['id'], user['name'], 'Close PO', 'Production PO', f"Closed PO: {po.get('po_number')}")
    return {'success': True}

@api.put("/production-pos/{po_id}")
async def update_po(po_id: str, request: Request):
    """
    Phase 8.6 — Full PO edit (header + items + po_accessories) with strict guardrails.

    Accepts optional `items` and `po_accessories` in body for delta update:
      - Upsert existing by `id` (update in place)
      - Insert new (item without `id`)
      - Delete items/accessories whose `id` is no longer present in payload,
        but ONLY when no downstream references exist.

    Strict guardrails (confirmed with user):
      - If any vendor_shipment_items or buyer_shipment_items reference a po_item:
          * forbid editing sku / size / color
          * forbid reducing qty below max(already-sent-to-vendor, already-shipped-to-buyer)
          * forbid deleting the item
    """
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    existing = await db.production_pos.find_one({'id': po_id})
    if not existing: raise HTTPException(404, 'PO not found')
    if existing.get('status') == 'Closed' and user.get('role') != 'superadmin':
        raise HTTPException(403, 'PO ini sudah Closed.')
    body = await request.json()
    body.pop('_id', None); body.pop('id', None)

    # Separate items / accessories payloads (optional)
    items_payload = body.pop('items', None)
    acc_payload = body.pop('po_accessories', None)

    # ─── Header update ────────────────────────────────────────────────
    if body.get('deadline'): body['deadline'] = parse_date(body['deadline'])
    if body.get('delivery_deadline'): body['delivery_deadline'] = parse_date(body['delivery_deadline'])
    if body.get('po_date'): body['po_date'] = parse_date(body['po_date'])
    if body.get('vendor_id'):
        vd = await db.garments.find_one({'id': body['vendor_id']})
        body['vendor_name'] = vd.get('garment_name', '') if vd else ''
    # resolve buyer_name from buyer_id (consistent with create_po)
    if body.get('buyer_id'):
        buyer_doc = await db.buyers.find_one({'id': body['buyer_id']})
        if buyer_doc:
            body['customer_name'] = buyer_doc.get('buyer_name', body.get('customer_name', ''))

    new_po_number = body.get('po_number')
    if new_po_number and new_po_number != existing.get('po_number'):
        dup = await db.production_pos.find_one({'po_number': new_po_number, 'id': {'$ne': po_id}})
        if dup: raise HTTPException(400, f'Nomor PO "{new_po_number}" sudah digunakan')

    await db.production_pos.update_one({'id': po_id}, {'$set': {**body, 'updated_at': now()}})

    # ─── Items delta update (with guardrails) ─────────────────────────
    if items_payload is not None:
        existing_items = await db.po_items.find({'po_id': po_id}).to_list(None)
        existing_by_id = {i['id']: i for i in existing_items}
        payload_ids = set()

        async def _shipped_qty_for_item(item_id):
            vsis = await db.vendor_shipment_items.find({'po_item_id': item_id}).to_list(None)
            bsis = await db.buyer_shipment_items.find({'po_item_id': item_id}).to_list(None)
            sent_to_vendor = sum(int(v.get('qty_sent', 0) or 0) for v in vsis)
            shipped_to_buyer = sum(int(b.get('qty_shipped', 0) or 0) for b in bsis)
            return sent_to_vendor, shipped_to_buyer, (len(vsis) > 0 or len(bsis) > 0)

        # 1) upsert / insert from payload
        for raw in items_payload:
            item_id = raw.get('id')
            # resolve product / variant metadata (mirror create_po)
            product = await db.products.find_one({'id': raw.get('product_id')}) if raw.get('product_id') else None
            variant = await db.product_variants.find_one({'id': raw.get('variant_id')}) if raw.get('variant_id') else None
            qty_new = int(raw.get('qty', 0) or 0)
            sku_new = (variant or {}).get('sku', raw.get('sku', ''))
            size_new = (variant or {}).get('size', raw.get('size', ''))
            color_new = (variant or {}).get('color', raw.get('color', ''))

            if item_id and item_id in existing_by_id:
                old = existing_by_id[item_id]
                payload_ids.add(item_id)
                sent_to_vendor, shipped_to_buyer, has_refs = await _shipped_qty_for_item(item_id)
                if has_refs:
                    # block sku/size/color changes
                    if sku_new != old.get('sku', '') or size_new != old.get('size', '') or color_new != old.get('color', ''):
                        raise HTTPException(400, f"Item '{old.get('product_name','')}' sudah memiliki shipment; SKU/Size/Color tidak dapat diubah.")
                    # block qty reduction below max(sent, shipped)
                    floor = max(sent_to_vendor, shipped_to_buyer)
                    if qty_new < floor:
                        raise HTTPException(400, f"Qty item '{old.get('product_name','')}' tidak dapat < {floor} (sudah dikirim/shipped).")
                await db.po_items.update_one({'id': item_id}, {'$set': {
                    'po_id': po_id,
                    'po_number': new_po_number or existing.get('po_number'),
                    'product_id': raw.get('product_id'),
                    'product_name': (product or {}).get('product_name', old.get('product_name', '')),
                    'variant_id': raw.get('variant_id'),
                    'size': size_new, 'color': color_new, 'sku': sku_new,
                    'qty': qty_new,
                    'serial_number': raw.get('serial_number', old.get('serial_number', '')),
                    'selling_price_snapshot': float(raw.get('selling_price_snapshot', 0) or (product or {}).get('selling_price', 0) or 0),
                    'cmt_price_snapshot': float(raw.get('cmt_price_snapshot', 0) or (product or {}).get('cmt_price', 0) or 0),
                    'updated_at': now(),
                }})
            else:
                # insert new po_item
                new_item = {
                    'id': new_id(), 'po_id': po_id,
                    'po_number': new_po_number or existing.get('po_number'),
                    'product_id': raw.get('product_id'),
                    'product_name': (product or {}).get('product_name', ''),
                    'variant_id': raw.get('variant_id'),
                    'size': size_new, 'color': color_new, 'sku': sku_new,
                    'qty': qty_new,
                    'serial_number': raw.get('serial_number', ''),
                    'selling_price_snapshot': float(raw.get('selling_price_snapshot', 0) or (product or {}).get('selling_price', 0) or 0),
                    'cmt_price_snapshot': float(raw.get('cmt_price_snapshot', 0) or (product or {}).get('cmt_price', 0) or 0),
                    'created_at': now(),
                }
                await db.po_items.insert_one(new_item)

        # 2) delete po_items not present in payload (only if no references)
        for existing_id, old in existing_by_id.items():
            if existing_id in payload_ids:
                continue
            _, _, has_refs = await _shipped_qty_for_item(existing_id)
            if has_refs:
                raise HTTPException(400, f"Item '{old.get('product_name','')}' tidak dapat dihapus karena sudah memiliki shipment/returns. Kurangi qty atau biarkan.")
            await db.po_items.delete_one({'id': existing_id})

        # Also propagate new po_number to vendor/buyer shipment items (denormalized)
        if new_po_number and new_po_number != existing.get('po_number'):
            await db.vendor_shipment_items.update_many({'po_id': po_id}, {'$set': {'po_number': new_po_number}})
            await db.buyer_shipment_items.update_many({'po_id': po_id}, {'$set': {'po_number': new_po_number}})
            await db.po_items.update_many({'po_id': po_id}, {'$set': {'po_number': new_po_number}})

    # ─── Accessories delta update ─────────────────────────────────────
    if acc_payload is not None:
        existing_accs = await db.po_accessories.find({'po_id': po_id}).to_list(None)
        existing_acc_by_id = {a['id']: a for a in existing_accs}
        payload_acc_ids = set()
        for raw in acc_payload:
            if not (raw.get('accessory_name') or raw.get('accessory_id')):
                continue
            acc_id = raw.get('id')
            doc_fields = {
                'po_id': po_id,
                'accessory_id': raw.get('accessory_id'),
                'accessory_name': raw.get('accessory_name', ''),
                'accessory_code': raw.get('accessory_code', ''),
                'qty_needed': int(raw.get('qty_needed', 0) or 0),
                'unit': raw.get('unit', 'pcs'),
                'notes': raw.get('notes', ''),
            }
            if acc_id and acc_id in existing_acc_by_id:
                payload_acc_ids.add(acc_id)
                await db.po_accessories.update_one({'id': acc_id}, {'$set': {**doc_fields, 'updated_at': now()}})
            else:
                await db.po_accessories.insert_one({**doc_fields, 'id': new_id(), 'created_at': now()})
        # delete accessories dropped from payload (accessory records are safe to delete)
        for existing_id in existing_acc_by_id.keys():
            if existing_id not in payload_acc_ids:
                await db.po_accessories.delete_one({'id': existing_id})

    await log_activity(user['id'], user['name'], 'Update', 'Production PO', f"Updated PO: {existing.get('po_number')}")
    return serialize_doc(await db.production_pos.find_one({'id': po_id}, {'_id': 0}))

@api.delete("/production-pos/{po_id}")
async def delete_po(po_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.production_pos.find_one({'id': po_id})
    if not doc: raise HTTPException(404, 'Not found')
    await cascade_delete_po(po_id)
    await log_activity(user['id'], user['name'], 'Delete', 'Production PO', f"Cascade deleted PO: {doc.get('po_number')}")
    return {'success': True}

# ─── PO ITEMS ────────────────────────────────────────────────────────────────
@api.get("/po-items")
async def get_po_items(request: Request):
    await require_auth(request)
    db = get_db()
    query = {}
    po_id = request.query_params.get('po_id')
    if po_id: query['po_id'] = po_id
    items = await db.po_items.find(query, {'_id': 0}).sort('created_at', 1).to_list(None)
    # ── 10B-rem: batch-fetch all vendor shipment items in 1 query ──
    item_ids = [it['id'] for it in items]
    all_vsis = await db.vendor_shipment_items.find({'po_item_id': {'$in': item_ids}}).to_list(None) if item_ids else []
    vsi_map: dict = {}
    for vsi in all_vsis:
        vsi_map.setdefault(vsi.get('po_item_id'), []).append(vsi)
    # Phase 8.5: enrich each po_item with total_sent_to_vendor & remaining_qty_to_vendor
    # so the Vendor Shipment UI can cap qty and hide fully-sent items.
    enriched = []
    for item in items:
        total_sent = sum(v.get('qty_sent', 0) or 0 for v in vsi_map.get(item['id'], []))
        ordered = int(item.get('qty', 0) or 0)
        remaining = max(0, ordered - total_sent)
        enriched.append({**serialize_doc(item),
                         'total_sent_to_vendor': total_sent,
                         'remaining_qty_to_vendor': remaining})
    return enriched

@api.get("/po-items-produced")
async def get_po_items_produced(request: Request):
    await require_auth(request)
    db = get_db()
    po_id = request.query_params.get('po_id')
    if not po_id: raise HTTPException(400, 'po_id wajib diisi')
    po_items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).sort('created_at', 1).to_list(None)
    if not po_items: return []
    po_item_ids = [it['id'] for it in po_items]

    # ── 10B-rem: batch everything for this PO in ~6 queries instead of N×M×K ──
    # 1. All parent job_items for these po_items
    all_ji = await db.production_job_items.find({'po_item_id': {'$in': po_item_ids}}).to_list(None)
    ji_by_poitem: dict = {}
    for ji in all_ji:
        ji_by_poitem.setdefault(ji.get('po_item_id'), []).append(ji)
    # 2. Batch-fetch parent jobs
    parent_job_ids = list({ji.get('job_id') for ji in all_ji if ji.get('job_id')})
    # 3. Batch-fetch child jobs for all parent jobs at once
    child_jobs = await db.production_jobs.find({'parent_job_id': {'$in': parent_job_ids}}).to_list(None) if parent_job_ids else []
    child_job_ids = [cj['id'] for cj in child_jobs]
    # 4. Batch-fetch child job items
    child_ji_all = await db.production_job_items.find({'job_id': {'$in': child_job_ids}}).to_list(None) if child_job_ids else []
    # Build map: po_item_id -> sum of child produced_qty
    child_prod_by_poitem: dict = {}
    for cji in child_ji_all:
        poi = cji.get('po_item_id')
        if poi:
            child_prod_by_poitem[poi] = child_prod_by_poitem.get(poi, 0) + cji.get('produced_qty', 0)
    # 5. Batch return items
    all_returns = await db.production_return_items.find({'po_item_id': {'$in': po_item_ids}}).to_list(None)
    ret_by_poitem: dict = {}
    for r in all_returns:
        poi = r.get('po_item_id')
        if poi: ret_by_poitem[poi] = ret_by_poitem.get(poi, 0) + r.get('return_qty', 0)
    # 6. Batch buyer shipment items
    all_buyer = await db.buyer_shipment_items.find({'po_item_id': {'$in': po_item_ids}}).to_list(None)
    shipped_by_poitem: dict = {}
    for b in all_buyer:
        poi = b.get('po_item_id')
        if poi: shipped_by_poitem[poi] = shipped_by_poitem.get(poi, 0) + b.get('qty_shipped', 0)

    enriched = []
    for item in po_items:
        parent_prod = sum(ji.get('produced_qty', 0) for ji in ji_by_poitem.get(item['id'], []))
        total_produced = parent_prod + child_prod_by_poitem.get(item['id'], 0)
        total_returned = ret_by_poitem.get(item['id'], 0)
        total_shipped  = shipped_by_poitem.get(item['id'], 0)
        enriched.append({**serialize_doc(item),
            'total_produced': total_produced, 'total_shipped': total_shipped,
            'total_returned': total_returned,
            'max_returnable': max(0, total_shipped - total_returned)})
    return enriched

@api.put("/po-items/{item_id}")
async def update_po_item(item_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None)
    await db.po_items.update_one({'id': item_id}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.po_items.find_one({'id': item_id}, {'_id': 0}))

@api.delete("/po-items/{item_id}")
async def delete_po_item(item_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    await db.po_items.delete_one({'id': item_id})
    return {'success': True}

# ─── VENDOR SHIPMENTS ────────────────────────────────────────────────────────
@api.get("/vendor-shipments")
async def get_vendor_shipments(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if user.get('role') == 'vendor': query['vendor_id'] = user.get('vendor_id')
    if sp.get('vendor_id'): query['vendor_id'] = sp['vendor_id']
    if sp.get('status'): query['status'] = sp['status']
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'shipment_number': {'$regex': search, '$options': 'i'}},
            {'vendor_name': {'$regex': search, '$options': 'i'}},
        ]

    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'shipment_number', 'shipment_date',
                                 'vendor_name', 'status', 'shipment_type'})
    total = await db.vendor_shipments.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    cursor = db.vendor_shipments.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit)
    shipments = await cursor.to_list(limit)

    # ── Phase 10B: batch-fetch related rows ──
    ship_ids = [s['id'] for s in shipments]
    if ship_ids:
        items_all = await db.vendor_shipment_items.find({'shipment_id': {'$in': ship_ids}}, {'_id': 0}).to_list(None)
        # count child shipments in one aggregation
        child_agg = await db.vendor_shipments.aggregate([
            {'$match': {'parent_shipment_id': {'$in': ship_ids}}},
            {'$group': {'_id': '$parent_shipment_id', 'n': {'$sum': 1}}},
        ]).to_list(None)
    else:
        items_all, child_agg = [], []

    items_by_ship = {}
    for it in items_all:
        items_by_ship.setdefault(it['shipment_id'], []).append(it)
    child_count_by_ship = {c['_id']: c['n'] for c in child_agg}

    # Collect all PO ids referenced, fetch accessory counts in one aggregation
    all_po_ids = set()
    for s in shipments:
        if s.get('po_id'): all_po_ids.add(s['po_id'])
    for it in items_all:
        if it.get('po_id'): all_po_ids.add(it['po_id'])
    if all_po_ids:
        acc_agg = await db.po_accessories.aggregate([
            {'$match': {'po_id': {'$in': list(all_po_ids)}}},
            {'$group': {'_id': '$po_id', 'n': {'$sum': 1}}},
        ]).to_list(None)
        acc_count_by_po = {a['_id']: a['n'] for a in acc_agg}
    else:
        acc_count_by_po = {}

    result = []
    for s in shipments:
        items = items_by_ship.get(s['id'], [])
        child_ships = child_count_by_ship.get(s['id'], 0)
        po_ids_s = {s['po_id']} if s.get('po_id') else set()
        for item in items:
            if item.get('po_id'): po_ids_s.add(item['po_id'])
        po_acc_count = sum(acc_count_by_po.get(pid, 0) for pid in po_ids_s)
        result.append({**serialize_doc(s), 'items': serialize_doc(items),
                       'child_shipment_count': child_ships, 'has_children': child_ships > 0,
                       'po_accessories_count': po_acc_count})

    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result

@api.get("/vendor-shipments/{sid}")
async def get_vendor_shipment(sid: str, request: Request):
    await require_auth(request)
    db = get_db()
    s = await db.vendor_shipments.find_one({'id': sid}, {'_id': 0})
    if not s: raise HTTPException(404, 'Not found')
    items = await db.vendor_shipment_items.find({'shipment_id': sid}, {'_id': 0}).to_list(None)
    # Get accessory shipment items if this is an accessory additional shipment
    accessory_items = await db.accessory_shipment_items.find({'shipment_id': sid}, {'_id': 0}).to_list(None)
    child_ships = await db.vendor_shipments.find({'parent_shipment_id': sid}, {'_id': 0}).to_list(None)
    # ── 10E: batch child ship items in 2 queries instead of 2N ──
    child_ids = [cs['id'] for cs in child_ships]
    cs_items_all  = await db.vendor_shipment_items.find({'shipment_id': {'$in': child_ids}}, {'_id': 0}).to_list(None) if child_ids else []
    cs_acc_all    = await db.accessory_shipment_items.find({'shipment_id': {'$in': child_ids}}, {'_id': 0}).to_list(None) if child_ids else []
    cs_items_map: dict = {}
    for it in cs_items_all: cs_items_map.setdefault(it.get('shipment_id'), []).append(it)
    cs_acc_map: dict = {}
    for it in cs_acc_all: cs_acc_map.setdefault(it.get('shipment_id'), []).append(it)
    child_with_items = [
        {**serialize_doc(cs),
         'items': serialize_doc(cs_items_map.get(cs['id'], [])),
         'accessory_items': serialize_doc(cs_acc_map.get(cs['id'], []))}
        for cs in child_ships
    ]
    # ── 10E: batch PO accessories + PO info in 2 queries instead of 2N ──
    po_ids: set = set()
    if s.get('po_id'): po_ids.add(s['po_id'])
    for item in items:
        if item.get('po_id'): po_ids.add(item['po_id'])
    po_ids_list = list(po_ids)
    all_po_accs = await db.po_accessories.find({'po_id': {'$in': po_ids_list}}, {'_id': 0}).to_list(None) if po_ids_list else []
    all_po_docs = await db.production_pos.find({'id': {'$in': po_ids_list}}, {'_id': 0, 'id': 1, 'po_number': 1}).to_list(None) if po_ids_list else []
    po_num_map = {doc['id']: doc.get('po_number', '') for doc in all_po_docs}
    po_accessories_all = []
    for acc in all_po_accs:
        acc['po_number'] = po_num_map.get(acc.get('po_id'), '')
        po_accessories_all.append(acc)
    po_info_map = po_num_map
    items = await enrich_with_product_photos(items, db)
    result = serialize_doc(s)
    result['items'] = serialize_doc(items)
    result['accessory_items'] = serialize_doc(accessory_items)
    result['child_shipments'] = child_with_items
    result['po_accessories'] = serialize_doc(po_accessories_all)
    return result

@api.post("/vendor-shipments")
async def create_vendor_shipment(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    vendor = await db.garments.find_one({'id': body.get('vendor_id')})
    if not vendor: raise HTTPException(404, 'Vendor not found')
    dup = await db.vendor_shipments.find_one({'shipment_number': body.get('shipment_number')})
    if dup: raise HTTPException(400, f'Nomor shipment "{body.get("shipment_number")}" sudah digunakan')
    items_data = body.get('items', [])
    # Derive po_id and po_number from items if all items reference the same PO
    shipment_po_id = body.get('po_id', '')
    shipment_po_number = body.get('po_number', '')
    if not shipment_po_id and items_data:
        po_ids_in_items = list(set(i.get('po_id') for i in items_data if i.get('po_id')))
        if len(po_ids_in_items) == 1:
            shipment_po_id = po_ids_in_items[0]
            po_doc = await db.production_pos.find_one({'id': shipment_po_id}, {'_id': 0})
            shipment_po_number = po_doc.get('po_number', '') if po_doc else ''
    for item in items_data:
        if item.get('po_id'):
            po = await db.production_pos.find_one({'id': item['po_id']})
            if po and po.get('vendor_id') and po['vendor_id'] != body['vendor_id']:
                raise HTTPException(400, f"PO {po.get('po_number')} ditujukan untuk vendor lain")
    # Phase 8.5 — NORMAL shipment over-ship guard (reject lines that exceed remaining qty to vendor)
    shipment_type = body.get('shipment_type', 'NORMAL')
    if shipment_type == 'NORMAL':
        # (a) reject duplicate po_item_id within this shipment
        seen_item_ids = []
        for item in items_data:
            pid = item.get('po_item_id')
            if not pid:
                continue
            if pid in seen_item_ids:
                raise HTTPException(400, f"PO Item terduplikasi dalam shipment yang sama (po_item_id={pid})")
            seen_item_ids.append(pid)
        # (b) ensure each line does not exceed remaining qty (ordered - already sent)
        for item in items_data:
            pid = item.get('po_item_id')
            if not pid:
                continue
            po_item_doc = await db.po_items.find_one({'id': pid})
            if not po_item_doc:
                raise HTTPException(400, f"PO Item tidak ditemukan (po_item_id={pid})")
            ordered = int(po_item_doc.get('qty', 0) or 0)
            prev_vsis = await db.vendor_shipment_items.find({'po_item_id': pid}).to_list(None)
            already_sent = sum(int(v.get('qty_sent', 0) or 0) for v in prev_vsis)
            remaining = max(0, ordered - already_sent)
            qty_sent_now = int(item.get('qty_sent', 0) or 0)
            if remaining <= 0:
                raise HTTPException(400, f"Item PO '{po_item_doc.get('product_name','')}' sudah fully shipped ke vendor (ordered={ordered}, dikirim={already_sent}). Tidak bisa membuat NORMAL shipment lagi.")
            if qty_sent_now > remaining:
                raise HTTPException(400, f"Qty dikirim ({qty_sent_now}) melebihi sisa qty ke vendor ({remaining}) untuk item '{po_item_doc.get('product_name','')}'. Kurangi qty atau gunakan permintaan ADDITIONAL.")
    shipment_id = new_id()
    shipment = {
        'id': shipment_id, 'shipment_number': body.get('shipment_number'),
        'delivery_note_number': body.get('delivery_note_number', ''),
        'vendor_id': body['vendor_id'], 'vendor_name': vendor.get('garment_name', ''),
        'po_id': shipment_po_id, 'po_number': shipment_po_number,
        'shipment_date': parse_date(body.get('shipment_date')) or now(),
        'shipment_type': body.get('shipment_type', 'NORMAL'),
        'parent_shipment_id': body.get('parent_shipment_id'),
        'status': 'Sent', 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.vendor_shipments.insert_one(shipment)
    inserted_items = []
    affected_pos = set()
    for item in items_data:
        po_item = await db.po_items.find_one({'id': item.get('po_item_id')}) if item.get('po_item_id') else None
        si = {
            'id': new_id(), 'shipment_id': shipment_id, 'shipment_number': body.get('shipment_number'),
            'po_id': item.get('po_id'), 'po_number': item.get('po_number'),
            'po_item_id': item.get('po_item_id'),
            'source_po_item_id': item.get('po_item_id'),
            'product_name': (po_item or {}).get('product_name', item.get('product_name', '')),
            'serial_number': (po_item or {}).get('serial_number', item.get('serial_number', '')),
            'size': (po_item or {}).get('size', item.get('size', '')),
            'color': (po_item or {}).get('color', item.get('color', '')),
            'sku': (po_item or {}).get('sku', item.get('sku', '')),
            'qty_sent': int(item.get('qty_sent', 0) or 0),
            'ordered_qty': (po_item or {}).get('qty', int(item.get('ordered_qty', 0) or 0)),
            'shipment_type': body.get('shipment_type', 'NORMAL'),
            'parent_shipment_id': body.get('parent_shipment_id'),
            'created_at': now()
        }
        await db.vendor_shipment_items.insert_one(si)
        inserted_items.append(si)
        if item.get('po_id'): affected_pos.add(item['po_id'])
    for pid in affected_pos:
        po = await db.production_pos.find_one({'id': pid})
        if po and po.get('status') == 'Draft':
            await db.production_pos.update_one({'id': pid}, {'$set': {'status': 'Distributed', 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Create', 'Vendor Shipment', f"Created shipment {body.get('shipment_number')}")
    result = serialize_doc(shipment)
    result['items'] = serialize_doc(inserted_items)
    return JSONResponse(result, status_code=201)

@api.put("/vendor-shipments/{sid}")
async def update_vendor_shipment(sid: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin', 'vendor']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None); body.pop('items', None)
    await db.vendor_shipments.update_one({'id': sid}, {'$set': {**body, 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Update', 'Vendor Shipment', f"Updated shipment: {sid}")
    return serialize_doc(await db.vendor_shipments.find_one({'id': sid}, {'_id': 0}))

@api.delete("/vendor-shipments/{sid}")
async def delete_vendor_shipment(sid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.vendor_shipments.find_one({'id': sid})
    if not doc: raise HTTPException(404, 'Not found')
    inspections = await db.vendor_material_inspections.find({'shipment_id': sid}).to_list(None)
    for insp in inspections:
        await db.vendor_material_inspection_items.delete_many({'inspection_id': insp['id']})
    await db.vendor_material_inspections.delete_many({'shipment_id': sid})
    jobs = await db.production_jobs.find({'vendor_shipment_id': sid}).to_list(None)
    for job in jobs:
        child_jobs = await db.production_jobs.find({'parent_job_id': job['id']}).to_list(None)
        for cj in child_jobs:
            await db.production_job_items.delete_many({'job_id': cj['id']})
            await db.production_progress.delete_many({'job_id': cj['id']})
            await db.production_jobs.delete_one({'id': cj['id']})
        await db.production_job_items.delete_many({'job_id': job['id']})
        await db.production_progress.delete_many({'job_id': job['id']})
        await db.production_jobs.delete_one({'id': job['id']})
    await db.material_requests.delete_many({'original_shipment_id': sid})
    child_ships = await db.vendor_shipments.find({'parent_shipment_id': sid}).to_list(None)
    for cs in child_ships:
        await db.vendor_shipment_items.delete_many({'shipment_id': cs['id']})
        await db.vendor_shipments.delete_one({'id': cs['id']})
    await db.vendor_shipment_items.delete_many({'shipment_id': sid})
    await db.vendor_shipments.delete_one({'id': sid})
    await log_activity(user['id'], user['name'], 'Delete', 'Vendor Shipment', f"Cascade deleted shipment: {doc.get('shipment_number')}")
    return {'success': True}

# ─── VENDOR MATERIAL INSPECTIONS ─────────────────────────────────────────────
@api.get("/vendor-material-inspections")
async def get_inspections(request: Request):
    user = await require_auth(request)
    db = get_db()
    query = {}
    sp = request.query_params
    if user.get('role') == 'vendor': query['vendor_id'] = user.get('vendor_id')
    if sp.get('vendor_id'): query['vendor_id'] = sp['vendor_id']
    if sp.get('shipment_id'): query['shipment_id'] = sp['shipment_id']
    inspections = await db.vendor_material_inspections.find(query, {'_id': 0}).sort('created_at', -1).to_list(None)
    # ── 10B-rem: batch-fetch all shipments + inspection items in 2 queries ──
    insp_ids = [insp['id'] for insp in inspections]
    ship_ids_needed = list({insp.get('shipment_id') for insp in inspections if insp.get('shipment_id')})
    all_ship_docs = await db.vendor_shipments.find(
        {'id': {'$in': ship_ids_needed}}, {'_id': 0, 'id': 1, 'shipment_number': 1}
    ).to_list(None) if ship_ids_needed else []
    ship_num_map = {s['id']: s.get('shipment_number', '') for s in all_ship_docs}
    all_insp_items = await db.vendor_material_inspection_items.find(
        {'inspection_id': {'$in': insp_ids}}, {'_id': 0}
    ).to_list(None) if insp_ids else []
    items_by_insp: dict = {}
    for it in all_insp_items:
        items_by_insp.setdefault(it.get('inspection_id'), []).append(it)
    result = []
    for insp in inspections:
        all_items = items_by_insp.get(insp['id'], [])
        mat_items = [i for i in all_items if i.get('item_type') != 'accessory']
        acc_items  = [i for i in all_items if i.get('item_type') == 'accessory']
        result.append({
            **serialize_doc(insp),
            'shipment_number': ship_num_map.get(insp.get('shipment_id'), ''),
            'items': serialize_doc(mat_items),
            'accessory_items': serialize_doc(acc_items),
        })
    return result

@api.post("/vendor-material-inspections")
async def create_inspection(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    vendor_id = user.get('vendor_id') if user.get('role') == 'vendor' else body.get('vendor_id')
    # Try to infer vendor_id from shipment if not provided
    if not vendor_id and body.get('shipment_id'):
        ship = await db.vendor_shipments.find_one({'id': body['shipment_id']})
        if ship: vendor_id = ship.get('vendor_id')
    if not vendor_id: raise HTTPException(400, 'vendor_id diperlukan')
    shipment = await db.vendor_shipments.find_one({'id': body.get('shipment_id')}) if body.get('shipment_id') else None
    if not shipment: raise HTTPException(404, 'Shipment tidak ditemukan')
    existing = await db.vendor_material_inspections.find_one({'shipment_id': body['shipment_id']})
    if existing: raise HTTPException(400, 'Inspeksi untuk shipment ini sudah dilakukan')
    inspection_id = new_id()
    items_data = body.get('items', [])
    accessory_items_data = body.get('accessory_items', [])
    total_received = sum(int(i.get('received_qty', 0) or 0) for i in items_data)
    total_missing = sum(int(i.get('missing_qty', 0) or 0) for i in items_data)
    total_acc_received = sum(int(a.get('received_qty', 0) or 0) for a in accessory_items_data)
    total_acc_missing = sum(int(a.get('missing_qty', 0) or 0) for a in accessory_items_data)
    inspection = {
        'id': inspection_id, 'shipment_id': body['shipment_id'],
        'shipment_number': shipment.get('shipment_number', ''),
        'vendor_id': vendor_id, 'vendor_name': shipment.get('vendor_name', ''),
        'inspection_date': parse_date(body.get('inspection_date')) or now(),
        'total_received': total_received, 'total_missing': total_missing,
        'total_acc_received': total_acc_received, 'total_acc_missing': total_acc_missing,
        'overall_notes': body.get('overall_notes', ''), 'status': 'Submitted',
        'submitted_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.vendor_material_inspections.insert_one(inspection)
    for item in items_data:
        await db.vendor_material_inspection_items.insert_one({
            'id': new_id(), 'inspection_id': inspection_id,
            'item_type': 'material',
            'shipment_item_id': item.get('shipment_item_id'),
            'sku': item.get('sku', ''), 'product_name': item.get('product_name', ''),
            'size': item.get('size', ''), 'color': item.get('color', ''),
            'ordered_qty': int(item.get('ordered_qty', 0) or 0),
            'received_qty': int(item.get('received_qty', 0) or 0),
            'missing_qty': int(item.get('missing_qty', 0) or 0),
            'condition_notes': item.get('condition_notes', ''), 'created_at': now()
        })
    for acc in accessory_items_data:
        await db.vendor_material_inspection_items.insert_one({
            'id': new_id(), 'inspection_id': inspection_id,
            'item_type': 'accessory',
            'accessory_id': acc.get('accessory_id', ''),
            'accessory_name': acc.get('accessory_name', ''),
            'accessory_code': acc.get('accessory_code', ''),
            'unit': acc.get('unit', 'pcs'),
            'ordered_qty': int(acc.get('ordered_qty', 0) or 0),
            'received_qty': int(acc.get('received_qty', 0) or 0),
            'missing_qty': int(acc.get('missing_qty', 0) or 0),
            'condition_notes': acc.get('condition_notes', ''), 'created_at': now()
        })
    # Update shipment
    await db.vendor_shipments.update_one({'id': body['shipment_id']}, {'$set': {
        'inspection_status': 'Inspected', 'total_received': total_received,
        'total_missing': total_missing, 'inspected_at': now(), 'updated_at': now()
    }})
    # Auto-create child job for additional/replacement shipment
    if shipment.get('parent_shipment_id') and shipment.get('status') == 'Received':
        parent_job = await db.production_jobs.find_one({'vendor_shipment_id': shipment['parent_shipment_id']})
        already_exists = await db.production_jobs.find_one({'vendor_shipment_id': body['shipment_id']})
        if parent_job and not already_exists and total_received > 0:
            child_job_id = new_id()
            suffix = 'A' if shipment.get('shipment_type') == 'ADDITIONAL' else 'R'
            child_count = await db.production_jobs.count_documents({'parent_job_id': parent_job['id']})
            child_job_number = f"{parent_job['job_number']}-{suffix}{child_count + 1}"
            child_job = {
                'id': child_job_id, 'job_number': child_job_number,
                'parent_job_id': parent_job['id'], 'parent_job_number': parent_job['job_number'],
                'vendor_id': parent_job['vendor_id'], 'vendor_name': parent_job['vendor_name'],
                'po_id': parent_job.get('po_id'), 'po_number': parent_job.get('po_number', ''),
                'customer_name': parent_job.get('customer_name', ''),
                'vendor_shipment_id': body['shipment_id'],
                'shipment_number': shipment.get('shipment_number'),
                'shipment_type': shipment.get('shipment_type', 'ADDITIONAL'),
                'deadline': parent_job.get('deadline'), 'delivery_deadline': parent_job.get('delivery_deadline'),
                'status': 'In Progress', 'notes': f"Auto-created from {shipment.get('shipment_type')} shipment",
                'created_by': 'system', 'created_at': now(), 'updated_at': now()
            }
            await db.production_jobs.insert_one(child_job)
            ship_items = await db.vendor_shipment_items.find({'shipment_id': body['shipment_id']}).to_list(None)
            for si in ship_items:
                po_item = await db.po_items.find_one({'id': si.get('po_item_id')}) if si.get('po_item_id') else None
                matched = next((ii for ii in items_data if ii.get('shipment_item_id') == si['id']), None)
                if not matched:
                    matched = next((ii for ii in items_data if ii.get('sku') == si.get('sku') and ii.get('size') == si.get('size', '')), None)
                avail = int(matched.get('received_qty', 0)) if matched else si.get('qty_sent', 0)
                await db.production_job_items.insert_one({
                    'id': new_id(), 'job_id': child_job_id, 'job_number': child_job_number,
                    'po_item_id': si.get('po_item_id'),
                    'vendor_shipment_item_id': si['id'],
                    'product_name': si.get('product_name', ''), 'sku': si.get('sku', ''),
                    'size': si.get('size', ''), 'color': si.get('color', ''),
                    'serial_number': (po_item or {}).get('serial_number', si.get('serial_number', '')),
                    'ordered_qty': si.get('qty_sent', 0), 'shipment_qty': si.get('qty_sent', 0),
                    'available_qty': avail, 'produced_qty': 0, 'created_at': now()
                })
    # Auto-create material request for missing accessories
    missing_accessories = [a for a in accessory_items_data if int(a.get('missing_qty', 0) or 0) > 0]
    if missing_accessories:
        po_id = shipment.get('po_id', '')
        if not po_id:
            first_si = await db.vendor_shipment_items.find_one({'shipment_id': body['shipment_id']})
            if first_si: po_id = first_si.get('po_id', '')
        if po_id:
            po_doc = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
            po_number = (po_doc or {}).get('po_number', '')
            req_count = await db.material_requests.count_documents({'po_id': po_id, 'request_type': 'ADDITIONAL'})
            req_number = f"REQ-ACC-{req_count + 1}-{po_number}"
            acc_details = ', '.join([f"{a.get('accessory_name', '')}({a.get('missing_qty', 0)} {a.get('unit', 'pcs')})" for a in missing_accessories])
            req_doc = {
                'id': new_id(), 'request_number': req_number,
                'po_id': po_id, 'po_number': po_number,
                'vendor_id': vendor_id, 'vendor_name': shipment.get('vendor_name', ''),
                'request_type': 'ADDITIONAL', 'category': 'accessories',
                'original_shipment_id': body.get('shipment_id'),
                'original_shipment_number': shipment.get('shipment_number', ''),
                'reason': f"Aksesoris kurang saat inspeksi: {acc_details}",
                'vendor_notes': '',
                'status': 'Pending',
                'total_requested_qty': sum(int(a.get('missing_qty', 0)) for a in missing_accessories),
                'items': [{'accessory_name': a.get('accessory_name', ''), 'accessory_code': a.get('accessory_code', ''),
                           'requested_qty': int(a.get('missing_qty', 0)), 'unit': a.get('unit', 'pcs')} for a in missing_accessories],
                'created_by': user['name'], 'created_at': now(), 'updated_at': now()
            }
            await db.material_requests.insert_one(req_doc)

    # ─── H-2 FIX: Auto-create REPLACEMENT request for missing MATERIAL items ───
    # Mirror the accessory-missing block for material-missing, so the vendor doesn't
    # have to manually re-enter missing SKUs. Admin can approve/reject as usual.
    missing_materials = [m for m in items_data if int(m.get('missing_qty', 0) or 0) > 0]
    if missing_materials:
        po_id = shipment.get('po_id', '')
        if not po_id:
            first_si = await db.vendor_shipment_items.find_one({'shipment_id': body['shipment_id']})
            if first_si: po_id = first_si.get('po_id', '')
        if po_id:
            po_doc = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
            po_number = (po_doc or {}).get('po_number', '')
            # Idempotency: avoid duplicating the request if re-submitted (inspection is already one-shot, but defensive)
            already = await db.material_requests.find_one({
                'original_shipment_id': body['shipment_id'],
                'request_type': 'REPLACEMENT',
                'category': {'$ne': 'accessories'}
            })
            if not already:
                req_count = await db.material_requests.count_documents({'po_id': po_id, 'request_type': 'REPLACEMENT'}) if po_id else 0
                req_number = f"REQ-RPL-{req_count + 1}-{po_number}" if po_number else f"REQ-RPL-{str(req_count + 1).zfill(4)}"
                mat_details = ', '.join([f"{m.get('sku', '')}/{m.get('size', '')}/{m.get('color', '')}({m.get('missing_qty', 0)} pcs)" for m in missing_materials])
                # Build item list with po_item_id when available (via shipment_item link)
                req_items = []
                total_req_qty = 0
                for m in missing_materials:
                    ship_item_id = m.get('shipment_item_id')
                    po_item_id = ''
                    serial = ''
                    if ship_item_id:
                        si_doc = await db.vendor_shipment_items.find_one({'id': ship_item_id})
                        if si_doc:
                            po_item_id = si_doc.get('po_item_id', '')
                            serial = si_doc.get('serial_number', '')
                    miss_qty = int(m.get('missing_qty', 0) or 0)
                    req_items.append({
                        'po_item_id': po_item_id,
                        'sku': m.get('sku', ''), 'product_name': m.get('product_name', ''),
                        'size': m.get('size', ''), 'color': m.get('color', ''),
                        'serial_number': serial,
                        'requested_qty': miss_qty
                    })
                    total_req_qty += miss_qty
                req_doc = {
                    'id': new_id(), 'request_number': req_number,
                    'po_id': po_id, 'po_number': po_number,
                    'vendor_id': vendor_id, 'vendor_name': shipment.get('vendor_name', ''),
                    'request_type': 'REPLACEMENT', 'category': 'material',
                    'original_shipment_id': body['shipment_id'],
                    'original_shipment_number': shipment.get('shipment_number', ''),
                    'reason': f"Material kurang saat inspeksi: {mat_details}",
                    'vendor_notes': '',
                    'status': 'Pending',
                    'total_requested_qty': total_req_qty,
                    'items': req_items,
                    'auto_generated': True,
                    'created_by': f"system (inspeksi by {user['name']})",
                    'created_at': now(), 'updated_at': now()
                }
                await db.material_requests.insert_one(req_doc)

    await log_activity(user['id'], user['name'], 'Create', 'Material Inspection',
                       f"Inspeksi shipment {shipment.get('shipment_number')}: diterima {total_received}, missing {total_missing}, acc diterima {total_acc_received}, acc missing {total_acc_missing}")
    all_item_docs = await db.vendor_material_inspection_items.find({'inspection_id': inspection_id}, {'_id': 0}).to_list(None)
    result = serialize_doc(inspection)
    result['items'] = serialize_doc([i for i in all_item_docs if i.get('item_type') != 'accessory'])
    result['accessory_items'] = serialize_doc([i for i in all_item_docs if i.get('item_type') == 'accessory'])
    return JSONResponse(result, status_code=201)

# ─── PRODUCTION JOBS ─────────────────────────────────────────────────────────
@api.get("/production-jobs")
async def get_jobs(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    filt = {}
    if user.get('role') == 'vendor': filt['vendor_id'] = user.get('vendor_id')
    if sp.get('vendor_id'): filt['vendor_id'] = sp['vendor_id']
    if sp.get('status'): filt['status'] = sp['status']
    include_children = sp.get('include_children') == 'true'
    if not include_children:
        filt['parent_job_id'] = {'$in': [None, '', False]}
    search = sp.get('search')
    if search:
        filt['$or'] = [
            {'job_number': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
            {'vendor_name': {'$regex': search, '$options': 'i'}},
        ]

    # Pagination (Phase 10A) — applied to parent jobs
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'job_number', 'status', 'vendor_name'})
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    total = await db.production_jobs.count_documents(filt) if wants else None
    jobs = await db.production_jobs.find(filt, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)

    # Also include jobs where parent_job_id doesn't exist (legacy data without the field)
    if not include_children:
        extra_filt = {**{k: v for k, v in filt.items() if k != 'parent_job_id'},
                      'parent_job_id': {'$exists': False}}
        extra_limit = limit - len(jobs) if wants else LEGACY_DEFAULT_CAP
        if extra_limit > 0:
            extra = await db.production_jobs.find(extra_filt, {'_id': 0}).sort(sort).limit(extra_limit).to_list(extra_limit)
            existing_ids = {j['id'] for j in jobs}
            for e in extra:
                if e['id'] not in existing_ids:
                    jobs.append(e)

    # ── Phase 10B: batch-fetch all child jobs + all job_items in two queries each ──
    job_ids = [j['id'] for j in jobs]
    if job_ids:
        all_child_jobs = await db.production_jobs.find({'parent_job_id': {'$in': job_ids}}, {'_id': 0}).to_list(None)
        child_ids = [c['id'] for c in all_child_jobs]
        owner_ids = job_ids + child_ids
        all_job_items = await db.production_job_items.find({'job_id': {'$in': owner_ids}}, {'_id': 0}).to_list(None)
    else:
        all_child_jobs, all_job_items = [], []

    children_by_parent = {}
    for c in all_child_jobs:
        children_by_parent.setdefault(c.get('parent_job_id'), []).append(c)
    items_by_job = {}
    for it in all_job_items:
        items_by_job.setdefault(it['job_id'], []).append(it)

    # Aggregate buyer shipped qty per job_item_id in one pipeline
    all_job_item_ids = [i['id'] for i in all_job_items]
    if all_job_item_ids:
        buyer_agg = await db.buyer_shipment_items.aggregate([
            {'$match': {'job_item_id': {'$in': all_job_item_ids}}},
            {'$group': {'_id': '$job_item_id', 'qty': {'$sum': '$qty_shipped'}}},
        ]).to_list(None)
    else:
        buyer_agg = []
    buyer_by_item = {b['_id']: b['qty'] for b in buyer_agg}

    result = []
    for j in jobs:
        items = items_by_job.get(j['id'], [])
        child_jobs = children_by_parent.get(j['id'], [])
        total_ordered = sum(i.get('ordered_qty', 0) for i in items)
        total_available = sum(i.get('available_qty', i.get('shipment_qty', 0)) for i in items)
        total_produced = sum(i.get('produced_qty', 0) for i in items)
        all_jobitem_ids = [i['id'] for i in items]
        for child in child_jobs:
            ci = items_by_job.get(child['id'], [])
            total_available += sum(i.get('available_qty', i.get('shipment_qty', 0)) for i in ci)
            total_produced += sum(i.get('produced_qty', 0) for i in ci)
            all_jobitem_ids.extend([ci_item['id'] for ci_item in ci])

        total_shipped_to_buyer = sum(buyer_by_item.get(iid, 0) for iid in all_jobitem_ids)
        remaining_to_ship = max(0, total_produced - total_shipped_to_buyer)
        serial_numbers = list({i.get('serial_number', '') for i in items if i.get('serial_number')})
        result.append({**serialize_doc(j), 'item_count': len(items),
                       'total_ordered': total_ordered, 'total_available': total_available,
                       'total_produced': total_produced, 'total_shipped_to_buyer': total_shipped_to_buyer,
                       'remaining_to_ship': remaining_to_ship,
                       'progress_pct': round((total_produced / total_available * 100) if total_available > 0 else 0),
                       'serial_numbers': serial_numbers, 'child_job_count': len(child_jobs),
                       'child_jobs': [{'id': c['id'], 'job_number': c.get('job_number'),
                                       'status': c.get('status'),
                                       'shipment_type': c.get('shipment_type')} for c in child_jobs]})

    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result

@api.get("/production-jobs/{jid}")
async def get_job(jid: str, request: Request):
    await require_auth(request)
    db = get_db()
    job = await db.production_jobs.find_one({'id': jid}, {'_id': 0})
    if not job: raise HTTPException(404, 'Not found')
    items = await db.production_job_items.find({'job_id': jid}, {'_id': 0}).to_list(None)
    # ── 10E: batch defect reports for all items in 1 query ──
    item_ids = [it['id'] for it in items]
    all_defects = await db.material_defect_reports.find({'job_item_id': {'$in': item_ids}}).to_list(None) if item_ids else []
    defect_by_item: dict = {}
    for d in all_defects: defect_by_item.setdefault(d.get('job_item_id'), []).append(d)
    enriched_items = []
    for item in items:
        defects = defect_by_item.get(item['id'], [])
        total_defect = sum(d.get('defect_qty', 0) for d in defects)
        effective_available = max(0, (item.get('available_qty', item.get('shipment_qty', 0))) - total_defect)
        enriched_items.append({**serialize_doc(item), 'total_defect_qty': total_defect, 'effective_available_qty': effective_available})
    child_jobs = await db.production_jobs.find({'parent_job_id': jid}, {'_id': 0}).to_list(None)
    result = serialize_doc(job)
    result['items'] = enriched_items
    result['child_jobs'] = serialize_doc(child_jobs)
    return result

@api.post("/production-jobs")
async def create_job(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    vendor_id = user.get('vendor_id') if user.get('role') == 'vendor' else body.get('vendor_id')
    if not vendor_id: raise HTTPException(400, 'vendor_id diperlukan')
    shipment = await db.vendor_shipments.find_one({'id': body.get('vendor_shipment_id')})
    if not shipment: raise HTTPException(404, 'Shipment tidak ditemukan')
    if shipment.get('status') != 'Received': raise HTTPException(400, 'Shipment belum dikonfirmasi diterima.')
    if shipment.get('vendor_id') != vendor_id: raise HTTPException(403, 'Shipment ini bukan milik vendor Anda')
    if shipment.get('inspection_status') != 'Inspected':
        raise HTTPException(400, f"Inspeksi material belum selesai.")
    existing = await db.production_jobs.find_one({'vendor_shipment_id': body['vendor_shipment_id']})
    if existing: raise HTTPException(400, f"Production Job sudah ada ({existing.get('job_number')})")
    parent_job_id = None
    parent_job_number = None
    if shipment.get('parent_shipment_id'):
        parent_job = await db.production_jobs.find_one({'vendor_shipment_id': shipment['parent_shipment_id']})
        if parent_job:
            parent_job_id = parent_job['id']
            parent_job_number = parent_job.get('job_number')
    ship_items = await db.vendor_shipment_items.find({'shipment_id': body['vendor_shipment_id']}).to_list(None)
    po_id = body.get('po_id') or (ship_items[0].get('po_id') if ship_items else None)
    po = await db.production_pos.find_one({'id': po_id}) if po_id else None
    job_id = new_id()
    job_seq = (await db.production_jobs.count_documents({})) + 1
    if parent_job_number:
        suffix = 'A' if shipment.get('shipment_type') == 'ADDITIONAL' else 'R'
        child_count = await db.production_jobs.count_documents({'parent_job_id': parent_job_id})
        job_number = f"{parent_job_number}-{suffix}{child_count + 1}"
    else:
        job_number = f"JOB-{str(job_seq).zfill(4)}"
    job = {
        'id': job_id, 'job_number': job_number,
        'parent_job_id': parent_job_id, 'parent_job_number': parent_job_number,
        'vendor_id': vendor_id, 'vendor_name': shipment.get('vendor_name', ''),
        'po_id': po_id, 'po_number': (po or {}).get('po_number', ''),
        'customer_name': (po or {}).get('customer_name', ''),
        'vendor_shipment_id': body['vendor_shipment_id'],
        'shipment_number': shipment.get('shipment_number'),
        'shipment_type': shipment.get('shipment_type', 'NORMAL'),
        'deadline': (po or {}).get('deadline'), 'delivery_deadline': (po or {}).get('delivery_deadline'),
        'status': 'In Progress', 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.production_jobs.insert_one(job)
    inspection = await db.vendor_material_inspections.find_one({'shipment_id': body['vendor_shipment_id']})
    inserted_items = []
    for si in ship_items:
        po_item = await db.po_items.find_one({'id': si.get('po_item_id')}) if si.get('po_item_id') else None
        available_qty = si.get('qty_sent', 0)
        if inspection:
            insp_item = await db.vendor_material_inspection_items.find_one({'inspection_id': inspection['id'], 'shipment_item_id': si['id']})
            if not insp_item:
                insp_item = await db.vendor_material_inspection_items.find_one({'inspection_id': inspection['id'], 'sku': si.get('sku', ''), 'size': si.get('size', ''), 'color': si.get('color', '')})
            if insp_item:
                available_qty = insp_item.get('received_qty', si.get('qty_sent', 0))
        ji = {
            'id': new_id(), 'job_id': job_id, 'job_number': job_number,
            'po_item_id': si.get('po_item_id'),
            'vendor_shipment_item_id': si['id'],
            'product_name': si.get('product_name', ''), 'sku': si.get('sku', ''),
            'size': si.get('size', ''), 'color': si.get('color', ''),
            'serial_number': (po_item or {}).get('serial_number', si.get('serial_number', '')),
            'ordered_qty': (po_item or {}).get('qty', si.get('qty_sent', 0)),
            'shipment_qty': si.get('qty_sent', 0), 'available_qty': available_qty,
            'produced_qty': 0, 'created_at': now()
        }
        await db.production_job_items.insert_one(ji)
        inserted_items.append(ji)
    if po_id:
        current_po = await db.production_pos.find_one({'id': po_id})
        if current_po and current_po.get('status') not in ['Completed', 'Closed']:
            await db.production_pos.update_one({'id': po_id}, {'$set': {'status': 'In Production', 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Create', 'Production Job', f"Created job {job_number}")
    result = serialize_doc(job)
    result['items'] = serialize_doc(inserted_items)
    return JSONResponse(result, status_code=201)

@api.delete("/production-jobs/{jid}")
async def delete_job(jid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.production_jobs.find_one({'id': jid})
    if not doc: raise HTTPException(404, 'Not found')
    child_jobs = await db.production_jobs.find({'parent_job_id': jid}).to_list(None)
    for cj in child_jobs:
        await db.production_job_items.delete_many({'job_id': cj['id']})
        await db.production_progress.delete_many({'job_id': cj['id']})
        await db.production_jobs.delete_one({'id': cj['id']})
    await db.production_job_items.delete_many({'job_id': jid})
    await db.production_progress.delete_many({'job_id': jid})
    await db.production_jobs.delete_one({'id': jid})
    await log_activity(user['id'], user['name'], 'Delete', 'Production Job', f"Deleted job: {doc.get('job_number')}")
    return {'success': True}

# ─── PRODUCTION JOB ITEMS ────────────────────────────────────────────────────
@api.get("/production-job-items")
async def get_job_items(request: Request):
    await require_auth(request)
    db = get_db()
    job_id = request.query_params.get('job_id')
    if not job_id: raise HTTPException(400, 'job_id required')
    items = await db.production_job_items.find({'job_id': job_id}, {'_id': 0}).to_list(None)
    child_jobs = await db.production_jobs.find({'parent_job_id': job_id}).to_list(None)
    child_job_ids = [c['id'] for c in child_jobs]
    # ── 10E: batch child items, progress history, buyer items ──
    all_child_items = await db.production_job_items.find({'job_id': {'$in': child_job_ids}}).to_list(None) if child_job_ids else []
    child_items_by_poi: dict = {}
    for c in all_child_items:
        key = c.get('po_item_id') or c['id']
        child_items_by_poi.setdefault(key, []).append(c)
    all_item_ids = [it['id'] for it in items]
    all_progress = await db.production_progress.find({'job_item_id': {'$in': all_item_ids}}, {'_id': 0}).sort('progress_date', -1).to_list(None) if all_item_ids else []
    progress_by_item: dict = {}
    for p in all_progress: progress_by_item.setdefault(p.get('job_item_id'), []).append(p)
    all_po_item_ids = [it['po_item_id'] for it in items if it.get('po_item_id')]
    all_child_item_ids = [c['id'] for c in all_child_items]
    buyer_q = {}
    if all_po_item_ids:
        buyer_q = {'po_item_id': {'$in': all_po_item_ids}}
    elif all_child_item_ids or all_item_ids:
        buyer_q = {'job_item_id': {'$in': list({*all_item_ids, *all_child_item_ids})}}
    all_buyer = await db.buyer_shipment_items.find(buyer_q).to_list(None) if buyer_q else []
    buyer_by_poi: dict = {}
    buyer_by_ji: dict = {}
    for b in all_buyer:
        if b.get('po_item_id'): buyer_by_poi[b['po_item_id']] = buyer_by_poi.get(b['po_item_id'], 0) + b.get('qty_shipped', 0)
        if b.get('job_item_id'): buyer_by_ji[b['job_item_id']] = buyer_by_ji.get(b['job_item_id'], 0) + b.get('qty_shipped', 0)
    result = []
    for item in items:
        progress = progress_by_item.get(item['id'], [])
        key = item.get('po_item_id') or item['id']
        child_items = child_items_by_poi.get(key, [])
        child_produced = sum(ci.get('produced_qty', 0) for ci in child_items)
        total_produced = (item.get('produced_qty', 0)) + child_produced
        all_job_item_ids = [item['id']] + [ci['id'] for ci in child_items]
        if item.get('po_item_id'):
            shipped = buyer_by_poi.get(item['po_item_id'], 0)
        else:
            shipped = sum(buyer_by_ji.get(jid2, 0) for jid2 in all_job_item_ids)
        result.append({**serialize_doc(item), 'progress_history': serialize_doc(progress),
                       'shipped_to_buyer': shipped, 'remaining_to_ship': max(0, total_produced - shipped),
                       'child_produced_qty': child_produced, 'total_produced_qty': total_produced})
    return result

# ─── PRODUCTION PROGRESS ─────────────────────────────────────────────────────
@api.get("/production-progress")
async def get_progress(request: Request):
    user = await require_auth(request)
    db = get_db()
    query = {}
    sp = request.query_params
    if sp.get('work_order_id'): query['work_order_id'] = sp['work_order_id']
    if user.get('role') == 'vendor': query['garment_id'] = user.get('vendor_id')
    return serialize_doc(await db.production_progress.find(query, {'_id': 0}).sort('progress_date', -1).to_list(None))

@api.post("/production-progress")
async def create_progress(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    if body.get('job_item_id'):
        job_item = await db.production_job_items.find_one({'id': body['job_item_id']})
        if not job_item: raise HTTPException(404, 'Job item tidak ditemukan')
        qty_today = int(body.get('completed_quantity', 0) or 0)
        if qty_today <= 0: raise HTTPException(400, 'Jumlah produksi harus lebih dari 0')

        # ─── H-3 FIX: respect defect-adjusted capacity (Invariant I-1)
        # Vendor cannot produce from defective or missing material.
        raw_available = job_item.get('available_qty', job_item.get('shipment_qty', 0))
        defect_docs = await db.material_defect_reports.find({'job_item_id': body['job_item_id']}).to_list(None)
        total_defect = sum(int(d.get('defect_qty', 0) or 0) for d in defect_docs)
        effective_max = max(0, raw_available - total_defect)

        new_total = (job_item.get('produced_qty', 0)) + qty_today
        if new_total > effective_max:
            if total_defect > 0:
                raise HTTPException(400,
                    f"Total produksi ({new_total}) melebihi material usable ({effective_max} pcs). "
                    f"Material tersedia: {raw_available}, defect: {total_defect}.")
            else:
                raise HTTPException(400,
                    f"Total produksi ({new_total}) melebihi material tersedia ({effective_max} pcs)")
        progress = {
            'id': new_id(), 'job_id': job_item.get('job_id'), 'job_item_id': body['job_item_id'],
            'sku': job_item.get('sku', ''), 'product_name': job_item.get('product_name', ''),
            'size': job_item.get('size', ''), 'color': job_item.get('color', ''),
            'progress_date': parse_date(body.get('progress_date')) or now(),
            'completed_quantity': qty_today, 'notes': body.get('notes', ''),
            'recorded_by': user['name'], 'created_at': now()
        }
        await db.production_progress.insert_one(progress)
        await db.production_job_items.update_one({'id': body['job_item_id']}, {'$set': {'produced_qty': new_total, 'updated_at': now()}})
        all_items = await db.production_job_items.find({'job_id': job_item['job_id']}).to_list(None)
        all_done = all(
            (new_total if i['id'] == body['job_item_id'] else i.get('produced_qty', 0)) >= i.get('shipment_qty', 0)
            for i in all_items
        )
        if all_done:
            await db.production_jobs.update_one({'id': job_item['job_id']}, {'$set': {'status': 'Completed', 'updated_at': now()}})
        await log_activity(user['id'], user['name'], 'Create', 'Production Progress', f"Progress {job_item.get('sku')}: +{qty_today}")
        result = serialize_doc(progress)
        result['new_total'] = new_total
        return JSONResponse(result, status_code=201)
    # Legacy: work_order_id
    wo = await db.work_orders.find_one({'id': body.get('work_order_id')})
    if not wo: raise HTTPException(404, 'Work order tidak ditemukan')
    progress = {
        'id': new_id(), 'work_order_id': body['work_order_id'],
        'distribution_code': wo.get('distribution_code'),
        'garment_id': wo.get('garment_id'), 'garment_name': wo.get('garment_name'),
        'po_id': wo.get('po_id'), 'po_number': wo.get('po_number'),
        'progress_date': parse_date(body.get('progress_date')) or now(),
        'completed_quantity': int(body.get('completed_quantity', 0)),
        'notes': body.get('notes', ''), 'recorded_by': user['name'], 'created_at': now()
    }
    await db.production_progress.insert_one(progress)
    all_prog = await db.production_progress.find({'work_order_id': body['work_order_id']}).to_list(None)
    total_completed = sum(p.get('completed_quantity', 0) for p in all_prog)
    new_status = 'Completed' if total_completed >= wo.get('quantity', 0) else 'In Progress'
    await db.work_orders.update_one({'id': body['work_order_id']}, {'$set': {'completed_quantity': total_completed, 'status': new_status, 'updated_at': now()}})
    await db.production_pos.update_one({'id': wo.get('po_id')}, {'$set': {'status': 'In Production', 'updated_at': now()}})
    return JSONResponse(serialize_doc(progress), status_code=201)

# ─── BUYER SHIPMENTS ─────────────────────────────────────────────────────────
@api.get("/buyer-shipments")
async def get_buyer_shipments(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('po_id'): query['po_id'] = sp['po_id']
    if user.get('role') == 'vendor': query['vendor_id'] = user.get('vendor_id')
    if sp.get('status'): query['ship_status'] = sp['status']
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'shipment_number': {'$regex': search, '$options': 'i'}},
            {'customer_name': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
        ]

    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'shipment_number', 'customer_name',
                                 'vendor_name', 'po_number', 'ship_status'})
    total = await db.buyer_shipments.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    cursor = db.buyer_shipments.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit)
    shipments = await cursor.to_list(limit)

    # ── Phase 10B: batch-fetch items ──
    ship_ids = [s['id'] for s in shipments]
    if ship_ids:
        items_all = await db.buyer_shipment_items.find({'shipment_id': {'$in': ship_ids}}, {'_id': 0}).to_list(None)
    else:
        items_all = []
    items_by_ship = {}
    for it in items_all:
        items_by_ship.setdefault(it['shipment_id'], []).append(it)

    result = []
    for s in shipments:
        items = items_by_ship.get(s['id'], [])
        po_item_map = {}
        for item in items:
            key = item.get('po_item_id') or item['id']
            if key not in po_item_map:
                po_item_map[key] = {'ordered_qty': item.get('ordered_qty', 0), 'shipped': 0}
            po_item_map[key]['shipped'] += item.get('qty_shipped', 0)
        total_ordered = sum(v['ordered_qty'] for v in po_item_map.values())
        total_shipped = sum(v['shipped'] for v in po_item_map.values())
        remaining = max(0, total_ordered - total_shipped)
        pct = round((total_shipped / total_ordered * 100)) if total_ordered > 0 else 0
        max_dispatch = max((i.get('dispatch_seq', 1) for i in items), default=0)
        result.append({**serialize_doc(s), 'items': serialize_doc(items),
                       'total_ordered': total_ordered, 'total_shipped': total_shipped,
                       'remaining': remaining, 'progress_pct': pct, 'dispatch_count': max_dispatch})

    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result

@api.get("/buyer-shipments/{bsid}")
async def get_buyer_shipment(bsid: str, request: Request):
    await require_auth(request)
    db = get_db()
    s = await db.buyer_shipments.find_one({'id': bsid}, {'_id': 0})
    if not s: raise HTTPException(404, 'Not found')
    items = await db.buyer_shipment_items.find({'shipment_id': bsid}, {'_id': 0}).sort([('dispatch_seq', 1), ('created_at', 1)]).to_list(None)
    dispatch_map = {}
    poi_totals = {}
    for item in items:
        seq = item.get('dispatch_seq', 1)
        if seq not in dispatch_map:
            dispatch_map[seq] = {'dispatch_seq': seq, 'dispatch_date': item.get('dispatch_date') or item.get('created_at'), 'items': [], 'total_qty': 0}
        dispatch_map[seq]['items'].append(serialize_doc(item))
        dispatch_map[seq]['total_qty'] += item.get('qty_shipped', 0)
        key = item.get('po_item_id') or item['id']
        if key not in poi_totals:
            poi_totals[key] = {'po_item_id': item.get('po_item_id'), 'sku': item.get('sku', ''),
                               'product_name': item.get('product_name', ''), 'serial_number': item.get('serial_number', ''),
                               'size': item.get('size', ''), 'color': item.get('color', ''),
                               'ordered_qty': item.get('ordered_qty', 0), 'cumulative_shipped': 0}
        poi_totals[key]['cumulative_shipped'] += item.get('qty_shipped', 0)
    dispatches = sorted(dispatch_map.values(), key=lambda d: d['dispatch_seq'])
    summary_items = list(poi_totals.values())
    total_ordered = sum(i['ordered_qty'] for i in summary_items)
    total_shipped = sum(i['cumulative_shipped'] for i in summary_items)
    remaining = max(0, total_ordered - total_shipped)
    pct = round((total_shipped / total_ordered * 100)) if total_ordered > 0 else 0
    result = serialize_doc(s)
    result.update({'items': serialize_doc(items), 'dispatches': dispatches,
                   'summary_items': summary_items, 'total_ordered': total_ordered,
                   'total_shipped': total_shipped, 'remaining': remaining, 'progress_pct': pct})
    return result

@api.post("/buyer-shipments")
async def create_buyer_shipment(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    vendor_id = user.get('vendor_id') if user.get('role') == 'vendor' else body.get('vendor_id')
    vendor_doc = await db.garments.find_one({'id': vendor_id}) if vendor_id else None
    po = await db.production_pos.find_one({'id': body.get('po_id')}) if body.get('po_id') else None
    job_id = body.get('job_id')
    master_shipment = None
    if job_id:
        master_shipment = await db.buyer_shipments.find_one({'job_id': job_id, 'vendor_id': vendor_id})
    is_new = not master_shipment
    if is_new:
        shipment_id = new_id()
        master_shipment = {
            'id': shipment_id,
            'shipment_number': body.get('shipment_number') or f"SJ-BYR-{(po or {}).get('po_number', '') or int(datetime.now().timestamp())}",
            'vendor_id': vendor_id, 'vendor_name': (vendor_doc or {}).get('garment_name', user['name']),
            'po_id': body.get('po_id'), 'po_number': (po or {}).get('po_number', body.get('po_number', '')),
            'customer_name': (po or {}).get('customer_name', body.get('customer_name', '')),
            'job_id': job_id, 'ship_status': 'Pending', 'notes': body.get('notes', ''),
            'created_by': user['name'], 'created_at': now(), 'updated_at': now()
        }
        await db.buyer_shipments.insert_one(master_shipment)
    else:
        shipment_id = master_shipment['id']
    existing_items = await db.buyer_shipment_items.find({'shipment_id': shipment_id}).to_list(None)
    max_dispatch = max((i.get('dispatch_seq', 1) for i in existing_items), default=0)
    dispatch_seq = max_dispatch + 1
    dispatch_date = parse_date(body.get('shipment_date')) or now()
    items_data = body.get('items', [])

    # ─── VALIDATION GUARDRAILS (Phase A — C-1 & M-1) ──────────────────────
    # Reject 0-qty dispatches (M-1): require at least one item with qty_shipped > 0
    total_qty_in_request = sum(int(i.get('qty_shipped', 0) or 0) for i in items_data)
    if total_qty_in_request <= 0:
        raise HTTPException(400, 'Dispatch harus memiliki minimal 1 pcs barang dikirim')
    # Cap qty_shipped against total produced (C-1): supports overproduction,
    # blocks phantom/ghost shipments. Cumulative across all dispatches.
    for item in items_data:
        po_item_id = item.get('po_item_id')
        qty_req = int(item.get('qty_shipped', 0) or 0)
        if qty_req < 0:
            raise HTTPException(400, f'qty_shipped tidak boleh negatif')
        if po_item_id and qty_req > 0:
            # Sum all produced for this po_item (all jobs + child jobs)
            all_job_items = await db.production_job_items.find({'po_item_id': po_item_id}).to_list(None)
            total_produced = sum(int(ji.get('produced_qty', 0) or 0) for ji in all_job_items)
            # Sum already shipped for this po_item (exclude current dispatch — none yet)
            all_bs_items = await db.buyer_shipment_items.find({'po_item_id': po_item_id}).to_list(None)
            total_already_shipped = sum(int(bi.get('qty_shipped', 0) or 0) for bi in all_bs_items)
            if total_already_shipped + qty_req > total_produced:
                sku = (await db.po_items.find_one({'id': po_item_id}) or {}).get('sku', '')
                raise HTTPException(400,
                    f'Qty kirim ke buyer untuk {sku} ({total_already_shipped + qty_req}) melebihi qty diproduksi ({total_produced}). '
                    f'Maksimal kirim: {max(0, total_produced - total_already_shipped)} pcs.')

    inserted_items = []
    for item in items_data:
        po_item = await db.po_items.find_one({'id': item.get('po_item_id')}) if item.get('po_item_id') else None
        si = {
            'id': new_id(), 'shipment_id': shipment_id,
            'dispatch_seq': dispatch_seq, 'dispatch_date': dispatch_date,
            'po_item_id': item.get('po_item_id'), 'job_item_id': item.get('job_item_id'),
            'job_id': job_id,
            'product_name': (po_item or {}).get('product_name', item.get('product_name', '')),
            'serial_number': (po_item or {}).get('serial_number', item.get('serial_number', '')),
            'size': (po_item or {}).get('size', item.get('size', '')),
            'color': (po_item or {}).get('color', item.get('color', '')),
            'sku': (po_item or {}).get('sku', item.get('sku', '')),
            'ordered_qty': int(item.get('ordered_qty', 0) or 0),
            'qty_shipped': int(item.get('qty_shipped', 0) or 0), 'created_at': now()
        }
        await db.buyer_shipment_items.insert_one(si)
        inserted_items.append(si)
    all_items = await db.buyer_shipment_items.find({'shipment_id': shipment_id}).to_list(None)
    any_shipped = any(i.get('qty_shipped', 0) > 0 for i in all_items)
    ship_status = 'Partially Shipped' if any_shipped else 'Pending'
    await db.buyer_shipments.update_one({'id': shipment_id}, {'$set': {
        'ship_status': ship_status, 'last_dispatch': dispatch_date,
        'last_dispatch_seq': dispatch_seq, 'updated_at': now()
    }})
    await log_activity(user['id'], user['name'], 'Create' if is_new else 'Add Dispatch', 'Buyer Shipment', f"Buyer shipment - {ship_status}")
    result = serialize_doc(master_shipment)
    result.update({'ship_status': ship_status, 'dispatch_seq': dispatch_seq, 'is_new': is_new, 'items': serialize_doc(inserted_items)})
    return JSONResponse(result, status_code=201 if is_new else 200)

@api.put("/buyer-shipments/{bsid}")
async def update_buyer_shipment(bsid: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None); body.pop('items', None)
    await db.buyer_shipments.update_one({'id': bsid}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.buyer_shipments.find_one({'id': bsid}, {'_id': 0}))

@api.delete("/buyer-shipments/{bsid}")
async def delete_buyer_shipment(bsid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.buyer_shipments.find_one({'id': bsid})
    if not doc: raise HTTPException(404, 'Not found')
    await db.buyer_shipment_items.delete_many({'shipment_id': bsid})
    await db.buyer_shipments.delete_one({'id': bsid})
    return {'success': True}

@api.get("/buyer-shipment-dispatches")
async def get_dispatches(request: Request):
    await require_auth(request)
    db = get_db()
    sid = request.query_params.get('shipment_id')
    if not sid: raise HTTPException(400, 'shipment_id required')
    items = await db.buyer_shipment_items.find({'shipment_id': sid}, {'_id': 0}).sort([('dispatch_seq', 1), ('created_at', 1)]).to_list(None)
    dm = {}
    for item in items:
        seq = item.get('dispatch_seq', 1)
        if seq not in dm:
            dm[seq] = {'dispatch_seq': seq, 'dispatch_date': item.get('dispatch_date') or item.get('created_at'), 'items': [], 'total_qty': 0}
        dm[seq]['items'].append(serialize_doc(item))
        dm[seq]['total_qty'] += item.get('qty_shipped', 0)
    return sorted(dm.values(), key=lambda d: d['dispatch_seq'])

# ─── INVOICES ────────────────────────────────────────────────────────────────
@api.get("/invoices")
async def get_invoices(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('garment_id'): query['garment_id'] = sp['garment_id']
    if sp.get('type') == 'vendor': query['invoice_category'] = 'VENDOR'
    elif sp.get('type') == 'customer': query['invoice_category'] = 'BUYER'
    if sp.get('category'): query['invoice_category'] = sp['category']
    if sp.get('invoice_type'): query['invoice_type'] = sp['invoice_type']
    if sp.get('date_from') or sp.get('date_to'):
        query['created_at'] = {}
        if sp.get('date_from'): query['created_at']['$gte'] = parse_date(sp['date_from'])
        if sp.get('date_to'): query['created_at']['$lte'] = to_end_of_day(sp['date_to'])
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'invoice_number': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
            {'customer_name': {'$regex': search, '$options': 'i'}},
            {'vendor_name': {'$regex': search, '$options': 'i'}},
        ]
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'invoice_number', 'status',
                                 'total_amount', 'invoice_category', 'po_number'})
    total = await db.invoices.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    cursor = db.invoices.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit)
    docs = await cursor.to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.get("/invoices/{inv_id}")
async def get_invoice(inv_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    inv = await db.invoices.find_one({'id': inv_id}, {'_id': 0})
    if not inv: raise HTTPException(404, 'Not found')
    payments = await db.payments.find({'invoice_id': inv_id}, {'_id': 0}).to_list(None)
    adjustments = await db.invoice_adjustments.find({'invoice_id': inv_id}, {'_id': 0}).sort('created_at', -1).to_list(None)
    total_add = sum(a.get('amount', 0) for a in adjustments if a.get('adjustment_type') == 'ADD')
    total_deduct = sum(a.get('amount', 0) for a in adjustments if a.get('adjustment_type') == 'DEDUCT')
    base_amount = inv.get('base_amount', inv.get('total_amount', 0))
    adjusted_total = base_amount + total_add - total_deduct
    result = serialize_doc(inv)
    result.update({'payments': serialize_doc(payments), 'adjustments': serialize_doc(adjustments),
                   'base_amount': base_amount, 'adjusted_total': adjusted_total})
    return result

@api.post("/invoices")
async def create_invoice(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin', 'finance']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    po_id = body.get('source_po_id')
    if not po_id: raise HTTPException(400, 'source_po_id wajib diisi')
    po = await db.production_pos.find_one({'id': po_id})
    if not po: raise HTTPException(404, 'PO tidak ditemukan')
    category = body.get('invoice_category')
    if category not in ['VENDOR', 'BUYER']: raise HTTPException(400, 'invoice_category harus VENDOR atau BUYER')
    
    # Generate invoice number with PO number
    po_number = po.get('po_number', 'UNKNOWN')
    revision = body.get('revision_number', 0) or 0
    prefix = 'INV-VND' if category == 'VENDOR' else 'INV-BYR'
    inv_number = f"{prefix}-{po_number}-R{revision}"
    
    # Check if invoice number already exists (should be unique)
    existing = await db.invoices.find_one({'invoice_number': inv_number})
    if existing:
        # Increment revision if duplicate
        revision += 1
        inv_number = f"{prefix}-{po_number}-R{revision}"
    
    items = body.get('invoice_items', [])
    recalc_items = []
    for it in items:
        price = it.get('cmt_price', 0) if category == 'VENDOR' else it.get('selling_price', 0)
        qty = it.get('invoice_qty', it.get('qty', 0))
        recalc_items.append({**it, 'invoice_qty': qty, 'subtotal': qty * price})
    total_amount = sum(i['subtotal'] for i in recalc_items) - float(body.get('discount', 0) or 0)
    invoice = {
        'id': new_id(), 'invoice_number': inv_number, 'invoice_type': 'MANUAL',
        'invoice_category': category, 'source_po_id': po_id, 'po_number': po.get('po_number'),
        'vendor_or_customer_id': po.get('vendor_id') if category == 'VENDOR' else None,
        'vendor_or_customer_name': po.get('vendor_name', '') if category == 'VENDOR' else po.get('customer_name', ''),
        'garment_id': po.get('vendor_id'), 'garment_name': po.get('vendor_name', ''),
        'vendor_id': po.get('vendor_id'), 'vendor_name': po.get('vendor_name', ''),
        'customer_name': po.get('customer_name', ''),
        'invoice_items': recalc_items, 'total_amount': total_amount,
        'paid_amount': 0, 'total_paid': 0, 'remaining_balance': total_amount,
        'status': 'Unpaid', 'revision_number': revision,
        'discount': float(body.get('discount', 0) or 0), 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.invoices.insert_one(invoice)
    await log_activity(user['id'], user['name'], 'Create Manual Invoice', 'Invoice', f"Manual {category} invoice {inv_number}")
    return JSONResponse(serialize_doc(invoice), status_code=201)

@api.put("/invoices/{inv_id}")
async def update_invoice(inv_id: str, request: Request):
    user = await require_auth(request)
    # Check permission: superadmin always allowed, or check invoice.update permission
    if user.get('role') != 'superadmin':
        if not (user.get('role') in ['admin', 'finance'] or 'invoice.update' in user.get('_permissions', [])):
            raise HTTPException(403, 'Forbidden: Tidak memiliki permission untuk edit invoice')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None)
    await db.invoices.update_one({'id': inv_id}, {'$set': {**body, 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Update', 'Invoice', f"Updated invoice {body.get('invoice_number', inv_id)}")
    return serialize_doc(await db.invoices.find_one({'id': inv_id}, {'_id': 0}))

@api.delete("/invoices/{inv_id}")
async def delete_invoice(inv_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.invoices.find_one({'id': inv_id})
    if not doc: raise HTTPException(404, 'Not found')
    await db.payments.delete_many({'invoice_id': inv_id})
    await db.invoice_adjustments.delete_many({'invoice_id': inv_id})
    await db.invoices.delete_one({'id': inv_id})
    return {'success': True}

# ─── INVOICE ADJUSTMENTS ─────────────────────────────────────────────────────
@api.get("/invoice-adjustments")
async def get_adjustments(request: Request):
    await require_auth(request)
    db = get_db()
    inv_id = request.query_params.get('invoice_id')
    if not inv_id: raise HTTPException(400, 'invoice_id required')
    return serialize_doc(await db.invoice_adjustments.find({'invoice_id': inv_id}, {'_id': 0}).sort('created_at', -1).to_list(None))

@api.post("/invoice-adjustments")
async def create_adjustment(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin', 'finance', 'superadmin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    if not body.get('invoice_id'): raise HTTPException(400, 'invoice_id wajib diisi')
    if body.get('adjustment_type') not in ['ADD', 'DEDUCT']: raise HTTPException(400, 'adjustment_type harus ADD atau DEDUCT')
    if not body.get('amount') or float(body['amount']) <= 0: raise HTTPException(400, 'amount harus lebih dari 0')
    if not body.get('reason'): raise HTTPException(400, 'reason wajib diisi')
    invoice = await db.invoices.find_one({'id': body['invoice_id']})
    if not invoice: raise HTTPException(404, 'Invoice not found')
    adjustment = {
        'id': new_id(), 'invoice_id': body['invoice_id'],
        'invoice_number': invoice.get('invoice_number'),
        'adjustment_type': body['adjustment_type'], 'amount': float(body['amount']),
        'reason': body.get('reason', ''), 'notes': body.get('notes', ''),
        'reference_event': body.get('reference_event', ''),
        'created_by': user['name'], 'created_at': now()
    }
    await db.invoice_adjustments.insert_one(adjustment)
    all_adj = await db.invoice_adjustments.find({'invoice_id': body['invoice_id']}).to_list(None)
    total_add = sum(a.get('amount', 0) for a in all_adj if a.get('adjustment_type') == 'ADD')
    total_deduct = sum(a.get('amount', 0) for a in all_adj if a.get('adjustment_type') == 'DEDUCT')
    base_amount = invoice.get('base_amount', invoice.get('total_amount', 0))
    new_total = base_amount + total_add - total_deduct
    new_status = 'Paid' if (invoice.get('total_paid', 0)) >= new_total else ('Partial' if (invoice.get('total_paid', 0)) > 0 else 'Unpaid')
    await db.invoices.update_one({'id': body['invoice_id']}, {'$set': {
        'base_amount': base_amount, 'total_amount': new_total,
        'remaining_balance': new_total - (invoice.get('total_paid', 0)),
        'status': new_status, 'updated_at': now()
    }})
    return JSONResponse(serialize_doc(adjustment), status_code=201)

@api.delete("/invoice-adjustments/{adj_id}")
async def delete_adjustment(adj_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.invoice_adjustments.find_one({'id': adj_id})
    if not doc: raise HTTPException(404, 'Not found')
    await db.invoice_adjustments.delete_one({'id': adj_id})
    invoice = await db.invoices.find_one({'id': doc.get('invoice_id')})
    if invoice:
        all_adj = await db.invoice_adjustments.find({'invoice_id': doc['invoice_id']}).to_list(None)
        total_add = sum(a.get('amount', 0) for a in all_adj if a.get('adjustment_type') == 'ADD')
        total_deduct = sum(a.get('amount', 0) for a in all_adj if a.get('adjustment_type') == 'DEDUCT')
        base_amount = invoice.get('base_amount', invoice.get('total_amount', 0))
        new_total = base_amount + total_add - total_deduct
        await db.invoices.update_one({'id': doc['invoice_id']}, {'$set': {
            'total_amount': new_total, 'remaining_balance': new_total - (invoice.get('total_paid', 0)), 'updated_at': now()
        }})
    return {'success': True}

# ─── INVOICE EDIT REQUESTS (APPROVAL SYSTEM) ─────────────────────────────────
@api.get("/invoice-edit-requests")
async def get_invoice_edit_requests(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['superadmin', 'admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('invoice_id'): query['invoice_id'] = sp['invoice_id']
    if sp.get('q'):
        q = sp['q']
        query['$or'] = [
            {'invoice_number': {'$regex': q, '$options': 'i'}},
            {'requested_by': {'$regex': q, '$options': 'i'}},
            {'change_summary': {'$regex': q, '$options': 'i'}}
        ]
    if sp.get('from') or sp.get('to'):
        query['requested_at'] = {}
        if sp.get('from'): query['requested_at']['$gte'] = parse_date(sp['from'])
        if sp.get('to'): query['requested_at']['$lte'] = to_end_of_day(sp['to'])
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'requested_at', 'desc',
                        allowed={'requested_at', 'status', 'invoice_number', 'requested_by'})
    total = await db.invoice_edit_requests.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    cursor = db.invoice_edit_requests.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit)
    docs = await cursor.to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.get("/invoice-edit-requests/{req_id}")
async def get_invoice_edit_request(req_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['superadmin', 'admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    req = await db.invoice_edit_requests.find_one({'id': req_id}, {'_id': 0})
    if not req: raise HTTPException(404, 'Request not found')
    return serialize_doc(req)

@api.post("/invoice-edit-requests")
async def create_invoice_edit_request(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['superadmin', 'admin']): raise HTTPException(403, 'Forbidden: Hanya Admin yang bisa mengajukan request edit')
    db = get_db()
    body = await request.json()
    invoice_id = body.get('invoice_id')
    if not invoice_id: raise HTTPException(400, 'invoice_id wajib diisi')
    
    # Get current invoice
    invoice = await db.invoices.find_one({'id': invoice_id})
    if not invoice: raise HTTPException(404, 'Invoice tidak ditemukan')
    if invoice.get('status') == 'Superseded': raise HTTPException(400, 'Tidak bisa mengedit invoice yang sudah Superseded')
    
    # Check if there's already a pending request for this invoice
    existing_pending = await db.invoice_edit_requests.find_one({
        'invoice_id': invoice_id,
        'status': 'Pending'
    })
    if existing_pending:
        raise HTTPException(400, f"Sudah ada request edit pending untuk invoice {invoice.get('invoice_number')}. Tunggu hingga di-approve/reject terlebih dahulu.")
    
    # Prepare changes (what user wants to change)
    changes_requested = body.get('changes_requested', {})
    if not changes_requested:
        raise HTTPException(400, 'changes_requested wajib diisi (object berisi field yang ingin diubah)')
    
    # Create before snapshot (current state)
    before_snapshot = {
        'invoice_items': invoice.get('invoice_items', []),
        'discount': invoice.get('discount', 0),
        'notes': invoice.get('notes', ''),
        'total_amount': invoice.get('total_amount', 0)
    }
    
    # Create after snapshot (proposed state) - merge current with changes
    after_snapshot = {**before_snapshot, **changes_requested}
    
    # Generate change summary
    change_summary = body.get('change_summary', 'Edit invoice items/fields')
    
    edit_request = {
        'id': new_id(),
        'invoice_id': invoice_id,
        'invoice_number': invoice.get('invoice_number'),
        'invoice_category': invoice.get('invoice_category'),
        'po_number': invoice.get('po_number'),
        'status': 'Pending',
        'requested_by': user['email'],
        'requested_by_name': user['name'],
        'requested_at': now(),
        'approved_by': None,
        'approved_by_name': None,
        'approved_at': None,
        'approval_notes': '',
        'changes_requested': changes_requested,
        'before_snapshot': before_snapshot,
        'after_snapshot': after_snapshot,
        'change_summary': change_summary,
        'created_at': now(),
        'updated_at': now()
    }
    
    await db.invoice_edit_requests.insert_one(edit_request)
    await log_activity(user['id'], user['name'], 'Request Invoice Edit', 'Invoice Approval', 
                      f"Request edit untuk invoice {invoice.get('invoice_number')}")
    return JSONResponse(serialize_doc(edit_request), status_code=201)

@api.put("/invoice-edit-requests/{req_id}/approve")
async def approve_invoice_edit_request(req_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['superadmin', 'admin']): raise HTTPException(403, 'Forbidden: Hanya Superadmin/Admin yang bisa approve')
    db = get_db()
    body = await request.json()
    
    # Get request
    edit_req = await db.invoice_edit_requests.find_one({'id': req_id})
    if not edit_req: raise HTTPException(404, 'Request tidak ditemukan')
    if edit_req.get('status') != 'Pending':
        raise HTTPException(400, f"Request sudah {edit_req.get('status')}. Tidak bisa approve lagi.")
    
    # Get invoice
    invoice = await db.invoices.find_one({'id': edit_req['invoice_id']})
    if not invoice: raise HTTPException(404, 'Invoice tidak ditemukan')
    
    # Prepare update payload from changes_requested
    changes = edit_req.get('changes_requested', {})
    update_payload = {**changes, 'updated_at': now()}
    
    # If invoice_items changed, recalculate total
    if 'invoice_items' in changes:
        items = changes['invoice_items']
        category = invoice.get('invoice_category')
        recalc_items = []
        for it in items:
            price = float(it.get('cmt_price', 0) or 0) if category == 'VENDOR' else float(it.get('selling_price', 0) or 0)
            qty = float(it.get('invoice_qty', it.get('qty', 0)) or 0)
            subtotal = qty * price
            recalc_items.append({**it, 'invoice_qty': qty, 'subtotal': subtotal})
        total_amount = sum(i['subtotal'] for i in recalc_items) - float(changes.get('discount', invoice.get('discount', 0)) or 0)
        update_payload['invoice_items'] = recalc_items
        update_payload['total_amount'] = total_amount
        update_payload['remaining_balance'] = total_amount - float(invoice.get('total_paid', 0) or 0)
        # Update status based on payment
        if float(invoice.get('total_paid', 0) or 0) >= total_amount:
            update_payload['status'] = 'Paid'
        elif float(invoice.get('total_paid', 0) or 0) > 0:
            update_payload['status'] = 'Partial'
        else:
            update_payload['status'] = 'Unpaid'
    
    # Update invoice
    await db.invoices.update_one({'id': edit_req['invoice_id']}, {'$set': update_payload})
    
    # Create change history record
    history = {
        'id': new_id(),
        'invoice_id': edit_req['invoice_id'],
        'invoice_number': invoice.get('invoice_number'),
        'changed_by': user['email'],
        'changed_by_name': user['name'],
        'changed_at': now(),
        'change_type': 'EDIT_APPROVAL',
        'old_values': edit_req.get('before_snapshot', {}),
        'new_values': edit_req.get('after_snapshot', {}),
        'approval_request_id': req_id,
        'notes': body.get('approval_notes', '')
    }
    await db.invoice_change_history.insert_one(history)
    
    # Update request status
    await db.invoice_edit_requests.update_one({'id': req_id}, {'$set': {
        'status': 'Approved',
        'approved_by': user['email'],
        'approved_by_name': user['name'],
        'approved_at': now(),
        'approval_notes': body.get('approval_notes', ''),
        'updated_at': now()
    }})
    
    await log_activity(user['id'], user['name'], 'Approve Invoice Edit', 'Invoice Approval',
                      f"Approved edit untuk invoice {invoice.get('invoice_number')}")
    
    return {'success': True, 'message': 'Request approved dan invoice berhasil diupdate'}

@api.put("/invoice-edit-requests/{req_id}/reject")
async def reject_invoice_edit_request(req_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['superadmin', 'admin']): raise HTTPException(403, 'Forbidden: Hanya Superadmin/Admin yang bisa reject')
    db = get_db()
    body = await request.json()
    
    # Get request
    edit_req = await db.invoice_edit_requests.find_one({'id': req_id})
    if not edit_req: raise HTTPException(404, 'Request tidak ditemukan')
    if edit_req.get('status') != 'Pending':
        raise HTTPException(400, f"Request sudah {edit_req.get('status')}. Tidak bisa reject lagi.")
    
    # Update request status
    await db.invoice_edit_requests.update_one({'id': req_id}, {'$set': {
        'status': 'Rejected',
        'approved_by': user['email'],
        'approved_by_name': user['name'],
        'approved_at': now(),
        'approval_notes': body.get('approval_notes', 'Request ditolak'),
        'updated_at': now()
    }})
    
    await log_activity(user['id'], user['name'], 'Reject Invoice Edit', 'Invoice Approval',
                      f"Rejected edit request untuk invoice {edit_req.get('invoice_number')}")
    
    return {'success': True, 'message': 'Request rejected'}

# ─── INVOICE CHANGE HISTORY ──────────────────────────────────────────────────
@api.get("/invoices/{invoice_id}/change-history")
async def get_invoice_change_history(invoice_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['superadmin', 'admin', 'finance']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    history = await db.invoice_change_history.find({'invoice_id': invoice_id}, {'_id': 0}).sort('changed_at', -1).to_list(None)
    return serialize_doc(history)


# ─── PAYMENTS ────────────────────────────────────────────────────────────────
@api.get("/payments")
async def get_payments(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('invoice_id'): query['invoice_id'] = sp['invoice_id']
    if sp.get('payment_type'): query['payment_type'] = sp['payment_type']
    if sp.get('date_from') or sp.get('date_to'):
        query['payment_date'] = {}
        if sp.get('date_from'): query['payment_date']['$gte'] = parse_date(sp['date_from'])
        if sp.get('date_to'): query['payment_date']['$lte'] = to_end_of_day(sp['date_to'])
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'invoice_number': {'$regex': search, '$options': 'i'}},
            {'reference_number': {'$regex': search, '$options': 'i'}},
            {'vendor_or_customer_name': {'$regex': search, '$options': 'i'}},
        ]
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'payment_date', 'desc',
                        allowed={'payment_date', 'created_at', 'amount', 'invoice_number',
                                 'payment_type'})
    total = await db.payments.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.payments.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.post("/payments")
async def create_payment(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin', 'finance']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    invoice = await db.invoices.find_one({'id': body.get('invoice_id')})
    if not invoice: raise HTTPException(404, 'Invoice not found')
    outstanding = (invoice.get('total_amount', 0)) - (invoice.get('total_paid', 0))
    amount = float(body.get('amount', 0) or 0)
    if amount <= 0: raise HTTPException(400, 'Jumlah pembayaran harus lebih dari 0')
    if amount > outstanding: raise HTTPException(400, f'Jumlah melebihi sisa tagihan! Maksimal: Rp {outstanding:,.0f}')
    payment_type = body.get('payment_type') or (
        'VENDOR_PAYMENT' if invoice.get('invoice_category') == 'VENDOR' else 'CUSTOMER_PAYMENT')
    payment = {
        'id': new_id(), 'invoice_id': body['invoice_id'],
        'invoice_number': invoice.get('invoice_number'),
        'payment_type': payment_type,
        'garment_id': invoice.get('garment_id'), 'garment_name': invoice.get('garment_name'),
        'vendor_or_customer_name': invoice.get('vendor_or_customer_name', invoice.get('vendor_name', invoice.get('customer_name', ''))),
        'payment_date': parse_date(body.get('payment_date')) or now(),
        'amount': amount, 'payment_method': body.get('payment_method', 'Transfer Bank'),
        'reference_number': body.get('reference_number', body.get('reference', '')),
        'notes': body.get('notes', ''), 'recorded_by': user['name'], 'created_at': now()
    }
    await db.payments.insert_one(payment)
    all_pmts = await db.payments.find({'invoice_id': body['invoice_id']}).to_list(None)
    total_paid = sum(p.get('amount', 0) for p in all_pmts)
    new_status = 'Paid' if total_paid >= invoice.get('total_amount', 0) else 'Partial'
    await db.invoices.update_one({'id': body['invoice_id']}, {'$set': {
        'status': new_status, 'total_paid': total_paid, 'paid_amount': total_paid,
        'remaining_balance': invoice.get('total_amount', 0) - total_paid, 'updated_at': now()
    }})
    return JSONResponse(serialize_doc(payment), status_code=201)

@api.delete("/payments/{pay_id}")
async def delete_payment(pay_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.payments.find_one({'id': pay_id})
    if not doc: raise HTTPException(404, 'Not found')
    await db.payments.delete_one({'id': pay_id})
    all_pmts = await db.payments.find({'invoice_id': doc.get('invoice_id')}).to_list(None)
    total_paid = sum(p.get('amount', 0) for p in all_pmts)
    invoice = await db.invoices.find_one({'id': doc.get('invoice_id')})
    if invoice:
        new_status = 'Unpaid' if total_paid <= 0 else ('Paid' if total_paid >= invoice.get('total_amount', 0) else 'Partial')
        await db.invoices.update_one({'id': doc['invoice_id']}, {'$set': {
            'status': new_status, 'total_paid': total_paid, 'updated_at': now()
        }})
    return {'success': True}

# ─── USERS ───────────────────────────────────────────────────────────────────
@api.get("/users")
async def get_users(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('role'): query['role'] = sp['role']
    if sp.get('status'): query['status'] = sp['status']
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'email': {'$regex': search, '$options': 'i'}},
        ]
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'name', 'email', 'role', 'status'})
    total = await db.users.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.users.find(query, {'password': 0, '_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.post("/users")
async def create_user(request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    hashed = hash_password(body.get('password', 'User@123'))
    new_user = {'id': new_id(), **body, 'password': hashed, 'status': 'active', 'created_at': now(), 'updated_at': now()}
    await db.users.insert_one(new_user)
    result = {k: v for k, v in new_user.items() if k != 'password'}
    return JSONResponse(serialize_doc(result), status_code=201)

@api.put("/users/{uid}")
async def update_user(uid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None)
    if body.get('password'): body['password'] = hash_password(body['password'])
    await db.users.update_one({'id': uid}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.users.find_one({'id': uid}, {'password': 0, '_id': 0}))

@api.delete("/users/{uid}")
async def delete_user(uid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.users.find_one({'id': uid})
    if not doc: raise HTTPException(404, 'Not found')
    if doc.get('role') == 'superadmin': raise HTTPException(403, 'Cannot delete superadmin')
    if doc['id'] == user['id']: raise HTTPException(403, 'Cannot delete own account')
    await db.users.delete_one({'id': uid})
    return {'success': True}

# ─── ACTIVITY LOGS ───────────────────────────────────────────────────────────
@api.get("/activity-logs")
async def get_activity_logs(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('module'): query['module'] = sp['module']
    if sp.get('user_id'): query['user_id'] = sp['user_id']  # filter by user
    if sp.get('action'): query['action'] = sp['action']
    if sp.get('date_from') or sp.get('date_to'):
        query['timestamp'] = {}
        if sp.get('date_from'): query['timestamp']['$gte'] = parse_date(sp['date_from'])
        if sp.get('date_to'): query['timestamp']['$lte'] = to_end_of_day(sp['date_to'])
    # Pagination (Phase 10A) — supports both new `page/per_page` and legacy `limit=`
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'timestamp', 'desc',
                        allowed={'timestamp', 'module', 'action', 'user_name'})
    if wants:
        total = await db.activity_logs.count_documents(query)
        docs = await db.activity_logs.find(query, {'_id': 0}).sort(sort).skip(skip).limit(per_page).to_list(per_page)
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    # Legacy mode — preserve old `limit` behaviour, default 100
    legacy_limit = min(int(sp.get('limit', '100')), LEGACY_DEFAULT_CAP)
    return serialize_doc(await db.activity_logs.find(query, {'_id': 0}).sort(sort).limit(legacy_limit).to_list(legacy_limit))

@api.delete("/activity-logs/{log_id}")
async def delete_activity_log(log_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    if log_id == 'all':
        await db.activity_logs.delete_many({})
    else:
        await db.activity_logs.delete_one({'id': log_id})
    return {'success': True}

# ─── COMPANY SETTINGS ────────────────────────────────────────────────────────
@api.get("/company-settings")
async def get_company_settings(request: Request):
    await require_auth(request)
    db = get_db()
    settings = await db.company_settings.find_one({'type': 'general'}, {'_id': 0})
    if not settings:
        settings = {
            'id': new_id(), 'type': 'general',
            'company_name': 'PT Garment ERP System', 'company_address': '',
            'company_phone': '', 'company_email': '', 'company_website': '',
            'company_logo_url': '', 'pdf_header_line1': '', 'pdf_header_line2': '',
            'pdf_footer_text': '', 'created_at': now(), 'updated_at': now()
        }
        await db.company_settings.insert_one(settings)
    return serialize_doc(settings)

@api.post("/company-settings")
async def save_company_settings(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    existing = await db.company_settings.find_one({'type': 'general'})
    data = {
        'company_name': body.get('company_name', ''), 'company_address': body.get('company_address', ''),
        'company_phone': body.get('company_phone', ''), 'company_email': body.get('company_email', ''),
        'company_website': body.get('company_website', ''), 'company_logo_url': body.get('company_logo_url', ''),
        'pdf_header_line1': body.get('pdf_header_line1', ''), 'pdf_header_line2': body.get('pdf_header_line2', ''),
        'pdf_footer_text': body.get('pdf_footer_text', ''),
        'updated_by': user['name'], 'updated_at': now()
    }
    if existing:
        await db.company_settings.update_one({'type': 'general'}, {'$set': data})
    else:
        await db.company_settings.insert_one({'id': new_id(), 'type': 'general', **data, 'created_at': now()})
    return serialize_doc(await db.company_settings.find_one({'type': 'general'}, {'_id': 0}))

# ─── MATERIAL REQUESTS ──────────────────────────────────────────────────────
@api.get("/material-requests")
async def get_material_requests(request: Request):
    user = await require_auth(request)
    db = get_db()
    query = {}
    sp = request.query_params
    if user.get('role') == 'vendor': query['vendor_id'] = user.get('vendor_id')
    if sp.get('request_type'): query['request_type'] = sp['request_type']
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('vendor_id'): query['vendor_id'] = sp['vendor_id']
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'request_type', 'status', 'po_number'})
    total = await db.material_requests.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.material_requests.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.post("/material-requests")
async def create_material_request(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    vendor_id = user.get('vendor_id') if user.get('role') == 'vendor' else body.get('vendor_id')
    if not vendor_id: raise HTTPException(400, 'vendor_id diperlukan')
    if body.get('request_type') not in ['ADDITIONAL', 'REPLACEMENT']: raise HTTPException(400, 'request_type harus ADDITIONAL atau REPLACEMENT')
    orig = await db.vendor_shipments.find_one({'id': body.get('original_shipment_id')}) if body.get('original_shipment_id') else None
    if not orig: raise HTTPException(404, 'Shipment asal tidak ditemukan')
    # Get PO number for request numbering
    po_number = body.get('po_number', '')
    po_id = body.get('po_id', '')
    if not po_number and po_id:
        po_doc = await db.production_pos.find_one({'id': po_id})
        if po_doc: po_number = po_doc.get('po_number', '')
    if not po_number:
        # Try to get from shipment items
        first_si = await db.vendor_shipment_items.find_one({'shipment_id': orig['id']})
        if first_si:
            po_number = first_si.get('po_number', '')
            if not po_id: po_id = first_si.get('po_id', '')
    # Count existing requests for THIS PO (not global)
    po_req_count = await db.material_requests.count_documents({'po_number': po_number, 'request_type': body['request_type']}) if po_number else await db.material_requests.count_documents({'request_type': body['request_type']})
    prefix = 'REQ-ADD' if body['request_type'] == 'ADDITIONAL' else 'REQ-RPL'
    req_number = f"{prefix}-{po_req_count + 1}-{po_number}" if po_number else f"{prefix}-{str(po_req_count + 1).zfill(4)}"
    items = body.get('items', [])
    # Use vendor notes as reason (adopt notes from form)
    reason = body.get('reason', '') or body.get('notes', '') or body.get('vendor_notes', '')
    req_doc = {
        'id': new_id(), 'request_number': req_number, 'request_type': body['request_type'],
        'vendor_id': vendor_id, 'vendor_name': orig.get('vendor_name', ''),
        'original_shipment_id': body['original_shipment_id'],
        'original_shipment_number': orig.get('shipment_number', ''),
        'po_id': po_id, 'po_number': po_number,
        'items': items,
        'total_requested_qty': sum(int(i.get('requested_qty', 0) or 0) for i in items),
        'reason': reason, 'vendor_notes': body.get('notes', ''), 'status': 'Pending',
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.material_requests.insert_one(req_doc)
    return JSONResponse(serialize_doc(req_doc), status_code=201)

@api.put("/material-requests/{req_id}")
async def update_material_request(req_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    req = await db.material_requests.find_one({'id': req_id})
    if not req: raise HTTPException(404, 'Request tidak ditemukan')
    new_status = body.get('status')
    if new_status == 'Approved' and req.get('status') == 'Pending':
        orig = await db.vendor_shipments.find_one({'id': req.get('original_shipment_id')})
        if not orig: raise HTTPException(404, 'Shipment asal tidak ditemukan')
        existing_children = await db.vendor_shipments.count_documents({
            'parent_shipment_id': req['original_shipment_id'], 'shipment_type': req['request_type']})
        suffix = f"A{existing_children + 1}" if req['request_type'] == 'ADDITIONAL' else f"R{existing_children + 1}"
        child_number = f"{orig.get('shipment_number')}-{suffix}"
        child_id = new_id()
        admin_notes = body.get('admin_notes', '')
        child_ship = {
            'id': child_id, 'shipment_number': child_number,
            'delivery_note_number': f"DN-{child_number}",
            'vendor_id': orig['vendor_id'], 'vendor_name': orig.get('vendor_name', ''),
            'shipment_date': now(), 'shipment_type': req['request_type'],
            'parent_shipment_id': req['original_shipment_id'],
            'material_request_id': req_id, 'status': 'Sent',
            'notes': admin_notes or f"Child shipment dari {orig.get('shipment_number')}",
            'notes_for_vendor': admin_notes,
            'created_by': user['name'], 'created_at': now(), 'updated_at': now()
        }
        await db.vendor_shipments.insert_one(child_ship)
        # Check if this is an accessories-only request
        is_accessories_request = req.get('category') == 'accessories'
        
        if is_accessories_request:
            # For accessories request, create accessory shipment items only
            for ri in req.get('items', []):
                await db.accessory_shipment_items.insert_one({
                    'id': new_id(), 'shipment_id': child_id, 'shipment_number': child_number,
                    'po_id': req.get('po_id'), 'po_number': req.get('po_number', ''),
                    'accessory_id': ri.get('accessory_id', ''),
                    'accessory_name': ri.get('accessory_name', ''),
                    'accessory_code': ri.get('accessory_code', ''),
                    'qty_sent': int(ri.get('requested_qty', 0) or 0),
                    'unit': ri.get('unit', 'pcs'),
                    'shipment_type': req['request_type'],
                    'parent_shipment_id': req['original_shipment_id'],
                    'created_at': now()
                })
        else:
            # For material request, create vendor shipment items
            # Get original shipment items to inherit serial numbers
            orig_items_map = {}
            orig_si_list = await db.vendor_shipment_items.find({'shipment_id': orig['id']}).to_list(None)
            for osi in orig_si_list:
                if osi.get('po_item_id'):
                    orig_items_map[osi['po_item_id']] = osi
            for ri in req.get('items', []):
                # Inherit serial_number from original shipment item or PO item
                serial = ri.get('serial_number', '')
                po_item_id = ri.get('po_item_id', '')
                if not serial and po_item_id:
                    # Try original shipment item
                    orig_si = orig_items_map.get(po_item_id, {})
                    serial = orig_si.get('serial_number', '')
                if not serial and po_item_id:
                    # Try PO item
                    poi = await db.po_items.find_one({'id': po_item_id})
                    if poi: serial = poi.get('serial_number', '')
                await db.vendor_shipment_items.insert_one({
                    'id': new_id(), 'shipment_id': child_id, 'shipment_number': child_number,
                    'po_id': req.get('po_id'), 'po_number': req.get('po_number', ''),
                    'po_item_id': po_item_id,
                    'product_name': ri.get('product_name', ''), 'sku': ri.get('sku', ''),
                    'size': ri.get('size', ''), 'color': ri.get('color', ''),
                    'serial_number': serial,
                    'qty_sent': int(ri.get('requested_qty', 0) or 0),
                    'shipment_type': req['request_type'],
                    'parent_shipment_id': req['original_shipment_id'],
                    'created_at': now()
                })
        await db.material_requests.update_one({'id': req_id}, {'$set': {
            'status': 'Approved', 'admin_notes': body.get('admin_notes', ''),
            'approved_by': user['name'], 'approved_at': now(),
            'child_shipment_id': child_id, 'child_shipment_number': child_number,
            'updated_at': now()
        }})
        result = serialize_doc(await db.material_requests.find_one({'id': req_id}, {'_id': 0}))
        result['child_shipment'] = serialize_doc(child_ship)
        return result
    elif new_status == 'Rejected':
        await db.material_requests.update_one({'id': req_id}, {'$set': {
            'status': 'Rejected', 'admin_notes': body.get('admin_notes', ''), 'updated_at': now()
        }})
        return serialize_doc(await db.material_requests.find_one({'id': req_id}, {'_id': 0}))
    body.pop('_id', None); body.pop('id', None)
    await db.material_requests.update_one({'id': req_id}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.material_requests.find_one({'id': req_id}, {'_id': 0}))

# ─── MATERIAL DEFECT REPORTS ─────────────────────────────────────────────────
@api.get("/material-defect-reports")
async def get_defect_reports(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if user.get('role') == 'vendor': query['vendor_id'] = user.get('vendor_id')
    if sp.get('vendor_id'): query['vendor_id'] = sp['vendor_id']
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('defect_type'): query['defect_type'] = sp['defect_type']
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'report_date', 'status', 'defect_type'})
    total = await db.material_defect_reports.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.material_defect_reports.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.post("/material-defect-reports")
async def create_defect_report(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    # ─── M-3 FIX: Derive vendor_id from job/job_item when admin calls without it ───
    # Vendor role: always uses user.vendor_id.
    # Admin role: accepts explicit vendor_id in body, OR derives from referenced job/job_item.
    vendor_id = user.get('vendor_id') if user.get('role') == 'vendor' else body.get('vendor_id')
    job_item = None
    if body.get('job_item_id'):
        job_item = await db.production_job_items.find_one({'id': body['job_item_id']})
    job_doc = None
    if body.get('job_id'):
        job_doc = await db.production_jobs.find_one({'id': body['job_id']})
    elif job_item and job_item.get('job_id'):
        job_doc = await db.production_jobs.find_one({'id': job_item['job_id']})
    if not vendor_id and job_doc:
        vendor_id = job_doc.get('vendor_id')
    if not vendor_id:
        raise HTTPException(400, 'vendor_id diperlukan (atau kirim job_id / job_item_id yang valid)')
    defect = {
        'id': new_id(), 'vendor_id': vendor_id,
        'job_id': body.get('job_id') or (job_item or {}).get('job_id'),
        'job_item_id': body.get('job_item_id'),
        'po_id': body.get('po_id'), 'po_item_id': body.get('po_item_id'),
        'sku': body.get('sku', (job_item or {}).get('sku', '')),
        'product_name': body.get('product_name', (job_item or {}).get('product_name', '')),
        'size': body.get('size', (job_item or {}).get('size', '')),
        'color': body.get('color', (job_item or {}).get('color', '')),
        'defect_qty': int(body.get('defect_qty', 0) or 0),
        'defect_type': body.get('defect_type', 'Material Cacat'),
        'description': body.get('description', ''),
        'shipment_id': body.get('shipment_id'),
        'report_date': parse_date(body.get('report_date')) or now(),
        'status': 'Reported', 'reported_by': user['name'],
        'created_at': now(), 'updated_at': now()
    }
    await db.material_defect_reports.insert_one(defect)
    return JSONResponse(serialize_doc(defect), status_code=201)

# ─── PRODUCTION RETURNS ──────────────────────────────────────────────────────
@api.get("/production-returns")
async def get_returns(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('po_id'): query['reference_po_id'] = sp['po_id']
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'return_number': {'$regex': search, '$options': 'i'}},
            {'vendor_name': {'$regex': search, '$options': 'i'}},
        ]
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'return_number', 'status'})
    total = await db.production_returns.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    returns = await db.production_returns.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)

    # ── Phase 10B: batch-fetch items ──
    ret_ids = [r['id'] for r in returns]
    if ret_ids:
        items_all = await db.production_return_items.find({'return_id': {'$in': ret_ids}}, {'_id': 0}).to_list(None)
    else:
        items_all = []
    items_by_ret = {}
    for it in items_all:
        items_by_ret.setdefault(it['return_id'], []).append(it)

    result = [{**serialize_doc(r), 'items': serialize_doc(items_by_ret.get(r['id'], []))} for r in returns]
    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result

@api.get("/production-returns/{ret_id}")
async def get_return(ret_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    ret = await db.production_returns.find_one({'id': ret_id}, {'_id': 0})
    if not ret: raise HTTPException(404, 'Not found')
    items = await db.production_return_items.find({'return_id': ret_id}, {'_id': 0}).to_list(None)
    result = serialize_doc(ret)
    result['items'] = serialize_doc(items)
    return result

@api.post("/production-returns")
async def create_return(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    return_id = new_id()
    seq = (await db.production_returns.count_documents({})) + 1
    return_number = f"RTN-{str(seq).zfill(4)}"
    ref_po = await db.production_pos.find_one({'id': body.get('reference_po_id')}) if body.get('reference_po_id') else None
    items_data = body.get('items', [])

    # ─── VALIDATION GUARDRAILS (Phase A — C-2 & H-4) ──────────────────────
    # Reject empty/negative returns and returns that exceed max_returnable
    if not items_data:
        raise HTTPException(400, 'Retur harus memiliki minimal 1 item')
    for item in items_data:
        try:
            qty = int(item.get('return_qty', 0) or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, 'return_qty harus bilangan bulat')
        if qty < 1:
            raise HTTPException(400, f'return_qty harus minimal 1 (diterima: {qty})')
        po_item_id = item.get('po_item_id')
        if po_item_id:
            # max_returnable = total_shipped - total_already_returned
            buyer_items = await db.buyer_shipment_items.find({'po_item_id': po_item_id}).to_list(None)
            total_shipped = sum(int(bi.get('qty_shipped', 0) or 0) for bi in buyer_items)
            prev_return_items = await db.production_return_items.find({'po_item_id': po_item_id}).to_list(None)
            total_already_returned = sum(int(ri.get('return_qty', 0) or 0) for ri in prev_return_items)
            max_returnable = max(0, total_shipped - total_already_returned)
            if qty > max_returnable:
                sku = item.get('sku') or (await db.po_items.find_one({'id': po_item_id}) or {}).get('sku', '')
                raise HTTPException(400,
                    f'Retur {sku}: qty {qty} melebihi maks yang bisa diretur ({max_returnable} pcs). '
                    f'Total dikirim ke buyer: {total_shipped}, sudah diretur: {total_already_returned}.')

    total_qty = sum(int(i.get('return_qty', 0) or 0) for i in items_data)
    return_doc = {
        'id': return_id, 'return_number': return_number,
        'reference_po_id': body.get('reference_po_id'),
        'reference_po_number': (ref_po or {}).get('po_number', body.get('reference_po_number', '')),
        'customer_name': body.get('customer_name', (ref_po or {}).get('customer_name', '')),
        'buyer_name': body.get('buyer_name', body.get('customer_name', '')),
        'return_date': parse_date(body.get('return_date')) or now(),
        'return_reason': body.get('return_reason', ''), 'notes': body.get('notes', ''),
        'status': 'Repair Needed', 'total_return_qty': total_qty,
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.production_returns.insert_one(return_doc)
    inserted_items = []
    for item in items_data:
        ri = {
            'id': new_id(), 'return_id': return_id,
            'po_item_id': item.get('po_item_id'),
            'sku': item.get('sku', ''), 'product_name': item.get('product_name', ''),
            'serial_number': item.get('serial_number', ''),
            'size': item.get('size', ''), 'color': item.get('color', ''),
            'return_qty': int(item.get('return_qty', 0) or 0),
            'defect_type': item.get('defect_type', ''),
            'repair_notes': item.get('repair_notes', ''), 'repaired_qty': 0,
            'created_at': now()
        }
        await db.production_return_items.insert_one(ri)
        inserted_items.append(ri)
    result = serialize_doc(return_doc)
    result['items'] = serialize_doc(inserted_items)
    return JSONResponse(result, status_code=201)

@api.put("/production-returns/{ret_id}")
async def update_return(ret_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None); body.pop('items', None)
    if body.get('return_date'): body['return_date'] = parse_date(body['return_date'])
    await db.production_returns.update_one({'id': ret_id}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.production_returns.find_one({'id': ret_id}, {'_id': 0}))

@api.delete("/production-returns/{ret_id}")
async def delete_return(ret_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.production_returns.find_one({'id': ret_id})
    if not doc: raise HTTPException(404, 'Not found')
    await db.production_return_items.delete_many({'return_id': ret_id})
    await db.production_returns.delete_one({'id': ret_id})
    return {'success': True}

# ─── DASHBOARD ───────────────────────────────────────────────────────────────
@api.get("/dashboard")
async def get_dashboard(request: Request):
    await require_auth(request)
    db = get_db()
    n = now()
    three_days = n + timedelta(days=3)
    # PO counts by status
    total_pos = await db.production_pos.count_documents({})
    po_status_counts = {}
    for st in ["Draft", "Confirmed", "Distributed", "In Production", "Production Complete",
               "Variance Review", "Return Review", "Ready to Close", "Closed"]:
        po_status_counts[st] = await db.production_pos.count_documents({'status': st})
    active_pos = po_status_counts.get('In Production', 0) + po_status_counts.get('Distributed', 0)
    garments_count = await db.garments.count_documents({'status': 'active'})
    products_count = await db.products.count_documents({})
    invoices = await db.invoices.find({}, {'_id': 0}).to_list(None)
    payments = await db.payments.find({}, {'_id': 0}).to_list(None)
    # Active jobs
    all_active_parent_jobs = await db.production_jobs.find({
        'status': 'In Progress',
        '$or': [{'parent_job_id': None}, {'parent_job_id': ''}, {'parent_job_id': {'$exists': False}}]
    }).to_list(None)
    active_jobs = len(all_active_parent_jobs)
    # Production stats
    all_job_items = await db.production_job_items.find({}).to_list(None)
    total_produced_global = sum(i.get('produced_qty', 0) for i in all_job_items)
    total_available_global = sum(i.get('available_qty', i.get('shipment_qty', 0)) for i in all_job_items)
    global_progress_pct = round((total_produced_global / total_available_global * 100) if total_available_global > 0 else 0)
    # Shipment & request counts
    pending_shipments = await db.vendor_shipments.count_documents({'status': {'$in': ['Sent', 'In Transit']}})
    pending_additional = await db.material_requests.count_documents({'request_type': 'ADDITIONAL', 'status': 'Pending'})
    pending_replacement = await db.material_requests.count_documents({'request_type': 'REPLACEMENT', 'status': 'Pending'})
    pending_returns = await db.production_returns.count_documents({'status': {'$nin': ['Shipped Back', 'Closed']}})
    total_buyer_shipments = await db.buyer_shipments.count_documents({})
    total_vendor_shipments = await db.vendor_shipments.count_documents({'shipment_type': 'NORMAL'})
    # Accessory stats
    total_accessories = await db.accessories.count_documents({'status': 'active'})
    total_acc_shipments = await db.accessory_shipments.count_documents({})
    pending_acc_inspections = await db.accessory_inspections.count_documents({'status': 'Pending'})
    pending_acc_requests = await db.accessory_requests.count_documents({'status': 'Pending'})
    # Financial
    all_adjustments = await db.invoice_adjustments.find({}).to_list(None)
    adj_map = {}
    for adj in all_adjustments:
        iid = adj.get('invoice_id')
        if iid not in adj_map: adj_map[iid] = {'add': 0, 'deduct': 0}
        if adj.get('adjustment_type') == 'ADD': adj_map[iid]['add'] += adj.get('amount', 0)
        else: adj_map[iid]['deduct'] += adj.get('amount', 0)
    def get_adj_total(inv):
        a = adj_map.get(inv['id'], {'add': 0, 'deduct': 0})
        return (inv.get('base_amount', inv.get('total_amount', 0))) + a['add'] - a['deduct']
    vendor_invs = [i for i in invoices if i.get('invoice_category') == 'VENDOR']
    customer_invs = [i for i in invoices if i.get('invoice_category') == 'BUYER']
    total_vendor_cost = sum(get_adj_total(i) for i in vendor_invs)
    total_revenue = sum(get_adj_total(i) for i in customer_invs)
    paid_by_inv = {}
    for p in payments:
        if p.get('invoice_id'):
            paid_by_inv[p['invoice_id']] = paid_by_inv.get(p['invoice_id'], 0) + p.get('amount', 0)
    total_invoiced_ar = sum(get_adj_total(i) for i in customer_invs)
    total_invoiced_ap = sum(get_adj_total(i) for i in vendor_invs)
    total_paid_ar = sum(paid_by_inv.get(i['id'], i.get('total_paid', 0)) for i in customer_invs)
    total_paid_ap = sum(paid_by_inv.get(i['id'], i.get('total_paid', 0)) for i in vendor_invs)
    outstanding_ar = total_invoiced_ar - total_paid_ar
    outstanding_ap = total_invoiced_ap - total_paid_ap
    # Delayed POs
    delayed_pos = await db.production_pos.count_documents({
        'status': {'$in': ['Draft', 'Distributed', 'In Production']},
        'deadline': {'$lt': n}
    })
    # Alerts
    overdue_pos = await db.production_pos.find({
        'status': {'$in': ['Draft', 'Distributed', 'In Production']}, 'deadline': {'$lt': n}
    }, {'_id': 0}).sort('deadline', 1).limit(5).to_list(None)
    near_deadline = await db.production_pos.find({
        'status': {'$in': ['Draft', 'Distributed', 'In Production']},
        'deadline': {'$gte': n, '$lt': three_days}
    }, {'_id': 0}).sort('deadline', 1).limit(5).to_list(None)
    unpaid_invs = await db.invoices.find({'status': {'$in': ['Unpaid', 'Partial']}}, {'_id': 0}).sort('created_at', 1).limit(5).to_list(None)
    # Monthly data (6 months) — ── 10E: 2 aggregations instead of 12 separate queries ──
    monthly_data = []
    monthly_start_base = datetime(n.year, n.month, 1, tzinfo=timezone.utc) - timedelta(days=5 * 30)
    monthly_start_base = monthly_start_base.replace(day=1)
    prog_monthly_agg = await db.production_progress.aggregate([
        {'$match': {'progress_date': {'$gte': monthly_start_base}}},
        {'$group': {'_id': {'year': {'$year': '$progress_date'}, 'month': {'$month': '$progress_date'}},
                    'total': {'$sum': '$completed_quantity'}}}
    ]).to_list(None)
    prog_monthly_map = {(g['_id']['year'], g['_id']['month']): g['total'] for g in prog_monthly_agg}
    pos_monthly_agg = await db.production_pos.aggregate([
        {'$match': {'created_at': {'$gte': monthly_start_base}}},
        {'$group': {'_id': {'year': {'$year': '$created_at'}, 'month': {'$month': '$created_at'}},
                    'count': {'$sum': 1}}}
    ]).to_list(None)
    pos_monthly_map = {(g['_id']['year'], g['_id']['month']): g['count'] for g in pos_monthly_agg}
    for i in range(5, -1, -1):
        start = datetime(n.year, n.month, 1, tzinfo=timezone.utc) - timedelta(days=i * 30)
        start = start.replace(day=1)
        monthly_data.append({
            'month': start.strftime('%b %y'),
            'pos': pos_monthly_map.get((start.year, start.month), 0),
            'production': prog_monthly_map.get((start.year, start.month), 0)
        })
    # Work order status distribution (use production_jobs since work_orders may be sparse)
    wo_status_agg = await db.production_jobs.aggregate([
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
    ]).to_list(None)
    # Top garments by production
    top_garments_agg = await db.production_job_items.aggregate([
        {'$group': {'_id': '$vendor_name', 'total_qty': {'$sum': '$produced_qty'}}},
        {'$sort': {'total_qty': -1}}, {'$limit': 5}
    ]).to_list(None)
    # If vendor_name is not on job_items, aggregate via jobs — ── 10E: $lookup instead of N queries ──
    if not top_garments_agg or all(not g.get('_id') for g in top_garments_agg):
        vendor_prod_agg = await db.production_job_items.aggregate([
            {'$group': {'_id': '$job_id', 'total_qty': {'$sum': '$produced_qty'}}},
            {'$lookup': {'from': 'production_jobs', 'localField': '_id', 'foreignField': 'id', 'as': 'job'}},
            {'$unwind': {'path': '$job', 'preserveNullAndEmptyArrays': True}},
            {'$group': {'_id': {'$ifNull': ['$job.vendor_name', 'Unknown']}, 'total_qty': {'$sum': '$total_qty'}}},
            {'$sort': {'total_qty': -1}}, {'$limit': 5}
        ]).to_list(None)
        top_garments_agg = vendor_prod_agg
    # PO status breakdown — ── 10E: single batch query for all status samples ──
    po_status_list = []
    active_statuses = [st for st, cnt in po_status_counts.items() if cnt > 0]
    all_status_samples = await db.production_pos.find(
        {'status': {'$in': active_statuses}}, {'_id': 0}
    ).sort('created_at', -1).limit(5 * len(active_statuses) if active_statuses else 1).to_list(None) if active_statuses else []
    samples_by_status: dict = {}
    for s_po in all_status_samples:
        st = s_po.get('status', '')
        if len(samples_by_status.get(st, [])) < 5:
            samples_by_status.setdefault(st, []).append(s_po)
    for st, cnt in po_status_counts.items():
        if cnt > 0:
            po_status_list.append({'status': st, 'count': cnt, 'samples': serialize_doc(samples_by_status.get(st, []))})
    # Reminders
    pending_reminders = await db.reminders.count_documents({'status': 'pending'})
    # On-time rate
    closed_pos = await db.production_pos.find({'status': 'Closed'}).to_list(None)
    on_time = sum(1 for p in closed_pos if p.get('deadline') and p.get('updated_at') and p['updated_at'] <= p['deadline'])
    on_time_rate = round((on_time / len(closed_pos) * 100) if closed_pos else 0)
    return {
        'totalPOs': total_pos, 'activePOs': active_pos, 'garments': garments_count,
        'products': products_count,
        'poStatusCounts': po_status_counts,
        'poStatusList': po_status_list,
        'totalInvoiced': total_invoiced_ar + total_invoiced_ap,
        'totalPaid': total_paid_ar + total_paid_ap,
        'outstanding': outstanding_ar + outstanding_ap,
        'totalVendorCost': total_vendor_cost, 'totalRevenue': total_revenue,
        'grossMargin': total_revenue - total_vendor_cost,
        'totalInvoicedAR': total_invoiced_ar, 'totalInvoicedAP': total_invoiced_ap,
        'outstandingAR': outstanding_ar, 'outstandingAP': outstanding_ap,
        'totalPaidAR': total_paid_ar, 'totalPaidAP': total_paid_ap,
        'activeJobs': active_jobs,
        'pendingShipments': pending_shipments,
        'pendingAdditionalRequests': pending_additional,
        'pendingReplacementRequests': pending_replacement,
        'pendingReturns': pending_returns,
        'totalBuyerShipments': total_buyer_shipments,
        'totalVendorShipments': total_vendor_shipments,
        'totalProducedGlobal': total_produced_global,
        'totalAvailableGlobal': total_available_global,
        'globalProgressPct': global_progress_pct,
        'totalAccessories': total_accessories,
        'totalAccShipments': total_acc_shipments,
        'pendingAccInspections': pending_acc_inspections,
        'pendingAccRequests': pending_acc_requests,
        'unpaidInvoices': sum(1 for i in invoices if i.get('status') == 'Unpaid'),
        'partialInvoices': sum(1 for i in invoices if i.get('status') == 'Partial'),
        'delayedPOs': delayed_pos,
        'monthlyData': monthly_data,
        'woStatus': wo_status_agg,
        'topGarments': top_garments_agg,
        'pendingReminders': pending_reminders,
        'onTimeRate': on_time_rate,
        'alerts': {
            'overduePos': serialize_doc(overdue_pos),
            'nearDeadlinePos': serialize_doc(near_deadline),
            'unpaidInvoices': serialize_doc(unpaid_invs)
        }
    }

@api.get("/dashboard/analytics")
async def get_dashboard_analytics(request: Request):
    """Enhanced analytics with date range filter"""
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    date_from = parse_date(sp.get('from'))
    date_to = to_end_of_day(sp.get('to'))
    date_filter = {}
    if date_from: date_filter['$gte'] = date_from
    if date_to: date_filter['$lte'] = date_to
    date_q = {'created_at': date_filter} if date_filter else {}
    # Vendor lead times (shipment sent → received)
    vendor_lead_times = []
    ships = await db.vendor_shipments.find({**date_q, 'status': 'Received', 'shipment_type': 'NORMAL'}, {'_id': 0}).to_list(None)
    vendor_lt_map = {}
    for s in ships:
        vn = s.get('vendor_name', 'Unknown')
        if s.get('shipment_date') and s.get('updated_at'):
            delta = (s['updated_at'] - s['shipment_date']).days if isinstance(s['updated_at'], datetime) and isinstance(s['shipment_date'], datetime) else 0
            if delta >= 0:
                if vn not in vendor_lt_map: vendor_lt_map[vn] = []
                vendor_lt_map[vn].append(delta)
    for vn, days_list in sorted(vendor_lt_map.items()):
        avg_lt = round(sum(days_list) / len(days_list), 1) if days_list else 0
        vendor_lead_times.append({'vendor': vn, 'avg_days': avg_lt, 'shipment_count': len(days_list)})
    # Missing/defect rates by vendor
    all_inspections = await db.vendor_material_inspections.find(date_q, {'_id': 0}).to_list(None)
    vendor_defect_map = {}
    for insp in all_inspections:
        vn = insp.get('vendor_name', 'Unknown')
        if vn not in vendor_defect_map: vendor_defect_map[vn] = {'received': 0, 'missing': 0}
        vendor_defect_map[vn]['received'] += insp.get('total_received', 0)
        vendor_defect_map[vn]['missing'] += insp.get('total_missing', 0)
    defect_rates = []
    for vn, vals in sorted(vendor_defect_map.items()):
        total = vals['received'] + vals['missing']
        rate = round((vals['missing'] / total * 100) if total > 0 else 0, 1)
        defect_rates.append({'vendor': vn, 'missing_rate': rate, 'total_received': vals['received'], 'total_missing': vals['missing']})
    # Production throughput by week — ── 10B-rem: single find instead of 8 aggregations ──
    weekly_throughput = []
    n = now()
    week_boundaries = []
    for w in range(7, -1, -1):
        start = n - timedelta(days=(w + 1) * 7)
        end   = n - timedelta(days=w * 7)
        week_boundaries.append({'w': 8 - w, 'start': start, 'end': end, 'label': start.strftime('%d/%m')})
    overall_start = week_boundaries[0]['start']
    overall_end   = week_boundaries[-1]['end']
    prog_docs = await db.production_progress.find(
        {'progress_date': {'$gte': overall_start, '$lt': overall_end}},
        {'_id': 0, 'progress_date': 1, 'completed_quantity': 1}
    ).to_list(None)
    for wb in week_boundaries:
        qty = sum(
            p.get('completed_quantity', 0) for p in prog_docs
            if wb['start'] <= (p.get('progress_date') or datetime.min.replace(tzinfo=timezone.utc)) < wb['end']
        )
        weekly_throughput.append({'week': f"W{wb['w']}", 'label': wb['label'], 'qty': qty})
    # Production completion rate by product
    product_completion = await db.production_job_items.aggregate([
        {'$group': {'_id': '$product_name', 'total_available': {'$sum': '$available_qty'}, 'total_produced': {'$sum': '$produced_qty'}}},
        {'$sort': {'total_available': -1}}, {'$limit': 10}
    ]).to_list(None)
    product_comp = [{'product': p['_id'] or 'Unknown',
                     'available': p.get('total_available', 0),
                     'produced': p.get('total_produced', 0),
                     'rate': round((p['total_produced'] / p['total_available'] * 100) if p.get('total_available', 0) > 0 else 0, 1)
                     } for p in product_completion]
    # Shipment status breakdown
    ship_status_agg = await db.vendor_shipments.aggregate([
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
    ]).to_list(None)
    # PO deadline distribution
    all_pos = await db.production_pos.find({'status': {'$nin': ['Closed', 'Draft']}}, {'_id': 0, 'deadline': 1, 'po_number': 1}).to_list(None)
    overdue_count = 0
    this_week_count = 0
    next_week_count = 0
    later_count = 0
    for p in all_pos:
        dl = p.get('deadline')
        if not dl: continue
        if isinstance(dl, str):
            dl = parse_date(dl)
        if not isinstance(dl, datetime): continue
        # Ensure timezone-aware comparison
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        if dl < n: overdue_count += 1
        elif dl < n + timedelta(days=7): this_week_count += 1
        elif dl < n + timedelta(days=14): next_week_count += 1
        else: later_count += 1
    return {
        'vendorLeadTimes': vendor_lead_times,
        'defectRates': defect_rates,
        'weeklyThroughput': weekly_throughput,
        'productCompletion': product_comp,
        'shipmentStatus': [{'status': s['_id'] or 'Unknown', 'count': s['count']} for s in ship_status_agg],
        'deadlineDistribution': {
            'overdue': overdue_count, 'thisWeek': this_week_count,
            'nextWeek': next_week_count, 'later': later_count
        }
    }

# ─── VENDOR DASHBOARD ────────────────────────────────────────────────────────
@api.get("/vendor/dashboard")
async def get_vendor_dashboard(request: Request):
    user = await require_auth(request)
    if user.get('role') != 'vendor': raise HTTPException(403, 'Forbidden')
    db = get_db()
    vendor_id = user.get('vendor_id')
    from datetime import date, timedelta
    today = date.today().isoformat()
    week_later = (date.today() + timedelta(days=7)).isoformat()

    # Jobs for this vendor
    jobs = await db.production_jobs.find({'vendor_id': vendor_id}, {'_id': 0}).sort('created_at', -1).to_list(None)
    parent_jobs = [j for j in jobs if not j.get('parent_job_id')]
    active_jobs = len([j for j in parent_jobs if j.get('status') == 'In Progress'])
    completed_jobs = len([j for j in parent_jobs if j.get('status') == 'Completed'])

    # Overdue: In Progress + deadline < today
    overdue_jobs = [j for j in parent_jobs if j.get('status') == 'In Progress' and j.get('deadline') and str(j.get('deadline',''))[:10] < today]
    near_deadline = [j for j in parent_jobs if j.get('status') == 'In Progress' and j.get('deadline')
                     and today <= str(j.get('deadline',''))[:10] <= week_later]

    # Shipments
    incoming = await db.vendor_shipments.count_documents({'vendor_id': vendor_id, 'status': 'Sent'})
    pending_inspections = await db.vendor_shipments.count_documents({'vendor_id': vendor_id, 'status': 'Confirmed'})

    # Production job items
    all_job_ids = [j['id'] for j in jobs]
    all_job_items = await db.production_job_items.find({'job_id': {'$in': all_job_ids}}).to_list(None) if all_job_ids else []
    total_produced = sum(i.get('produced_qty', 0) for i in all_job_items)
    total_available = sum(i.get('available_qty', i.get('shipment_qty', 0)) for i in all_job_items)

    # Material missing & defect: from shipment items for this vendor
    all_shipments = await db.vendor_shipments.find({'vendor_id': vendor_id}, {'_id': 0, 'id': 1}).to_list(None)
    shipment_ids = [s['id'] for s in all_shipments]
    ship_items = await db.vendor_shipment_items.find({'shipment_id': {'$in': shipment_ids}}).to_list(None) if shipment_ids else []
    total_missing = sum(max(0, (i.get('qty', 0) or 0) - (i.get('received_qty', i.get('qty', 0)) or 0)) for i in ship_items)
    total_defect = sum(i.get('defect_qty', 0) or 0 for i in ship_items)

    # Pending requests: additional material requests for this vendor's jobs
    pending_additional = await db.material_requests.count_documents({'vendor_id': vendor_id, 'request_type': 'additional', 'status': 'pending'}) if all_job_ids else 0
    pending_replacement = await db.material_requests.count_documents({'vendor_id': vendor_id, 'request_type': 'replacement', 'status': 'pending'}) if all_job_ids else 0

    # Buyer shipments total (vendor's dispatches)
    pending_buyer_shipments = await db.buyer_shipments.count_documents({'vendor_id': vendor_id})

    return {
        'activeJobs': active_jobs,
        'completedJobs': completed_jobs,
        'overdueJobs': len(overdue_jobs),
        'incomingShipments': incoming,
        'pendingInspections': pending_inspections,
        'totalProduced': total_produced,
        'totalAvailable': total_available,
        'progressPct': round((total_produced / total_available * 100) if total_available > 0 else 0),
        'totalMissing': total_missing,
        'totalDefect': total_defect,
        'pendingAdditional': pending_additional,
        'pendingReplacement': pending_replacement,
        'pendingBuyerShipments': pending_buyer_shipments,
        'recentProgress': [],
        'alerts': {
            'overdueJobs': serialize_doc(overdue_jobs[:5]),
            'nearDeadlineJobs': serialize_doc(near_deadline[:5])
        }
    }

# ─── GLOBAL SEARCH ───────────────────────────────────────────────────────────
@api.get("/global-search")
async def global_search(request: Request):
    await require_auth(request)
    db = get_db()
    q = request.query_params.get('q', '').strip()
    if not q: return {'results': []}
    regex = {'$regex': q, '$options': 'i'}
    pos = await db.production_pos.find({'$or': [{'po_number': regex}, {'customer_name': regex}]}).limit(5).to_list(None)
    vendors = await db.garments.find({'$or': [{'garment_name': regex}, {'garment_code': regex}]}).limit(5).to_list(None)
    products = await db.products.find({'$or': [{'product_name': regex}, {'product_code': regex}]}).limit(5).to_list(None)
    variants = await db.product_variants.find({'sku': regex}).limit(5).to_list(None)
    # Search by serial number
    serial_items = await db.po_items.find({'serial_number': regex}).limit(5).to_list(None)
    buyers = await db.buyers.find({'$or': [{'buyer_name': regex}, {'buyer_code': regex}]}).limit(5).to_list(None)
    results = (
        [{'type': 'PO', 'id': p['id'], 'label': p.get('po_number'), 'sub': p.get('customer_name'), 'module': 'production-po'} for p in pos] +
        [{'type': 'Vendor', 'id': v['id'], 'label': v.get('garment_name'), 'sub': v.get('garment_code'), 'module': 'garments'} for v in vendors] +
        [{'type': 'Produk', 'id': p['id'], 'label': p.get('product_name'), 'sub': p.get('product_code'), 'module': 'products'} for p in products] +
        [{'type': 'SKU', 'id': v['id'], 'label': v.get('sku'), 'sub': f"{v.get('size','')}/{v.get('color','')}", 'module': 'products'} for v in variants] +
        [{'type': 'Serial', 'id': s['id'], 'label': s.get('serial_number'), 'sub': f"{s.get('product_name','')} | {s.get('po_number','')}", 'module': 'serial-tracking'} for s in serial_items] +
        [{'type': 'Buyer', 'id': b['id'], 'label': b.get('buyer_name'), 'sub': b.get('buyer_code'), 'module': 'buyers'} for b in buyers]
    )
    return {'results': results}

# ─── ATTACHMENTS ─────────────────────────────────────────────────────────────
@api.get("/attachments")
async def get_attachments(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    entity_type = sp.get('entity_type')
    entity_id = sp.get('entity_id')
    if not entity_type or not entity_id: raise HTTPException(400, 'entity_type and entity_id required')
    return serialize_doc(await db.attachments.find({'entity_type': entity_type, 'entity_id': entity_id}, {'_id': 0}).sort('uploaded_at', -1).to_list(None))

# ─── FINANCIAL RECAP ─────────────────────────────────────────────────────────
@api.get("/financial-recap")
async def financial_recap(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    inv_query = {}
    pmt_query = {}
    if sp.get('date_from') or sp.get('date_to'):
        d_range = {}
        if sp.get('date_from'): d_range['$gte'] = parse_date(sp['date_from'])
        if sp.get('date_to'): d_range['$lte'] = to_end_of_day(sp['date_to'])
        inv_query['created_at'] = d_range
        pmt_query['payment_date'] = d_range
    invoices = await db.invoices.find(inv_query, {'_id': 0}).to_list(None)
    payments = await db.payments.find(pmt_query, {'_id': 0}).to_list(None)
    all_adj = await db.invoice_adjustments.find({}).to_list(None)
    adj_map = {}
    for adj in all_adj:
        iid = adj.get('invoice_id')
        if iid not in adj_map: adj_map[iid] = {'add': 0, 'deduct': 0}
        if adj.get('adjustment_type') == 'ADD': adj_map[iid]['add'] += adj.get('amount', 0)
        else: adj_map[iid]['deduct'] += adj.get('amount', 0)
    vendor_invs = [i for i in invoices if i.get('invoice_category') == 'VENDOR']
    buyer_invs = [i for i in invoices if i.get('invoice_category') == 'BUYER']
    def adj_total(inv):
        a = adj_map.get(inv['id'], {'add': 0, 'deduct': 0})
        return (inv.get('base_amount', inv.get('total_amount', 0))) + a['add'] - a['deduct']
    total_sales = sum(adj_total(i) for i in buyer_invs)
    total_cost = sum(adj_total(i) for i in vendor_invs)
    vendor_inv_ids = {i['id'] for i in vendor_invs}
    buyer_inv_ids  = {i['id'] for i in buyer_invs}
    vendor_pmts = [p for p in payments if p.get('payment_type') == 'VENDOR_PAYMENT' or p.get('invoice_id') in vendor_inv_ids]
    cust_pmts   = [p for p in payments if p.get('payment_type') == 'CUSTOMER_PAYMENT' or p.get('invoice_id') in buyer_inv_ids]
    total_cash_in = sum(p.get('amount', 0) for p in cust_pmts)
    total_cash_out = sum(p.get('amount', 0) for p in vendor_pmts)
    gross_margin = total_sales - total_cost
    return {
        'total_sales_value': total_sales, 'total_vendor_cost': total_cost,
        'total_cash_in': total_cash_in, 'total_cash_out': total_cash_out,
        'gross_margin': gross_margin,
        'gross_margin_pct': round((gross_margin / total_sales * 100) if total_sales > 0 else 0),
        'total_invoiced': total_sales + total_cost, 'total_paid': total_cash_in + total_cash_out,
        'total_outstanding': (total_sales - total_cash_in) + (total_cost - total_cash_out),
        'accounts_receivable_outstanding': total_sales - total_cash_in,
        'accounts_payable_outstanding': total_cost - total_cash_out,
        'total_vendor_invoices': len(vendor_invs), 'total_buyer_invoices': len(buyer_invs),
        'garment_summary': [], 'monthly_trend': [],
        'invoices': serialize_doc(invoices), 'payments': serialize_doc(payments)
    }

# ─── ACCOUNTS PAYABLE / RECEIVABLE ──────────────────────────────────────────
@api.get("/accounts-payable")
async def accounts_payable(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {'invoice_category': 'VENDOR'}
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('date_from') or sp.get('date_to'):
        query['created_at'] = {}
        if sp.get('date_from'): query['created_at']['$gte'] = parse_date(sp['date_from'])
        if sp.get('date_to'): query['created_at']['$lte'] = to_end_of_day(sp['date_to'])
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'invoice_number', 'status', 'total_amount'})
    total = await db.invoices.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.invoices.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.get("/accounts-receivable")
async def accounts_receivable(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {'invoice_category': 'BUYER'}
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('date_from') or sp.get('date_to'):
        query['created_at'] = {}
        if sp.get('date_from'): query['created_at']['$gte'] = parse_date(sp['date_from'])
        if sp.get('date_to'): query['created_at']['$lte'] = to_end_of_day(sp['date_to'])
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'invoice_number', 'status', 'total_amount'})
    total = await db.invoices.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.invoices.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

# ─── REPORTS ─────────────────────────────────────────────────────────────────
@api.get("/reports/{report_type}")
async def get_report(report_type: str, request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    if report_type == 'production':
        po_query = {}
        if sp.get('status'): po_query['status'] = sp['status']
        if sp.get('vendor_id'): po_query['vendor_id'] = sp['vendor_id']
        pos = await db.production_pos.find(po_query, {'_id': 0}).sort('created_at', -1).to_list(None)
        # ─── 10B-rem: batch-fetch po_items for all POs at once ───
        po_ids = [po['id'] for po in pos]
        all_items = await db.po_items.find({'po_id': {'$in': po_ids}}, {'_id': 0}).to_list(None) if po_ids else []
        items_by_po = {}
        for it in all_items:
            items_by_po.setdefault(it['po_id'], []).append(it)
        rows = []
        serial_filter = sp.get('serial_number')
        for po in pos:
            for item in items_by_po.get(po['id'], []):
                if serial_filter and item.get('serial_number') != serial_filter: continue
                rows.append({
                    'tanggal': serialize_doc(po.get('po_date', po.get('created_at'))),
                    'no_po': po.get('po_number'), 'no_seri': item.get('serial_number', ''),
                    'nama_produk': item.get('product_name', ''), 'sku': item.get('sku', ''),
                    'size': item.get('size', ''), 'warna': item.get('color', ''),
                    'output_qty': item.get('qty', 0),
                    'harga': item.get('selling_price_snapshot', 0), 'hpp': item.get('cmt_price_snapshot', 0),
                    'garment': po.get('vendor_name', ''), 'po_status': po.get('status'),
                })
        return rows
    if report_type == 'financial':
        inv_query = {}
        if sp.get('status'): inv_query['status'] = sp['status']
        invoices = await db.invoices.find(inv_query, {'_id': 0}).sort('created_at', -1).to_list(None)
        return serialize_doc(invoices)
    if report_type == 'shipment':
        # ── 10B-rem: push vendor_id filter to DB, then batch-fetch items in 2 queries ──
        vs_q = {'vendor_id': sp['vendor_id']} if sp.get('vendor_id') else {}
        bs_q = {'vendor_id': sp['vendor_id']} if sp.get('vendor_id') else {}
        vs = await db.vendor_shipments.find(vs_q, {'_id': 0}).sort('created_at', -1).to_list(None)
        bs = await db.buyer_shipments.find(bs_q, {'_id': 0}).sort('created_at', -1).to_list(None)
        vs_ids = [v['id'] for v in vs]
        bs_ids = [b['id'] for b in bs]
        vsi_all = await db.vendor_shipment_items.find({'shipment_id': {'$in': vs_ids}}).to_list(None) if vs_ids else []
        bsi_all = await db.buyer_shipment_items.find({'shipment_id': {'$in': bs_ids}}).to_list(None) if bs_ids else []
        vsi_by_ship: dict = {}
        for it in vsi_all: vsi_by_ship.setdefault(it.get('shipment_id'), []).append(it)
        bsi_by_ship: dict = {}
        for it in bsi_all: bsi_by_ship.setdefault(it.get('shipment_id'), []).append(it)
        rows = []
        for v in vs:
            items = vsi_by_ship.get(v['id'], [])
            rows.append({'direction': 'VENDOR → PRODUKSI', 'shipment_number': v.get('shipment_number'),
                         'shipment_type': v.get('shipment_type', 'NORMAL'),
                         'vendor_name': v.get('vendor_name', ''), 'status': v.get('status'),
                         'inspection_status': v.get('inspection_status', 'Pending'),
                         'date': serialize_doc(v.get('shipment_date', v.get('created_at'))),
                         'total_qty': sum(i.get('qty_sent', 0) for i in items), 'item_count': len(items)})
        for b in bs:
            items = bsi_by_ship.get(b['id'], [])
            rows.append({'direction': 'PRODUKSI → BUYER', 'shipment_number': b.get('shipment_number'),
                         'shipment_type': 'NORMAL', 'vendor_name': b.get('vendor_name', ''),
                         'status': b.get('status', b.get('ship_status', '')),
                         'date': serialize_doc(b.get('created_at')),
                         'total_qty': sum(i.get('qty_shipped', 0) for i in items), 'item_count': len(items)})
        return rows
    if report_type == 'progress':
        progs = await db.production_progress.find({}, {'_id': 0}).sort('progress_date', -1).to_list(None)
        # ─── 10B-rem: batch-fetch all referenced job_items + jobs ───
        ji_ids = list({p['job_item_id'] for p in progs if p.get('job_item_id')})
        job_ids = list({p['job_id'] for p in progs if p.get('job_id')})
        ji_docs = await db.production_job_items.find({'id': {'$in': ji_ids}}, {'_id': 0}).to_list(None) if ji_ids else []
        job_docs = await db.production_jobs.find({'id': {'$in': job_ids}}, {'_id': 0}).to_list(None) if job_ids else []
        ji_map = {d['id']: d for d in ji_docs}
        job_map = {d['id']: d for d in job_docs}
        rows = []
        vendor_filter = sp.get('vendor_id')
        for p in progs:
            ji = ji_map.get(p.get('job_item_id'), {}) if p.get('job_item_id') else {}
            job = job_map.get(p.get('job_id'), {}) if p.get('job_id') else {}
            if vendor_filter and job.get('vendor_id') != vendor_filter: continue
            rows.append({
                'date': serialize_doc(p.get('progress_date')),
                'job_number': job.get('job_number', ''),
                'po_number': job.get('po_number', ''),
                'vendor_name': job.get('vendor_name', ''),
                'serial_number': ji.get('serial_number', ''),
                'sku': ji.get('sku', p.get('sku', '')),
                'product_name': ji.get('product_name', p.get('product_name', '')),
                'qty_progress': p.get('completed_quantity', 0),
                'notes': p.get('notes', ''), 'recorded_by': p.get('recorded_by', '')
            })
        return rows
    if report_type == 'defect':
        defects = await db.material_defect_reports.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
        rows = []
        for d in defects:
            if sp.get('vendor_id') and d.get('vendor_id') != sp['vendor_id']: continue
            rows.append({
                'date': serialize_doc(d.get('report_date', d.get('created_at'))),
                'vendor_id': d.get('vendor_id'), 'sku': d.get('sku', ''),
                'product_name': d.get('product_name', ''),
                'size': d.get('size', ''), 'color': d.get('color', ''),
                'defect_qty': d.get('defect_qty', 0), 'defect_type': d.get('defect_type', ''),
                'description': d.get('description', ''), 'status': d.get('status', '')
            })
        return rows
    if report_type == 'return':
        returns = await db.production_returns.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
        # ─── 10B-rem: batch-aggregate return_items in 1 query ───
        ret_ids = [r['id'] for r in returns]
        ret_agg = await db.production_return_items.aggregate([
            {'$match': {'return_id': {'$in': ret_ids}}},
            {'$group': {'_id': '$return_id', 'qty': {'$sum': '$return_qty'}, 'cnt': {'$sum': 1}}},
        ]).to_list(None) if ret_ids else []
        ret_map = {a['_id']: a for a in ret_agg}
        rows = []
        for r in returns:
            agg = ret_map.get(r['id'], {'qty': 0, 'cnt': 0})
            rows.append({
                'return_number': r.get('return_number', ''),
                'po_number': r.get('reference_po_number', ''),
                'customer_name': r.get('customer_name', ''),
                'return_date': serialize_doc(r.get('return_date')),
                'total_qty': agg['qty'],
                'item_count': agg['cnt'], 'reason': r.get('return_reason', ''),
                'status': r.get('status', ''), 'notes': r.get('notes', '')
            })
        return rows
    if report_type == 'missing-material':
        reqs = await db.material_requests.find({'request_type': 'ADDITIONAL'}, {'_id': 0}).sort('created_at', -1).to_list(None)
        rows = []
        for r in reqs:
            if sp.get('vendor_id') and r.get('vendor_id') != sp['vendor_id']: continue
            rows.append({
                'request_number': r.get('request_number', ''), 'request_type': r.get('request_type'),
                'vendor_name': r.get('vendor_name', ''), 'po_number': r.get('po_number', ''),
                'total_requested_qty': r.get('total_requested_qty', 0),
                'reason': r.get('reason', ''), 'status': r.get('status', ''),
                'child_shipment_number': r.get('child_shipment_number', ''),
                'created_at': serialize_doc(r.get('created_at'))
            })
        return rows
    if report_type == 'replacement':
        reqs = await db.material_requests.find({'request_type': 'REPLACEMENT'}, {'_id': 0}).sort('created_at', -1).to_list(None)
        rows = []
        for r in reqs:
            if sp.get('vendor_id') and r.get('vendor_id') != sp['vendor_id']: continue
            rows.append({
                'request_number': r.get('request_number', ''), 'request_type': r.get('request_type'),
                'vendor_name': r.get('vendor_name', ''), 'po_number': r.get('po_number', ''),
                'total_requested_qty': r.get('total_requested_qty', 0),
                'reason': r.get('reason', ''), 'status': r.get('status', ''),
                'child_shipment_number': r.get('child_shipment_number', ''),
                'created_at': serialize_doc(r.get('created_at'))
            })
        return rows
    if report_type == 'accessory':
        # ── 10B-rem: push vendor_id filter to DB, batch-fetch items in 1 query ──
        acc_q = {'vendor_id': sp['vendor_id']} if sp.get('vendor_id') else {}
        acc_ships = await db.accessory_shipments.find(acc_q, {'_id': 0}).sort('created_at', -1).to_list(None)
        acc_ids = [s['id'] for s in acc_ships]
        all_acc_items = await db.accessory_shipment_items.find({'shipment_id': {'$in': acc_ids}}).to_list(None) if acc_ids else []
        acc_items_by_ship: dict = {}
        for it in all_acc_items: acc_items_by_ship.setdefault(it.get('shipment_id'), []).append(it)
        rows = []
        for s in acc_ships:
            for item in acc_items_by_ship.get(s['id'], []):
                rows.append({
                    'shipment_number': s.get('shipment_number', ''),
                    'vendor_name': s.get('vendor_name', ''), 'po_number': s.get('po_number', ''),
                    'date': serialize_doc(s.get('shipment_date')),
                    'accessory_name': item.get('accessory_name', ''), 'accessory_code': item.get('accessory_code', ''),
                    'qty_sent': item.get('qty_sent', 0), 'unit': item.get('unit', 'pcs'),
                    'status': s.get('status', ''), 'inspection_status': s.get('inspection_status', 'Pending')
                })
        return rows
    return {'error': 'Unknown report type', 'available_types': [
        'production', 'financial', 'shipment', 'progress', 'defect', 'return',
        'missing-material', 'replacement', 'accessory']}

# ─── PRODUCTION MONITORING V2 ────────────────────────────────────────────────
@api.get("/production-monitoring-v2")
async def production_monitoring(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    g_query = {'status': 'active'}
    if sp.get('vendor_id'): g_query['id'] = sp['vendor_id']
    garments = await db.garments.find(g_query, {'_id': 0}).to_list(None)
    if not garments: return []
    garment_ids = [g['id'] for g in garments]

    # ─── 10B-rem: batch-fetch all jobs (parents + children) for the requested vendors ───
    all_jobs = await db.production_jobs.find(
        {'vendor_id': {'$in': garment_ids}}, {'_id': 0}
    ).sort('created_at', -1).to_list(None)
    parent_jobs_by_vendor = {}
    children_by_parent = {}
    for j in all_jobs:
        pid = j.get('parent_job_id')
        if not pid:
            parent_jobs_by_vendor.setdefault(j.get('vendor_id'), []).append(j)
        else:
            children_by_parent.setdefault(pid, []).append(j)

    # Batch-fetch all job_items for any of these jobs in one query
    all_job_ids = [j['id'] for j in all_jobs]
    all_job_items = await db.production_job_items.find(
        {'job_id': {'$in': all_job_ids}}, {'_id': 0}
    ).to_list(None) if all_job_ids else []
    items_by_job = {}
    for it in all_job_items:
        items_by_job.setdefault(it.get('job_id'), []).append(it)

    # Aggregate buyer-shipped per po_item_id once
    po_item_ids = list({i.get('po_item_id') for i in all_job_items if i.get('po_item_id')})
    buyer_agg = await db.buyer_shipment_items.aggregate([
        {'$match': {'po_item_id': {'$in': po_item_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_shipped'}}},
    ]).to_list(None) if po_item_ids else []
    buyer_by_poitem = {a['_id']: a['qty'] for a in buyer_agg}

    result = []
    for g in garments:
        parent_jobs = parent_jobs_by_vendor.get(g['id'], [])
        if not parent_jobs: continue
        total_qty = 0
        total_produced = 0
        total_shipped_to_buyer_set = set()  # avoid double counting buyer ship across child jobs sharing po_item_id
        running_shipped = 0
        for job in parent_jobs:
            items = items_by_job.get(job['id'], [])
            child_jobs = children_by_parent.get(job['id'], [])
            child_items_for_parent = []
            for cj in child_jobs:
                child_items_for_parent.extend(items_by_job.get(cj['id'], []))
            for item in items:
                # Total produced for this po_item across this parent + its child jobs
                child_produced = sum(
                    ci.get('produced_qty', 0)
                    for ci in child_items_for_parent
                    if ci.get('po_item_id') and ci.get('po_item_id') == item.get('po_item_id')
                )
                total_prod = (item.get('produced_qty', 0)) + child_produced
                # Buyer shipped per po_item_id, count only once per po_item across the result
                poi = item.get('po_item_id')
                if poi and poi not in total_shipped_to_buyer_set:
                    running_shipped += buyer_by_poitem.get(poi, 0)
                    total_shipped_to_buyer_set.add(poi)
                total_qty += item.get('ordered_qty', 0)
                total_produced += total_prod
        pct = round((total_produced / total_qty * 100) if total_qty > 0 else 0)
        result.append({
            'vendor_id': g['id'], 'vendor_name': g.get('garment_name'),
            'vendor_code': g.get('garment_code'), 'location': g.get('location', ''),
            'total_jobs': len(parent_jobs), 'total_qty': total_qty,
            'total_produced': total_produced, 'total_shipped_to_buyer': running_shipped,
            'progress_pct': pct,
            'jobs_by_status': {
                'in_progress': len([j for j in parent_jobs if j.get('status') == 'In Progress']),
                'completed': len([j for j in parent_jobs if j.get('status') == 'Completed'])
            }
        })
    return result

# ─── DISTRIBUSI KERJA ────────────────────────────────────────────────────────
@api.get("/distribusi-kerja")
async def distribusi_kerja(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    # Get all POs (or filtered by vendor)
    po_query = {}
    if sp.get('vendor_id'): po_query['vendor_id'] = sp['vendor_id']
    if sp.get('po_id'): po_query['id'] = sp['po_id']
    pos = await db.production_pos.find(po_query, {'_id': 0}).sort('created_at', -1).to_list(None)
    if not pos: return {'hierarchy': [], 'flat': [], 'invalid_records': []}

    # ─── 10B-rem: batch every dependency in one shot ───
    po_ids = [po['id'] for po in pos]
    all_po_items = await db.po_items.find({'po_id': {'$in': po_ids}}).to_list(None)
    po_item_ids = [pi['id'] for pi in all_po_items]
    items_by_po = {}
    for pi in all_po_items:
        items_by_po.setdefault(pi.get('po_id'), []).append(pi)

    # qty_sent per po_item (single aggregation)
    sent_agg = await db.vendor_shipment_items.aggregate([
        {'$match': {'po_item_id': {'$in': po_item_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_sent'}}},
    ]).to_list(None) if po_item_ids else []
    sent_by_poitem = {a['_id']: a['qty'] for a in sent_agg}

    # produced_qty per po_item
    prod_agg = await db.production_job_items.aggregate([
        {'$match': {'po_item_id': {'$in': po_item_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$produced_qty'}}},
    ]).to_list(None) if po_item_ids else []
    prod_by_poitem = {a['_id']: a['qty'] for a in prod_agg}

    # shipped_to_buyer per po_item
    buyer_agg = await db.buyer_shipment_items.aggregate([
        {'$match': {'po_item_id': {'$in': po_item_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_shipped'}}},
    ]).to_list(None) if po_item_ids else []
    buyer_by_poitem = {a['_id']: a['qty'] for a in buyer_agg}

    # received_qty: join shipment_items -> inspections -> inspection_items
    # Step 1 — pull all shipment items for these po_items
    all_ship_items = await db.vendor_shipment_items.find(
        {'po_item_id': {'$in': po_item_ids}}, {'_id': 0}
    ).to_list(None) if po_item_ids else []
    ship_ids = list({si.get('shipment_id') for si in all_ship_items if si.get('shipment_id')})
    # Step 2 — find inspections for those shipments in 1 query
    inspections = await db.vendor_material_inspections.find(
        {'shipment_id': {'$in': ship_ids}}, {'_id': 0, 'id': 1, 'shipment_id': 1}
    ).to_list(None) if ship_ids else []
    insp_id_by_ship = {i['shipment_id']: i['id'] for i in inspections}
    insp_ids = list(insp_id_by_ship.values())
    # Step 3 — fetch all inspection items keyed by shipment_item_id
    insp_items = await db.vendor_material_inspection_items.find(
        {'inspection_id': {'$in': insp_ids}}, {'_id': 0, 'shipment_item_id': 1, 'received_qty': 1}
    ).to_list(None) if insp_ids else []
    received_by_shipitem = {ii['shipment_item_id']: ii.get('received_qty', 0) for ii in insp_items if ii.get('shipment_item_id')}
    # Step 4 — sum received_qty per po_item via shipment_item linkage
    received_by_poitem = {}
    for si in all_ship_items:
        poi = si.get('po_item_id')
        if not poi: continue
        received_by_poitem[poi] = received_by_poitem.get(poi, 0) + received_by_shipitem.get(si.get('id'), 0)

    flat_rows = []
    for po in pos:
        for pi in items_by_po.get(po['id'], []):
            poi = pi['id']
            ordered_qty = pi.get('qty', 0)
            produced_qty = prod_by_poitem.get(poi, 0)
            progress_pct = round((produced_qty / ordered_qty * 100) if ordered_qty > 0 else 0)
            flat_rows.append({
                'id': poi, 'po_item_id': poi,
                'vendor_id': po.get('vendor_id'), 'vendor_name': po.get('vendor_name', ''),
                'po_id': po['id'], 'po_number': po.get('po_number', ''),
                'po_date': serialize_doc(po.get('created_at')),
                'customer_name': po.get('customer_name', ''),
                'serial_number': pi.get('serial_number', ''),
                'product_name': pi.get('product_name', ''), 'sku': pi.get('sku', ''),
                'size': pi.get('size', ''), 'color': pi.get('color', ''),
                'ordered_qty': ordered_qty,
                'shipment_qty': sent_by_poitem.get(poi, 0),
                'received_qty': received_by_poitem.get(poi, 0),
                'produced_qty': produced_qty,
                'shipped_to_buyer_qty': buyer_by_poitem.get(poi, 0),
                'progress_pct': progress_pct,
            })
    # Build hierarchy
    vendor_map = {}
    for row in flat_rows:
        vid = row.get('vendor_id')
        if vid not in vendor_map:
            vendor_map[vid] = {'vendor_id': vid, 'vendor_name': row.get('vendor_name'),
                               'total_ordered': 0, 'total_received': 0, 'total_produced': 0, 'total_shipped_to_buyer': 0, 'pos': {}}
        vm = vendor_map[vid]
        vm['total_ordered'] += row.get('ordered_qty', 0)
        vm['total_received'] += row.get('received_qty', 0)
        vm['total_produced'] += row.get('produced_qty', 0)
        vm['total_shipped_to_buyer'] += row.get('shipped_to_buyer_qty', 0)
        po_key = row.get('po_id', 'unknown')
        if po_key not in vm['pos']:
            vm['pos'][po_key] = {'po_id': row.get('po_id'), 'po_number': row.get('po_number'),
                                  'customer_name': row.get('customer_name'),
                                  'total_ordered': 0, 'total_received': 0, 'total_produced': 0, 'total_shipped_to_buyer': 0, 'serials': {}}
        pm = vm['pos'][po_key]
        pm['total_ordered'] += row.get('ordered_qty', 0)
        pm['total_received'] += row.get('received_qty', 0)
        pm['total_produced'] += row.get('produced_qty', 0)
        pm['total_shipped_to_buyer'] += row.get('shipped_to_buyer_qty', 0)
        sn = row.get('serial_number', '__no_serial__')
        if sn not in pm['serials']:
            pm['serials'][sn] = {'serial_number': row.get('serial_number', ''),
                                  'total_ordered': 0, 'total_received': 0, 'total_produced': 0, 'total_shipped_to_buyer': 0, 'skus': []}
        sm = pm['serials'][sn]
        sm['total_ordered'] += row.get('ordered_qty', 0)
        sm['total_received'] += row.get('received_qty', 0)
        sm['total_produced'] += row.get('produced_qty', 0)
        sm['total_shipped_to_buyer'] += row.get('shipped_to_buyer_qty', 0)
        sm['skus'].append(row)
    hierarchy = []
    for vm in vendor_map.values():
        vm['progress_pct'] = round((vm['total_produced'] / vm['total_ordered'] * 100) if vm['total_ordered'] > 0 else 0)
        pos_list = []
        for pm in vm['pos'].values():
            pm['progress_pct'] = round((pm['total_produced'] / pm['total_ordered'] * 100) if pm['total_ordered'] > 0 else 0)
            serials_list = []
            for sm in pm['serials'].values():
                sm['progress_pct'] = round((sm['total_produced'] / sm['total_ordered'] * 100) if sm['total_ordered'] > 0 else 0)
                serials_list.append(sm)
            pm['serials'] = serials_list
            pos_list.append(pm)
        vm['pos'] = pos_list
        hierarchy.append(vm)
    return {'hierarchy': hierarchy, 'flat': flat_rows, 'invalid_records': []}

# ─── WORK ORDERS ─────────────────────────────────────────────────────────────
@api.get("/work-orders")
async def get_work_orders(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('po_id'): query['po_id'] = sp['po_id']
    if sp.get('garment_id'): query['garment_id'] = sp['garment_id']
    if sp.get('status'): query['status'] = sp['status']
    if user.get('role') == 'vendor': query['garment_id'] = user.get('vendor_id')
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'distribution_code': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
            {'garment_name': {'$regex': search, '$options': 'i'}},
        ]
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'distribution_code', 'po_number',
                                 'garment_name', 'status'})
    total = await db.work_orders.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.work_orders.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@api.post("/work-orders")
async def create_work_order(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    po = await db.production_pos.find_one({'id': body.get('po_id')})
    if not po: raise HTTPException(404, 'PO not found')
    garment = await db.garments.find_one({'id': body.get('garment_id')})
    if not garment: raise HTTPException(404, 'Garment not found')
    wo = {
        'id': new_id(), 'distribution_code': f"WO-{po.get('po_number')}-{garment.get('garment_code')}",
        'po_id': body['po_id'], 'po_number': po.get('po_number'),
        'customer_name': po.get('customer_name'),
        'garment_id': body['garment_id'], 'garment_name': garment.get('garment_name'),
        'garment_code': garment.get('garment_code'),
        'quantity': int(body.get('quantity', 0)), 'completed_quantity': 0,
        'status': 'Waiting', 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.work_orders.insert_one(wo)
    await db.production_pos.update_one({'id': body['po_id']}, {'$set': {'status': 'Distributed', 'updated_at': now()}})
    return JSONResponse(serialize_doc(wo), status_code=201)

@api.delete("/work-orders/{woid}")
async def delete_work_order(woid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.work_orders.find_one({'id': woid})
    if not doc: raise HTTPException(404, 'Not found')
    await db.production_progress.delete_many({'work_order_id': woid})
    await db.work_orders.delete_one({'id': woid})
    return {'success': True}

# ─── RECALCULATE JOBS ────────────────────────────────────────────────────────
@api.post("/recalculate-jobs")
async def recalculate_jobs(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    fixed = 0
    # First: backfill po_item_id on child shipment items that are missing it
    orphan_items = await db.vendor_shipment_items.find({'$or': [{'po_item_id': None}, {'po_item_id': ''}, {'po_item_id': {'$exists': False}}]}).to_list(None)
    for oi in orphan_items:
        ship = await db.vendor_shipments.find_one({'id': oi.get('shipment_id')})
        if not ship or not ship.get('parent_shipment_id'):
            continue
        # Find matching item in parent shipment by sku+size+color
        parent_items = await db.vendor_shipment_items.find({'shipment_id': ship['parent_shipment_id']}).to_list(None)
        for pi in parent_items:
            if pi.get('sku') == oi.get('sku') and pi.get('size', '') == oi.get('size', '') and pi.get('color', '') == oi.get('color', ''):
                if pi.get('po_item_id'):
                    await db.vendor_shipment_items.update_one({'id': oi['id']}, {'$set': {
                        'po_item_id': pi['po_item_id'], 'po_id': pi.get('po_id', ''),
                        'po_number': pi.get('po_number', ''), 'serial_number': pi.get('serial_number', ''),
                    }})
                    break
        # If still no match, try grandparent
        if not pi.get('po_item_id'):
            gp_ship = await db.vendor_shipments.find_one({'id': ship['parent_shipment_id']})
            if gp_ship and gp_ship.get('parent_shipment_id'):
                gp_items = await db.vendor_shipment_items.find({'shipment_id': gp_ship['parent_shipment_id']}).to_list(None)
                for gpi in gp_items:
                    if gpi.get('sku') == oi.get('sku') and gpi.get('size', '') == oi.get('size', '') and gpi.get('color', '') == oi.get('color', ''):
                        if gpi.get('po_item_id'):
                            await db.vendor_shipment_items.update_one({'id': oi['id']}, {'$set': {
                                'po_item_id': gpi['po_item_id'], 'po_id': gpi.get('po_id', ''),
                                'po_number': gpi.get('po_number', ''), 'serial_number': gpi.get('serial_number', ''),
                            }})
                            break
    # Now recalculate job items
    all_jobs = await db.production_jobs.find({}).to_list(None)
    for job in all_jobs:
        job_items = await db.production_job_items.find({'job_id': job['id']}).to_list(None)
        for ji in job_items:
            po_item_id = ji.get('po_item_id')
            if not po_item_id:
                continue
            # Aggregate received qty across ALL shipments (parent + children) for this po_item
            all_ship_items = await db.vendor_shipment_items.find({'po_item_id': po_item_id}).to_list(None)
            total_received = 0
            total_defect = 0
            for si in all_ship_items:
                insp = await db.vendor_material_inspections.find_one({'shipment_id': si.get('shipment_id')})
                if insp:
                    insp_item = await db.vendor_material_inspection_items.find_one({
                        'inspection_id': insp['id'], 'shipment_item_id': si['id']})
                    if insp_item:
                        total_received += insp_item.get('received_qty', 0)
                        total_defect += insp_item.get('defect_qty', 0)
            new_avail = max(0, total_received - total_defect)
            sn = ji.get('serial_number', '')
            if not sn and po_item_id:
                poi = await db.po_items.find_one({'id': po_item_id})
                sn = (poi or {}).get('serial_number', '')
            await db.production_job_items.update_one({'id': ji['id']}, {'$set': {
                'available_qty': new_avail, 'serial_number': sn,
                'total_received_qty': total_received, 'updated_at': now()
            }})
            fixed += 1
    return {'success': True, 'items_updated': fixed, 'jobs_processed': len(all_jobs), 'orphans_fixed': len(orphan_items)}

# ─── IMPORT DATA ─────────────────────────────────────────────────────────────
@api.post("/import-data")
async def import_data(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    import_type = body.get('type', '')
    data_rows = body.get('data', [])
    imported = 0
    errors = []
    if import_type == 'products':
        for row in data_rows:
            try:
                prod_id = new_id()
                prod = {'id': prod_id, 'product_code': row.get('product_code', ''),
                        'product_name': row.get('product_name', ''), 'category': row.get('category', ''),
                        'cmt_price': float(row.get('cmt_price', 0) or 0),
                        'selling_price': float(row.get('selling_price', 0) or 0),
                        'status': 'active', 'created_at': now(), 'updated_at': now()}
                await db.products.insert_one(prod)
                # Import variants if provided
                for v in row.get('variants', []):
                    await db.product_variants.insert_one({
                        'id': new_id(), 'product_id': prod_id,
                        'product_code': prod['product_code'], 'product_name': prod['product_name'],
                        'sku': v.get('sku', ''), 'size': v.get('size', ''), 'color': v.get('color', ''),
                        'status': 'active', 'created_at': now()})
                imported += 1
            except Exception as e: errors.append(f"Row {imported+1}: {str(e)}")
    elif import_type == 'garments':
        for row in data_rows:
            try:
                gid = new_id()
                code_slug = (row.get('garment_code', gid)).lower()
                code_slug = ''.join(c for c in code_slug if c.isalnum())
                email = f"vendor.{code_slug}@garment.com"
                raw_pw = generate_password(10)
                await db.users.insert_one({'id': new_id(), 'name': row.get('garment_name', ''),
                    'email': email, 'password': hash_password(raw_pw), 'role': 'vendor',
                    'vendor_id': gid, 'status': 'active', 'created_at': now(), 'updated_at': now()})
                await db.garments.insert_one({'id': gid, **row, 'status': 'active',
                    'login_email': email, 'vendor_password_plain': raw_pw,
                    'created_at': now(), 'updated_at': now()})
                imported += 1
            except Exception as e: errors.append(f"Row {imported+1}: {str(e)}")
    elif import_type == 'production-pos':
        for row in data_rows:
            try:
                vendor_name = ''
                if row.get('vendor_id'):
                    vd = await db.garments.find_one({'id': row['vendor_id']})
                    vendor_name = (vd or {}).get('garment_name', '')
                po_id = new_id()
                po = {'id': po_id, 'po_number': row.get('po_number', ''),
                      'customer_name': row.get('customer_name', ''),
                      'vendor_id': row.get('vendor_id'), 'vendor_name': vendor_name,
                      'po_date': parse_date(row.get('po_date')) or now(),
                      'deadline': parse_date(row.get('deadline')),
                      'status': 'Draft', 'notes': row.get('notes', ''),
                      'created_by': user['name'], 'created_at': now(), 'updated_at': now()}
                await db.production_pos.insert_one(po)
                for item in row.get('items', []):
                    await db.po_items.insert_one({
                        'id': new_id(), 'po_id': po_id, 'po_number': row['po_number'],
                        'product_name': item.get('product_name', ''),
                        'sku': item.get('sku', ''), 'size': item.get('size', ''),
                        'color': item.get('color', ''), 'serial_number': item.get('serial_number', ''),
                        'qty': int(item.get('qty', 0) or 0),
                        'selling_price_snapshot': float(item.get('selling_price', 0) or 0),
                        'cmt_price_snapshot': float(item.get('cmt_price', 0) or 0),
                        'created_at': now()})
                imported += 1
            except Exception as e: errors.append(f"Row {imported+1}: {str(e)}")
    elif import_type == 'accessories':
        for row in data_rows:
            try:
                await db.accessories.insert_one({'id': new_id(), 'name': row.get('name', ''),
                    'code': row.get('code', ''), 'category': row.get('category', ''),
                    'unit': row.get('unit', 'pcs'), 'description': row.get('description', ''),
                    'status': 'active', 'created_at': now(), 'updated_at': now()})
                imported += 1
            except Exception as e: errors.append(f"Row {imported+1}: {str(e)}")
    else:
        raise HTTPException(400, f"Unknown import type: {import_type}")
    await log_activity(user['id'], user['name'], 'Import', import_type, f"Imported {imported} records")
    return {'imported': imported, 'errors': errors, 'type': import_type}

@api.get("/import-template")
async def import_template(request: Request):
    await require_auth(request)
    ttype = request.query_params.get('type', '')
    templates = {
        'products': {'columns': ['product_code', 'product_name', 'category', 'cmt_price', 'selling_price'],
                     'variant_columns': ['sku', 'size', 'color'], 'example': {'product_code': 'PRD-001', 'product_name': 'T-Shirt Basic', 'category': 'Shirt', 'cmt_price': 5000, 'selling_price': 15000}},
        'garments': {'columns': ['garment_code', 'garment_name', 'location', 'contact_person', 'phone', 'monthly_capacity'],
                     'example': {'garment_code': 'VND-001', 'garment_name': 'PT Garmen Jaya', 'location': 'Jakarta', 'contact_person': 'Budi', 'phone': '08123456789'}},
        'production-pos': {'columns': ['po_number', 'customer_name', 'vendor_id', 'po_date', 'deadline', 'notes'],
                           'item_columns': ['product_name', 'sku', 'size', 'color', 'serial_number', 'qty', 'selling_price', 'cmt_price'],
                           'example': {'po_number': 'PO-001', 'customer_name': 'Buyer Corp'}},
        'accessories': {'columns': ['code', 'name', 'category', 'unit', 'description'],
                        'example': {'code': 'ACC-001', 'name': 'Kancing', 'category': 'Trimming', 'unit': 'pcs'}},
    }
    if ttype not in templates:
        return {'available_types': list(templates.keys())}
    return templates[ttype]

# ─── EXPORT EXCEL ────────────────────────────────────────────────────────────
@api.get("/export-excel")
async def export_excel(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    export_type = sp.get('type', '')
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        if export_type == 'production-pos':
            ws.title = "Production POs"
            headers = ['No', 'PO Number', 'Customer', 'Vendor', 'PO Date', 'Deadline', 'Status', 'Serial', 'SKU', 'Product', 'Size', 'Color', 'Qty', 'Selling Price', 'CMT Price']
            ws.append(headers)
            pos = await db.production_pos.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
            row_num = 1
            for po in pos:
                items = await db.po_items.find({'po_id': po['id']}).to_list(None)
                for item in items:
                    ws.append([row_num, po.get('po_number'), po.get('customer_name'), po.get('vendor_name'),
                               str(po.get('po_date', ''))[:10], str(po.get('deadline', ''))[:10], po.get('status'),
                               item.get('serial_number', ''), item.get('sku', ''), item.get('product_name', ''),
                               item.get('size', ''), item.get('color', ''), item.get('qty', 0),
                               item.get('selling_price_snapshot', 0), item.get('cmt_price_snapshot', 0)])
                    row_num += 1
        elif export_type == 'vendor-shipments':
            ws.title = "Vendor Shipments"
            headers = ['No', 'Shipment Number', 'Vendor', 'Type', 'Date', 'Status', 'Inspection', 'SKU', 'Product', 'Size', 'Color', 'Qty Sent', 'Ordered Qty']
            ws.append(headers)
            ships = await db.vendor_shipments.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
            row_num = 1
            for s in ships:
                items = await db.vendor_shipment_items.find({'shipment_id': s['id']}).to_list(None)
                for item in items:
                    ws.append([row_num, s.get('shipment_number'), s.get('vendor_name'), s.get('shipment_type', 'NORMAL'),
                               str(s.get('shipment_date', ''))[:10], s.get('status'), s.get('inspection_status', 'Pending'),
                               item.get('sku', ''), item.get('product_name', ''), item.get('size', ''), item.get('color', ''),
                               item.get('qty_sent', 0), item.get('ordered_qty', 0)])
                    row_num += 1
        elif export_type == 'buyer-shipments':
            ws.title = "Buyer Shipments"
            headers = ['No', 'Shipment Number', 'PO Number', 'Customer', 'Vendor', 'Dispatch #', 'Dispatch Date', 'SKU', 'Product', 'Serial', 'Size', 'Color', 'Ordered Qty', 'Shipped Qty']
            ws.append(headers)
            ships = await db.buyer_shipments.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
            row_num = 1
            for s in ships:
                items = await db.buyer_shipment_items.find({'shipment_id': s['id']}).sort([('dispatch_seq', 1)]).to_list(None)
                for item in items:
                    ws.append([row_num, s.get('shipment_number'), s.get('po_number'), s.get('customer_name'),
                               s.get('vendor_name'), item.get('dispatch_seq', 1), str(item.get('dispatch_date', ''))[:10],
                               item.get('sku', ''), item.get('product_name', ''), item.get('serial_number', ''),
                               item.get('size', ''), item.get('color', ''), item.get('ordered_qty', 0), item.get('qty_shipped', 0)])
                    row_num += 1
        elif export_type == 'invoices':
            ws.title = "Invoices"
            headers = ['No', 'Invoice Number', 'Category', 'PO Number', 'Vendor/Customer', 'Total Amount', 'Total Paid', 'Remaining', 'Status', 'Created']
            ws.append(headers)
            invs = await db.invoices.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
            for idx, inv in enumerate(invs, 1):
                ws.append([idx, inv.get('invoice_number'), inv.get('invoice_category'),
                           inv.get('po_number'), inv.get('vendor_or_customer_name', inv.get('vendor_name', '')),
                           inv.get('total_amount', 0), inv.get('total_paid', 0),
                           inv.get('remaining_balance', inv.get('total_amount', 0) - inv.get('total_paid', 0)),
                           inv.get('status'), str(inv.get('created_at', ''))[:10]])
        elif export_type == 'accessories':
            ws.title = "Accessories"
            headers = ['No', 'Code', 'Name', 'Category', 'Unit', 'Status']
            ws.append(headers)
            accs = await db.accessories.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
            for idx, acc in enumerate(accs, 1):
                ws.append([idx, acc.get('code'), acc.get('name'), acc.get('category'), acc.get('unit'), acc.get('status')])
        elif export_type == 'production-report':
            ws.title = "Production Report"
            headers = ['No', 'Date', 'PO Number', 'Serial', 'Product Code', 'Product Name', 'Size', 'SKU', 'Color',
                       'Output Qty', 'Selling Price', 'CMT Price', 'Total Sales', 'Total CMT', 'Vendor', 'Notes',
                       'Qty Produced', 'Qty Not Produced', 'Qty Shipped']
            ws.append(headers)
            pos = await db.production_pos.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
            row_num = 1
            for po in pos:
                items = await db.po_items.find({'po_id': po['id']}).to_list(None)
                for item in items:
                    ji_list = await db.production_job_items.find({'po_item_id': item['id']}).to_list(None)
                    produced = sum(j.get('produced_qty', 0) for j in ji_list)
                    bi_list = await db.buyer_shipment_items.find({'po_item_id': item['id']}).to_list(None)
                    shipped = sum(b.get('qty_shipped', 0) for b in bi_list)
                    qty = item.get('qty', 0)
                    sp_price = item.get('selling_price_snapshot', 0)
                    cmt = item.get('cmt_price_snapshot', 0)
                    ws.append([row_num, str(po.get('po_date', po.get('created_at', '')))[:10],
                               po.get('po_number'), item.get('serial_number', ''), item.get('sku', ''),
                               item.get('product_name', ''), item.get('size', ''), item.get('sku', ''),
                               item.get('color', ''), qty, sp_price, cmt, qty * sp_price, qty * cmt,
                               po.get('vendor_name', ''), po.get('notes', ''),
                               produced, max(0, qty - produced), shipped])
                    row_num += 1
        else:
            return JSONResponse({'error': f'Unknown export type: {export_type}', 'available_types': [
                'production-pos', 'vendor-shipments', 'buyer-shipments', 'invoices', 'accessories', 'production-report']}, status_code=400)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        filename = f"{export_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename={filename}"})
    except Exception as e:
        logger.error(f"Export error: {e}")
        raise HTTPException(500, f"Export failed: {str(e)}")


# ─── PDF exports live in routes/pdf_exports.py (registered below) ───────────

@api.get("/pdf-export-columns")
async def get_pdf_export_columns(request: Request):
    """Get available columns for a PDF type."""
    await require_auth(request)
    pdf_type = request.query_params.get('type', '')
    if pdf_type in PDF_COLUMN_DEFINITIONS:
        return {'pdf_type': pdf_type, 'columns': PDF_COLUMN_DEFINITIONS[pdf_type]}
    return {'pdf_type': pdf_type, 'columns': [], 'available_types': list(PDF_COLUMN_DEFINITIONS.keys())}

@api.get("/pdf-export-configs")
async def list_pdf_export_configs(request: Request):
    """List all PDF export configurations."""
    await require_auth(request)
    db = get_db()
    pdf_type = request.query_params.get('type')
    query = {}
    if pdf_type: query['pdf_type'] = pdf_type
    configs = await db.pdf_export_configs.find(query, {'_id': 0}).sort('created_at', -1).to_list(None)
    return serialize_doc(configs)

@api.get("/pdf-export-configs/{config_id}")
async def get_pdf_export_config(config_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    cfg = await db.pdf_export_configs.find_one({'id': config_id}, {'_id': 0})
    if not cfg: raise HTTPException(404, 'Config not found')
    return serialize_doc(cfg)

@api.post("/pdf-export-configs")
async def create_pdf_export_config(request: Request):
    """Create a new PDF export config. (RBAC: admin + superadmin only)"""
    user = await require_auth(request)
    if not check_role(user, ['admin'], 'settings.manage'):
        raise HTTPException(403, 'Forbidden: admin role required to manage PDF presets')
    db = get_db()
    body = await request.json()
    pdf_type = body.get('pdf_type', '')
    name = body.get('name', '')
    columns = body.get('columns', [])
    is_default = body.get('is_default', False)
    if not pdf_type or not name: raise HTTPException(400, 'pdf_type and name required')
    if not columns: raise HTTPException(400, 'columns array required')
    # Validate pdf_type against registered column definitions
    if pdf_type not in PDF_COLUMN_DEFINITIONS:
        raise HTTPException(400, f"Unknown pdf_type '{pdf_type}'. Valid types: {sorted(PDF_COLUMN_DEFINITIONS.keys())}")
    # Ensure required columns are included
    if pdf_type in PDF_COLUMN_DEFINITIONS:
        required = [c['key'] for c in PDF_COLUMN_DEFINITIONS[pdf_type] if c.get('required')]
        for rk in required:
            if rk not in columns:
                columns.insert(0, rk)
    # Validate orientation
    page_orientation = body.get('page_orientation', 'auto')
    if page_orientation not in ('auto', 'portrait', 'landscape'):
        page_orientation = 'auto'
    # If setting as default, unset other defaults for this type
    if is_default:
        await db.pdf_export_configs.update_many({'pdf_type': pdf_type, 'is_default': True}, {'$set': {'is_default': False}})
    doc = {
        'id': str(uuid.uuid4()),
        'pdf_type': pdf_type,
        'name': name,
        'columns': columns,
        'is_default': is_default,
        # Phase 3D - custom header/footer overrides
        'use_company_settings': bool(body.get('use_company_settings', True)),
        'custom_title': body.get('custom_title', '') or '',
        'custom_header_line1': body.get('custom_header_line1', '') or '',
        'custom_header_line2': body.get('custom_header_line2', '') or '',
        'custom_footer_text': body.get('custom_footer_text', '') or '',
        'custom_logo_url': body.get('custom_logo_url', '') or '',
        # Phase 3F - page orientation
        'page_orientation': page_orientation,
        'created_by': user.get('name', ''),
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }
    await db.pdf_export_configs.insert_one(doc)
    await log_activity(user['id'], user.get('name', ''), 'create', 'pdf_config', f"Created PDF config: {name} for {pdf_type}")
    return JSONResponse(serialize_doc({k: v for k, v in doc.items() if k != '_id'}), status_code=201)

@api.put("/pdf-export-configs/{config_id}")
async def update_pdf_export_config(config_id: str, request: Request):
    """Update an existing PDF export config. (RBAC: admin + superadmin only)"""
    user = await require_auth(request)
    if not check_role(user, ['admin'], 'settings.manage'):
        raise HTTPException(403, 'Forbidden: admin role required to manage PDF presets')
    db = get_db()
    body = await request.json()
    existing = await db.pdf_export_configs.find_one({'id': config_id})
    if not existing: raise HTTPException(404, 'Config not found')
    update = {'updated_at': datetime.now(timezone.utc)}
    if 'name' in body: update['name'] = body['name']
    if 'columns' in body:
        columns = body['columns']
        pdf_type = existing.get('pdf_type', '')
        if pdf_type in PDF_COLUMN_DEFINITIONS:
            required = [c['key'] for c in PDF_COLUMN_DEFINITIONS[pdf_type] if c.get('required')]
            for rk in required:
                if rk not in columns:
                    columns.insert(0, rk)
        update['columns'] = columns
    if 'is_default' in body:
        if body['is_default']:
            await db.pdf_export_configs.update_many({'pdf_type': existing['pdf_type'], 'is_default': True}, {'$set': {'is_default': False}})
        update['is_default'] = body['is_default']
    # Phase 3D - custom header/footer fields (all optional, only update if present in body)
    for fld in ('use_company_settings', 'custom_title', 'custom_header_line1',
                'custom_header_line2', 'custom_footer_text', 'custom_logo_url'):
        if fld in body:
            update[fld] = body[fld] if fld == 'use_company_settings' else (body[fld] or '')
    # Phase 3F - page orientation
    if 'page_orientation' in body:
        po = body['page_orientation']
        if po not in ('auto', 'portrait', 'landscape'):
            raise HTTPException(400, "page_orientation must be 'auto', 'portrait', or 'landscape'")
        update['page_orientation'] = po
    await db.pdf_export_configs.update_one({'id': config_id}, {'$set': update})
    updated = await db.pdf_export_configs.find_one({'id': config_id}, {'_id': 0})
    return serialize_doc(updated)

@api.delete("/pdf-export-configs/{config_id}")
async def delete_pdf_export_config(config_id: str, request: Request):
    """Delete a PDF export config. (RBAC: admin + superadmin only)"""
    user = await require_auth(request)
    if not check_role(user, ['admin'], 'settings.manage'):
        raise HTTPException(403, 'Forbidden: admin role required to manage PDF presets')
    db = get_db()
    existing = await db.pdf_export_configs.find_one({'id': config_id})
    if not existing: raise HTTPException(404, 'Config not found')
    await db.pdf_export_configs.delete_one({'id': config_id})
    await log_activity(user['id'], user.get('name', ''), 'delete', 'pdf_config', f"Deleted PDF config: {existing.get('name', config_id)}")
    return {'success': True}

# ─── UPLOAD (handled by routes/file_storage.py) ─────────────────────────────

# ─── PO STATUS TRANSITION ───────────────────────────────────────────────────
@api.post("/production-pos/{po_id}/status")
async def transition_po_status(po_id: str, request: Request):
    """Transition PO through staged statuses."""
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    new_status = body.get('status')
    if new_status not in PO_STATUSES:
        raise HTTPException(400, f"Invalid status. Valid: {PO_STATUSES}")
    po = await db.production_pos.find_one({'id': po_id})
    if not po: raise HTTPException(404, 'PO not found')
    update_data = {'status': new_status, 'updated_at': now()}
    if body.get('notes'): update_data['status_notes'] = body['notes']
    if new_status == 'Closed':
        update_data['closed_by'] = user['name']
        update_data['closed_at'] = now()
        update_data['close_reason'] = body.get('close_reason', '')
    await db.production_pos.update_one({'id': po_id}, {'$set': update_data})
    await log_activity(user['id'], user['name'], 'Status Change', 'Production PO',
                       f"PO {po.get('po_number')}: {po.get('status')} → {new_status}")
    return serialize_doc(await db.production_pos.find_one({'id': po_id}, {'_id': 0}))

# ─── PO QUANTITY SUMMARY ────────────────────────────────────────────────────
@api.get("/production-pos/{po_id}/quantity-summary")
async def po_quantity_summary(po_id: str, request: Request):
    """Get comprehensive quantity summary for a PO."""
    await require_auth(request)
    db = get_db()
    po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
    if not po: raise HTTPException(404, 'PO not found')
    items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    summary_items = []
    totals = {'ordered': 0, 'received': 0, 'missing': 0, 'defect': 0, 
              'available': 0, 'produced': 0, 'shipped': 0, 'returned': 0}
    # ── 10E: batch all sub-document lookups for PDF summary in 7 queries ──
    pdf_item_ids = [it['id'] for it in items]
    _s_vsi_all  = await db.vendor_shipment_items.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_vsi_ids  = [vsi['id'] for vsi in _s_vsi_all]
    _s_ship_ids = list({vsi.get('shipment_id') for vsi in _s_vsi_all if vsi.get('shipment_id')})
    _s_ships    = await db.vendor_shipments.find({'id': {'$in': _s_ship_ids}}, {'_id': 0, 'id': 1, 'status': 1, 'inspection_status': 1}).to_list(None) if _s_ship_ids else []
    _s_ship_map = {sh['id']: sh for sh in _s_ships}
    _s_insps    = await db.vendor_material_inspections.find({'shipment_id': {'$in': _s_ship_ids}}).to_list(None) if _s_ship_ids else []
    _s_insp_map = {insp.get('shipment_id'): insp for insp in _s_insps}
    _s_insp_ids = [insp['id'] for insp in _s_insps]
    _s_ii_all   = await db.vendor_material_inspection_items.find({'inspection_id': {'$in': _s_insp_ids}, 'shipment_item_id': {'$in': _s_vsi_ids}}).to_list(None) if (_s_insp_ids and _s_vsi_ids) else []
    _s_ii_map   = {ii.get('shipment_item_id'): ii for ii in _s_ii_all}
    _s_defects  = await db.material_defect_reports.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_ji_all   = await db.production_job_items.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_bi_all   = await db.buyer_shipment_items.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_ri_all   = await db.production_return_items.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_vsi_by_poi: dict = {}
    for vsi in _s_vsi_all: _s_vsi_by_poi.setdefault(vsi.get('po_item_id'), []).append(vsi)
    _s_def_by_poi: dict = {}
    for d in _s_defects: _s_def_by_poi.setdefault(d.get('po_item_id'), []).append(d)
    _s_ji_by_poi: dict = {}
    for ji in _s_ji_all: _s_ji_by_poi.setdefault(ji.get('po_item_id'), []).append(ji)
    _s_bi_by_poi: dict = {}
    for bi in _s_bi_all: _s_bi_by_poi.setdefault(bi.get('po_item_id'), []).append(bi)
    _s_ri_by_poi: dict = {}
    for ri in _s_ri_all: _s_ri_by_poi.setdefault(ri.get('po_item_id'), []).append(ri)
    for item in items:
        ship_items_for_item = _s_vsi_by_poi.get(item['id'], [])
        received = 0; missing = 0
        for si in ship_items_for_item:
            ship = _s_ship_map.get(si.get('shipment_id'), {})
            if ship.get('inspection_status') == 'Inspected':
                insp = _s_insp_map.get(si.get('shipment_id'))
                if insp:
                    ii = _s_ii_map.get(si['id'])
                    if ii:
                        received += ii.get('received_qty', 0); missing += ii.get('missing_qty', 0)
                    else: received += si.get('qty_sent', 0)
            elif ship.get('status') == 'Received':
                received += si.get('qty_sent', 0)
        total_defect = sum(d.get('defect_qty', 0) for d in _s_def_by_poi.get(item['id'], []))
        available = max(0, received - total_defect)
        produced = sum(ji.get('produced_qty', 0) for ji in _s_ji_by_poi.get(item['id'], []))
        shipped  = sum(bi.get('qty_shipped', 0) for bi in _s_bi_by_poi.get(item['id'], []))
        returned = sum(ri.get('return_qty', 0) for ri in _s_ri_by_poi.get(item['id'], []))
        ordered = item.get('qty', 0)
        over = max(0, produced - ordered); under = max(0, ordered - produced)
        summary_items.append({
            **serialize_doc(item),
            'ordered_qty': ordered, 'received_qty': received, 'missing_qty': missing,
            'defect_qty': total_defect, 'available_qty': available, 'produced_qty': produced,
            'shipped_qty': shipped, 'returned_qty': returned,
            'overproduction_qty': over, 'underproduction_qty': under
        })
        totals['ordered'] += ordered; totals['received'] += received
        totals['missing'] += missing; totals['defect'] += total_defect
        totals['available'] += available; totals['produced'] += produced
        totals['shipped'] += shipped; totals['returned'] += returned
    totals['overproduction'] = max(0, totals['produced'] - totals['ordered'])
    totals['underproduction'] = max(0, totals['ordered'] - totals['produced'])
    return {'po': serialize_doc(po), 'items': summary_items, 'totals': totals}

# ─── SERIAL TRACKING TIMELINE ───────────────────────────────────────────────
@api.get("/serial-list")
async def serial_list(request: Request):
    """Get list of all serial numbers with status info."""
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    search = sp.get('search', '').strip()
    status_filter = sp.get('status', '')  # ongoing, completed, all
    # Build query
    query = {}
    if search:
        query['serial_number'] = {'$regex': search, '$options': 'i'}
    if user.get('role') == 'vendor':
        # Only show serials for vendor's POs
        vendor_pos = await db.production_pos.find({'vendor_id': user.get('vendor_id')}, {'id': 1}).to_list(None)
        vendor_po_ids = [p['id'] for p in vendor_pos]
        query['po_id'] = {'$in': vendor_po_ids}
    po_items = await db.po_items.find(query, {'_id': 0}).sort('created_at', -1).to_list(None)
    # Filter first to only items with serial numbers
    serial_items = [it for it in po_items if it.get('serial_number')]
    if not serial_items: return []
    # ── 10E: batch all lookups in 5 queries instead of 5N+M ──
    item_ids = [it['id'] for it in serial_items]
    po_ids_needed = list({it.get('po_id') for it in serial_items if it.get('po_id')})
    all_pos_docs = await db.production_pos.find({'id': {'$in': po_ids_needed}}, {'_id': 0}).to_list(None) if po_ids_needed else []
    po_map = {p['id']: p for p in all_pos_docs}
    all_ji = await db.production_job_items.find({'po_item_id': {'$in': item_ids}}).to_list(None)
    ji_by_poi: dict = {}
    for ji in all_ji: ji_by_poi.setdefault(ji.get('po_item_id'), []).append(ji)
    all_bi = await db.buyer_shipment_items.find({'po_item_id': {'$in': item_ids}}).to_list(None)
    bi_by_poi: dict = {}
    for bi in all_bi: bi_by_poi.setdefault(bi.get('po_item_id'), []).append(bi)
    all_vs = await db.vendor_shipment_items.find({'po_item_id': {'$in': item_ids}}).to_list(None)
    vs_by_poi: dict = {}
    for vsi in all_vs: vs_by_poi.setdefault(vsi.get('po_item_id'), []).append(vsi)
    all_vsi_ids = [vsi['id'] for vsi in all_vs]
    all_insp_items = await db.vendor_material_inspection_items.find({'shipment_item_id': {'$in': all_vsi_ids}}).to_list(None) if all_vsi_ids else []
    insp_item_by_vsi = {ii.get('shipment_item_id'): ii for ii in all_insp_items}
    result = []
    for item in serial_items:
        po = po_map.get(item.get('po_id'), {})
        ji_list = ji_by_poi.get(item['id'], [])
        produced = sum(j.get('produced_qty', 0) for j in ji_list)
        bi_list = bi_by_poi.get(item['id'], [])
        shipped = sum(b.get('qty_shipped', 0) for b in bi_list)
        ordered = item.get('qty', 0)
        remaining = max(0, ordered - shipped)
        if shipped >= ordered: serial_status = 'completed'
        elif produced > 0 or ji_list: serial_status = 'ongoing'
        else: serial_status = 'pending'
        if status_filter and status_filter != 'all' and serial_status != status_filter: continue
        vs_items_list = vs_by_poi.get(item['id'], [])
        received_qty = 0
        for vsi in vs_items_list:
            insp_i = insp_item_by_vsi.get(vsi['id'])
            if insp_i: received_qty += insp_i.get('received_qty', 0)
            else: received_qty += vsi.get('qty_sent', 0)
        result.append({
            'serial_number': item.get('serial_number'),
            'po_number': po.get('po_number', ''),
            'po_id': item.get('po_id'),
            'customer_name': po.get('customer_name', ''),
            'vendor_name': po.get('vendor_name', ''),
            'product_name': item.get('product_name', ''),
            'sku': item.get('sku', ''),
            'size': item.get('size', ''),
            'color': item.get('color', ''),
            'ordered_qty': ordered,
            'received_qty': received_qty,
            'produced_qty': produced,
            'shipped_qty': shipped,
            'remaining_qty': remaining,
            'status': serial_status,
            'po_status': po.get('status', ''),
            'deadline': serialize_doc(po.get('deadline')),
        })
    return result

@api.get("/serial-trace")
async def serial_trace(request: Request):
    """Get full lifecycle timeline + PO-wide summary for a serial number."""
    await require_auth(request)
    db = get_db()
    serial = request.query_params.get('serial', '').strip()
    if not serial: raise HTTPException(400, 'serial parameter required')
    timeline = []
    # 1. PO items with this serial
    po_items = await db.po_items.find({'serial_number': serial}, {'_id': 0}).to_list(None)
    po_ids = list(set(pi.get('po_id') for pi in po_items if pi.get('po_id')))
    po_item_ids = [pi['id'] for pi in po_items]
    # ── 10E: batch all PO details + PO items in 2 queries ──
    all_po_docs_list = await db.production_pos.find({'id': {'$in': po_ids}}, {'_id': 0}).to_list(None) if po_ids else []
    po_details = {p['id']: p for p in all_po_docs_list}
    all_po_items = await db.po_items.find({'po_id': {'$in': po_ids}}, {'_id': 0}).to_list(None) if po_ids else []
    all_po_item_ids = [pi['id'] for pi in all_po_items]
    # ── 10E: batch all sub-document lookups for timeline + summary ──
    all_ji_docs    = await db.production_job_items.find({'po_item_id': {'$in': all_po_item_ids}}).to_list(None) if all_po_item_ids else []
    all_bi_docs    = await db.buyer_shipment_items.find({'po_item_id': {'$in': all_po_item_ids}}, {'_id': 0}).sort('dispatch_seq', 1).to_list(None) if all_po_item_ids else []
    ji_by_poi: dict = {}
    for ji in all_ji_docs: ji_by_poi.setdefault(ji.get('po_item_id'), []).append(ji)
    bi_by_poi: dict = {}
    for bi in all_bi_docs: bi_by_poi.setdefault(bi.get('po_item_id'), []).append(bi)
    # For timeline: vendor shipment items, inspections, progress, returns (only searched serial po_item_ids)
    trace_vsi    = await db.vendor_shipment_items.find({'po_item_id': {'$in': po_item_ids}}, {'_id': 0}).to_list(None) if po_item_ids else []
    trace_ji     = await db.production_job_items.find({'po_item_id': {'$in': po_item_ids}}, {'_id': 0}).to_list(None) if po_item_ids else []
    trace_bi     = await db.buyer_shipment_items.find({'po_item_id': {'$in': po_item_ids}}, {'_id': 0}).sort('dispatch_seq', 1).to_list(None) if po_item_ids else []
    trace_ri     = await db.production_return_items.find({'po_item_id': {'$in': po_item_ids}}, {'_id': 0}).to_list(None) if po_item_ids else []
    trace_ji_ids = [ji['id'] for ji in trace_ji]
    # Batch parent docs for timeline
    trace_ship_ids    = list({vsi.get('shipment_id') for vsi in trace_vsi if vsi.get('shipment_id')})
    trace_job_ids     = list({ji.get('job_id') for ji in trace_ji if ji.get('job_id')})
    trace_bs_ids      = list({bi.get('shipment_id') for bi in trace_bi if bi.get('shipment_id')})
    trace_ret_ids     = list({ri.get('return_id') for ri in trace_ri if ri.get('return_id')})
    trace_ships_docs  = await db.vendor_shipments.find({'id': {'$in': trace_ship_ids}}, {'_id': 0}).to_list(None) if trace_ship_ids else []
    trace_insp_docs   = await db.vendor_material_inspections.find({'shipment_id': {'$in': trace_ship_ids}}).to_list(None) if trace_ship_ids else []
    trace_job_docs    = await db.production_jobs.find({'id': {'$in': trace_job_ids}}, {'_id': 0}).to_list(None) if trace_job_ids else []
    trace_bs_docs     = await db.buyer_shipments.find({'id': {'$in': trace_bs_ids}}, {'_id': 0}).to_list(None) if trace_bs_ids else []
    trace_ret_docs    = await db.production_returns.find({'id': {'$in': trace_ret_ids}}, {'_id': 0}).to_list(None) if trace_ret_ids else []
    trace_progs       = await db.production_progress.find({'job_item_id': {'$in': trace_ji_ids}}, {'_id': 0}).sort('progress_date', 1).to_list(None) if trace_ji_ids else []
    # Batch inspection items by shipment_item_id
    trace_vsi_ids     = [vsi['id'] for vsi in trace_vsi]
    all_insp_ii       = await db.vendor_material_inspection_items.find({'shipment_item_id': {'$in': trace_vsi_ids}}).to_list(None) if trace_vsi_ids else []
    # Build in-memory maps
    ship_map    = {s['id']: s for s in trace_ships_docs}
    insp_by_ship: dict = {d.get('shipment_id'): d for d in trace_insp_docs}
    insp_ii_by_vsi: dict = {ii.get('shipment_item_id'): ii for ii in all_insp_ii}
    job_map     = {j['id']: j for j in trace_job_docs}
    bs_map      = {b['id']: b for b in trace_bs_docs}
    ret_map     = {r['id']: r for r in trace_ret_docs}
    progs_by_ji: dict = {}
    for p in trace_progs: progs_by_ji.setdefault(p.get('job_item_id'), []).append(p)
    # 3. Build summary for ALL items in the PO
    summary_items = []
    totals = {'ordered': 0, 'produced': 0, 'shipped': 0, 'not_produced': 0, 'not_shipped': 0}
    vendors_set: set = set()
    buyer_names: set = set()
    for item in all_po_items:
        po = po_details.get(item.get('po_id'), {})
        vendors_set.add(po.get('vendor_name', ''))
        buyer_names.add(po.get('customer_name', ''))
        produced = sum(j.get('produced_qty', 0) for j in ji_by_poi.get(item['id'], []))
        shipped  = sum(b.get('qty_shipped', 0) for b in bi_by_poi.get(item['id'], []))
        ordered  = item.get('qty', 0)
        summary_items.append({
            'po_item_id': item['id'], 'serial_number': item.get('serial_number', ''),
            'product_name': item.get('product_name', ''), 'sku': item.get('sku', ''),
            'size': item.get('size', ''), 'color': item.get('color', ''),
            'ordered_qty': ordered, 'produced_qty': produced, 'shipped_qty': shipped,
            'not_produced': max(0, ordered - produced), 'not_shipped': max(0, ordered - shipped),
            'is_searched_serial': item.get('serial_number') == serial,
            'po_number': item.get('po_number', po.get('po_number', ''))
        })
        totals['ordered'] += ordered; totals['produced'] += produced; totals['shipped'] += shipped
    totals['not_produced'] = max(0, totals['ordered'] - totals['produced'])
    totals['not_shipped']  = max(0, totals['ordered'] - totals['shipped'])
    # 4. Build timeline events for the SEARCHED serial only
    for pi in po_items:
        po = po_details.get(pi.get('po_id'), {})
        timeline.append({
            'step': 'PO Created', 'event': 'PO Dibuat',
            'details': f"PO {po.get('po_number','')} - {pi.get('product_name','')} ({pi.get('sku','')}) x{pi.get('qty',0)}",
            'date': serialize_doc(pi.get('created_at')),
            'module': 'production-po', 'po_number': pi.get('po_number'),
            'po_item_id': pi['id'], 'qty': pi.get('qty', 0),
            'sku': pi.get('sku'), 'size': pi.get('size'), 'color': pi.get('color'),
            'customer_name': po.get('customer_name', ''),
            'vendor_name': po.get('vendor_name', ''), 'status': po.get('status', '')
        })
    for vsi in trace_vsi:
        ship = ship_map.get(vsi.get('shipment_id'), {})
        timeline.append({
            'step': f"Vendor Shipment ({ship.get('shipment_type','NORMAL')})",
            'event': f"Pengiriman Vendor ({ship.get('shipment_type','NORMAL')})",
            'details': f"Shipment {ship.get('shipment_number','')} - dikirim {vsi.get('qty_sent',0)} pcs",
            'date': serialize_doc(ship.get('shipment_date', vsi.get('created_at'))),
            'module': 'vendor-shipments', 'shipment_number': ship.get('shipment_number',''),
            'qty_sent': vsi.get('qty_sent', 0), 'status': ship.get('status',''),
            'inspection_status': ship.get('inspection_status','Pending')
        })
        insp = insp_by_ship.get(vsi.get('shipment_id'))
        if insp:
            ii = insp_ii_by_vsi.get(vsi['id'])
            if ii:
                timeline.append({'step': 'Material Inspection', 'event': 'Inspeksi Material',
                    'details': f"Diterima: {ii.get('received_qty',0)}, Missing: {ii.get('missing_qty',0)}, Defect: {ii.get('defect_qty',0)}",
                    'date': serialize_doc(insp.get('inspection_date')),
                    'module': 'inspections', 'received_qty': ii.get('received_qty',0),
                    'missing_qty': ii.get('missing_qty',0), 'condition_notes': ii.get('condition_notes','')})
    for ji in trace_ji:
        job = job_map.get(ji.get('job_id'), {})
        timeline.append({'step': 'Production Job', 'event': 'Job Produksi Dibuat',
            'details': f"Job {job.get('job_number','')} - tersedia {ji.get('available_qty',0)} pcs, diproduksi {ji.get('produced_qty',0)} pcs",
            'date': serialize_doc(ji.get('created_at')),
            'module': 'production-jobs', 'job_number': job.get('job_number',''),
            'available_qty': ji.get('available_qty',0), 'produced_qty': ji.get('produced_qty',0),
            'status': job.get('status','')})
        for p in progs_by_ji.get(ji['id'], []):
            timeline.append({'step': 'Production Progress', 'event': 'Progres Produksi',
                'details': f"Selesai {p.get('completed_quantity',0)} pcs - {p.get('notes','')}",
                'date': serialize_doc(p.get('progress_date')),
                'module': 'production-progress', 'completed_quantity': p.get('completed_quantity',0),
                'notes': p.get('notes',''), 'recorded_by': p.get('recorded_by','')})
    for bi in trace_bi:
        bs = bs_map.get(bi.get('shipment_id'), {})
        timeline.append({'step': f"Buyer Dispatch #{bi.get('dispatch_seq',1)}",
            'event': f"Pengiriman ke Buyer #{bi.get('dispatch_seq',1)}",
            'details': f"Shipment {bs.get('shipment_number','')} - dikirim {bi.get('qty_shipped',0)} pcs",
            'date': serialize_doc(bi.get('dispatch_date', bi.get('created_at'))),
            'module': 'buyer-shipments', 'shipment_number': bs.get('shipment_number',''),
            'qty_shipped': bi.get('qty_shipped',0), 'ordered_qty': bi.get('ordered_qty',0)})
    for ri in trace_ri:
        ret = ret_map.get(ri.get('return_id'), {})
        timeline.append({'step': 'Production Return', 'event': 'Retur Produksi',
            'details': f"Return {ret.get('return_number','')} - {ri.get('return_qty',0)} pcs",
            'date': serialize_doc(ret.get('return_date')),
            'module': 'production-returns', 'return_number': ret.get('return_number',''),
            'return_qty': ri.get('return_qty',0), 'status': ret.get('status','')})
    timeline.sort(key=lambda x: x.get('date', '') or '')
    # Build PO info
    po_info = []
    for pid in po_ids:
        po = po_details.get(pid, {})
        po_info.append({'po_id': pid, 'po_number': po.get('po_number', ''),
            'customer_name': po.get('customer_name', ''), 'vendor_name': po.get('vendor_name', ''),
            'status': po.get('status', ''), 'deadline': serialize_doc(po.get('deadline'))})
    return {
        'serial_number': serial, 'po_item_count': len(po_items),
        'po_count': len(po_ids), 'po_info': po_info,
        'summary': {
            'buyer': ', '.join(filter(None, buyer_names)),
            'vendors': ', '.join(filter(None, vendors_set)),
            'total_ordered': totals['ordered'], 'total_produced': totals['produced'],
            'total_not_produced': totals['not_produced'], 'total_shipped': totals['shipped'],
            'total_not_shipped': totals['not_shipped'],
            'all_serials': list(set(i.get('serial_number', '') for i in all_po_items if i.get('serial_number'))),
        },
        'all_items': summary_items, 'timeline': timeline
    }

# ─── ACCESSORY MANAGEMENT ───────────────────────────────────────────────────
@api.get("/accessories")
async def get_accessories(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('search'):
        # Support both canonical (accessory_name/accessory_code) and legacy (name/code) for backward-compat.
        s = sp['search']
        query['$or'] = [
            {'accessory_name': {'$regex': s, '$options': 'i'}},
            {'accessory_code': {'$regex': s, '$options': 'i'}},
            {'name': {'$regex': s, '$options': 'i'}},
            {'code': {'$regex': s, '$options': 'i'}},
        ]
    if sp.get('status'): query['status'] = sp['status']
    docs = await db.accessories.find(query, {'_id': 0}).sort('created_at', -1).to_list(None)
    # On-read normalization: ensure legacy records also expose canonical field names to the UI.
    for d in docs:
        if not d.get('accessory_name') and d.get('name'):
            d['accessory_name'] = d['name']
        if not d.get('accessory_code') and d.get('code'):
            d['accessory_code'] = d['code']
    return serialize_doc(docs)

@api.post("/accessories")
async def create_accessory(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    # Normalize legacy field names to canonical ones so all modules (PO, inspeksi, smart import) see the same shape.
    if body.get('name') and not body.get('accessory_name'):
        body['accessory_name'] = body.pop('name')
    elif body.get('name'):
        body.pop('name', None)
    if body.get('code') and not body.get('accessory_code'):
        body['accessory_code'] = body.pop('code')
    elif body.get('code'):
        body.pop('code', None)
    if not body.get('accessory_name'):
        raise HTTPException(400, 'Nama aksesoris wajib diisi')
    acc = {'id': new_id(), **body, 'status': body.get('status', 'active'),
           'created_at': now(), 'updated_at': now()}
    await db.accessories.insert_one(acc)
    await log_activity(user['id'], user['name'], 'Create', 'Accessories', f"Created accessory: {body.get('accessory_name')}")
    return JSONResponse(serialize_doc(acc), status_code=201)

@api.put("/accessories/{acc_id}")
async def update_accessory(acc_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None)
    # Same legacy → canonical normalization on update.
    if body.get('name') and not body.get('accessory_name'):
        body['accessory_name'] = body.pop('name')
    elif 'name' in body:
        body.pop('name', None)
    if body.get('code') and not body.get('accessory_code'):
        body['accessory_code'] = body.pop('code')
    elif 'code' in body:
        body.pop('code', None)
    await db.accessories.update_one({'id': acc_id}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.accessories.find_one({'id': acc_id}, {'_id': 0}))

@api.delete("/accessories/{acc_id}")
async def delete_accessory(acc_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    await db.accessories.delete_one({'id': acc_id})
    return {'success': True}

# ─── ACCESSORY SHIPMENTS ────────────────────────────────────────────────────
@api.get("/accessory-shipments")
async def get_accessory_shipments(request: Request):
    user = await require_auth(request)
    db = get_db()
    query = {}
    sp = request.query_params
    if sp.get('po_id'): query['po_id'] = sp['po_id']
    if sp.get('vendor_id'): query['vendor_id'] = sp['vendor_id']
    if user.get('role') == 'vendor': query['vendor_id'] = user.get('vendor_id')
    shipments = await db.accessory_shipments.find(query, {'_id': 0}).sort('created_at', -1).to_list(None)
    result = []
    for s in shipments:
        items = await db.accessory_shipment_items.find({'shipment_id': s['id']}, {'_id': 0}).to_list(None)
        result.append({**serialize_doc(s), 'items': serialize_doc(items)})
    return result

@api.post("/accessory-shipments")
async def create_accessory_shipment(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    vendor = await db.garments.find_one({'id': body.get('vendor_id')})
    if not vendor: raise HTTPException(404, 'Vendor not found')
    ship_id = new_id()
    shipment = {
        'id': ship_id, 'shipment_number': body.get('shipment_number'),
        'vendor_id': body['vendor_id'], 'vendor_name': vendor.get('garment_name', ''),
        'po_id': body.get('po_id'), 'po_number': body.get('po_number', ''),
        'shipment_date': parse_date(body.get('shipment_date')) or now(),
        'status': 'Sent', 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.accessory_shipments.insert_one(shipment)
    inserted_items = []
    for item in body.get('items', []):
        si = {
            'id': new_id(), 'shipment_id': ship_id,
            'accessory_id': item.get('accessory_id'),
            'accessory_name': item.get('accessory_name', ''),
            'accessory_code': item.get('accessory_code', ''),
            'qty_sent': int(item.get('qty_sent', 0) or 0),
            'unit': item.get('unit', 'pcs'),
            'notes': item.get('notes', ''), 'created_at': now()
        }
        await db.accessory_shipment_items.insert_one(si)
        inserted_items.append(si)
    await log_activity(user['id'], user['name'], 'Create', 'Accessory Shipment',
                       f"Created accessory shipment {body.get('shipment_number')}")
    result = serialize_doc(shipment)
    result['items'] = serialize_doc(inserted_items)
    return JSONResponse(result, status_code=201)

@api.put("/accessory-shipments/{sid}")
async def update_accessory_shipment(sid: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None); body.pop('items', None)
    await db.accessory_shipments.update_one({'id': sid}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.accessory_shipments.find_one({'id': sid}, {'_id': 0}))

@api.delete("/accessory-shipments/{sid}")
async def delete_accessory_shipment(sid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    await db.accessory_shipment_items.delete_many({'shipment_id': sid})
    await db.accessory_shipments.delete_one({'id': sid})
    return {'success': True}

# ─── ACCESSORY INSPECTIONS ───────────────────────────────────────────────────
@api.get("/accessory-inspections")
async def get_acc_inspections(request: Request):
    user = await require_auth(request)
    db = get_db()
    query = {}
    sp = request.query_params
    if sp.get('shipment_id'): query['shipment_id'] = sp['shipment_id']
    if sp.get('vendor_id'): query['vendor_id'] = sp['vendor_id']
    if user.get('role') == 'vendor': query['vendor_id'] = user.get('vendor_id')
    return serialize_doc(await db.accessory_inspections.find(query, {'_id': 0}).sort('created_at', -1).to_list(None))

@api.post("/accessory-inspections")
async def create_acc_inspection(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    vendor_id = user.get('vendor_id') if user.get('role') == 'vendor' else body.get('vendor_id')
    shipment = await db.accessory_shipments.find_one({'id': body.get('shipment_id')}) if body.get('shipment_id') else None
    if not shipment: raise HTTPException(404, 'Accessory shipment tidak ditemukan')
    existing = await db.accessory_inspections.find_one({'shipment_id': body['shipment_id']})
    if existing: raise HTTPException(400, 'Inspeksi sudah dilakukan untuk shipment ini')
    insp_id = new_id()
    items_data = body.get('items', [])
    total_received = sum(int(i.get('received_qty', 0) or 0) for i in items_data)
    total_missing = sum(int(i.get('missing_qty', 0) or 0) for i in items_data)
    inspection = {
        'id': insp_id, 'shipment_id': body['shipment_id'],
        'vendor_id': vendor_id, 'vendor_name': shipment.get('vendor_name', ''),
        'po_id': shipment.get('po_id'), 'po_number': shipment.get('po_number', ''),
        'inspection_date': parse_date(body.get('inspection_date')) or now(),
        'total_received': total_received, 'total_missing': total_missing,
        'notes': body.get('notes', ''), 'status': 'Submitted',
        'submitted_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.accessory_inspections.insert_one(inspection)
    for item in items_data:
        await db.accessory_inspection_items.insert_one({
            'id': new_id(), 'inspection_id': insp_id,
            'shipment_item_id': item.get('shipment_item_id'),
            'accessory_name': item.get('accessory_name', ''), 'accessory_code': item.get('accessory_code', ''),
            'qty_sent': int(item.get('qty_sent', 0) or 0),
            'received_qty': int(item.get('received_qty', 0) or 0),
            'missing_qty': int(item.get('missing_qty', 0) or 0),
            'condition_notes': item.get('condition_notes', ''), 'created_at': now()
        })
    await db.accessory_shipments.update_one({'id': body['shipment_id']}, {'$set': {
        'inspection_status': 'Inspected', 'total_received': total_received,
        'total_missing': total_missing, 'updated_at': now()
    }})
    await log_activity(user['id'], user['name'], 'Create', 'Accessory Inspection',
                       f"Inspeksi aksesoris shipment {shipment.get('shipment_number')}")
    result = serialize_doc(inspection)
    items_docs = await db.accessory_inspection_items.find({'inspection_id': insp_id}, {'_id': 0}).to_list(None)
    result['items'] = serialize_doc(items_docs)
    return JSONResponse(result, status_code=201)

# ─── ACCESSORY DEFECTS ──────────────────────────────────────────────────────
@api.get("/accessory-defects")
async def get_acc_defects(request: Request):
    user = await require_auth(request)
    db = get_db()
    query = {}
    if user.get('role') == 'vendor': query['vendor_id'] = user.get('vendor_id')
    if request.query_params.get('vendor_id'): query['vendor_id'] = request.query_params['vendor_id']
    return serialize_doc(await db.accessory_defects.find(query, {'_id': 0}).sort('created_at', -1).to_list(None))

@api.post("/accessory-defects")
async def create_acc_defect(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    vendor_id = user.get('vendor_id') if user.get('role') == 'vendor' else body.get('vendor_id')
    if not vendor_id: raise HTTPException(400, 'vendor_id diperlukan')
    defect = {
        'id': new_id(), 'vendor_id': vendor_id,
        'po_id': body.get('po_id'), 'shipment_id': body.get('shipment_id'),
        'accessory_name': body.get('accessory_name', ''), 'accessory_code': body.get('accessory_code', ''),
        'defect_qty': int(body.get('defect_qty', 0) or 0),
        'defect_type': body.get('defect_type', 'Material Cacat'),
        'description': body.get('description', ''),
        'report_date': parse_date(body.get('report_date')) or now(),
        'status': 'Reported', 'reported_by': user['name'],
        'created_at': now(), 'updated_at': now()
    }
    await db.accessory_defects.insert_one(defect)
    await log_activity(user['id'], user['name'], 'Create', 'Accessory Defect',
                       f"Laporan cacat aksesoris: {body.get('accessory_name')} - {body.get('defect_qty')} pcs")
    return JSONResponse(serialize_doc(defect), status_code=201)

# ─── ACCESSORY REQUESTS ─────────────────────────────────────────────────────
@api.get("/accessory-requests")
async def get_acc_requests(request: Request):
    user = await require_auth(request)
    db = get_db()
    query = {}
    sp = request.query_params
    if user.get('role') == 'vendor': query['vendor_id'] = user.get('vendor_id')
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('request_type'): query['request_type'] = sp['request_type']
    return serialize_doc(await db.accessory_requests.find(query, {'_id': 0}).sort('created_at', -1).to_list(None))

@api.post("/accessory-requests")
async def create_acc_request(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    vendor_id = user.get('vendor_id') if user.get('role') == 'vendor' else body.get('vendor_id')
    if not vendor_id: raise HTTPException(400, 'vendor_id diperlukan')
    if body.get('request_type') not in ['ADDITIONAL', 'REPLACEMENT']:
        raise HTTPException(400, 'request_type harus ADDITIONAL atau REPLACEMENT')
    seq = (await db.accessory_requests.count_documents({})) + 1
    prefix = 'ACC-ADD' if body['request_type'] == 'ADDITIONAL' else 'ACC-RPL'
    req_doc = {
        'id': new_id(), 'request_number': f"{prefix}-{str(seq).zfill(4)}",
        'request_type': body['request_type'],
        'vendor_id': vendor_id,
        'original_shipment_id': body.get('original_shipment_id'),
        'po_id': body.get('po_id'), 'po_number': body.get('po_number', ''),
        'items': body.get('items', []),
        'total_requested_qty': sum(int(i.get('requested_qty', 0) or 0) for i in body.get('items', [])),
        'reason': body.get('reason', ''), 'status': 'Pending',
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.accessory_requests.insert_one(req_doc)
    await log_activity(user['id'], user['name'], 'Create', 'Accessory Request',
                       f"Request aksesoris {body['request_type']}: {req_doc['request_number']}")
    return JSONResponse(serialize_doc(req_doc), status_code=201)

@api.put("/accessory-requests/{req_id}")
async def update_acc_request(req_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    req = await db.accessory_requests.find_one({'id': req_id})
    if not req: raise HTTPException(404, 'Request tidak ditemukan')
    new_status = body.get('status')
    if new_status == 'Approved' and req.get('status') == 'Pending':
        orig_ship = await db.accessory_shipments.find_one({'id': req.get('original_shipment_id')})
        if orig_ship:
            existing_children = await db.accessory_shipments.count_documents({
                'parent_shipment_id': req['original_shipment_id']})
            suffix = f"A{existing_children + 1}" if req['request_type'] == 'ADDITIONAL' else f"R{existing_children + 1}"
            child_number = f"{orig_ship.get('shipment_number', '')}-{suffix}"
            child_id = new_id()
            child_ship = {
                'id': child_id, 'shipment_number': child_number,
                'vendor_id': orig_ship.get('vendor_id'), 'vendor_name': orig_ship.get('vendor_name', ''),
                'po_id': orig_ship.get('po_id'), 'po_number': orig_ship.get('po_number', ''),
                'shipment_date': now(), 'shipment_type': req['request_type'],
                'parent_shipment_id': req['original_shipment_id'],
                'status': 'Sent', 'notes': f"Child accessory shipment ({req['request_type']})",
                'created_by': user['name'], 'created_at': now(), 'updated_at': now()
            }
            await db.accessory_shipments.insert_one(child_ship)
            for ri in req.get('items', []):
                await db.accessory_shipment_items.insert_one({
                    'id': new_id(), 'shipment_id': child_id,
                    'accessory_name': ri.get('accessory_name', ''), 'accessory_code': ri.get('accessory_code', ''),
                    'qty_sent': int(ri.get('requested_qty', 0) or 0), 'unit': ri.get('unit', 'pcs'),
                    'created_at': now()
                })
            await db.accessory_requests.update_one({'id': req_id}, {'$set': {
                'status': 'Approved', 'admin_notes': body.get('admin_notes', ''),
                'approved_by': user['name'], 'approved_at': now(),
                'child_shipment_id': child_id, 'child_shipment_number': child_number,
                'updated_at': now()
            }})
            result = serialize_doc(await db.accessory_requests.find_one({'id': req_id}, {'_id': 0}))
            result['child_shipment'] = serialize_doc(child_ship)
            return result
    if new_status == 'Rejected':
        await db.accessory_requests.update_one({'id': req_id}, {'$set': {
            'status': 'Rejected', 'admin_notes': body.get('admin_notes', ''), 'updated_at': now()
        }})
    else:
        upd = {k: v for k, v in body.items() if k not in ('_id', 'id')}
        await db.accessory_requests.update_one({'id': req_id}, {'$set': {**upd, 'updated_at': now()}})
    return serialize_doc(await db.accessory_requests.find_one({'id': req_id}, {'_id': 0}))


# ─── REMINDER SYSTEM ─────────────────────────────────────────────────────────
@api.get("/reminders")
async def get_reminders(request: Request):
    user = await require_auth(request)
    db = get_db()
    query = {}
    if user.get('role') == 'vendor':
        query['vendor_id'] = user.get('vendor_id')
    sp = request.query_params
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('vendor_id') and user.get('role') != 'vendor': query['vendor_id'] = sp['vendor_id']
    reminders = await db.reminders.find(query, {'_id': 0}).sort('created_at', -1).to_list(None)
    return serialize_doc(reminders)

@api.post("/reminders")
async def create_reminder(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    vendor_id = body.get('vendor_id')
    if not vendor_id: raise HTTPException(400, 'vendor_id required')
    vendor = await db.garments.find_one({'id': vendor_id})
    reminder = {
        'id': new_id(),
        'vendor_id': vendor_id, 'vendor_name': (vendor or {}).get('garment_name', ''),
        'po_id': body.get('po_id', ''), 'po_number': body.get('po_number', ''),
        'reminder_type': body.get('reminder_type', 'general'),
        'subject': body.get('subject', ''), 'message': body.get('message', ''),
        'priority': body.get('priority', 'normal'),
        'status': 'pending', 'response': None, 'response_date': None,
        'created_by': user.get('name', ''), 'created_at': now(), 'updated_at': now()
    }
    await db.reminders.insert_one(reminder)
    await log_activity(user['id'], user.get('name', ''), 'create', 'reminder', f"Sent reminder to {(vendor or {}).get('garment_name', vendor_id)}")
    return JSONResponse(serialize_doc({k: v for k, v in reminder.items() if k != '_id'}), status_code=201)

@api.put("/reminders/{reminder_id}")
async def update_reminder(reminder_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    existing = await db.reminders.find_one({'id': reminder_id})
    if not existing: raise HTTPException(404, 'Reminder not found')
    update = {'updated_at': now()}
    # Vendor responding
    if user.get('role') == 'vendor' and body.get('response'):
        update['response'] = body['response']
        update['response_date'] = now()
        update['responded_by'] = user.get('name', '')
        update['status'] = 'responded'
    # Admin updating
    if user.get('role') in ['admin', 'superadmin']:
        if 'status' in body: update['status'] = body['status']
        if 'message' in body: update['message'] = body['message']
    await db.reminders.update_one({'id': reminder_id}, {'$set': update})
    return serialize_doc(await db.reminders.find_one({'id': reminder_id}, {'_id': 0}))

@api.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    await db.reminders.delete_one({'id': reminder_id})
    return {'success': True}


# ─── RBAC ────────────────────────────────────────────────────────────────────
@api.get("/roles")
async def get_roles(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    roles = await db.roles.find({}, {'_id': 0}).sort('name', 1).to_list(None)
    # ── 10E: batch all permissions in 1 query ──
    role_ids = [r['id'] for r in roles]
    all_perms = await db.role_permissions.find({'role_id': {'$in': role_ids}}, {'_id': 0}).to_list(None) if role_ids else []
    perms_by_role: dict = {}
    for p in all_perms: perms_by_role.setdefault(p.get('role_id'), []).append(p)
    result = []
    for r in roles:
        result.append({**serialize_doc(r), 'permissions': serialize_doc(perms_by_role.get(r['id'], []))})
    return result

@api.post("/roles")
async def create_role(request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    existing = await db.roles.find_one({'name': body.get('name')})
    if existing: raise HTTPException(400, f"Role '{body['name']}' already exists")
    role = {'id': new_id(), 'name': body['name'], 'description': body.get('description', ''),
            'is_system': False, 'created_at': now(), 'updated_at': now()}
    await db.roles.insert_one(role)
    # Assign permissions
    for perm_key in body.get('permissions', []):
        await db.role_permissions.insert_one({
            'id': new_id(), 'role_id': role['id'], 'permission_key': perm_key, 'created_at': now()
        })
    return JSONResponse(serialize_doc(role), status_code=201)

@api.put("/roles/{role_id}")
async def update_role(role_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    await db.roles.update_one({'id': role_id}, {'$set': {
        'name': body.get('name'), 'description': body.get('description', ''), 'updated_at': now()
    }})
    if 'permissions' in body:
        await db.role_permissions.delete_many({'role_id': role_id})
        for perm_key in body['permissions']:
            await db.role_permissions.insert_one({
                'id': new_id(), 'role_id': role_id, 'permission_key': perm_key, 'created_at': now()
            })
        # ── 10E: invalidate perm cache for this role ──
        from auth import _perm_cache
        role_doc = await db.roles.find_one({'id': role_id}, {'_id': 0, 'name': 1})
        if role_doc: _perm_cache.invalidate(role_doc.get('name'))
    return serialize_doc(await db.roles.find_one({'id': role_id}, {'_id': 0}))

@api.delete("/roles/{role_id}")
async def delete_role(role_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    role = await db.roles.find_one({'id': role_id})
    if role and role.get('is_system'): raise HTTPException(400, 'Cannot delete system role')
    await db.role_permissions.delete_many({'role_id': role_id})
    await db.roles.delete_one({'id': role_id})
    return {'success': True}

@api.get("/permissions")
async def get_permissions(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    # Return available permission keys
    permissions = [
        {"key": "dashboard.view", "module": "Dashboard", "description": "View dashboard"},
        {"key": "products.view", "module": "Products", "description": "View products"},
        {"key": "products.create", "module": "Products", "description": "Create products"},
        {"key": "products.edit", "module": "Products", "description": "Edit products"},
        {"key": "products.delete", "module": "Products", "description": "Delete products"},
        {"key": "garments.view", "module": "Garments", "description": "View vendors"},
        {"key": "garments.create", "module": "Garments", "description": "Create vendors"},
        {"key": "garments.edit", "module": "Garments", "description": "Edit vendors"},
        {"key": "garments.delete", "module": "Garments", "description": "Delete vendors"},
        {"key": "po.view", "module": "Production PO", "description": "View POs"},
        {"key": "po.create", "module": "Production PO", "description": "Create POs"},
        {"key": "po.edit", "module": "Production PO", "description": "Edit POs"},
        {"key": "po.delete", "module": "Production PO", "description": "Delete POs"},
        {"key": "po.close", "module": "Production PO", "description": "Close POs"},
        {"key": "shipment.view", "module": "Shipments", "description": "View shipments"},
        {"key": "shipment.create", "module": "Shipments", "description": "Create shipments"},
        {"key": "jobs.view", "module": "Production Jobs", "description": "View production jobs"},
        {"key": "jobs.create", "module": "Production Jobs", "description": "Create production jobs"},
        {"key": "progress.view", "module": "Production Progress", "description": "View progress"},
        {"key": "progress.create", "module": "Production Progress", "description": "Report progress"},
        {"key": "invoice.view", "module": "Invoices", "description": "View invoices"},
        {"key": "invoice.create", "module": "Invoices", "description": "Create invoices"},
        {"key": "invoice.edit", "module": "Invoices", "description": "Edit invoices"},
        {"key": "payment.view", "module": "Payments", "description": "View payments"},
        {"key": "payment.create", "module": "Payments", "description": "Create payments"},
        {"key": "report.view", "module": "Reports", "description": "View reports"},
        {"key": "report.export", "module": "Reports", "description": "Export reports"},
        {"key": "users.view", "module": "Users", "description": "View users"},
        {"key": "users.manage", "module": "Users", "description": "Manage users"},
        {"key": "roles.manage", "module": "Roles", "description": "Manage roles"},
        {"key": "accessories.view", "module": "Accessories", "description": "View accessories"},
        {"key": "accessories.manage", "module": "Accessories", "description": "Manage accessories"},
        {"key": "requests.approve", "module": "Material Requests", "description": "Approve material requests"},
        {"key": "settings.manage", "module": "Settings", "description": "Manage company settings"},
    ]
    return permissions

# ─── PO ACCESSORIES (add-on) ─────────────────────────────────────────────────
@api.get("/po-accessories")
async def get_po_accessories(request: Request):
    """Get accessories linked to a PO."""
    await require_auth(request)
    db = get_db()
    po_id = request.query_params.get('po_id')
    if not po_id: raise HTTPException(400, 'po_id required')
    return serialize_doc(await db.po_accessories.find({'po_id': po_id}, {'_id': 0}).sort('created_at', 1).to_list(None))

@api.post("/po-accessories")
async def add_po_accessory(request: Request):
    """Add accessory to a PO."""
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    po_id = body.get('po_id')
    if not po_id: raise HTTPException(400, 'po_id required')
    items = body.get('items', [])
    inserted = []
    for item in items:
        acc_doc = {
            'id': new_id(), 'po_id': po_id,
            'accessory_id': item.get('accessory_id'),
            'accessory_name': item.get('accessory_name', ''),
            'accessory_code': item.get('accessory_code', ''),
            'qty_needed': int(item.get('qty_needed', 0) or 0),
            'unit': item.get('unit', 'pcs'),
            'notes': item.get('notes', ''),
            'created_at': now()
        }
        await db.po_accessories.insert_one(acc_doc)
        inserted.append(acc_doc)
    await log_activity(user['id'], user['name'], 'Add Accessories', 'Production PO',
                       f"Added {len(inserted)} accessories to PO")
    return JSONResponse(serialize_doc(inserted), status_code=201)

@api.delete("/po-accessories/{acc_id}")
async def remove_po_accessory(acc_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    await db.po_accessories.delete_one({'id': acc_id})
    return {'success': True}

# ─── PRODUCTION VARIANCES (OVERPRODUCTION/UNDERPRODUCTION) ──────────────────
@api.post("/production-variances")
async def create_variance(request: Request):
    """Vendor reports overproduction or underproduction for a job/item"""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    # Get vendor_id from user context if vendor role
    vendor_id = user.get('vendor_id') if user.get('role') == 'vendor' else body.get('vendor_id')
    if not vendor_id: raise HTTPException(400, 'vendor_id required')
    
    # Validate job exists
    job_id = body.get('job_id')
    if not job_id: raise HTTPException(400, 'job_id required')
    job = await db.production_jobs.find_one({'id': job_id})
    if not job: raise HTTPException(404, 'Job not found')
    if job.get('vendor_id') != vendor_id: raise HTTPException(403, 'Job does not belong to this vendor')
    
    # Get PO info
    po_id = job.get('po_id') or body.get('po_id')
    po = await db.production_pos.find_one({'id': po_id}) if po_id else None
    po_number = po.get('po_number', '') if po else ''
    
    variance_type = body.get('variance_type')  # 'OVERPRODUCTION' or 'UNDERPRODUCTION'
    if variance_type not in ['OVERPRODUCTION', 'UNDERPRODUCTION']:
        raise HTTPException(400, 'variance_type must be OVERPRODUCTION or UNDERPRODUCTION')
    
    # Create variance record
    variance = {
        'id': new_id(),
        'vendor_id': vendor_id,
        'vendor_name': job.get('vendor_name', ''),
        'job_id': job_id,
        'job_number': job.get('job_number', ''),
        'po_id': po_id,
        'po_number': po_number,
        'variance_type': variance_type,
        'reason': body.get('reason', ''),
        'notes': body.get('notes', ''),
        'items': body.get('items', []),  # Array of {job_item_id, product_name, sku, ordered_qty, produced_qty, variance_qty}
        'total_variance_qty': sum(int(item.get('variance_qty', 0) or 0) for item in body.get('items', [])),
        'reported_by': user['name'],
        'status': 'Reported',  # Reported, Acknowledged, Resolved
        'created_at': now(),
        'updated_at': now()
    }
    
    await db.production_variances.insert_one(variance)
    await log_activity(user['id'], user['name'], 'Create', 'Production Variance',
                      f"Reported {variance_type} for job {job.get('job_number')}: {variance['total_variance_qty']} pcs")
    
    return JSONResponse(serialize_doc(variance), status_code=201)

@api.get("/production-variances")
async def get_variances(request: Request):
    """List production variances with filters"""
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    
    query = {}
    
    # Vendor filter (auto for vendor role, optional for admin)
    if user.get('role') == 'vendor':
        query['vendor_id'] = user.get('vendor_id')
    elif sp.get('vendor_id'):
        query['vendor_id'] = sp['vendor_id']
    
    # Type filter
    if sp.get('variance_type'):
        query['variance_type'] = sp['variance_type']
    
    # Status filter
    if sp.get('status'):
        query['status'] = sp['status']
    
    # Date range filter
    date_from = parse_date(sp.get('from'))
    date_to = to_end_of_day(sp.get('to'))
    if date_from or date_to:
        date_filter = {}
        if date_from: date_filter['$gte'] = date_from
        if date_to: date_filter['$lte'] = date_to
        if date_filter: query['created_at'] = date_filter
    
    # Search
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'job_number': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
            {'vendor_name': {'$regex': search, '$options': 'i'}},
            {'reason': {'$regex': search, '$options': 'i'}}
        ]
    
    variances = await db.production_variances.find(query, {'_id': 0}).sort('created_at', -1).to_list(None)
    return serialize_doc(variances)

@api.get("/production-variances/stats")
async def get_variance_stats(request: Request):
    """Get summary statistics for production variances"""
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    
    query = {}
    
    # Vendor filter
    if user.get('role') == 'vendor':
        query['vendor_id'] = user.get('vendor_id')
    elif sp.get('vendor_id'):
        query['vendor_id'] = sp['vendor_id']
    
    # Date range filter
    date_from = parse_date(sp.get('from'))
    date_to = to_end_of_day(sp.get('to'))
    if date_from or date_to:
        date_filter = {}
        if date_from: date_filter['$gte'] = date_from
        if date_to: date_filter['$lte'] = date_to
        if date_filter: query['created_at'] = date_filter
    
    # Aggregate stats
    all_variances = await db.production_variances.find(query, {'_id': 0}).to_list(None)
    
    overproduction = [v for v in all_variances if v.get('variance_type') == 'OVERPRODUCTION']
    underproduction = [v for v in all_variances if v.get('variance_type') == 'UNDERPRODUCTION']
    
    stats = {
        'total_records': len(all_variances),
        'overproduction': {
            'count': len(overproduction),
            'total_qty': sum(v.get('total_variance_qty', 0) for v in overproduction)
        },
        'underproduction': {
            'count': len(underproduction),
            'total_qty': sum(v.get('total_variance_qty', 0) for v in underproduction)
        },
        'by_status': {},
        'by_vendor': {}
    }
    
    # Group by status
    for v in all_variances:
        status = v.get('status', 'Unknown')
        if status not in stats['by_status']:
            stats['by_status'][status] = 0
        stats['by_status'][status] += 1
    
    # Group by vendor
    for v in all_variances:
        vname = v.get('vendor_name', 'Unknown')
        if vname not in stats['by_vendor']:
            stats['by_vendor'][vname] = {'overproduction': 0, 'underproduction': 0, 'total_qty': 0}
        stats['by_vendor'][vname][v.get('variance_type', '').lower()] += 1
        stats['by_vendor'][vname]['total_qty'] += v.get('total_variance_qty', 0)
    
    return stats

@api.put("/production-variances/{vid}")
async def update_variance_status(vid: str, request: Request):
    """Admin updates variance status (Acknowledged/Resolved)"""
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    
    variance = await db.production_variances.find_one({'id': vid})
    if not variance: raise HTTPException(404, 'Variance not found')
    
    await db.production_variances.update_one({'id': vid}, {'$set': {
        'status': body.get('status', variance.get('status')),
        'admin_notes': body.get('admin_notes', ''),
        'updated_by': user['name'],
        'updated_at': now()
    }})
    
    await log_activity(user['id'], user['name'], 'Update', 'Production Variance',
                      f"Updated variance status to {body.get('status')} for {variance.get('job_number')}")
    
    return {'success': True}

# ─── RATE LIMITING MIDDLEWARE ────────────────────────────────────────────────
from collections import defaultdict
import time as _time
_rate_limit_store = defaultdict(list)
_RATE_LIMIT = 200  # requests per minute
_RATE_WINDOW = 60  # seconds

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    current = _time.time()
    # Clean old entries
    _rate_limit_store[client_ip] = [t for t in _rate_limit_store[client_ip] if current - t < _RATE_WINDOW]
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT:
        return JSONResponse({"error": "Rate limit exceeded. Max 200 requests/minute."}, status_code=429)
    _rate_limit_store[client_ip].append(current)
    response = await call_next(request)
    return response

# ─── INCLUDE ROUTERS ─────────────────────────────────────────────────────────
app.include_router(api)

# Include modular route files
from routes.buyer_portal import router as buyer_router
from routes.file_storage import router as file_router
from routes.websocket import router as ws_router
from routes.smart_import import router as smart_import_router
app.include_router(buyer_router)
app.include_router(file_router)
app.include_router(ws_router)
app.include_router(smart_import_router)

from routes.pdf_exports import router as pdf_router, PDF_COLUMN_DEFINITIONS
app.include_router(pdf_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
