"""
PDF export helpers and /export-pdf endpoint for Garment ERP.
Refactored from server.py -- follows the same APIRouter pattern as buyer_portal.py.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from database import get_db
from auth import require_auth, serialize_doc
import uuid, io, logging
from io import BytesIO
from datetime import datetime, timezone

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

def new_id(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)

# ─── EXPORT PDF ──────────────────────────────────────────────────────────────
# PDF helper utilities
def _pdf_styles():
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallCell', fontSize=7, leading=9, wordWrap='LTR'))
    styles.add(ParagraphStyle(name='SmallCellBold', fontSize=7, leading=9, fontName='Helvetica-Bold', wordWrap='LTR'))
    return styles

def _pdf_table_style():
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ])

def _pdf_total_row_style():
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle
    return TableStyle([
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ])

def _build_pdf(buf, elements, page=None, orientation=None):
    """Build PDF with page orientation.

    page: legacy param — 'landscape' forces landscape (portrait by default).
    orientation: explicit override from preset — 'portrait' | 'landscape' | 'auto' | None.
                 'auto' or None falls back to `page` legacy default.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate
    # Resolve effective orientation: preset override wins
    effective = None
    if orientation in ('portrait', 'landscape'):
        effective = orientation
    else:
        # Legacy default
        effective = 'landscape' if page == 'landscape' else 'portrait'
    ps = landscape(A4) if effective == 'landscape' else A4
    doc = SimpleDocTemplate(buf, pagesize=ps, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    doc.build(elements)
    buf.seek(0)
    return buf

def _pdf_load_logo(logo_url, max_w_mm=30, max_h_mm=20):
    """
    Safely load a company logo into a ReportLab Image for PDF embedding.
    Supports:
      - data:image/... base64 data URIs
      - http(s):// absolute URLs (short timeout, fails gracefully)
      - /files/{storage_path} — Emergent object storage relative paths
      - /uploads/... or other absolute filesystem paths
    Returns a reportlab.platypus.Image or None on failure.
    """
    if not logo_url or not isinstance(logo_url, str):
        return None
    try:
        from reportlab.platypus import Image as RLImage
        from reportlab.lib.units import mm
        import io, base64, os
        img_bytes = None
        # Case 1: data URI
        if logo_url.startswith('data:image'):
            try:
                _, b64 = logo_url.split(',', 1)
                img_bytes = base64.b64decode(b64)
            except Exception:
                return None
        # Case 2: HTTP(S) absolute URL
        elif logo_url.startswith('http://') or logo_url.startswith('https://'):
            try:
                import requests as _rq
                r = _rq.get(logo_url, timeout=3)
                if r.ok and r.content:
                    img_bytes = r.content
            except Exception:
                return None
        # Case 3: Emergent object storage path (/files/...)
        elif logo_url.startswith('/files/'):
            try:
                from storage import get_object
                path = logo_url.replace('/files/', '', 1).split('?', 1)[0]
                content, _ = get_object(path)
                img_bytes = content
            except Exception:
                return None
        # Case 4: Local filesystem path (/uploads/..., /app/uploads/...)
        elif logo_url.startswith('/'):
            for candidate in [logo_url, f"/app{logo_url}", f"/app/backend{logo_url}"]:
                if os.path.exists(candidate):
                    try:
                        with open(candidate, 'rb') as f:
                            img_bytes = f.read()
                        break
                    except Exception:
                        continue
        if not img_bytes:
            return None
        # Use PIL to sniff dimensions and validate the image
        try:
            from PIL import Image as PILImage
            pil = PILImage.open(io.BytesIO(img_bytes))
            pil.verify()
        except Exception:
            return None
        # Return ReportLab Image sized proportionally within bounds
        bio = io.BytesIO(img_bytes)
        return RLImage(bio, width=max_w_mm*mm, height=max_h_mm*mm, kind='proportional')
    except Exception:
        return None


def _pdf_header(elements, settings, title, subtitle=None, info_pairs=None, override=None):
    """
    Render a branded PDF header.

    settings: dict from db.company_settings (may contain company_name, company_address,
              company_phone, company_email, company_website, company_logo_url,
              pdf_header_line1, pdf_header_line2).
    override: optional preset override dict with keys:
              use_company_settings (bool, default True),
              custom_title, custom_header_line1, custom_header_line2, custom_logo_url.
              When a field is non-empty, it overrides the settings value.
              When use_company_settings=False, fallbacks to settings are suppressed.
    """
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    styles = _pdf_styles()
    settings = settings or {}
    override = override or {}
    use_cs = override.get('use_company_settings', True) if override else True

    def _pick(field_key, override_key):
        ov = (override.get(override_key) or '').strip() if override else ''
        if ov:
            return ov
        if not use_cs:
            return ''
        return (settings.get(field_key) or '').strip()

    company_name = (settings.get('company_name') or 'Garment ERP').strip()
    header_line1 = _pick('pdf_header_line1', 'custom_header_line1')
    header_line2 = _pick('pdf_header_line2', 'custom_header_line2')
    logo_url = _pick('company_logo_url', 'custom_logo_url')
    effective_title = (override.get('custom_title') or '').strip() if override else ''
    effective_title = effective_title or title or ''

    # Company contact block (address/phone/email/website) — only when using company settings
    contact_bits = []
    if use_cs:
        if settings.get('company_address'): contact_bits.append(settings['company_address'])
        tp = []
        if settings.get('company_phone'): tp.append(f"Tel: {settings['company_phone']}")
        if settings.get('company_email'): tp.append(f"Email: {settings['company_email']}")
        if settings.get('company_website'): tp.append(settings['company_website'])
        if tp: contact_bits.append(' | '.join(tp))

    # Build left column (company text block) + right column (logo if any)
    left_parts = []
    left_parts.append(Paragraph(f"<b>{company_name}</b>", styles['Title']))
    if header_line1:
        left_parts.append(Paragraph(f"<font size='9'>{header_line1}</font>", styles['Normal']))
    if header_line2:
        left_parts.append(Paragraph(f"<font size='9'>{header_line2}</font>", styles['Normal']))
    for bit in contact_bits:
        left_parts.append(Paragraph(f"<font size='8' color='#64748b'>{bit}</font>", styles['Normal']))

    logo_img = _pdf_load_logo(logo_url) if logo_url else None
    if logo_img is not None:
        banner = Table([[left_parts, logo_img]], colWidths=[380, 120])
        banner.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(banner)
    else:
        for p in left_parts:
            elements.append(p)

    # Subtle rule under banner
    elements.append(Spacer(1, 2*mm))
    rule = Table([['']], colWidths=[500], rowHeights=[0.6])
    rule.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), 0.6, colors.HexColor('#cbd5e1'))]))
    elements.append(rule)
    elements.append(Spacer(1, 3*mm))

    # Title + subtitle
    if effective_title:
        elements.append(Paragraph(f"<b>{effective_title}</b>", styles['Heading2']))
    if subtitle:
        elements.append(Paragraph(subtitle, styles['Normal']))
    elements.append(Spacer(1, 3*mm))

    # Info pairs table
    if info_pairs:
        info_data = []
        row = []
        for i, (k, v) in enumerate(info_pairs):
            row.extend([f"{k}:", str(v or '-')])
            if len(row) >= 4 or i == len(info_pairs) - 1:
                while len(row) < 4: row.append('')
                info_data.append(row)
                row = []
        if info_data:
            it = Table(info_data, colWidths=[85, 180, 85, 180])
            it.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold')]))
            elements.append(it)
            elements.append(Spacer(1, 5*mm))
    return elements


