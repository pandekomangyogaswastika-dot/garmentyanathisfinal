"""Buyer Portal routes - read-only access for buyers."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from database import get_db
from auth import verify_token, require_auth, check_role, hash_password, create_token, log_activity, serialize_doc, generate_password
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/api")

def new_id(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)

# ─── BUYER AUTH ──────────────────────────────────────────────────────────────
@router.post("/buyer/register")
async def register_buyer(request: Request):
    """Admin creates a buyer account."""
    user = await require_auth(request)
    if not check_role(user, ['admin']): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    existing = await db.users.find_one({'email': body.get('email')})
    if existing: raise HTTPException(400, f"Email {body['email']} sudah digunakan")
    buyer_id = new_id()
    buyer_user = {
        'id': buyer_id, 'name': body.get('name', ''),
        'email': body['email'], 'password': hash_password(body.get('password', 'Buyer@123')),
        'role': 'buyer', 'buyer_company': body.get('buyer_company', ''),
        'customer_name': body.get('customer_name', body.get('buyer_company', '')),
        'phone': body.get('phone', ''), 'status': 'active',
        'created_at': now(), 'updated_at': now()
    }
    await db.users.insert_one(buyer_user)
    await log_activity(user['id'], user['name'], 'Create', 'Buyer Account', f"Created buyer: {body['email']}")
    return JSONResponse({k: v for k, v in serialize_doc(buyer_user).items() if k != 'password'}, status_code=201)

# ─── BUYER DASHBOARD ─────────────────────────────────────────────────────────
@router.get("/buyer/portal/dashboard")
async def buyer_dashboard(request: Request):
    user = await require_auth(request)
    if user.get('role') != 'buyer': raise HTTPException(403, 'Forbidden')
    db = get_db()
    customer_name = user.get('customer_name', user.get('name', ''))
    # POs for this buyer
    pos = await db.production_pos.find({'customer_name': {'$regex': customer_name, '$options': 'i'}}, {'_id': 0}).to_list(None)
    po_ids = [p['id'] for p in pos]
    total_pos = len(pos)
    active_pos = len([p for p in pos if p.get('status') in ['In Production', 'Distributed', 'Confirmed']])
    completed_pos = len([p for p in pos if p.get('status') in ['Closed', 'Ready to Close', 'Production Complete']])
    # Buyer shipments
    buyer_ships = []
    for pid in po_ids:
        ships = await db.buyer_shipments.find({'po_id': pid}, {'_id': 0}).to_list(None)
        buyer_ships.extend(ships)
    total_dispatches = 0
    total_shipped = 0
    total_ordered = 0
    for bs in buyer_ships:
        items = await db.buyer_shipment_items.find({'shipment_id': bs['id']}).to_list(None)
        poi_map = {}
        for it in items:
            key = it.get('po_item_id') or it['id']
            if key not in poi_map: poi_map[key] = {'ordered': it.get('ordered_qty', 0), 'shipped': 0}
            poi_map[key]['shipped'] += it.get('qty_shipped', 0)
        total_ordered += sum(v['ordered'] for v in poi_map.values())
        total_shipped += sum(v['shipped'] for v in poi_map.values())
        max_d = max((it.get('dispatch_seq', 1) for it in items), default=0)
        total_dispatches += max_d
    progress_pct = round(total_shipped / total_ordered * 100) if total_ordered > 0 else 0
    return {
        'customer_name': customer_name, 'totalPOs': total_pos,
        'activePOs': active_pos, 'completedPOs': completed_pos,
        'totalDispatches': total_dispatches, 'totalShipped': total_shipped,
        'totalOrdered': total_ordered, 'progressPct': progress_pct,
        'recentPOs': serialize_doc(pos[:5])
    }

# ─── BUYER PO LIST ───────────────────────────────────────────────────────────
@router.get("/buyer/portal/pos")
async def buyer_pos(request: Request):
    user = await require_auth(request)
    if user.get('role') != 'buyer': raise HTTPException(403, 'Forbidden')
    db = get_db()
    customer_name = user.get('customer_name', user.get('name', ''))
    pos = await db.production_pos.find({'customer_name': {'$regex': customer_name, '$options': 'i'}}, {'_id': 0}).sort('created_at', -1).to_list(None)
    result = []
    for po in pos:
        items = await db.po_items.find({'po_id': po['id']}, {'_id': 0}).to_list(None)
        total_qty = sum(i.get('qty', 0) for i in items)
        result.append({**serialize_doc(po), 'item_count': len(items), 'total_qty': total_qty})
    return result

# ─── BUYER SHIPMENT HISTORY ──────────────────────────────────────────────────
@router.get("/buyer/portal/shipments")
async def buyer_shipments(request: Request):
    user = await require_auth(request)
    if user.get('role') != 'buyer': raise HTTPException(403, 'Forbidden')
    db = get_db()
    customer_name = user.get('customer_name', user.get('name', ''))
    pos = await db.production_pos.find({'customer_name': {'$regex': customer_name, '$options': 'i'}}).to_list(None)
    po_ids = [p['id'] for p in pos]
    all_ships = []
    for pid in po_ids:
        ships = await db.buyer_shipments.find({'po_id': pid}, {'_id': 0}).sort('created_at', -1).to_list(None)
        for s in ships:
            items = await db.buyer_shipment_items.find({'shipment_id': s['id']}, {'_id': 0}).to_list(None)
            poi_map = {}
            for it in items:
                key = it.get('po_item_id') or it['id']
                if key not in poi_map: poi_map[key] = {'ordered': it.get('ordered_qty', 0), 'shipped': 0}
                poi_map[key]['shipped'] += it.get('qty_shipped', 0)
            total_ordered = sum(v['ordered'] for v in poi_map.values())
            total_shipped = sum(v['shipped'] for v in poi_map.values())
            max_d = max((it.get('dispatch_seq', 1) for it in items), default=0)
            all_ships.append({**serialize_doc(s), 'total_ordered': total_ordered, 'total_shipped': total_shipped,
                              'remaining': max(0, total_ordered - total_shipped),
                              'progress_pct': round(total_shipped / total_ordered * 100) if total_ordered > 0 else 0,
                              'dispatch_count': max_d})
    return all_ships

# ─── BUYER DISPATCH DETAIL ───────────────────────────────────────────────────
@router.get("/buyer/portal/shipments/{ship_id}")
async def buyer_shipment_detail(ship_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'buyer': raise HTTPException(403, 'Forbidden')
    db = get_db()
    s = await db.buyer_shipments.find_one({'id': ship_id}, {'_id': 0})
    if not s: raise HTTPException(404, 'Not found')
    # Verify buyer owns this
    customer_name = user.get('customer_name', user.get('name', ''))
    po = await db.production_pos.find_one({'id': s.get('po_id')}) if s.get('po_id') else None
    if po and customer_name.lower() not in (po.get('customer_name', '')).lower():
        raise HTTPException(403, 'Not your shipment')
    items = await db.buyer_shipment_items.find({'shipment_id': ship_id}, {'_id': 0}).sort([('dispatch_seq', 1), ('created_at', 1)]).to_list(None)
    dispatch_map = {}
    for item in items:
        seq = item.get('dispatch_seq', 1)
        if seq not in dispatch_map:
            dispatch_map[seq] = {'dispatch_seq': seq, 'dispatch_date': serialize_doc(item.get('dispatch_date') or item.get('created_at')), 'items': [], 'total_qty': 0}
        dispatch_map[seq]['items'].append(serialize_doc(item))
        dispatch_map[seq]['total_qty'] += item.get('qty_shipped', 0)
    dispatches = sorted(dispatch_map.values(), key=lambda d: d['dispatch_seq'])
    return {**serialize_doc(s), 'dispatches': dispatches, 'items': serialize_doc(items)}

# ─── BUYER SERIAL TRACE ──────────────────────────────────────────────────────
@router.get("/buyer/portal/serial-trace")
async def buyer_serial_trace(request: Request):
    user = await require_auth(request)
    if user.get('role') != 'buyer': raise HTTPException(403, 'Forbidden')
    db = get_db()
    serial = request.query_params.get('serial', '').strip()
    if not serial: raise HTTPException(400, 'serial required')
    customer_name = user.get('customer_name', user.get('name', ''))
    # Only show PO items belonging to this buyer
    po_items = await db.po_items.find({'serial_number': serial}, {'_id': 0}).to_list(None)
    timeline = []
    for pi in po_items:
        po = await db.production_pos.find_one({'id': pi.get('po_id')}, {'_id': 0})
        if not po or customer_name.lower() not in (po.get('customer_name', '')).lower():
            continue
        timeline.append({'step': 'PO Created', 'date': serialize_doc(pi.get('created_at')),
                         'po_number': pi.get('po_number'), 'qty': pi.get('qty', 0),
                         'status': po.get('status', '')})
        # Buyer dispatches only
        buyer_items = await db.buyer_shipment_items.find({'po_item_id': pi['id']}, {'_id': 0}).sort('dispatch_seq', 1).to_list(None)
        for bi in buyer_items:
            timeline.append({'step': f"Dispatch #{bi.get('dispatch_seq', 1)}",
                             'date': serialize_doc(bi.get('dispatch_date')),
                             'qty_shipped': bi.get('qty_shipped', 0), 'ordered_qty': bi.get('ordered_qty', 0)})
    timeline.sort(key=lambda x: x.get('date', '') or '')
    return {'serial_number': serial, 'timeline': timeline}
