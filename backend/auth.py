import jwt
import bcrypt
import uuid
import os
import time
import string
import random
from datetime import datetime, timezone, timedelta
from fastapi import Request, HTTPException
from database import get_db

JWT_SECRET = os.environ.get('JWT_SECRET', 'garment_erp_jwt_secret_2025')

# ── 10E: TTL cache for custom-role permissions (avoids 2 DB hits per request) ──
class _PermCache:
    """Thread-safe enough for asyncio; values are plain Python objects."""
    TTL = 300  # 5 minutes
    def __init__(self): self._store: dict = {}
    def get(self, key: str):
        e = self._store.get(key)
        if e and time.monotonic() - e['ts'] < self.TTL: return e['val']
        self._store.pop(key, None); return None
    def set(self, key: str, val): self._store[key] = {'val': val, 'ts': time.monotonic()}
    def invalidate(self, key: str = None):
        if key: self._store.pop(key, None)
        else: self._store.clear()

_perm_cache = _PermCache()


# ── Convenience helper: auth + db in one call ─────────────────────────────
async def db_auth(request: Request):
    """
    Replaces the two-line boilerplate:
        user = await require_auth(request)
        db   = get_db()
    with a single call:
        db, user = await db_auth(request)
    """
    from database import get_db
    user = await require_auth(request)
    db   = get_db()
    return db, user

def generate_password(length=10):
    chars = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789@#!'
    return ''.join(random.choice(chars) for _ in range(length))

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(10)).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_data: dict) -> str:
    payload = {
        'id': user_data['id'],
        'email': user_data['email'],
        'role': user_data['role'],
        'name': user_data['name'],
        'vendor_id': user_data.get('vendor_id'),
        'buyer_id': user_data.get('buyer_id'),
        'customer_name': user_data.get('customer_name', user_data.get('buyer_company', '')),
        'exp': datetime.now(timezone.utc) + timedelta(hours=24)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_token(request: Request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    try:
        token = auth_header.split(' ')[1]
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except Exception:
        return None

async def require_auth(request: Request):
    user = verify_token(request)
    if not user:
        raise HTTPException(status_code=401, detail='Unauthorized')
    # Pre-load permissions for custom roles
    role = user.get('role', '')
    if role == 'superadmin' or role == 'admin':
        user['_permissions'] = ['*']
    elif role == 'vendor':
        user['_permissions'] = ['dashboard.view', 'shipment.view', 'jobs.view', 'jobs.create', 'progress.view', 'progress.create']
    elif role == 'buyer':
        user['_permissions'] = ['dashboard.view', 'po.view', 'shipment.view']
    else:
        # Custom role: load from DB (cached for 5 min via _perm_cache)
        cached = _perm_cache.get(role)
        if cached is not None:
            user['_permissions'] = cached
        else:
            db = get_db()
            custom_role = await db.roles.find_one({'name': role})
            if custom_role:
                role_perms = await db.role_permissions.find({'role_id': custom_role['id']}, {'_id': 0}).to_list(None)
                perms = [rp.get('permission_key') for rp in role_perms]
            else:
                perms = []
            _perm_cache.set(role, perms)
            user['_permissions'] = perms
    return user

def check_role(user: dict, allowed_roles: list, perm_key: str = None) -> bool:
    """Role + permission check.

    Access is granted when ANY of the following is true:
      1. User's role is 'superadmin' (global bypass).
      2. User's role is explicitly listed in `allowed_roles`.
      3. User has wildcard permission '*' (custom admin-equivalent role).
      4. A specific `perm_key` is provided AND the user has that permission.

    IMPORTANT: We intentionally do NOT grant access merely because the user
    has "any" permissions. Previously this fallback allowed vendor/buyer
    users (who always have at least dashboard.view) to bypass admin-only
    guards whenever the endpoint called check_role() without a perm_key.
    """
    if user.get('role') == 'superadmin':
        return True
    if user.get('role') in allowed_roles:
        return True
    # Check custom role permissions loaded by require_auth
    perms = user.get('_permissions', [])
    if '*' in perms:
        return True
    if perm_key and perm_key in perms:
        return True
    return False

async def log_activity(user_id, user_name, action, module, details=''):
    db = get_db()
    await db.activity_logs.insert_one({
        'id': str(uuid.uuid4()),
        'user_id': user_id,
        'user_name': user_name,
        'action': action,
        'module': module,
        'details': details,
        'timestamp': datetime.now(timezone.utc)
    })

async def seed_initial_data():
    db = get_db()
    # Check for old schema migration
    first_product = await db.products.find_one({})
    if first_product and first_product.get('selling_price') is None and first_product.get('product_name'):
        collections_to_clear = ['products', 'garments', 'production_pos', 'po_items',
            'work_orders', 'production_progress', 'invoices', 'payments',
            'product_variants', 'vendor_shipments', 'vendor_shipment_items',
            'buyer_shipments', 'buyer_shipment_items']
        for col in collections_to_clear:
            await db[col].delete_many({})
        print('Migration v2: cleared old schema data')

    # ─── Migration v3: Accessories field alignment ─────────────────────────
    # Older records used {name, code}; the rest of the app (PO items, vendor
    # inspection, PDF exports, smart import) all standardized on
    # {accessory_name, accessory_code}. Normalize legacy docs idempotently.
    try:
        legacy_accs = db.accessories.find({
            '$or': [
                {'name': {'$exists': True}, 'accessory_name': {'$exists': False}},
                {'code': {'$exists': True}, 'accessory_code': {'$exists': False}},
            ]
        }, {'_id': 0})
        migrated = 0
        async for acc in legacy_accs:
            patch = {}
            unset = {}
            if acc.get('name') and not acc.get('accessory_name'):
                patch['accessory_name'] = acc['name']
                unset['name'] = ''
            if acc.get('code') and not acc.get('accessory_code'):
                patch['accessory_code'] = acc['code']
                unset['code'] = ''
            if patch:
                op = {'$set': patch}
                if unset: op['$unset'] = unset
                await db.accessories.update_one({'id': acc['id']}, op)
                migrated += 1
        if migrated:
            print(f'Migration v3: normalized {migrated} accessory record(s) to accessory_name/accessory_code')
    except Exception as e:
        print(f'Migration v3 accessory normalization warning: {e}')

    # Ensure superadmin
    admin = await db.users.find_one({'email': 'admin@garment.com'})
    if not admin:
        hashed = hash_password('Admin@123')
        await db.users.insert_one({
            'id': str(uuid.uuid4()),
            'name': 'Super Admin',
            'email': 'admin@garment.com',
            'password': hashed,
            'role': 'superadmin',
            'status': 'active',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        })
        print('Superadmin seeded: admin@garment.com / Admin@123')

def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict"""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    if isinstance(doc, dict):
        result = {}
        for k, v in doc.items():
            if k == '_id':
                continue
            result[k] = serialize_doc(v)
        return result
    if isinstance(doc, datetime):
        return doc.isoformat()
    return doc