def _pdf_footer(elements, settings=None, override=None):
    """
    Render a branded PDF footer:
      - pdf_footer_text from settings (or override.custom_footer_text)
      - a generated timestamp line (always)
    """
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    styles = _pdf_styles()
    settings = settings or {}
    override = override or {}
    use_cs = override.get('use_company_settings', True) if override else True

    override_footer = (override.get('custom_footer_text') or '').strip() if override else ''
    if override_footer:
        footer_text = override_footer
    elif use_cs:
        footer_text = (settings.get('pdf_footer_text') or '').strip()
    else:
        footer_text = ''

    elements.append(Spacer(1, 6*mm))
    # Thin rule above footer
    rule = Table([['']], colWidths=[500], rowHeights=[0.6])
    rule.setStyle(TableStyle([('LINEABOVE', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1'))]))
    elements.append(rule)
    elements.append(Spacer(1, 2*mm))
    if footer_text:
        elements.append(Paragraph(f"<font size='9' color='#475569'>{footer_text}</font>", styles['Normal']))
    elements.append(Paragraph(
        f"<font size='8' color='#94a3b8'><i>Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}</i></font>",
        styles['Normal']))
    return elements

def _safe_str(v, max_len=40):
    s = str(v or '')
    return s[:max_len] if len(s) > max_len else s

async def enrich_with_product_photos(items, db):
    """Add product photo_url to items that have a product_name."""
    if not items: return items
    product_cache = {}
    for item in items:
        pname = item.get('product_name', '')
        if pname and pname not in product_cache:
            prod = await db.products.find_one({'product_name': pname}, {'_id': 0, 'photo_url': 1})
            product_cache[pname] = (prod or {}).get('photo_url', '')
        if pname:
            item['product_photo'] = product_cache.get(pname, '')
    return items

def _fmt_date(v):
    if not v: return '-'
    s = str(v)[:10]
    return s if s != 'None' else '-'

def _fmt_num(v):
    try:
        return f"{int(v):,}".replace(',', '.')
    except (ValueError, TypeError):
        return str(v or 0)

def _fmt_money(v):
    try:
        return f"Rp {int(v):,}".replace(',', '.')
    except (ValueError, TypeError):
        return 'Rp 0'

# ─── PDF Export Config helpers ─────────────────────────────────────────────
async def _get_pdf_config(db, pdf_type, config_id=None):
    """Get PDF export config (custom columns) if exists."""
    if config_id:
        cfg = await db.pdf_export_configs.find_one({'id': config_id})
        if cfg:
            return cfg
    # Try default for this type
    cfg = await db.pdf_export_configs.find_one({'pdf_type': pdf_type, 'is_default': True})
    return cfg

def _filter_columns(headers, all_col_keys, selected_keys, data_rows):
    """Filter table columns based on selected keys from config.

    Respects the order in `selected_keys` so presets can also define column order
    (used by the drag-and-drop preset editor).
    """
    if not selected_keys:
        return headers, data_rows
    key_to_idx = {k: i for i, k in enumerate(all_col_keys)}
    indices = [key_to_idx[k] for k in selected_keys if k in key_to_idx]
    if not indices:
        return headers, data_rows
    new_headers = [headers[i] for i in indices]
    new_rows = [[row[i] if i < len(row) else '' for i in indices] for row in data_rows]
    return new_headers, new_rows

@router.get("/export-pdf")
async def export_pdf(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    pdf_type = sp.get('type', '')
    config_id = sp.get('config_id')
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        buf = BytesIO()
        styles = _pdf_styles()
        settings = await db.company_settings.find_one({'type': 'general'}) or {}

        # Get optional custom column config
        config = await _get_pdf_config(db, pdf_type, config_id)

        # ──── PRODUCTION PO (SPP - Surat Perintah Produksi) ────
        if pdf_type == 'production-po':
            po_id = sp.get('id')
            if not po_id: raise HTTPException(400, 'id required')
            po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
            if not po: raise HTTPException(404, 'PO not found')
            items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(None)
            if not items: raise HTTPException(404, 'No items in this PO')
            accessories = await db.po_accessories.find({'po_id': po_id}, {'_id': 0}).to_list(None)
            elements = []
            _pdf_header(elements, settings, 'Surat Perintah Produksi (SPP)', info_pairs=[
                ('No PO', po.get('po_number', '')), ('Customer', po.get('customer_name', '')),
                ('Vendor', po.get('vendor_name', '')), ('Status', po.get('status', '')),
                ('Tanggal PO', _fmt_date(po.get('po_date'))), ('Deadline', _fmt_date(po.get('deadline'))),
                ('Delivery Deadline', _fmt_date(po.get('delivery_deadline'))),
            ], override=config)
            # Items table — includes optional DB-backed columns (po-level repeated per row)
            all_col_keys = ['no', 'serial', 'product', 'sku', 'size', 'color', 'qty', 'price', 'cmt', 'po_number', 'po_date', 'deadline', 'delivery_deadline', 'po_status', 'barcode', 'notes']
            headers = ['No', 'Serial No', 'Product', 'SKU', 'Size', 'Color', 'Qty', 'Price', 'CMT', 'PO No', 'Tgl PO', 'Deadline', 'Delivery', 'Status', 'Barcode', 'Notes']
            data_rows = []
            for idx, item in enumerate(items, 1):
                data_rows.append([
                    idx, _safe_str(item.get('serial_number')), _safe_str(item.get('product_name')),
                    _safe_str(item.get('sku')), _safe_str(item.get('size')), _safe_str(item.get('color')),
                    item.get('qty', 0), _fmt_money(item.get('selling_price_snapshot', 0)),
                    _fmt_money(item.get('cmt_price_snapshot', 0)),
                    po.get('po_number', ''), _fmt_date(po.get('po_date')),
                    _fmt_date(po.get('deadline')), _fmt_date(po.get('delivery_deadline')),
                    po.get('status', ''), _safe_str(item.get('barcode', '')), _safe_str(item.get('notes', ''))
                ])
            if config and config.get('columns'):
                headers, data_rows = _filter_columns(headers, all_col_keys, config['columns'], data_rows)
            td = [headers] + data_rows
            total_qty = sum(i.get('qty', 0) for i in items)
            # Dynamic total row based on visible columns
            sel_cols = (config.get('columns') if config and config.get('columns') else all_col_keys)
            total_row = []
            for k in sel_cols:
                if k == 'qty': total_row.append(total_qty)
                elif k in ('product', 'color'): total_row.append('TOTAL' if 'TOTAL' not in total_row else '')
                else: total_row.append('')
            if 'TOTAL' not in total_row and len(total_row) > 1:
                total_row[max(0, len(total_row) - 2)] = 'TOTAL'
            td.append(total_row)
            cw = [max(22, int(720 / max(1, len(headers))))] * len(headers)
            t = Table(td, colWidths=cw, repeatRows=1)
            t.setStyle(_pdf_table_style())
            t.setStyle(_pdf_total_row_style())
            elements.append(t)
            # Accessories section
            if accessories:
                elements.append(Spacer(1, 6*mm))
                elements.append(Paragraph("<b>Accessories Required:</b>", styles['Heading3']))
                acc_td = [['No', 'Accessory', 'Code', 'Qty Needed', 'Unit', 'Notes']]
                for idx, acc in enumerate(accessories, 1):
                    acc_td.append([idx, acc.get('accessory_name', ''), acc.get('accessory_code', ''),
                                   acc.get('qty_needed', 0), acc.get('unit', 'pcs'), _safe_str(acc.get('notes', ''))])
                at = Table(acc_td, colWidths=[25, 120, 80, 70, 50, 120])
                at.setStyle(_pdf_table_style())
                elements.append(at)
            if po.get('notes'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(f"<b>Notes:</b> {po.get('notes', '')}", styles['Normal']))
            _pdf_footer(elements, settings, override=config)
            _build_pdf(buf, elements, page='landscape', orientation=(config or {}).get('page_orientation'))
            fname = f"SPP-{po.get('po_number', 'unknown')}.pdf"
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename={fname}"})

        # ──── VENDOR SHIPMENT (Surat Jalan Material) ────
        elif pdf_type == 'vendor-shipment':
            sid = sp.get('id')
            if not sid: raise HTTPException(400, 'id required')
            ship = await db.vendor_shipments.find_one({'id': sid}, {'_id': 0})
            if not ship: raise HTTPException(404, 'Shipment not found')
            items = await db.vendor_shipment_items.find({'shipment_id': sid}, {'_id': 0}).to_list(None)
            elements = []
            _pdf_header(elements, settings, 'Surat Jalan Material (Vendor Shipment)', info_pairs=[
                ('Shipment No', ship.get('shipment_number', '')), ('Vendor', ship.get('vendor_name', '')),
                ('Type', ship.get('shipment_type', 'NORMAL')), ('Status', ship.get('status', '')),
                ('Date', _fmt_date(ship.get('shipment_date'))),
                ('Inspection', ship.get('inspection_status', 'Pending')),
            ], override=config)
            all_col_keys = ['no', 'po', 'serial', 'product', 'sku', 'size', 'color', 'qty_sent', 'ordered_qty', 'shipment_number', 'shipment_date', 'shipment_type', 'inspection_status']
            headers = ['No', 'PO', 'Serial', 'Product', 'SKU', 'Size', 'Color', 'Qty Sent', 'Qty Ordered', 'No SJ', 'Tgl SJ', 'Tipe SJ', 'Inspeksi']
            data_rows = []
            for idx, i in enumerate(items, 1):
                data_rows.append([idx, _safe_str(i.get('po_number')), _safe_str(i.get('serial_number')),
                    _safe_str(i.get('product_name')), _safe_str(i.get('sku')),
                    _safe_str(i.get('size')), _safe_str(i.get('color')), i.get('qty_sent', 0),
                    i.get('ordered_qty', 0), ship.get('shipment_number', ''),
                    _fmt_date(ship.get('shipment_date')), ship.get('shipment_type', 'NORMAL'),
                    ship.get('inspection_status', 'Pending')])
            if config and config.get('columns'):
                headers, data_rows = _filter_columns(headers, all_col_keys, config['columns'], data_rows)
            td = [headers] + data_rows
            # Dynamic total row
            sel_cols = (config.get('columns') if config and config.get('columns') else all_col_keys)
            total_row = []
            for k in sel_cols:
                if k == 'qty_sent': total_row.append(sum(i.get('qty_sent', 0) for i in items))
                elif k == 'ordered_qty': total_row.append(sum(i.get('ordered_qty', 0) for i in items))
                elif k == 'color': total_row.append('TOTAL' if 'TOTAL' not in total_row else '')
                else: total_row.append('')
            if 'TOTAL' not in total_row and len(total_row) > 1:
                total_row[max(0, len(total_row) - 2)] = 'TOTAL'
            td.append(total_row)
            cw = [max(25, int(545 / len(headers)))] * len(headers)
            t = Table(td, colWidths=cw, repeatRows=1)
            t.setStyle(_pdf_table_style())
            t.setStyle(_pdf_total_row_style())
            elements.append(t)
            # Signature area
            elements.append(Spacer(1, 15*mm))
            sig_data = [['Pengirim (Vendor)', '', 'Penerima'], ['', '', ''], ['_________________', '', '_________________']]
            st = Table(sig_data, colWidths=[180, 100, 180])
            st.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, -1), 9)]))
            elements.append(st)
            _pdf_footer(elements, settings, override=config)
            _build_pdf(buf, elements, orientation=(config or {}).get('page_orientation'))
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename=SJ-Material-{ship.get('shipment_number','')}.pdf"})

        # ──── VENDOR INSPECTION PDF ────
        elif pdf_type == 'vendor-inspection':
            insp_id = sp.get('id')
            if not insp_id: raise HTTPException(400, 'id required')
            insp = await db.vendor_material_inspections.find_one({'id': insp_id}, {'_id': 0})
            if not insp: raise HTTPException(404, 'Inspection not found')
            shipment = await db.vendor_shipments.find_one({'id': insp.get('shipment_id')}, {'_id': 0})
            # Get PO info
            po_id = (shipment or {}).get('po_id', '')
            if not po_id:
                first_si = await db.vendor_shipment_items.find_one({'shipment_id': insp.get('shipment_id')})
                if first_si: po_id = first_si.get('po_id', '')
            po = await db.production_pos.find_one({'id': po_id}, {'_id': 0}) if po_id else None
            # Get invoice if linked
            invoice = await db.invoices.find_one({'po_id': po_id, 'invoice_category': 'AP'}, {'_id': 0}) if po_id else None
            # Get all inspection items
            all_insp_items = await db.vendor_material_inspection_items.find({'inspection_id': insp_id}, {'_id': 0}).to_list(None)
            material_items = [i for i in all_insp_items if i.get('item_type') != 'accessory']
            accessory_items = [i for i in all_insp_items if i.get('item_type') == 'accessory']
            elements = []
            info_pairs = [
                ('No PO', (po or {}).get('po_number', '-')),
                ('No Invoice', (invoice or {}).get('invoice_number', '-')),
                ('Vendor', insp.get('vendor_name', '')),
                ('Tanggal Inspeksi', _fmt_date(insp.get('inspection_date'))),
                ('No Shipment', insp.get('shipment_number', '')),
                ('Status', insp.get('status', '')),
            ]
            _pdf_header(elements, settings, 'Laporan Inspeksi Material (Vendor)', info_pairs=info_pairs, override=config)
            # Material items table
            if material_items:
                elements.append(Paragraph("<b>Material Items:</b>", styles['Heading3']))
                all_col_keys = ['no', 'product', 'sku', 'size', 'color', 'ordered_qty', 'received_qty', 'missing_qty', 'condition_notes', 'category']
                headers = ['No', 'Produk', 'SKU', 'Size', 'Warna', 'Qty Dikirim', 'Qty Diterima', 'Qty Missing', 'Catatan', 'Kategori']
                data_rows = []
                for idx, item in enumerate(material_items, 1):
                    # Get product info for category
                    prod = await db.products.find_one({'product_name': item.get('product_name')}, {'_id': 0})
                    category = (prod or {}).get('category', '-')
                    data_rows.append([
                        idx, _safe_str(item.get('product_name', '')),
                        item.get('sku', ''), item.get('size', ''), item.get('color', ''),
                        item.get('ordered_qty', 0), item.get('received_qty', 0),
                        item.get('missing_qty', 0), _safe_str(item.get('condition_notes', '')),
                        category
                    ])
                if config and config.get('columns'):
                    headers, data_rows = _filter_columns(headers, all_col_keys, config['columns'], data_rows)
                td = [headers] + data_rows
                # Build total row dynamically based on visible columns
                sel = config.get('columns') if config and config.get('columns') else all_col_keys
                total_row = []
                for k in sel:
                    if k == 'ordered_qty': total_row.append(sum(i.get('ordered_qty', 0) for i in material_items))
                    elif k == 'received_qty': total_row.append(sum(i.get('received_qty', 0) for i in material_items))
                    elif k == 'missing_qty': total_row.append(sum(i.get('missing_qty', 0) for i in material_items))
                    elif k == 'product': total_row.append('TOTAL')
                    else: total_row.append('')
                td.append(total_row)
                cw = [max(25, int(600 / len(headers)))] * len(headers)
                t = Table(td, colWidths=cw, repeatRows=1)
                t.setStyle(_pdf_table_style())
                t.setStyle(_pdf_total_row_style())
                elements.append(t)
            # Accessory items table
            if accessory_items:
                elements.append(Spacer(1, 6*mm))
                elements.append(Paragraph("<b>Aksesoris Items:</b>", styles['Heading3']))
                acc_headers = ['No', 'Aksesoris', 'Kode', 'Satuan', 'Qty Dikirim', 'Qty Diterima', 'Qty Missing', 'Catatan']
                acc_rows = []
                for idx, acc in enumerate(accessory_items, 1):
                    acc_rows.append([
                        idx, acc.get('accessory_name', ''), acc.get('accessory_code', ''),
                        acc.get('unit', 'pcs'), acc.get('ordered_qty', 0),
                        acc.get('received_qty', 0), acc.get('missing_qty', 0),
                        _safe_str(acc.get('condition_notes', ''))
                    ])
                acc_td = [acc_headers] + acc_rows
                acc_total = ['', '', '', 'TOTAL',
                    sum(a.get('ordered_qty', 0) for a in accessory_items),
                    sum(a.get('received_qty', 0) for a in accessory_items),
                    sum(a.get('missing_qty', 0) for a in accessory_items), '']
                acc_td.append(acc_total)
                acc_cw = [25, 100, 70, 45, 60, 60, 60, 90]
                at = Table(acc_td, colWidths=acc_cw, repeatRows=1)
                at.setStyle(_pdf_table_style())
                at.setStyle(_pdf_total_row_style())
                elements.append(at)
            if insp.get('overall_notes'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(f"<b>Catatan Umum:</b> {insp.get('overall_notes', '')}", styles['Normal']))
            # Signature
            elements.append(Spacer(1, 12*mm))
            sig_data = [['Inspektor', '', 'Pengirim (Vendor)'], ['', '', ''], ['_________________', '', '_________________']]
            st = Table(sig_data, colWidths=[180, 100, 180])
            st.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, -1), 9)]))
            elements.append(st)
            _pdf_footer(elements, settings, override=config)
            _build_pdf(buf, elements, page='landscape', orientation=(config or {}).get('page_orientation'))
            fname = f"Inspeksi-{insp.get('shipment_number', 'unknown')}.pdf"
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename={fname}"})

        # ──── BUYER SHIPMENT DISPATCH ────
        elif pdf_type == 'buyer-shipment-dispatch':
            shipment_id = sp.get('shipment_id')
            dispatch_seq = int(sp.get('dispatch_seq', 0))
            if not shipment_id or not dispatch_seq:
                raise HTTPException(400, 'shipment_id and dispatch_seq required')
            bs = await db.buyer_shipments.find_one({'id': shipment_id}, {'_id': 0})
            if not bs: raise HTTPException(404, 'Buyer shipment not found')
            items = await db.buyer_shipment_items.find({
                'shipment_id': shipment_id, 'dispatch_seq': dispatch_seq
            }, {'_id': 0}).to_list(None)
            if not items: raise HTTPException(404, f'No items for dispatch #{dispatch_seq}')
            all_items = await db.buyer_shipment_items.find({'shipment_id': shipment_id}).to_list(None)
            cumulative_by_poi = {}
            for ai in all_items:
                key = ai.get('po_item_id') or ai['id']
                if key not in cumulative_by_poi:
                    cumulative_by_poi[key] = {'ordered': ai.get('ordered_qty', 0), 'shipped': 0}
                if ai.get('dispatch_seq', 1) <= dispatch_seq:
                    cumulative_by_poi[key]['shipped'] += ai.get('qty_shipped', 0)
            elements = []
            _pdf_header(elements, settings, f'Surat Jalan Buyer — Dispatch #{dispatch_seq}', info_pairs=[
                ('Shipment No', bs.get('shipment_number', '')), ('PO Number', bs.get('po_number', '')),
                ('Customer', bs.get('customer_name', '')), ('Vendor', bs.get('vendor_name', '')),
                ('Dispatch Date', _fmt_date(items[0].get('dispatch_date', ''))), ('Dispatch #', str(dispatch_seq)),
            ], override=config)
            all_col_keys = ['no', 'serial', 'product', 'sku', 'size', 'color', 'ordered', 'this_dispatch', 'cumul_shipped', 'remaining', 'po_number', 'vendor_name', 'customer', 'shipment_number', 'dispatch_date', 'dispatch_seq']
            headers = ['No', 'Serial', 'Product', 'SKU', 'Size', 'Color', 'Ordered', 'This Dispatch', 'Cumul. Shipped', 'Remaining', 'No PO', 'Vendor', 'Customer', 'No SJ', 'Tgl Dispatch', 'Dispatch #']
            data_rows = []
            for idx, item in enumerate(items, 1):
                key = item.get('po_item_id') or item['id']
                cum = cumulative_by_poi.get(key, {'ordered': 0, 'shipped': 0})
                data_rows.append([
                    idx, _safe_str(item.get('serial_number')), _safe_str(item.get('product_name')),
                    _safe_str(item.get('sku')), _safe_str(item.get('size')), _safe_str(item.get('color')),
                    item.get('ordered_qty', 0), item.get('qty_shipped', 0), cum['shipped'],
                    max(0, cum['ordered'] - cum['shipped']),
                    bs.get('po_number', ''), bs.get('vendor_name', ''),
                    bs.get('customer_name', ''), bs.get('shipment_number', ''),
                    _fmt_date(item.get('dispatch_date', '')), str(dispatch_seq)
                ])
            if config and config.get('columns'):
                headers, data_rows = _filter_columns(headers, all_col_keys, config['columns'], data_rows)
            td = [headers] + data_rows
            total_this = sum(i.get('qty_shipped', 0) for i in items)
            total_cum = sum(v['shipped'] for v in cumulative_by_poi.values())
            total_ord = sum(v['ordered'] for v in cumulative_by_poi.values())
            # Dynamic total row
            sel_cols = (config.get('columns') if config and config.get('columns') else all_col_keys)
            total_row = []
            for k in sel_cols:
                if k == 'ordered': total_row.append(total_ord)
                elif k == 'this_dispatch': total_row.append(total_this)
                elif k == 'cumul_shipped': total_row.append(total_cum)
                elif k == 'remaining': total_row.append(max(0, total_ord - total_cum))
                elif k == 'color': total_row.append('TOTAL' if 'TOTAL' not in total_row else '')
                else: total_row.append('')
            if 'TOTAL' not in total_row and len(total_row) > 1:
                total_row[max(0, len(total_row) - 5)] = 'TOTAL'
            td.append(total_row)
            cw = [max(25, int(680 / len(headers)))] * len(headers)
            t = Table(td, colWidths=cw, repeatRows=1)
            t.setStyle(_pdf_table_style())
            t.setStyle(_pdf_total_row_style())
            t.setStyle(TableStyle([('ALIGN', (6, 0), (-1, -1), 'RIGHT')]))
            elements.append(t)
            _pdf_footer(elements, settings, override=config)
            _build_pdf(buf, elements, page='landscape', orientation=(config or {}).get('page_orientation'))
            fname = f"buyer_dispatch_{bs.get('shipment_number','')}_D{dispatch_seq}.pdf"
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename={fname}"})

        # ──── BUYER SHIPMENT (Summary - all dispatches) ────
        elif pdf_type == 'buyer-shipment':
            sid = sp.get('id')
            if not sid: raise HTTPException(400, 'id required')
            bs = await db.buyer_shipments.find_one({'id': sid}, {'_id': 0})
            if not bs: raise HTTPException(404, 'Buyer shipment not found')
            all_items = await db.buyer_shipment_items.find({'shipment_id': sid}, {'_id': 0}).to_list(None)
            elements = []
            _pdf_header(elements, settings, 'Surat Jalan Buyer — Summary', info_pairs=[
                ('Shipment No', bs.get('shipment_number', '')), ('PO Number', bs.get('po_number', '')),
                ('Customer', bs.get('customer_name', '')), ('Vendor', bs.get('vendor_name', '')),
                ('Status', bs.get('status', bs.get('ship_status', ''))),
            ], override=config)
            # Group by dispatch
            dispatches = {}
            for item in all_items:
                ds = item.get('dispatch_seq', 1)
                if ds not in dispatches:
                    dispatches[ds] = []
                dispatches[ds].append(item)
            if not dispatches:
                elements.append(Paragraph("No dispatch items found for this shipment.", styles['Normal']))
            for ds in sorted(dispatches.keys()):
                d_items = dispatches[ds]
                elements.append(Paragraph(f"<b>Dispatch #{ds}</b> — {_fmt_date(d_items[0].get('dispatch_date', ''))}", styles['Heading3']))
                elements.append(Spacer(1, 2*mm))
                all_col_keys = ['no', 'serial', 'product', 'sku', 'size', 'color', 'ordered', 'shipped', 'dispatch_date']
                headers = ['No', 'Serial', 'Product', 'SKU', 'Size', 'Color', 'Ordered', 'Shipped', 'Tgl Dispatch']
                data_rows = []
                for idx, item in enumerate(d_items, 1):
                    data_rows.append([idx, _safe_str(item.get('serial_number')), _safe_str(item.get('product_name')),
                               _safe_str(item.get('sku')), _safe_str(item.get('size')), _safe_str(item.get('color')),
                               item.get('ordered_qty', 0), item.get('qty_shipped', 0), _fmt_date(item.get('dispatch_date', ''))])
                if config and config.get('columns'):
                    headers, data_rows = _filter_columns(headers, all_col_keys, config['columns'], data_rows)
                td = [headers] + data_rows
                # Dynamic total row
                sel = config.get('columns') if config and config.get('columns') else all_col_keys
                total_row = []
                for k in sel:
                    if k == 'ordered': total_row.append(sum(i.get('ordered_qty', 0) for i in d_items))
                    elif k == 'shipped': total_row.append(sum(i.get('qty_shipped', 0) for i in d_items))
                    elif k == 'color' or k == 'size': total_row.append('TOTAL' if total_row and total_row[-1] != 'TOTAL' else '')
                    else: total_row.append('')
                # Ensure a TOTAL label somewhere
                if 'TOTAL' not in total_row and len(total_row) > 1:
                    total_row[max(0, len(total_row) - 3)] = 'TOTAL'
                td.append(total_row)
                cw = [max(25, int(680 / len(headers)))] * len(headers)
                t = Table(td, colWidths=cw, repeatRows=1)
                t.setStyle(_pdf_table_style())
                t.setStyle(_pdf_total_row_style())
                elements.append(t)
                elements.append(Spacer(1, 5*mm))
            _pdf_footer(elements, settings, override=config)
            _build_pdf(buf, elements, page='landscape', orientation=(config or {}).get('page_orientation'))
            fname = f"Buyer-Shipment-{bs.get('shipment_number', sid)}.pdf"
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename={fname}"})

        # ──── PRODUCTION RETURN ────
        elif pdf_type == 'production-return':
            rid = sp.get('id')
            if not rid: raise HTTPException(400, 'id required')
            ret = await db.production_returns.find_one({'id': rid}, {'_id': 0})
            if not ret: raise HTTPException(404, 'Production return not found')
            items = await db.production_return_items.find({'return_id': rid}, {'_id': 0}).to_list(None)
            elements = []
            _pdf_header(elements, settings, 'Surat Retur Produksi', info_pairs=[
                ('Return No', ret.get('return_number', '')), ('PO Number', ret.get('reference_po_number', '')),
                ('Customer', ret.get('customer_name', '')), ('Status', ret.get('status', '')),
                ('Return Date', _fmt_date(ret.get('return_date'))), ('Reason', _safe_str(ret.get('return_reason', ''), 60)),
            ], override=config)
            if items:
                all_col_keys = ['no', 'serial', 'product', 'sku', 'size', 'color', 'return_qty', 'notes', 'return_number', 'return_date', 'return_reason', 'status']
                headers = ['No', 'Serial', 'Product', 'SKU', 'Size', 'Color', 'Qty Returned', 'Notes', 'No Retur', 'Tgl Retur', 'Alasan', 'Status']
                data_rows = []
                for idx, i in enumerate(items, 1):
                    data_rows.append([idx, _safe_str(i.get('serial_number')), _safe_str(i.get('product_name')),
                               _safe_str(i.get('sku')), _safe_str(i.get('size')), _safe_str(i.get('color')),
                               i.get('return_qty', 0), _safe_str(i.get('notes', ''), 30),
                               ret.get('return_number', ''), _fmt_date(ret.get('return_date')),
                               _safe_str(ret.get('return_reason', ''), 30), ret.get('status', '')])
                if config and config.get('columns'):
                    headers, data_rows = _filter_columns(headers, all_col_keys, config['columns'], data_rows)
                td = [headers] + data_rows
                sel = config.get('columns') if config and config.get('columns') else all_col_keys
                total_row = []
                for k in sel:
                    if k == 'return_qty': total_row.append(sum(i.get('return_qty', 0) for i in items))
                    elif k == 'color': total_row.append('TOTAL')
                    else: total_row.append('')
                if 'TOTAL' not in total_row and len(total_row) > 1:
                    total_row[max(0, len(total_row) - 2)] = 'TOTAL'
                td.append(total_row)
                cw = [max(25, int(560 / len(headers)))] * len(headers)
                t = Table(td, colWidths=cw, repeatRows=1)
                t.setStyle(_pdf_table_style())
                t.setStyle(_pdf_total_row_style())
                elements.append(t)
            else:
                elements.append(Paragraph("No return items found.", styles['Normal']))
            if ret.get('notes'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(f"<b>Notes:</b> {ret.get('notes', '')}", styles['Normal']))
            _pdf_footer(elements, settings, override=config)
            _build_pdf(buf, elements, orientation=(config or {}).get('page_orientation'))
            fname = f"Retur-{ret.get('return_number', rid)}.pdf"
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename={fname}"})

        # ──── MATERIAL REQUEST ────
        elif pdf_type == 'material-request':
            req_id = sp.get('id')
            if not req_id: raise HTTPException(400, 'id required')
            req = await db.material_requests.find_one({'id': req_id}, {'_id': 0})
            if not req: raise HTTPException(404, 'Material request not found')
            elements = []
            req_type = req.get('request_type', 'ADDITIONAL')
            _pdf_header(elements, settings, f'Surat Permohonan Material ({req_type})', info_pairs=[
                ('Request No', req.get('request_number', '')), ('PO Number', req.get('po_number', '')),
                ('Vendor', req.get('vendor_name', '')), ('Status', req.get('status', '')),
                ('Total Qty', req.get('total_requested_qty', 0)),
                ('Child Shipment', req.get('child_shipment_number', '-')),
            ], override=config)
            # Request items if available
            req_items = req.get('items', [])
            if req_items:
                all_col_keys = ['no', 'serial', 'product', 'sku', 'size', 'color', 'qty_requested', 'request_number', 'po_number', 'request_type', 'status', 'reason']
                headers = ['No', 'Serial', 'Product', 'SKU', 'Size', 'Color', 'Qty Requested', 'No Request', 'No PO', 'Tipe', 'Status', 'Alasan']
                data_rows = []
                for idx, i in enumerate(req_items, 1):
                    data_rows.append([idx, _safe_str(i.get('serial_number')), _safe_str(i.get('product_name')),
                               _safe_str(i.get('sku')), _safe_str(i.get('size')), _safe_str(i.get('color')),
                               i.get('qty_requested', i.get('requested_qty', 0)),
                               req.get('request_number', ''), req.get('po_number', ''),
                               req.get('request_type', ''), req.get('status', ''),
                               _safe_str(req.get('reason', ''), 30)])
                if config and config.get('columns'):
                    headers, data_rows = _filter_columns(headers, all_col_keys, config['columns'], data_rows)
                td = [headers] + data_rows
                cw = [max(25, int(560 / len(headers)))] * len(headers)
                t = Table(td, colWidths=cw, repeatRows=1)
                t.setStyle(_pdf_table_style())
                elements.append(t)
            else:
                elements.append(Paragraph(f"Total Requested Quantity: <b>{req.get('total_requested_qty', 0)}</b>", styles['Normal']))
            if req.get('reason'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(f"<b>Reason:</b> {req.get('reason', '')}", styles['Normal']))
            # Approval signatures
            elements.append(Spacer(1, 15*mm))
            sig_data = [['Diajukan oleh:', '', 'Disetujui oleh:'], ['', '', ''], ['_________________', '', '_________________']]
            st = Table(sig_data, colWidths=[180, 100, 180])
            st.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, -1), 9)]))
            elements.append(st)
            _pdf_footer(elements, settings, override=config)
            _build_pdf(buf, elements, orientation=(config or {}).get('page_orientation'))
            fname = f"Permohonan-{req.get('request_number', req_id)}.pdf"
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename={fname}"})

        # ──── PRODUCTION REPORT (full) ────
        elif pdf_type == 'production-report':
            elements = []
            _pdf_header(elements, settings, 'Laporan Produksi Lengkap', override=config)
            pos = await db.production_pos.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
            all_col_keys = ['no', 'date', 'po', 'serial', 'product', 'sku', 'size', 'color', 'qty', 'price', 'cmt', 'vendor', 'produced', 'shipped']
            headers = ['No', 'Date', 'PO', 'Serial', 'Product', 'SKU', 'Size', 'Color', 'Qty', 'Price', 'CMT', 'Vendor', 'Produced', 'Shipped']
            # ── 10E: batch all po_items, ji, bi in 3 queries instead of 3N ──
            pdf_po_ids = [po['id'] for po in pos]
            _pdf_items_all = await db.po_items.find({'po_id': {'$in': pdf_po_ids}}).to_list(None) if pdf_po_ids else []
            _pdf_item_ids  = [it['id'] for it in _pdf_items_all]
            _pdf_ji_all    = await db.production_job_items.find({'po_item_id': {'$in': _pdf_item_ids}}).to_list(None) if _pdf_item_ids else []
            _pdf_bi_all    = await db.buyer_shipment_items.find({'po_item_id': {'$in': _pdf_item_ids}}).to_list(None) if _pdf_item_ids else []
            _pdf_items_by_po: dict = {}
            for it in _pdf_items_all: _pdf_items_by_po.setdefault(it.get('po_id'), []).append(it)
            _pdf_ji_prod: dict = {}
            for ji in _pdf_ji_all: _pdf_ji_prod[ji.get('po_item_id')] = _pdf_ji_prod.get(ji.get('po_item_id'), 0) + ji.get('produced_qty', 0)
            _pdf_bi_ship: dict = {}
            for bi in _pdf_bi_all: _pdf_bi_ship[bi.get('po_item_id')] = _pdf_bi_ship.get(bi.get('po_item_id'), 0) + bi.get('qty_shipped', 0)
            data_rows = []
            rn = 1
            for po in pos:
                for item in _pdf_items_by_po.get(po['id'], []):
                    data_rows.append([rn, _fmt_date(po.get('po_date')), _safe_str(po.get('po_number'), 15),
                        _safe_str(item.get('serial_number'), 15), _safe_str(item.get('product_name'), 20),
                        _safe_str(item.get('sku'), 15), _safe_str(item.get('size'), 8), _safe_str(item.get('color'), 10),
                        item.get('qty', 0), _fmt_money(item.get('selling_price_snapshot', 0)),
                        _fmt_money(item.get('cmt_price_snapshot', 0)),
                        _safe_str(po.get('vendor_name'), 15),
                        _pdf_ji_prod.get(item['id'], 0),
                        _pdf_bi_ship.get(item['id'], 0)])
                    rn += 1
            if config and config.get('columns'):
                headers, data_rows = _filter_columns(headers, all_col_keys, config['columns'], data_rows)
            if not data_rows:
                elements.append(Paragraph("No production data found.", styles['Normal']))
            else:
                td = [headers] + data_rows
                cw = [max(22, int(680 / len(headers)))] * len(headers)
                t = Table(td, colWidths=cw, repeatRows=1)
                t.setStyle(_pdf_table_style())
                t.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7)]))
                elements.append(t)
            _pdf_footer(elements, settings, override=config)
            _build_pdf(buf, elements, page='landscape', orientation=(config or {}).get('page_orientation'))
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename=production_report_{datetime.now().strftime('%Y%m%d')}.pdf"})

        # ──── REPORT-* (Reuse /api/reports/{type} query logic) ────
        elif pdf_type.startswith('report-'):
            report_type = pdf_type[7:]  # strip 'report-' prefix
            valid_report_types = ['production', 'progress', 'financial', 'shipment', 'defect', 'return', 'missing-material', 'replacement', 'accessory']
            if report_type not in valid_report_types:
                return JSONResponse({'error': f'Unknown report type: {report_type}', 'available': valid_report_types}, status_code=400)

            # ── Get report data by reusing the same query logic as /api/reports/{type} ──
            report_data = []

            if report_type == 'production':
                po_query = {}
                if sp.get('status'): po_query['status'] = sp['status']
                pos = await db.production_pos.find(po_query, {'_id': 0}).sort('created_at', -1).to_list(None)
                for po in pos:
                    if sp.get('vendor_id') and po.get('vendor_id') != sp['vendor_id']: continue
                    items = await db.po_items.find({'po_id': po['id']}).to_list(None)
                    for item in items:
                        if sp.get('serial_number') and item.get('serial_number') != sp['serial_number']: continue
                        report_data.append({
                            'tanggal': _fmt_date(po.get('po_date', po.get('created_at'))),
                            'no_po': po.get('po_number', ''), 'no_seri': item.get('serial_number', ''),
                            'nama_produk': item.get('product_name', ''), 'sku': item.get('sku', ''),
                            'size': item.get('size', ''), 'warna': item.get('color', ''),
                            'output_qty': item.get('qty', 0),
                            'harga': item.get('selling_price_snapshot', 0), 'hpp': item.get('cmt_price_snapshot', 0),
                            'garment': po.get('vendor_name', ''), 'po_status': po.get('status', ''),
                        })
                headers = ['No', 'Tanggal', 'No PO', 'Serial', 'Produk', 'SKU', 'Size', 'Warna', 'Qty', 'Harga', 'HPP/CMT', 'Vendor', 'Status']
                all_col_keys = ['no', 'tanggal', 'no_po', 'no_seri', 'nama_produk', 'sku', 'size', 'warna', 'output_qty', 'harga', 'hpp', 'garment', 'po_status']

            elif report_type == 'progress':
                progs = await db.production_progress.find({}, {'_id': 0}).sort('progress_date', -1).to_list(None)
                # ── 10E: batch fetch ji + job docs in 2 queries ──
                prog_ji_ids  = list({p.get('job_item_id') for p in progs if p.get('job_item_id')})
                prog_job_ids = list({p.get('job_id') for p in progs if p.get('job_id')})
                _ji_docs  = await db.production_job_items.find({'id': {'$in': prog_ji_ids}}).to_list(None) if prog_ji_ids else []
                _job_docs = await db.production_jobs.find({'id': {'$in': prog_job_ids}}).to_list(None) if prog_job_ids else []
                _ji_map  = {d['id']: d for d in _ji_docs}
                _job_map = {d['id']: d for d in _job_docs}
                for p in progs:
                    ji  = _ji_map.get(p.get('job_item_id'), {})
                    job = _job_map.get(p.get('job_id'), {})
                    if sp.get('vendor_id') and job.get('vendor_id') != sp['vendor_id']: continue
                    report_data.append({
                        'date': _fmt_date(p.get('progress_date')),
                        'job_number': job.get('job_number', ''),
                        'po_number': job.get('po_number', ''),
                        'vendor_name': job.get('vendor_name', ''),
                        'serial_number': ji.get('serial_number', ''),
                        'sku': ji.get('sku', p.get('sku', '')),
                        'product_name': ji.get('product_name', p.get('product_name', '')),
                        'qty_progress': p.get('completed_quantity', 0),
                        'notes': p.get('notes', ''), 'recorded_by': p.get('recorded_by', '')
                    })
                headers = ['No', 'Tanggal', 'Job', 'PO', 'Vendor', 'Serial', 'SKU', 'Produk', 'Qty', 'Catatan', 'Dicatat oleh']
                all_col_keys = ['no', 'date', 'job_number', 'po_number', 'vendor_name', 'serial_number', 'sku', 'product_name', 'qty_progress', 'notes', 'recorded_by']

            elif report_type == 'financial':
                inv_query = {}
                if sp.get('status'): inv_query['status'] = sp['status']
                invoices = await db.invoices.find(inv_query, {'_id': 0}).sort('created_at', -1).to_list(None)
                for inv in invoices:
                    report_data.append({
                        'invoice_number': inv.get('invoice_number', ''),
                        'category': inv.get('invoice_category', ''),
                        'po_number': inv.get('po_number', ''),
                        'vendor_or_buyer': inv.get('vendor_name', inv.get('customer_name', '')),
                        'amount': inv.get('amount', 0),
                        'paid': inv.get('paid_amount', 0),
                        'remaining': inv.get('remaining_amount', inv.get('amount', 0) - inv.get('paid_amount', 0)),
                        'status': inv.get('status', ''),
                        'date': _fmt_date(inv.get('invoice_date', inv.get('created_at'))),
                    })
                headers = ['No', 'Invoice No', 'Category', 'PO', 'Vendor/Buyer', 'Amount', 'Paid', 'Remaining', 'Status', 'Date']
                all_col_keys = ['no', 'invoice_number', 'category', 'po_number', 'vendor_or_buyer', 'amount', 'paid', 'remaining', 'status', 'date']

            elif report_type == 'shipment':
                vs_q2 = {'vendor_id': sp['vendor_id']} if sp.get('vendor_id') else {}
                bs_q2 = {'vendor_id': sp['vendor_id']} if sp.get('vendor_id') else {}
                vs  = await db.vendor_shipments.find(vs_q2, {'_id': 0}).sort('created_at', -1).to_list(None)
                bsh = await db.buyer_shipments.find(bs_q2, {'_id': 0}).sort('created_at', -1).to_list(None)
                # ── 10E: batch fetch items in 2 queries ──
                vs_ids2   = [v['id'] for v in vs]
                bsh_ids2  = [b['id'] for b in bsh]
                _vsi_all  = await db.vendor_shipment_items.find({'shipment_id': {'$in': vs_ids2}}).to_list(None) if vs_ids2 else []
                _bsi_all  = await db.buyer_shipment_items.find({'shipment_id': {'$in': bsh_ids2}}).to_list(None) if bsh_ids2 else []
                _vsi_map2: dict = {}
                for it in _vsi_all: _vsi_map2.setdefault(it.get('shipment_id'), []).append(it)
                _bsi_map2: dict = {}
                for it in _bsi_all: _bsi_map2.setdefault(it.get('shipment_id'), []).append(it)
                for v in vs:
                    _items = _vsi_map2.get(v['id'], [])
                    report_data.append({
                        'direction': 'VENDOR', 'shipment_number': v.get('shipment_number', ''),
                        'shipment_type': v.get('shipment_type', 'NORMAL'), 'vendor_name': v.get('vendor_name', ''),
                        'status': v.get('status', ''), 'inspection': v.get('inspection_status', 'Pending'),
                        'date': _fmt_date(v.get('shipment_date', v.get('created_at'))),
                        'total_qty': sum(i.get('qty_sent', 0) for i in _items), 'items': len(_items)
                    })
                for b in bsh:
                    _items = _bsi_map2.get(b['id'], [])
                    report_data.append({
                        'direction': 'BUYER', 'shipment_number': b.get('shipment_number', ''),
                        'shipment_type': 'NORMAL', 'vendor_name': b.get('vendor_name', ''),
                        'status': b.get('status', b.get('ship_status', '')), 'inspection': '-',
                        'date': _fmt_date(b.get('created_at')),
                        'total_qty': sum(i.get('qty_shipped', 0) for i in _items), 'items': len(_items)
                    })
                headers = ['No', 'Direction', 'Shipment No', 'Type', 'Vendor', 'Status', 'Inspection', 'Date', 'Qty', 'Items']
                all_col_keys = ['no', 'direction', 'shipment_number', 'shipment_type', 'vendor_name', 'status', 'inspection', 'date', 'total_qty', 'items']

            elif report_type == 'defect':
                defects = await db.material_defect_reports.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
                for d in defects:
                    if sp.get('vendor_id') and d.get('vendor_id') != sp['vendor_id']: continue
                    report_data.append({
                        'date': _fmt_date(d.get('report_date', d.get('created_at'))),
                        'sku': d.get('sku', ''), 'product_name': d.get('product_name', ''),
                        'size': d.get('size', ''), 'color': d.get('color', ''),
                        'defect_qty': d.get('defect_qty', 0), 'defect_type': d.get('defect_type', ''),
                        'description': d.get('description', ''), 'status': d.get('status', '')
                    })
                headers = ['No', 'Tanggal', 'SKU', 'Produk', 'Size', 'Warna', 'Qty Defect', 'Tipe', 'Deskripsi', 'Status']
                all_col_keys = ['no', 'date', 'sku', 'product_name', 'size', 'color', 'defect_qty', 'defect_type', 'description', 'status']

            elif report_type == 'return':
                returns = await db.production_returns.find({}, {'_id': 0}).sort('created_at', -1).to_list(None)
                # ── 10E: batch fetch return items in 1 query ──
                ret_ids2 = [r['id'] for r in returns]
                _ret_items_all = await db.production_return_items.find({'return_id': {'$in': ret_ids2}}).to_list(None) if ret_ids2 else []
                _ret_items_map: dict = {}
                for it in _ret_items_all: _ret_items_map.setdefault(it.get('return_id'), []).append(it)
                for r in returns:
                    _items = _ret_items_map.get(r['id'], [])
                    report_data.append({
                        'return_number': r.get('return_number', ''), 'po_number': r.get('reference_po_number', ''),
                        'customer_name': r.get('customer_name', ''), 'return_date': _fmt_date(r.get('return_date')),
                        'total_qty': sum(i.get('return_qty', 0) for i in _items), 'item_count': len(_items),
                        'reason': r.get('return_reason', ''), 'status': r.get('status', ''),
                    })
                headers = ['No', 'Return No', 'PO', 'Customer', 'Date', 'Total Qty', 'Items', 'Reason', 'Status']
                all_col_keys = ['no', 'return_number', 'po_number', 'customer_name', 'return_date', 'total_qty', 'item_count', 'reason', 'status']

            elif report_type == 'missing-material':
                reqs = await db.material_requests.find({'request_type': 'ADDITIONAL'}, {'_id': 0}).sort('created_at', -1).to_list(None)
                for r in reqs:
                    if sp.get('vendor_id') and r.get('vendor_id') != sp['vendor_id']: continue
                    report_data.append({
                        'request_number': r.get('request_number', ''), 'vendor_name': r.get('vendor_name', ''),
                        'po_number': r.get('po_number', ''), 'total_qty': r.get('total_requested_qty', 0),
                        'reason': r.get('reason', ''), 'status': r.get('status', ''),
                        'child_shipment': r.get('child_shipment_number', '-'),
                        'date': _fmt_date(r.get('created_at')),
                    })
                headers = ['No', 'Request No', 'Vendor', 'PO', 'Qty', 'Reason', 'Status', 'Child Shipment', 'Date']
                all_col_keys = ['no', 'request_number', 'vendor_name', 'po_number', 'total_qty', 'reason', 'status', 'child_shipment', 'date']

            elif report_type == 'replacement':
                reqs = await db.material_requests.find({'request_type': 'REPLACEMENT'}, {'_id': 0}).sort('created_at', -1).to_list(None)
                for r in reqs:
                    if sp.get('vendor_id') and r.get('vendor_id') != sp['vendor_id']: continue
                    report_data.append({
                        'request_number': r.get('request_number', ''), 'vendor_name': r.get('vendor_name', ''),
                        'po_number': r.get('po_number', ''), 'total_qty': r.get('total_requested_qty', 0),
                        'reason': r.get('reason', ''), 'status': r.get('status', ''),
                        'child_shipment': r.get('child_shipment_number', '-'),
                        'date': _fmt_date(r.get('created_at')),
                    })
                headers = ['No', 'Request No', 'Vendor', 'PO', 'Qty', 'Reason', 'Status', 'Child Shipment', 'Date']
                all_col_keys = ['no', 'request_number', 'vendor_name', 'po_number', 'total_qty', 'reason', 'status', 'child_shipment', 'date']

            elif report_type == 'accessory':
                acc_q2 = {'vendor_id': sp['vendor_id']} if sp.get('vendor_id') else {}
                acc_ships = await db.accessory_shipments.find(acc_q2, {'_id': 0}).sort('created_at', -1).to_list(None)
                # ── 10E: batch fetch accessory items in 1 query ──
                acc_ship_ids2 = [s['id'] for s in acc_ships]
                _acc_items_all = await db.accessory_shipment_items.find({'shipment_id': {'$in': acc_ship_ids2}}).to_list(None) if acc_ship_ids2 else []
                _acc_items_map2: dict = {}
                for it in _acc_items_all: _acc_items_map2.setdefault(it.get('shipment_id'), []).append(it)
                for s in acc_ships:
                    for item in _acc_items_map2.get(s['id'], []):
                        report_data.append({
                            'shipment_number': s.get('shipment_number', ''), 'vendor_name': s.get('vendor_name', ''),
                            'po_number': s.get('po_number', ''), 'date': _fmt_date(s.get('shipment_date')),
                            'accessory_name': item.get('accessory_name', ''), 'accessory_code': item.get('accessory_code', ''),
                            'qty_sent': item.get('qty_sent', 0), 'unit': item.get('unit', 'pcs'),
                            'status': s.get('status', ''),
                        })
                headers = ['No', 'Shipment', 'Vendor', 'PO', 'Date', 'Accessory', 'Code', 'Qty', 'Unit', 'Status']
                all_col_keys = ['no', 'shipment_number', 'vendor_name', 'po_number', 'date', 'accessory_name', 'accessory_code', 'qty_sent', 'unit', 'status']
            else:
                return JSONResponse({'error': f'Unhandled report type: {report_type}'}, status_code=400)

            # Build the report PDF
            report_labels = {
                'production': 'Laporan Produksi', 'progress': 'Laporan Progres Produksi',
                'financial': 'Laporan Keuangan', 'shipment': 'Laporan Pengiriman',
                'defect': 'Laporan Defect Material', 'return': 'Laporan Retur Produksi',
                'missing-material': 'Laporan Material Hilang/Tambahan', 'replacement': 'Laporan Material Pengganti',
                'accessory': 'Laporan Aksesoris',
            }
            elements = []
            title = report_labels.get(report_type, f'Report: {report_type}')
            filter_info = []
            if sp.get('vendor_id'):
                vendor = await db.garments.find_one({'id': sp['vendor_id']})
                filter_info.append(('Vendor', (vendor or {}).get('garment_name', sp['vendor_id'])))
            if sp.get('date_from'): filter_info.append(('From', sp['date_from']))
            if sp.get('date_to'): filter_info.append(('To', sp['date_to']))
            if sp.get('status'): filter_info.append(('Status', sp['status']))
            _pdf_header(elements, settings, title, info_pairs=filter_info if filter_info else None, override=config)

            if not report_data:
                elements.append(Paragraph("Tidak ada data ditemukan untuk filter yang dipilih.", styles['Normal']))
            else:
                # Build table data
                data_rows = []
                for idx, row in enumerate(report_data, 1):
                    row_values = [idx]
                    for key in all_col_keys[1:]:  # skip 'no'
                        val = row.get(key, '')
                        if key in ('harga', 'hpp', 'amount', 'paid', 'remaining'):
                            val = _fmt_money(val)
                        elif key in ('output_qty', 'qty_progress', 'defect_qty', 'total_qty', 'item_count', 'items', 'qty_sent'):
                            val = val if val else 0
                        else:
                            val = _safe_str(val, 25)
                        row_values.append(val)
                    data_rows.append(row_values)
                if config and config.get('columns'):
                    headers, data_rows = _filter_columns(headers, all_col_keys, config['columns'], data_rows)
                td = [headers] + data_rows
                num_cols = len(headers)
                use_landscape = num_cols > 7
                page_width = 680 if use_landscape else 445
                cw = [max(22, int(page_width / num_cols))] * num_cols
                t = Table(td, colWidths=cw, repeatRows=1)
                t.setStyle(_pdf_table_style())
                t.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 7 if num_cols > 8 else 8)]))
                elements.append(t)

            elements.append(Spacer(1, 4*mm))
            elements.append(Paragraph(f"<i>Total Records: {len(report_data)}</i>", styles['Normal']))
            _pdf_footer(elements, settings, override=config)
            _build_pdf(buf, elements, page='landscape' if len(headers) > 7 else None, orientation=(config or {}).get('page_orientation'))
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename=laporan_{report_type}_{datetime.now().strftime('%Y%m%d')}.pdf"})

        else:
            all_types = [
                'production-po', 'vendor-shipment', 'buyer-shipment', 'buyer-shipment-dispatch',
                'production-return', 'material-request', 'production-report',
                'report-production', 'report-progress', 'report-financial', 'report-shipment',
                'report-defect', 'report-return', 'report-missing-material', 'report-replacement', 'report-accessory'
            ]
            return JSONResponse({'error': f'Unknown PDF type: {pdf_type}', 'available_types': all_types}, status_code=400)
    except HTTPException: raise
    except Exception as e:
        logger.error(f"PDF export error: {e}", exc_info=True)
        raise HTTPException(500, f"PDF export failed: {str(e)}")

# ─── PDF EXPORT CONFIGURATION CRUD ───────────────────────────────────────────

# Available columns per PDF type (used by config UI)
PDF_COLUMN_DEFINITIONS = {
    'production-po': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Product Name'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Color'},
        {'key': 'qty', 'label': 'Quantity', 'required': True},
        {'key': 'price', 'label': 'Selling Price'},
        {'key': 'cmt', 'label': 'CMT Price'},
        {'key': 'po_number', 'label': 'No PO (repeat)'},
        {'key': 'po_date', 'label': 'Tanggal PO'},
        {'key': 'deadline', 'label': 'Deadline'},
        {'key': 'delivery_deadline', 'label': 'Delivery Deadline'},
        {'key': 'po_status', 'label': 'Status PO'},
        {'key': 'barcode', 'label': 'Barcode'},
        {'key': 'notes', 'label': 'Catatan Item'},
    ],
    'vendor-shipment': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'po', 'label': 'PO Number'},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Product Name'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Color'},
        {'key': 'qty_sent', 'label': 'Qty Sent', 'required': True},
        {'key': 'ordered_qty', 'label': 'Qty Ordered'},
        {'key': 'shipment_number', 'label': 'No Surat Jalan'},
        {'key': 'shipment_date', 'label': 'Tanggal SJ'},
        {'key': 'shipment_type', 'label': 'Tipe SJ'},
        {'key': 'inspection_status', 'label': 'Status Inspeksi'},
    ],
    'vendor-inspection': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'product', 'label': 'Produk'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Warna'},
        {'key': 'ordered_qty', 'label': 'Qty Dikirim', 'required': True},
        {'key': 'received_qty', 'label': 'Qty Diterima'},
        {'key': 'missing_qty', 'label': 'Qty Missing'},
        {'key': 'condition_notes', 'label': 'Catatan'},
        {'key': 'category', 'label': 'Kategori'},
    ],
    'buyer-shipment': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Product Name'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Color'},
        {'key': 'ordered', 'label': 'Ordered Qty'},
        {'key': 'shipped', 'label': 'Shipped Qty', 'required': True},
        {'key': 'dispatch_date', 'label': 'Tgl Dispatch'},
    ],
    'production-return': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Product Name'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Color'},
        {'key': 'return_qty', 'label': 'Qty Returned', 'required': True},
        {'key': 'notes', 'label': 'Notes'},
        {'key': 'return_number', 'label': 'No Retur'},
        {'key': 'return_date', 'label': 'Tanggal Retur'},
        {'key': 'return_reason', 'label': 'Alasan Retur'},
        {'key': 'status', 'label': 'Status'},
    ],
    'material-request': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Product Name'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Color'},
        {'key': 'qty_requested', 'label': 'Qty Requested', 'required': True},
        {'key': 'request_number', 'label': 'No Request'},
        {'key': 'po_number', 'label': 'No PO'},
        {'key': 'request_type', 'label': 'Tipe Request'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'reason', 'label': 'Alasan'},
    ],
    'buyer-shipment-dispatch': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Product Name'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Color'},
        {'key': 'ordered', 'label': 'Ordered Qty'},
        {'key': 'this_dispatch', 'label': 'This Dispatch'},
        {'key': 'cumul_shipped', 'label': 'Cumulative Shipped'},
        {'key': 'remaining', 'label': 'Remaining'},
        {'key': 'po_number', 'label': 'No PO'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'customer', 'label': 'Customer'},
        {'key': 'shipment_number', 'label': 'No Surat Jalan'},
        {'key': 'dispatch_date', 'label': 'Tanggal Dispatch'},
        {'key': 'dispatch_seq', 'label': 'Dispatch #'},
    ],
    'production-report': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'date', 'label': 'Date'},
        {'key': 'po', 'label': 'PO Number'},
        {'key': 'serial', 'label': 'Serial No'},
        {'key': 'product', 'label': 'Product Name'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Color'},
        {'key': 'qty', 'label': 'Quantity'},
        {'key': 'price', 'label': 'Price'},
        {'key': 'cmt', 'label': 'CMT'},
        {'key': 'vendor', 'label': 'Vendor'},
        {'key': 'produced', 'label': 'Produced'},
        {'key': 'shipped', 'label': 'Shipped'},
    ],
    'report-production': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'tanggal', 'label': 'Tanggal'},
        {'key': 'no_po', 'label': 'No PO'},
        {'key': 'no_seri', 'label': 'Serial'},
        {'key': 'nama_produk', 'label': 'Produk'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'warna', 'label': 'Warna'},
        {'key': 'output_qty', 'label': 'Qty'},
        {'key': 'harga', 'label': 'Harga'},
        {'key': 'hpp', 'label': 'HPP/CMT'},
        {'key': 'garment', 'label': 'Vendor'},
        {'key': 'po_status', 'label': 'Status'},
    ],
    'report-progress': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'date', 'label': 'Tanggal'},
        {'key': 'job_number', 'label': 'Job'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'serial_number', 'label': 'Serial'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'product_name', 'label': 'Produk'},
        {'key': 'qty_progress', 'label': 'Qty'},
        {'key': 'notes', 'label': 'Catatan'},
        {'key': 'recorded_by', 'label': 'Dicatat oleh'},
    ],
    'report-financial': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'invoice_number', 'label': 'Invoice No'},
        {'key': 'category', 'label': 'Category'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'vendor_or_buyer', 'label': 'Vendor/Buyer'},
        {'key': 'amount', 'label': 'Amount'},
        {'key': 'paid', 'label': 'Paid'},
        {'key': 'remaining', 'label': 'Remaining'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'date', 'label': 'Date'},
    ],
    'report-shipment': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'direction', 'label': 'Direction'},
        {'key': 'shipment_number', 'label': 'Shipment No'},
        {'key': 'shipment_type', 'label': 'Type'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'inspection', 'label': 'Inspection'},
        {'key': 'date', 'label': 'Date'},
        {'key': 'total_qty', 'label': 'Qty'},
        {'key': 'items', 'label': 'Items'},
    ],
    'report-defect': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'date', 'label': 'Tanggal'},
        {'key': 'sku', 'label': 'SKU'},
        {'key': 'product_name', 'label': 'Produk'},
        {'key': 'size', 'label': 'Size'},
        {'key': 'color', 'label': 'Warna'},
        {'key': 'defect_qty', 'label': 'Qty Defect'},
        {'key': 'defect_type', 'label': 'Tipe'},
        {'key': 'description', 'label': 'Deskripsi'},
        {'key': 'status', 'label': 'Status'},
    ],
    'report-return': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'return_number', 'label': 'Return No'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'customer_name', 'label': 'Customer'},
        {'key': 'return_date', 'label': 'Date'},
        {'key': 'total_qty', 'label': 'Total Qty'},
        {'key': 'item_count', 'label': 'Items'},
        {'key': 'reason', 'label': 'Reason'},
        {'key': 'status', 'label': 'Status'},
    ],
    'report-missing-material': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'request_number', 'label': 'Request No'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'total_qty', 'label': 'Qty'},
        {'key': 'reason', 'label': 'Reason'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'child_shipment', 'label': 'Child Shipment'},
        {'key': 'date', 'label': 'Date'},
    ],
    'report-replacement': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'request_number', 'label': 'Request No'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'total_qty', 'label': 'Qty'},
        {'key': 'reason', 'label': 'Reason'},
        {'key': 'status', 'label': 'Status'},
        {'key': 'child_shipment', 'label': 'Child Shipment'},
        {'key': 'date', 'label': 'Date'},
    ],
    'report-accessory': [
        {'key': 'no', 'label': 'No', 'required': True},
        {'key': 'shipment_number', 'label': 'Shipment'},
        {'key': 'vendor_name', 'label': 'Vendor'},
        {'key': 'po_number', 'label': 'PO'},
        {'key': 'date', 'label': 'Date'},
        {'key': 'accessory_name', 'label': 'Accessory'},
        {'key': 'accessory_code', 'label': 'Code'},
        {'key': 'qty_sent', 'label': 'Qty'},
        {'key': 'unit', 'label': 'Unit'},
        {'key': 'status', 'label': 'Status'},
    ],
}

