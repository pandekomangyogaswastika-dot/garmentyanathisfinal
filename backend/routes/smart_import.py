"""
Smart Import Module — Garment ERP v8.0
Handles intelligent Excel/CSV, Photo/Scan, and PDF import with:
- Fuzzy column mapping + LLM fallback
- Preview & inline edit with auto-create detection
- Preset management per buyer/vendor
- Batch commit with safety confirmation
"""
import os, uuid, json, base64, logging, re
from io import BytesIO
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

import pandas as pd
from rapidfuzz import process as fuzz_process, fuzz
import pdfplumber

from database import get_db
from auth import require_auth, check_role, serialize_doc, hash_password, generate_password

router = APIRouter(prefix="/api/smart-import")
logger = logging.getLogger(__name__)

# ─── Helpers ─────────────────────────────────────────────────────────────────
def new_id(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)

ALLOWED_TYPES = {
    'xlsx': 'excel', 'xls': 'excel', 'csv': 'csv',
    'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'webp': 'image',
    'pdf': 'pdf'
}

# ─── Field Definitions ───────────────────────────────────────────────────────
FIELD_DEFINITIONS = {
    "production_po": {
        "po_number":      {"label": "No. PO",         "aliases": ["no po","nomor po","po number","po_no","no_po","purchase order","order number","no order","nomor order","order no","no. po","nopo"], "required": True,  "type": "string"},
        "customer_name":  {"label": "Nama Buyer",      "aliases": ["buyer","customer","pelanggan","nama buyer","nama pelanggan","client","nama customer","customer name","pembeli"], "required": True,  "type": "string"},
        "vendor_name":    {"label": "Nama Vendor",     "aliases": ["vendor","garment","kontraktor","factory","pabrik","nama vendor","supplier","nama garmen","garmen"], "required": True,  "type": "string"},
        "po_date":        {"label": "Tanggal PO",      "aliases": ["tanggal po","tanggal order","order date","po date","tgl po","tgl order","date","tanggal","tgl"], "required": False, "type": "date"},
        # Phase 8.2 — deadline terminology is now explicit:
        #   deadline          = Deadline Produksi (internal production due date)
        #   delivery_deadline = Deadline Pengiriman (ship-to-buyer / ETD)
        "deadline":       {"label": "Deadline Produksi", "aliases": ["deadline","deadline produksi","production deadline","batas produksi","batas waktu","tgl deadline","tgl produksi","tgl produksi selesai","tgl selesai","tanggal selesai","finish date","due date","selesai"], "required": False, "type": "date"},
        "delivery_deadline": {"label": "Deadline Pengiriman", "aliases": ["delivery deadline","deadline pengiriman","tgl pengiriman","tanggal pengiriman","tgl kirim","tanggal kirim","ship date","shipping date","etd","estimated delivery","delivery date","delivery"], "required": False, "type": "date"},
        "product_name":   {"label": "Nama Produk",     "aliases": ["nama produk","produk","product","nama barang","barang","item","style","product name","nama item","artikel"], "required": False, "type": "string"},
        "product_code":   {"label": "Kode Produk",     "aliases": ["kode produk","product code","product_code","style code","kode style","kode artikel","article code"], "required": False, "type": "string"},
        "sku":            {"label": "SKU",             "aliases": ["sku","kode produk","product code","article","kode","kode barang","article no"], "required": False, "type": "string"},
        "serial_number":  {"label": "Nomor Seri",      "aliases": ["serial","serial number","nomor seri","no seri","sn","sn no","nomor","serial no"], "required": False, "type": "string"},
        "size":           {"label": "Ukuran",          "aliases": ["ukuran","size","sz","s/m/l/xl","size group","ukuran baju"], "required": False, "type": "string"},
        "color":          {"label": "Warna",           "aliases": ["warna","color","colour","col","warna produk"], "required": False, "type": "string"},
        "qty":            {"label": "Qty",             "aliases": ["qty","jumlah","quantity","pcs","kuantitas","jumlah pcs","jumlah order","total qty"], "required": False, "type": "number"},
        "cmt_price":      {"label": "Harga CMT",       "aliases": ["harga cmt","cmt price","harga produksi","cost","production price","harga maklon","cmt","biaya maklon","harga vendor"], "required": False, "type": "number"},
        "selling_price":  {"label": "Harga Jual",      "aliases": ["harga jual","selling price","sell price","harga buyer","price buyer","harga jual buyer"], "required": False, "type": "number"},
        "unit_price":     {"label": "Harga Satuan",    "aliases": ["harga","price","unit price","harga satuan","harga per pcs"], "required": False, "type": "number"},
        # Phase 8.1 — accessory add-on columns (po_accessories)
        "accessory_code": {"label": "Kode Aksesoris",  "aliases": ["kode aksesoris","accessory code","acc code","kode acc","kode aks","aksesoris code"], "required": False, "type": "string"},
        "accessory_name": {"label": "Nama Aksesoris",  "aliases": ["nama aksesoris","accessory name","acc name","nama acc","aksesoris","add-on","addon","nama add-on"], "required": False, "type": "string"},
        "accessory_qty_needed": {"label": "Qty Aksesoris", "aliases": ["qty aksesoris","accessory qty","qty acc","jumlah aksesoris","qty add-on","kebutuhan aksesoris","qty needed"], "required": False, "type": "number"},
        "accessory_unit": {"label": "Satuan Aksesoris", "aliases": ["satuan aksesoris","accessory unit","acc unit","unit aksesoris","uom aksesoris"], "required": False, "type": "string"},
        "accessory_notes":{"label": "Catatan Aksesoris","aliases": ["catatan aksesoris","accessory notes","keterangan aksesoris","notes aksesoris"], "required": False, "type": "string"},
        "notes":          {"label": "Catatan",         "aliases": ["catatan","notes","keterangan","remark","note","ket","memo"], "required": False, "type": "string"},
    },
    "products": {
        "product_code":   {"label": "Kode Produk",    "aliases": ["kode produk","product code","kode","sku","article","kode barang","no produk","product no"], "required": True,  "type": "string"},
        "product_name":   {"label": "Nama Produk",    "aliases": ["nama produk","product name","nama","item","style","nama barang","deskripsi produk"], "required": True,  "type": "string"},
        "category":       {"label": "Kategori",       "aliases": ["kategori","category","jenis","type","tipe","jenis produk"], "required": False, "type": "string"},
        "cmt_price":      {"label": "Harga CMT",      "aliases": ["harga cmt","cmt price","harga produksi","cost","production price","harga maklon","cmt","biaya maklon"], "required": False, "type": "number"},
        "selling_price":  {"label": "Harga Jual",     "aliases": ["harga jual","selling price","harga","price","sell price","harga beli"], "required": False, "type": "number"},
    },
    "accessories": {
        "accessory_code": {"label": "Kode Aksesoris", "aliases": ["kode aksesoris","accessory code","kode","code","acc code","kode acc","no aksesoris"], "required": True,  "type": "string"},
        "accessory_name": {"label": "Nama Aksesoris", "aliases": ["nama aksesoris","accessory name","nama","item","aksesoris","acc name","nama acc"], "required": True,  "type": "string"},
        "category":       {"label": "Kategori",       "aliases": ["kategori","category","jenis","type"], "required": False, "type": "string"},
        "unit":           {"label": "Satuan",         "aliases": ["satuan","unit","uom","unit of measure","ukuran satuan"], "required": False, "type": "string"},
        "description":    {"label": "Deskripsi",      "aliases": ["deskripsi","description","keterangan","notes","penjelasan"], "required": False, "type": "string"},
    },
    "vendors": {
        "garment_name":   {"label": "Nama Vendor",     "aliases": ["nama vendor","vendor","garment","factory","pabrik","nama","company","nama perusahaan","vendor name","nama garmen","garmen"], "required": True,  "type": "string"},
        "garment_code":   {"label": "Kode Vendor",     "aliases": ["kode vendor","vendor code","kode","code","company code","kode garmen"], "required": False, "type": "string"},
        "contact_person": {"label": "Contact Person",  "aliases": ["contact","kontak","pic","person in charge","contact person","nama kontak","penanggung jawab"], "required": False, "type": "string"},
        "phone":          {"label": "Telepon",         "aliases": ["telepon","phone","hp","no hp","nomor telepon","telp","no telp","handphone","whatsapp"], "required": False, "type": "string"},
        "email":          {"label": "Email",           "aliases": ["email","e-mail","surel","mail","alamat email"], "required": False, "type": "string"},
        "address":        {"label": "Alamat",          "aliases": ["alamat","address","lokasi","location","domisili","kota","kota/kabupaten"], "required": False, "type": "string"},
    },
    "buyers": {
        "buyer_name":     {"label": "Nama Buyer",      "aliases": ["nama buyer","buyer","customer","client","nama pelanggan","nama","company","nama perusahaan","pembeli"], "required": True,  "type": "string"},
        "buyer_code":     {"label": "Kode Buyer",      "aliases": ["kode buyer","buyer code","kode","code","customer code"], "required": False, "type": "string"},
        "contact_person": {"label": "Contact Person",  "aliases": ["contact","kontak","pic","person in charge","contact person","nama kontak"], "required": False, "type": "string"},
        "phone":          {"label": "Telepon",         "aliases": ["telepon","phone","hp","no hp","nomor telepon","telp","no telp"], "required": False, "type": "string"},
        "email":          {"label": "Email",           "aliases": ["email","e-mail","surel","mail"], "required": False, "type": "string"},
        "address":        {"label": "Alamat",          "aliases": ["alamat","address","lokasi","location","domisili"], "required": False, "type": "string"},
    }
}

DATA_TYPE_LABELS = {
    "production_po": "Production PO",
    "products": "Data Produk",
    "accessories": "Data Aksesoris",
    "vendors": "Data Vendor/Garmen",
    "buyers": "Data Buyer"
}

# ─── LLM Prompts ─────────────────────────────────────────────────────────────
def get_llm_mapping_prompt(headers: list, data_type: str, sample_rows: list) -> str:
    fields = list(FIELD_DEFINITIONS.get(data_type, {}).keys())
    return f"""Kamu adalah asisten mapping kolom untuk import data garmen ERP.

Data type: {DATA_TYPE_LABELS.get(data_type, data_type)}
Kolom dari file: {json.dumps(headers)}
Contoh data (3 baris pertama): {json.dumps(sample_rows[:3])}
Field yang tersedia di sistem: {json.dumps(fields)}

Tugasmu: Untuk SETIAP kolom file, tentukan field sistem yang paling cocok.
Jika tidak ada yang cocok, gunakan null.

Kembalikan HANYA JSON (tanpa komentar, tanpa markdown):
{{
  "kolom_dari_file": "field_sistem_atau_null",
  ...
}}

Contoh: {{"No PO": "po_number", "Nama Buyer": "customer_name", "Tanggal": "po_date", "Kolom Tidak Dikenal": null}}"""

def get_ocr_prompt(data_type: str) -> str:
    fields = FIELD_DEFINITIONS.get(data_type, {})
    field_desc = "\n".join([f"- {k}: {v['label']} ({v['type']}){' [WAJIB]' if v['required'] else ''}" 
                             for k, v in fields.items()])
    
    if data_type == "production_po":
        return f"""Kamu adalah sistem OCR untuk dokumen PO garmen. Ekstrak semua data dari gambar ini.

Field yang harus diekstrak:
{field_desc}

Kembalikan data sebagai JSON array. Setiap elemen = 1 baris item.
Untuk PO dengan banyak item, ulangi po_number/customer_name/vendor_name/po_date/deadline di setiap baris.
Format tanggal: YYYY-MM-DD (jika tidak yakin, gunakan null).
Gunakan null untuk field yang tidak ditemukan.

Kembalikan HANYA JSON array (tanpa markdown):
[
  {{"po_number": "...", "customer_name": "...", "vendor_name": "...", "po_date": "...", "product_name": "...", "qty": 100, ...}},
  ...
]"""
    else:
        return f"""Kamu adalah sistem OCR untuk dokumen {DATA_TYPE_LABELS.get(data_type, data_type)}.

Field yang harus diekstrak:
{field_desc}

Kembalikan data sebagai JSON array. Setiap elemen = 1 baris/record.
Gunakan null untuk field yang tidak ditemukan.
Format angka: bilangan bulat atau desimal (tanpa simbol mata uang).

Kembalikan HANYA JSON array (tanpa markdown):
[{{"field": "value", ...}}, ...]"""

# ─── File Session Storage ────────────────────────────────────────────────────
IMPORT_TMP_DIR = "/tmp/smart_import"
os.makedirs(IMPORT_TMP_DIR, exist_ok=True)

def save_session(session_id: str, file_bytes: bytes, ext: str, filename: str, data_type: str):
    path = f"{IMPORT_TMP_DIR}/{session_id}.{ext}"
    with open(path, "wb") as f:
        f.write(file_bytes)
    meta = {"ext": ext, "filename": filename, "data_type": data_type, "created": now().isoformat()}
    with open(f"{IMPORT_TMP_DIR}/{session_id}.meta.json", "w") as f:
        json.dump(meta, f)
    return path

def load_session(session_id: str) -> tuple:
    meta_path = f"{IMPORT_TMP_DIR}/{session_id}.meta.json"
    if not os.path.exists(meta_path):
        raise HTTPException(400, f"Session {session_id} tidak ditemukan atau sudah expired")
    with open(meta_path) as f:
        meta = json.load(f)
    file_path = f"{IMPORT_TMP_DIR}/{session_id}.{meta['ext']}"
    if not os.path.exists(file_path):
        raise HTTPException(400, "File session tidak ditemukan")
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    return file_bytes, meta

# ─── Parsing Helpers ─────────────────────────────────────────────────────────
def normalize_header(h) -> str:
    if h is None: return ""
    return str(h).strip().lower().replace("_", " ").replace("-", " ").replace(".", " ")

def detect_header_row(df: pd.DataFrame) -> int:
    """Find the row with the most non-empty string values (likely the header row)."""
    best_row = 0
    best_score = 0
    for i in range(min(10, len(df))):
        row = df.iloc[i]
        score = sum(1 for v in row if isinstance(v, str) and len(str(v).strip()) > 0)
        if score > best_score:
            best_score = score
            best_row = i
    return best_row

def parse_file_to_df(file_bytes: bytes, ext: str) -> pd.DataFrame:
    """Parse Excel/CSV file to DataFrame."""
    bio = BytesIO(file_bytes)
    if ext in ('xlsx', 'xls'):
        return pd.read_excel(bio, header=None, dtype=str)
    elif ext == 'csv':
        # Try multiple encodings
        for enc in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
            try:
                bio.seek(0)
                return pd.read_csv(bio, header=None, dtype=str, encoding=enc)
            except:
                continue
        bio.seek(0)
        return pd.read_csv(bio, header=None, dtype=str, encoding='utf-8', errors='replace')

def fuzzy_match_columns(headers: list, data_type: str) -> dict:
    """Match each header to known field names using fuzzy matching."""
    fields = FIELD_DEFINITIONS.get(data_type, {})
    # Build alias → field map
    alias_map = {}
    for field_key, field_info in fields.items():
        for alias in field_info.get("aliases", []):
            alias_map[alias] = field_key
    
    result = {}
    for header in headers:
        norm = normalize_header(header)
        if not norm:
            result[header] = {"field": None, "confidence": 0, "method": "none"}
            continue
        
        # Direct match first
        if norm in alias_map:
            result[header] = {"field": alias_map[norm], "confidence": 100, "method": "exact"}
            continue
        
        # Fuzzy match against all aliases
        all_aliases = list(alias_map.keys())
        match = fuzz_process.extractOne(norm, all_aliases, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 70:
            result[header] = {"field": alias_map[match[0]], "confidence": match[1], "method": "fuzzy"}
        else:
            result[header] = {"field": None, "confidence": match[1] if match else 0, "method": "none"}
    
    return result

def parse_date(val) -> Optional[str]:
    """Parse a date value to YYYY-MM-DD string."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', '-', ''):
        return None
    # Try common formats
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y', '%d/%m/%y', '%Y%m%d', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except:
            pass
    # Try pandas
    try:
        return pd.to_datetime(s, dayfirst=True).strftime('%Y-%m-%d')
    except:
        return s  # Return as-is

def parse_number(val) -> Optional[float]:
    """Parse a number value."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().replace(',', '').replace('.', '', str(val).count('.') - 1)
    # Remove non-numeric except decimal point
    s = re.sub(r'[^\d.]', '', s)
    try:
        return float(s) if '.' in s else int(s)
    except:
        return None

def apply_mapping_to_df(df: pd.DataFrame, header_row: int, mapping: dict, data_type: str) -> list:
    """Apply column mapping to dataframe and return list of row dicts."""
    # Use the detected header row
    headers = df.iloc[header_row].tolist()
    data_rows = df.iloc[header_row + 1:].reset_index(drop=True)
    
    fields = FIELD_DEFINITIONS.get(data_type, {})
    rows = []
    
    for idx, row in data_rows.iterrows():
        row_dict = {}
        for col_idx, header in enumerate(headers):
            header_str = str(header) if header is not None else ""
            mapped_field = mapping.get(header_str)
            if mapped_field and col_idx < len(row):
                val = row.iloc[col_idx]
                if isinstance(val, float) and pd.isna(val):
                    val = None
                elif val is not None:
                    val = str(val).strip()
                    if val.lower() in ('nan', 'none', ''):
                        val = None
                
                # Type conversion
                field_info = fields.get(mapped_field, {})
                if val is not None:
                    if field_info.get("type") == "date":
                        val = parse_date(val)
                    elif field_info.get("type") == "number":
                        val = parse_number(val)
                
                if val is not None:
                    row_dict[mapped_field] = val
        
        # Skip completely empty rows
        non_empty = sum(1 for v in row_dict.values() if v is not None and str(v).strip())
        if non_empty > 0:
            rows.append(row_dict)
    
    return rows

# ─── Validation ──────────────────────────────────────────────────────────────
def validate_row(row: dict, data_type: str) -> list:
    """Validate a row and return list of error messages."""
    errors = []
    fields = FIELD_DEFINITIONS.get(data_type, {})
    
    for field_key, field_info in fields.items():
        if field_info.get("required"):
            val = row.get(field_key)
            if not val or str(val).strip() == "":
                errors.append(f"Field '{field_info['label']}' wajib diisi")
    
    # Validate qty > 0
    if "qty" in row and row["qty"] is not None:
        try:
            q = float(row["qty"])
            if q <= 0:
                errors.append("Qty harus > 0")
        except:
            errors.append("Qty harus berupa angka")
    
    return errors

# ─── Auto-create Detection ────────────────────────────────────────────────────
async def detect_auto_creates(rows: list, data_type: str, db) -> list:
    """For each row, detect which referenced entities don't exist and need auto-create."""
    processed = []
    
    # Cache lookups to avoid repeated DB queries
    vendor_cache = {}
    buyer_cache = {}
    product_cache = {}
    accessory_cache = {}
    
    for row in rows:
        auto_creates = []
        status = "valid"
        errors = validate_row(row, data_type)
        if errors:
            status = "error"
        
        if data_type == "production_po":
            # Check vendor
            vendor_name = row.get("vendor_name", "").strip()
            if vendor_name:
                if vendor_name not in vendor_cache:
                    vd = await db.garments.find_one(
                        {"garment_name": {"$regex": f"^{re.escape(vendor_name)}$", "$options": "i"}},
                        {"_id": 0, "id": 1, "garment_name": 1}
                    )
                    vendor_cache[vendor_name] = vd
                vd = vendor_cache[vendor_name]
                if not vd:
                    auto_creates.append({"entity": "vendor", "name": vendor_name, "status": "new"})
                else:
                    auto_creates.append({"entity": "vendor", "name": vendor_name, "status": "exists", "id": vd["id"]})
            
            # Check buyer
            buyer_name = row.get("customer_name", "").strip()
            if buyer_name:
                if buyer_name not in buyer_cache:
                    bd = await db.buyers.find_one(
                        {"buyer_name": {"$regex": f"^{re.escape(buyer_name)}$", "$options": "i"}},
                        {"_id": 0, "id": 1, "buyer_name": 1}
                    )
                    buyer_cache[buyer_name] = bd
                bd = buyer_cache[buyer_name]
                if not bd:
                    auto_creates.append({"entity": "buyer", "name": buyer_name, "status": "new"})
                else:
                    auto_creates.append({"entity": "buyer", "name": buyer_name, "status": "exists", "id": bd["id"]})
            
            # Check product
            product_name = row.get("product_name", "").strip()
            sku = row.get("sku", "").strip()
            if product_name:
                cache_key = f"{product_name}::{sku}"
                if cache_key not in product_cache:
                    q = {"product_name": {"$regex": f"^{re.escape(product_name)}$", "$options": "i"}}
                    if sku:
                        q = {"$and": [q, {"product_code": {"$regex": f"^{re.escape(sku)}$", "$options": "i"}}]}
                    pd_doc = await db.products.find_one(q, {"_id": 0, "id": 1, "product_name": 1})
                    product_cache[cache_key] = pd_doc
                pd_doc = product_cache[cache_key]
                if not pd_doc:
                    auto_creates.append({"entity": "product", "name": f"{product_name}" + (f" ({sku})" if sku else ""), "status": "new"})
                else:
                    auto_creates.append({"entity": "product", "name": product_name, "status": "exists", "id": pd_doc["id"]})

            # Phase 8.1 — Detect accessory master for accessory add-on rows
            acc_code = (row.get("accessory_code") or "").strip()
            acc_name = (row.get("accessory_name") or "").strip()
            if acc_code or acc_name:
                cache_key = f"acc::{acc_code}::{acc_name}"
                if cache_key not in accessory_cache:
                    q = {}
                    if acc_code:
                        q = {"$or": [{"accessory_code": acc_code}, {"code": acc_code}]}
                    elif acc_name:
                        q = {"accessory_name": {"$regex": f"^{re.escape(acc_name)}$", "$options": "i"}}
                    ad = await db.accessories.find_one(q, {"_id": 0, "id": 1}) if q else None
                    accessory_cache[cache_key] = ad
                ad = accessory_cache.get(cache_key)
                display = acc_name or acc_code
                if ad:
                    auto_creates.append({"entity": "accessory", "name": display, "status": "exists", "id": ad["id"]})
                else:
                    auto_creates.append({"entity": "accessory", "name": display, "status": "new"})

            # Check existing PO
            po_number = row.get("po_number", "").strip()
            if po_number:
                po_doc = await db.production_pos.find_one({"po_number": po_number}, {"_id": 0, "id": 1})
                if po_doc:
                    status = "exists"  # PO will be linked/updated
        
        elif data_type == "products":
            product_code = row.get("product_code", "").strip()
            if product_code:
                if product_code not in product_cache:
                    pd_doc = await db.products.find_one({"product_code": product_code}, {"_id": 0, "id": 1})
                    product_cache[product_code] = pd_doc
                pd_doc = product_cache[product_code]
                if pd_doc:
                    status = "exists"
        
        elif data_type == "accessories":
            accessory_code = row.get("accessory_code", "").strip()
            if accessory_code:
                if accessory_code not in accessory_cache:
                    # Match against both canonical and legacy field names.
                    ad = await db.accessories.find_one(
                        {"$or": [{"accessory_code": accessory_code}, {"code": accessory_code}]},
                        {"_id": 0, "id": 1}
                    )
                    accessory_cache[accessory_code] = ad
                ad = accessory_cache.get(accessory_code)
                if ad:
                    status = "exists"
        
        elif data_type == "vendors":
            garment_name = row.get("garment_name", "").strip()
            if garment_name:
                if garment_name not in vendor_cache:
                    vd = await db.garments.find_one(
                        {"garment_name": {"$regex": f"^{re.escape(garment_name)}$", "$options": "i"}},
                        {"_id": 0, "id": 1}
                    )
                    vendor_cache[garment_name] = vd
                vd = vendor_cache[garment_name]
                if vd:
                    status = "exists"
        
        elif data_type == "buyers":
            buyer_name = row.get("buyer_name", "").strip()
            if buyer_name:
                if buyer_name not in buyer_cache:
                    bd = await db.buyers.find_one(
                        {"buyer_name": {"$regex": f"^{re.escape(buyer_name)}$", "$options": "i"}},
                        {"_id": 0, "id": 1}
                    )
                    buyer_cache[buyer_name] = bd
                bd = buyer_cache.get(buyer_name)
                if bd:
                    status = "exists"
        
        processed.append({
            **row,
            "_status": "error" if errors else status,
            "_errors": errors,
            "_auto_creates": auto_creates
        })
    
    return processed

# ─── Commit Logic ─────────────────────────────────────────────────────────────
async def commit_production_po(rows: list, user: dict, db) -> dict:
    """Group rows by po_number and create POs with items, variants, and accessory add-ons.

    Phase 8.1 — Rows can contain accessory columns (accessory_code/accessory_name/
    accessory_qty_needed/etc.). Those are split into `po_accessories` records.

    Phase 8.3 — Products are deduplicated at the parent level (preferred by
    `product_code`, fallback to case-insensitive `product_name`). Each unique
    (product_id, size, color, sku) tuple becomes a `product_variants` document,
    and the PO item's `variant_id` is set accordingly.
    """
    from auth import log_activity

    # Apply edits and group by po_number
    po_groups = {}
    for row in rows:
        po_num = (row.get("po_number") or "").strip()
        if not po_num:
            continue
        if po_num not in po_groups:
            po_groups[po_num] = {"header": {}, "items": [], "accessories": []}
        # Update header fields
        for f in ["customer_name", "vendor_name", "po_date", "deadline", "delivery_deadline", "notes"]:
            if row.get(f):
                po_groups[po_num]["header"][f] = row[f]
        po_groups[po_num]["header"]["po_number"] = po_num

        # Identify item vs accessory content on this row
        item_fields = {k: row[k] for k in [
            "product_name", "product_code", "sku", "size", "color", "qty",
            "serial_number", "unit_price", "cmt_price", "selling_price", "notes"
        ] if row.get(k) not in (None, "")}
        is_item_row = bool(item_fields.get("product_name") or item_fields.get("sku") or item_fields.get("qty"))

        acc_fields = {
            "accessory_code": (row.get("accessory_code") or "").strip(),
            "accessory_name": (row.get("accessory_name") or "").strip(),
            "qty_needed":     row.get("accessory_qty_needed"),
            "unit":           (row.get("accessory_unit") or "").strip() or "pcs",
            "notes":          (row.get("accessory_notes") or "").strip(),
        }
        is_accessory_row = bool(acc_fields["accessory_code"] or acc_fields["accessory_name"])

        if is_item_row:
            po_groups[po_num]["items"].append(item_fields)
        if is_accessory_row:
            po_groups[po_num]["accessories"].append(acc_fields)

    created = 0
    updated = 0
    accessories_created = 0
    variants_created = 0
    products_created = 0
    errors = []
    vendor_cache = {}
    buyer_cache = {}
    product_cache = {}       # key: normalized product key → product doc
    variant_cache = {}       # key: f"{product_id}::{size}::{color}::{sku}" → variant doc
    accessory_master_cache = {}  # key: accessory_code or accessory_name.lower() → accessory master doc

    async def _resolve_or_create_accessory_master(name: str, code: str):
        nonlocal accessories_created
        key = (code or f"name::{name.lower()}").strip()
        if key in accessory_master_cache:
            return accessory_master_cache[key]
        q = None
        if code:
            q = {"$or": [{"accessory_code": code}, {"code": code}]}
        elif name:
            q = {"accessory_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
        ad = await db.accessories.find_one(q) if q else None
        if not ad:
            ad_id = new_id()
            ad = {
                "id": ad_id,
                "accessory_code": code or ad_id[:8].upper(),
                "accessory_name": name or code,
                "category": "Import",
                "unit": "pcs",
                "status": "active",
                "created_at": now(),
                "updated_at": now(),
            }
            await db.accessories.insert_one(ad)
        accessory_master_cache[key] = ad
        return ad

    async def _resolve_or_create_parent_product(product_name: str, product_code: str, cmt_val: float, sell_val: float):
        nonlocal products_created
        # Prefer explicit product_code; fallback to case-insensitive product_name
        key = (product_code or f"name::{product_name.lower()}").strip()
        if key in product_cache:
            return product_cache[key]
        q = None
        if product_code:
            q = {"product_code": {"$regex": f"^{re.escape(product_code)}$", "$options": "i"}}
        elif product_name:
            q = {"product_name": {"$regex": f"^{re.escape(product_name)}$", "$options": "i"}}
        pd_doc = await db.products.find_one(q) if q else None
        if not pd_doc and product_name:
            pd_id = new_id()
            pd_doc = {
                "id": pd_id,
                "product_code": product_code or pd_id[:8].upper(),
                "product_name": product_name,
                "category": "Import",
                "cmt_price": cmt_val,
                "selling_price": sell_val,
                "status": "active",
                "photo_url": "",
                "created_at": now(),
                "updated_at": now(),
            }
            await db.products.insert_one(pd_doc)
            products_created += 1
        if pd_doc:
            product_cache[key] = pd_doc
        return pd_doc

    async def _resolve_or_create_variant(product_id: str, size: str, color: str, sku: str):
        nonlocal variants_created
        if not product_id:
            return None
        # Normalize key for dedup
        k = f"{product_id}::{(size or '').lower()}::{(color or '').lower()}::{(sku or '').lower()}"
        if k in variant_cache:
            return variant_cache[k]
        # Lookup existing variant; match on provided keys (size/color/sku)
        q = {"product_id": product_id}
        if size: q["size"] = size
        if color: q["color"] = color
        if sku: q["sku"] = sku
        vdoc = await db.product_variants.find_one(q) if (size or color or sku) else None
        if not vdoc and (size or color or sku):
            vid = new_id()
            vdoc = {
                "id": vid,
                "product_id": product_id,
                "size": size or "",
                "color": color or "",
                "sku": sku or "",
                "status": "active",
                "created_at": now(),
                "updated_at": now(),
            }
            await db.product_variants.insert_one(vdoc)
            variants_created += 1
        if vdoc:
            variant_cache[k] = vdoc
        return vdoc

    for po_num, group in po_groups.items():
        try:
            header = group["header"]
            vendor_name = header.get("vendor_name", "")
            customer_name = header.get("customer_name", "")

            # Look up or create vendor
            if vendor_name not in vendor_cache:
                vd = await db.garments.find_one(
                    {"garment_name": {"$regex": f"^{re.escape(vendor_name)}$", "$options": "i"}}
                )
                if not vd:
                    # Auto-create vendor
                    vid = new_id()
                    code = ''.join(c for c in vendor_name.lower() if c.isalnum())[:8]
                    vemail = f"vendor.{code}.{vid[:6]}@garment.com"
                    raw_pw = generate_password(10)
                    await db.users.insert_one({
                        "id": new_id(), "name": vendor_name, "email": vemail,
                        "password": hash_password(raw_pw), "role": "vendor",
                        "vendor_id": vid, "status": "active", "created_at": now(), "updated_at": now()
                    })
                    vd = {"id": vid, "garment_name": vendor_name, "garment_code": code,
                          "status": "active", "login_email": vemail, "created_at": now(), "updated_at": now()}
                    await db.garments.insert_one(vd)
                vendor_cache[vendor_name] = vd
            vd = vendor_cache[vendor_name]

            # Look up or create buyer
            buyer_id = None
            if customer_name:
                if customer_name not in buyer_cache:
                    bd = await db.buyers.find_one(
                        {"buyer_name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"}}
                    )
                    if not bd:
                        # Auto-create buyer
                        bid = new_id()
                        code = ''.join(c for c in customer_name.lower() if c.isalnum())[:8]
                        bemail = f"buyer.{code}.{bid[:6]}@garment.com"
                        raw_pw = generate_password(10)
                        await db.users.insert_one({
                            "id": new_id(), "name": customer_name, "email": bemail,
                            "password": hash_password(raw_pw), "role": "buyer",
                            "buyer_id": bid, "customer_name": customer_name,
                            "status": "active", "created_at": now(), "updated_at": now()
                        })
                        bd = {"id": bid, "buyer_name": customer_name, "buyer_code": code,
                              "status": "active", "login_email": bemail, "created_at": now(), "updated_at": now()}
                        await db.buyers.insert_one(bd)
                    buyer_cache[customer_name] = bd
                buyer_id = buyer_cache[customer_name]["id"]

            # Check if PO already exists
            existing_po = await db.production_pos.find_one({"po_number": po_num})

            if not existing_po:
                # Helper: resolve per-item prices with legacy fallback.
                def _resolve_prices(item):
                    cmt = item.get("cmt_price")
                    sell = item.get("selling_price")
                    legacy = item.get("unit_price")
                    cmt_val = float(cmt) if cmt not in (None, "") else (float(legacy) if legacy not in (None, "") else 0.0)
                    sell_val = float(sell) if sell not in (None, "") else 0.0
                    return cmt_val, sell_val

                # Aggregate totals at PO header level (selling when available, else cmt).
                total_qty = sum(int(float(it.get("qty", 0) or 0)) for it in group["items"])
                total_val = 0.0
                for it in group["items"]:
                    cmt_v, sell_v = _resolve_prices(it)
                    price_for_total = sell_v if sell_v > 0 else cmt_v
                    total_val += float(it.get("qty", 0) or 0) * price_for_total

                po_id = new_id()
                po_doc = {
                    "id": po_id,
                    "po_number": po_num,
                    "customer_name": customer_name,
                    "vendor_id": vd["id"],
                    "vendor_name": vendor_name,
                    "buyer_id": buyer_id,
                    "buyer_name": customer_name,
                    "po_date": header.get("po_date") or now().strftime('%Y-%m-%d'),
                    "deadline": header.get("deadline"),
                    "delivery_deadline": header.get("delivery_deadline"),
                    "total_qty": total_qty,
                    "total_value": total_val,
                    "status": "Draft",
                    "notes": header.get("notes", ""),
                    "created_by": user["name"],
                    "source": "smart_import",
                    "created_at": now(),
                    "updated_at": now()
                }
                await db.production_pos.insert_one(po_doc)

                # Create PO items (Phase 8.3: dedup parent product + variant per (size,color,sku))
                for item in group["items"]:
                    product_name = (item.get("product_name") or "").strip()
                    product_code = (item.get("product_code") or "").strip()
                    sku = (item.get("sku") or "").strip()
                    size = (item.get("size") or "").strip()
                    color = (item.get("color") or "").strip()
                    cmt_val, sell_val = _resolve_prices(item)

                    pd_doc = await _resolve_or_create_parent_product(product_name, product_code, cmt_val, sell_val)

                    # Create/find variant for this (size,color,sku)
                    variant_id = ""
                    if pd_doc and (size or color or sku):
                        vdoc = await _resolve_or_create_variant(pd_doc["id"], size, color, sku)
                        if vdoc:
                            variant_id = vdoc.get("id", "")

                    # Snapshot prices fall back to product master
                    if sell_val == 0.0 and pd_doc:
                        sell_val = float(pd_doc.get("selling_price", 0) or 0)
                    if cmt_val == 0.0 and pd_doc:
                        cmt_val = float(pd_doc.get("cmt_price", 0) or 0)

                    qty = int(float(item.get("qty", 1) or 1))
                    price_for_total = sell_val if sell_val > 0 else cmt_val
                    poi = {
                        "id": new_id(),
                        "po_id": po_id,
                        "po_number": po_num,
                        "product_id": pd_doc["id"] if pd_doc else new_id(),
                        "product_name": product_name,
                        "variant_id": variant_id,
                        "sku": sku or (pd_doc.get("product_code", "") if pd_doc else ""),
                        "size": size,
                        "color": color,
                        "qty": qty,
                        "serial_number": item.get("serial_number", ""),
                        # Canonical snapshot fields — required by invoice / margin logic.
                        "selling_price_snapshot": sell_val,
                        "cmt_price_snapshot": cmt_val,
                        # Keep legacy fields for backward-compat with older reports.
                        "unit_price": price_for_total,
                        "total_price": qty * price_for_total,
                        "notes": item.get("notes", ""),
                        "created_at": now()
                    }
                    await db.po_items.insert_one(poi)

                # Phase 8.1 — insert po_accessories records (dedup by accessory_code/name within this PO)
                seen_acc_keys = set()
                for acc in group["accessories"]:
                    acc_name = acc.get("accessory_name", "")
                    acc_code = acc.get("accessory_code", "")
                    qty_needed = int(float(acc.get("qty_needed", 0) or 0))
                    if qty_needed <= 0:
                        # Skip accessory rows without positive qty
                        continue
                    dedup_key = f"{acc_code or ''}::{acc_name.lower() if acc_name else ''}"
                    if dedup_key in seen_acc_keys:
                        continue
                    seen_acc_keys.add(dedup_key)
                    master = await _resolve_or_create_accessory_master(acc_name, acc_code)
                    acc_doc = {
                        "id": new_id(),
                        "po_id": po_id,
                        "accessory_id": master.get("id") if master else None,
                        "accessory_name": acc_name or (master.get("accessory_name", "") if master else ""),
                        "accessory_code": acc_code or (master.get("accessory_code", "") if master else ""),
                        "qty_needed": qty_needed,
                        "unit": acc.get("unit", "pcs") or "pcs",
                        "notes": acc.get("notes", ""),
                        "created_at": now(),
                    }
                    await db.po_accessories.insert_one(acc_doc)
                    accessories_created += 1

                created += 1
            else:
                updated += 1  # PO exists, count as "already exists"

        except Exception as e:
            logger.error(f"Error committing PO {po_num}: {e}", exc_info=True)
            errors.append(f"PO {po_num}: {str(e)}")

    return {
        "created": created,
        "updated": updated,
        "errors": errors,
        "accessories_created": accessories_created,
        "variants_created": variants_created,
        "products_created": products_created,
    }

async def commit_products(rows: list, user: dict, db) -> dict:
    from auth import log_activity
    created = 0; updated = 0; errors = []
    for row in rows:
        try:
            code = row.get("product_code", "").strip()
            if not code: continue
            existing = await db.products.find_one({"product_code": code})
            if existing:
                await db.products.update_one({"product_code": code}, {"$set": {
                    "product_name": row.get("product_name", existing.get("product_name", "")),
                    "category": row.get("category", existing.get("category", "")),
                    "cmt_price": float(row.get("cmt_price", existing.get("cmt_price", 0)) or 0),
                    "selling_price": float(row.get("selling_price", existing.get("selling_price", 0)) or 0),
                    "updated_at": now()
                }})
                updated += 1
            else:
                doc = {
                    "id": new_id(), "product_code": code,
                    "product_name": row.get("product_name", ""),
                    "category": row.get("category", ""),
                    "cmt_price": float(row.get("cmt_price", 0) or 0),
                    "selling_price": float(row.get("selling_price", 0) or 0),
                    "status": "active", "photo_url": "",
                    "created_at": now(), "updated_at": now()
                }
                await db.products.insert_one(doc)
                created += 1
        except Exception as e:
            errors.append(f"Produk {row.get('product_code', '?')}: {str(e)}")
    return {"created": created, "updated": updated, "errors": errors}

async def commit_accessories(rows: list, user: dict, db) -> dict:
    created = 0; updated = 0; errors = []
    for row in rows:
        try:
            code = row.get("accessory_code", "").strip()
            if not code: continue
            # Match against canonical + legacy field names so a re-import does not duplicate records.
            existing = await db.accessories.find_one(
                {"$or": [{"accessory_code": code}, {"code": code}]}
            )
            if existing:
                # Write canonical field names; legacy fields (if present) are cleaned up.
                update_set = {
                    **{k: row[k] for k in ["accessory_name", "category", "unit", "description"] if row.get(k)},
                    "updated_at": now()
                }
                # Upgrade legacy record in-place for consistency.
                if existing.get("name") and not existing.get("accessory_name"):
                    update_set["accessory_name"] = existing["name"]
                if existing.get("code") and not existing.get("accessory_code"):
                    update_set["accessory_code"] = existing["code"]
                op = {"$set": update_set}
                unset = {k: "" for k in ("name", "code") if k in existing}
                if unset:
                    op["$unset"] = unset
                await db.accessories.update_one({"id": existing["id"]}, op)
                updated += 1
            else:
                doc = {
                    "id": new_id(),
                    "accessory_code": code,
                    "accessory_name": row.get("accessory_name", ""),
                    "category": row.get("category", ""),
                    "unit": row.get("unit", "pcs"),
                    "description": row.get("description", ""),
                    "status": "active",
                    "created_at": now(), "updated_at": now()
                }
                await db.accessories.insert_one(doc)
                created += 1
        except Exception as e:
            errors.append(f"Aksesoris {row.get('accessory_code', '?')}: {str(e)}")
    return {"created": created, "updated": updated, "errors": errors}

async def commit_vendors(rows: list, user: dict, db) -> dict:
    created = 0; updated = 0; errors = []
    for row in rows:
        try:
            name = row.get("garment_name", "").strip()
            if not name: continue
            existing = await db.garments.find_one(
                {"garment_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
            )
            if existing:
                await db.garments.update_one({"id": existing["id"]}, {"$set": {
                    **{k: row[k] for k in ["contact_person","phone","email","address","garment_code"] if row.get(k)},
                    "updated_at": now()
                }})
                updated += 1
            else:
                vid = new_id()
                code = row.get("garment_code") or ''.join(c for c in name.lower() if c.isalnum())[:8]
                vemail = f"vendor.{code}.{vid[:6]}@garment.com"
                raw_pw = generate_password(10)
                await db.users.insert_one({
                    "id": new_id(), "name": name, "email": vemail,
                    "password": hash_password(raw_pw), "role": "vendor",
                    "vendor_id": vid, "status": "active", "created_at": now(), "updated_at": now()
                })
                doc = {
                    "id": vid, "garment_name": name, "garment_code": code,
                    "contact_person": row.get("contact_person", ""),
                    "phone": row.get("phone", ""), "email": row.get("email", ""),
                    "address": row.get("address", ""),
                    "status": "active", "login_email": vemail,
                    "created_at": now(), "updated_at": now()
                }
                await db.garments.insert_one(doc)
                created += 1
        except Exception as e:
            errors.append(f"Vendor {row.get('garment_name', '?')}: {str(e)}")
    return {"created": created, "updated": updated, "errors": errors}

async def commit_buyers(rows: list, user: dict, db) -> dict:
    created = 0; updated = 0; errors = []
    for row in rows:
        try:
            name = row.get("buyer_name", "").strip()
            if not name: continue
            existing = await db.buyers.find_one(
                {"buyer_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
            )
            if existing:
                await db.buyers.update_one({"id": existing["id"]}, {"$set": {
                    **{k: row[k] for k in ["contact_person","phone","email","address","buyer_code"] if row.get(k)},
                    "updated_at": now()
                }})
                updated += 1
            else:
                bid = new_id()
                code = row.get("buyer_code") or ''.join(c for c in name.lower() if c.isalnum())[:8]
                bemail = f"buyer.{code}.{bid[:6]}@garment.com"
                raw_pw = generate_password(10)
                await db.users.insert_one({
                    "id": new_id(), "name": name, "email": bemail,
                    "password": hash_password(raw_pw), "role": "buyer",
                    "buyer_id": bid, "customer_name": name,
                    "status": "active", "created_at": now(), "updated_at": now()
                })
                doc = {
                    "id": bid, "buyer_name": name, "buyer_code": code,
                    "contact_person": row.get("contact_person", ""),
                    "phone": row.get("phone", ""), "email": row.get("email", ""),
                    "address": row.get("address", ""),
                    "status": "active", "login_email": bemail,
                    "created_at": now(), "updated_at": now()
                }
                await db.buyers.insert_one(doc)
                created += 1
        except Exception as e:
            errors.append(f"Buyer {row.get('buyer_name', '?')}: {str(e)}")
    return {"created": created, "updated": updated, "errors": errors}

# ─── LLM Helper ──────────────────────────────────────────────────────────────
async def call_llm_text(prompt: str) -> str:
    """Call LLM for text-based tasks."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(500, "LLM API key tidak tersedia")
    
    chat = LlmChat(
        api_key=api_key,
        session_id=new_id(),
        system_message="Kamu adalah asisten untuk mapping dan ekstraksi data dokumen garmen ERP. Kembalikan HANYA JSON yang valid."
    ).with_model("openai", "gpt-4o-mini")
    
    response = await chat.send_message(UserMessage(text=prompt))
    return response

async def call_llm_vision(image_b64: str, prompt: str, mime_type: str = "image/jpeg") -> str:
    """Call vision LLM for image-based tasks."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(500, "LLM API key tidak tersedia")
    
    chat = LlmChat(
        api_key=api_key,
        session_id=new_id(),
        system_message="Kamu adalah sistem OCR cerdas untuk dokumen garmen ERP. Ekstrak data secara akurat."
    ).with_model("openai", "gpt-4o")
    
    image_content = ImageContent(image_base64=image_b64)
    response = await chat.send_message(UserMessage(text=prompt, file_contents=[image_content]))
    return response

def extract_json_from_llm(response: str) -> Any:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    # Remove markdown code blocks
    clean = re.sub(r'```(?:json)?\s*', '', response).replace('```', '').strip()
    # Find JSON content
    start = clean.find('{') if clean.find('{') != -1 else clean.find('[')
    if start == -1:
        raise ValueError("No JSON found in LLM response")
    # Find the matching end
    if clean[start] == '{':
        end = clean.rfind('}') + 1
    else:
        end = clean.rfind(']') + 1
    return json.loads(clean[start:end])

# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    data_type: str = Form(...)
):
    """Step 1: Upload file and get session_id."""
    user = await require_auth(request)
    
    # Validate data_type
    if data_type not in FIELD_DEFINITIONS:
        raise HTTPException(400, f"data_type tidak valid: {data_type}")
    
    # Validate file type
    filename = file.filename or ""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ""
    if ext not in ALLOWED_TYPES:
        raise HTTPException(400, f"Tipe file tidak didukung: .{ext}. Gunakan: xlsx, xls, csv, jpg, jpeg, png, webp, pdf")
    
    file_type = ALLOWED_TYPES[ext]
    file_bytes = await file.read()
    
    # Size limit: 20MB
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(400, "Ukuran file maksimal 20MB")
    
    session_id = new_id()
    save_session(session_id, file_bytes, ext, filename, data_type)
    
    return JSONResponse({
        "session_id": session_id,
        "filename": filename,
        "file_type": file_type,
        "data_type": data_type,
        "file_size": len(file_bytes),
        "message": f"File '{filename}' berhasil diupload"
    })

@router.post("/analyze")
async def analyze_file(request: Request):
    """Step 2: Analyze file structure and suggest column mapping (Excel/CSV)."""
    user = await require_auth(request)
    body = await request.json()
    session_id = body.get("session_id")
    data_type = body.get("data_type")
    use_llm = body.get("use_llm", True)  # NEW: can disable LLM
    
    if not session_id:
        raise HTTPException(400, "session_id wajib")
    
    file_bytes, meta = load_session(session_id)
    ext = meta["ext"]
    data_type = data_type or meta["data_type"]
    file_type = ALLOWED_TYPES.get(ext, "unknown")
    
    if file_type not in ("excel", "csv"):
        return JSONResponse({
            "file_type": file_type,
            "needs_ocr": True,
            "use_llm": use_llm,
            "data_type": data_type,
            "message": "File ini memerlukan proses OCR. Gunakan endpoint /ocr untuk melanjutkan."
        })
    
    # Parse file
    df = parse_file_to_df(file_bytes, ext)
    if df is None or df.empty:
        raise HTTPException(400, "File kosong atau tidak dapat dibaca")
    
    # Detect header row
    header_row = detect_header_row(df)
    headers = [str(h).strip() for h in df.iloc[header_row].tolist() if str(h).strip() and str(h).strip().lower() != 'nan']
    
    # Get sample data (3 rows after header)
    sample_rows = []
    for i in range(header_row + 1, min(header_row + 4, len(df))):
        row = df.iloc[i].tolist()
        sample_rows.append([str(v).strip() if v is not None and str(v).strip().lower() != 'nan' else None for v in row[:len(headers)]])
    
    total_data_rows = len(df) - header_row - 1
    
    # Fuzzy match
    mapping_suggestions = fuzzy_match_columns(headers, data_type)
    
    # Identify low-confidence columns for LLM (only relevant if use_llm=True)
    low_conf = [h for h, m in mapping_suggestions.items() if m["confidence"] < 70 and m["field"] is None]
    
    # Check if preset exists
    db = get_db()
    col_signature = sorted([h.lower() for h in headers])
    preset = await db.import_presets.find_one({
        "data_type": data_type,
        "columns_signature": col_signature
    }, {"_id": 0})
    
    preset_match = None
    if preset:
        preset_match = {"preset_id": preset["id"], "preset_name": preset["name"], "mapping": preset["mapping"]}
        # Override suggestions with preset mapping
        for header, field in preset["mapping"].items():
            if header in mapping_suggestions:
                mapping_suggestions[header] = {"field": field, "confidence": 100, "method": "preset"}
    
    return JSONResponse({
        "file_type": file_type,
        "data_type": data_type,
        "use_llm": use_llm,
        "headers": headers,
        "header_row": header_row,
        "sample_rows": sample_rows,
        "total_rows": max(0, total_data_rows),
        "mapping_suggestions": mapping_suggestions,
        "low_confidence_headers": low_conf,
        "needs_llm_enhance": use_llm and len(low_conf) > 0,
        "preset_match": preset_match,
        "available_fields": {k: {"label": v["label"], "required": v["required"], "type": v["type"]} 
                             for k, v in FIELD_DEFINITIONS.get(data_type, {}).items()}
    })

@router.post("/enhance-mapping")
async def enhance_mapping_with_llm(request: Request):
    """Use LLM to improve mapping for ambiguous columns."""
    user = await require_auth(request)
    body = await request.json()
    session_id = body.get("session_id")
    headers = body.get("headers", [])
    data_type = body.get("data_type", "production_po")
    sample_rows = body.get("sample_rows", [])
    
    if not headers:
        raise HTTPException(400, "headers wajib")
    
    try:
        prompt = get_llm_mapping_prompt(headers, data_type, sample_rows)
        response = await call_llm_text(prompt)
        llm_mapping = extract_json_from_llm(response)
        
        # Validate that LLM returns valid fields
        valid_fields = set(FIELD_DEFINITIONS.get(data_type, {}).keys()) | {None}
        enhanced = {}
        for header, field in llm_mapping.items():
            if field and field not in valid_fields:
                field = None
            enhanced[header] = {
                "field": field,
                "confidence": 85 if field else 0,
                "method": "llm"
            }
        
        return JSONResponse({"enhanced_mapping": enhanced})
    except Exception as e:
        logger.error(f"LLM enhance error: {e}", exc_info=True)
        raise HTTPException(500, f"LLM error: {str(e)}")

@router.post("/ocr")
async def extract_with_ocr(request: Request):
    """Step 2 (for images/PDF): Extract structured data using Vision LLM or text-only (no-LLM mode)."""
    user = await require_auth(request)
    body = await request.json()
    session_id = body.get("session_id")
    data_type = body.get("data_type")
    use_llm = body.get("use_llm", True)  # NEW: can disable LLM
    
    if not session_id:
        raise HTTPException(400, "session_id wajib")
    
    file_bytes, meta = load_session(session_id)
    ext = meta["ext"]
    data_type = data_type or meta["data_type"]
    file_type = ALLOWED_TYPES.get(ext, "unknown")

    # ── No-LLM mode ─────────────────────────────────────────────────────────
    if not use_llm:
        if file_type == "image":
            raise HTTPException(400, "File gambar memerlukan Mode AI untuk OCR. Aktifkan 'Gunakan AI' atau upload file Excel/CSV.")
        
        if file_type == "pdf":
            # Text-only extraction from PDF → treat extracted text as tabular data
            bio = BytesIO(file_bytes)
            extracted_rows = []
            warnings = []
            try:
                with pdfplumber.open(bio) as pdf:
                    for page_num, page in enumerate(pdf.pages):
                        # Try tables first
                        tables = page.extract_tables()
                        for table in tables:
                            if not table: continue
                            # Detect header row in table
                            header_row_idx = 0
                            headers = [str(c).strip() if c else "" for c in (table[0] or [])]
                            # Skip completely empty tables
                            if not any(headers):
                                continue
                            # Map headers to fields using fuzzy matching
                            col_map = fuzzy_match_columns(headers, data_type)
                            for row in table[1:]:
                                row_dict = {}
                                for col_idx, header in enumerate(headers):
                                    mapped = col_map.get(header, {}).get("field")
                                    if mapped and col_idx < len(row):
                                        val = str(row[col_idx]).strip() if row[col_idx] else None
                                        if val and val.lower() not in ('none', 'nan', ''):
                                            fields = FIELD_DEFINITIONS.get(data_type, {})
                                            field_info = fields.get(mapped, {})
                                            if field_info.get("type") == "date":
                                                val = parse_date(val)
                                            elif field_info.get("type") == "number":
                                                val = parse_number(val)
                                            if val is not None:
                                                row_dict[mapped] = val
                                non_empty = sum(1 for v in row_dict.values() if v is not None)
                                if non_empty > 0:
                                    extracted_rows.append(row_dict)
                        
                        # If no tables found, try line-by-line text
                        if not tables:
                            text = page.extract_text() or ""
                            if text.strip():
                                warnings.append(f"Halaman {page_num+1}: Tidak ada tabel terdeteksi, menggunakan teks mentah")
            except Exception as e:
                raise HTTPException(400, f"Gagal membaca PDF: {str(e)}")
            
            if not extracted_rows:
                raise HTTPException(400, 
                    "PDF tidak memiliki tabel terstruktur yang dapat dibaca tanpa AI. "
                    "Coba aktifkan 'Mode AI' untuk ekstraksi cerdas, atau gunakan file Excel/CSV.")
            
            return JSONResponse({
                "data_type": data_type,
                "rows": extracted_rows,
                "total": len(extracted_rows),
                "warnings": warnings,
                "mode": "text_only",
                "message": f"Berhasil mengekstrak {len(extracted_rows)} baris dari tabel PDF (tanpa AI)"
            })
        
        raise HTTPException(400, f"Tipe file '{file_type}' tidak didukung tanpa Mode AI")

    # ── LLM mode (original) ──────────────────────────────────────────────────
    prompt = get_ocr_prompt(data_type)
    extracted_rows = []
    warnings = []
    
    try:
        if file_type == "image":
            # Encode image as base64
            image_b64 = base64.b64encode(file_bytes).decode()
            mime = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
            response = await call_llm_vision(image_b64, prompt, mime)
            extracted_rows = extract_json_from_llm(response)
            if not isinstance(extracted_rows, list):
                extracted_rows = [extracted_rows]
        
        elif file_type == "pdf":
            # Try text extraction first
            bio = BytesIO(file_bytes)
            text_pages = []
            try:
                with pdfplumber.open(bio) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            text_pages.append(text)
            except Exception as e:
                warnings.append(f"Text extraction partial: {str(e)}")
            
            full_text = "\n\n".join(text_pages)
            
            if len(full_text.strip()) > 100:
                # Use text LLM
                text_prompt = f"{prompt}\n\nTEKS DOKUMEN:\n{full_text[:8000]}"
                response = await call_llm_text(text_prompt)
                extracted_rows = extract_json_from_llm(response)
                if not isinstance(extracted_rows, list):
                    extracted_rows = [extracted_rows]
            else:
                # Fallback: convert first page to image using PDF rendering
                warnings.append("PDF text extraction minimal, menggunakan vision...")
                try:
                    bio.seek(0)
                    with pdfplumber.open(bio) as pdf:
                        if pdf.pages:
                            page = pdf.pages[0]
                            img = page.to_image(resolution=150)
                            img_bytes = BytesIO()
                            img.original.save(img_bytes, format="PNG")
                            image_b64 = base64.b64encode(img_bytes.getvalue()).decode()
                            response = await call_llm_vision(image_b64, prompt, "image/png")
                            extracted_rows = extract_json_from_llm(response)
                            if not isinstance(extracted_rows, list):
                                extracted_rows = [extracted_rows]
                except Exception as e2:
                    warnings.append(f"Vision fallback failed: {str(e2)}")
                    raise HTTPException(400, "PDF tidak dapat diproses. Coba upload sebagai gambar.")
        
        # Clean up null values
        clean_rows = []
        for row in extracted_rows:
            if isinstance(row, dict):
                clean = {k: v for k, v in row.items() if v is not None and str(v).strip() not in ('', 'null', 'None')}
                if clean:
                    clean_rows.append(clean)
        
        return JSONResponse({
            "data_type": data_type,
            "rows": clean_rows,
            "total": len(clean_rows),
            "warnings": warnings,
            "mode": "llm",
            "message": f"Berhasil mengekstrak {len(clean_rows)} baris data"
        })
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OCR error: {e}", exc_info=True)
        raise HTTPException(500, f"OCR error: {str(e)}")

@router.post("/preview")
async def preview_import(request: Request):
    """Step 3: Preview parsed data with validation and auto-create detection."""
    user = await require_auth(request)
    body = await request.json()
    session_id = body.get("session_id")
    mapping = body.get("mapping", {})  # {header_col: field_name}
    data_type = body.get("data_type", "production_po")
    page = int(body.get("page", 1))
    per_page = int(body.get("per_page", 50))
    # For OCR, rows may be provided directly
    direct_rows = body.get("rows")
    
    db = get_db()
    
    if direct_rows is not None:
        # OCR path: rows already extracted
        all_rows = direct_rows
    else:
        # Excel/CSV path
        if not session_id:
            raise HTTPException(400, "session_id wajib")
        file_bytes, meta = load_session(session_id)
        ext = meta["ext"]
        data_type = data_type or meta["data_type"]
        
        if not mapping:
            raise HTTPException(400, "mapping wajib untuk Excel/CSV")
        
        # Parse file with mapping
        df = parse_file_to_df(file_bytes, ext)
        header_row = detect_header_row(df)
        all_rows = apply_mapping_to_df(df, header_row, mapping, data_type)
    
    # Validate and detect auto-creates
    processed_rows = await detect_auto_creates(all_rows, data_type, db)
    
    # Summary
    total = len(processed_rows)
    valid_count = sum(1 for r in processed_rows if r["_status"] != "error")
    error_count = sum(1 for r in processed_rows if r["_status"] == "error")
    new_count = sum(1 for r in processed_rows if r["_status"] == "valid")
    exists_count = sum(1 for r in processed_rows if r["_status"] == "exists")
    
    # Count auto-creates
    auto_create_summary = {}
    for row in processed_rows:
        for ac in row.get("_auto_creates", []):
            if ac["status"] == "new":
                etype = ac["entity"]
                auto_create_summary[etype] = auto_create_summary.get(etype, 0) + 1
    # Deduplicate by name
    seen_creates = {}
    for row in processed_rows:
        for ac in row.get("_auto_creates", []):
            if ac["status"] == "new":
                key = f"{ac['entity']}:{ac['name']}"
                seen_creates[key] = ac
    dedupe_creates = {}
    for ac in seen_creates.values():
        etype = ac["entity"]
        dedupe_creates[etype] = dedupe_creates.get(etype, 0) + 1
    
    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    page_rows = processed_rows[start:end]
    
    # Add row_index
    for i, row in enumerate(page_rows):
        row["_row_index"] = start + i
    
    return JSONResponse({
        "rows": serialize_doc(page_rows),
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "summary": {
            "total": total,
            "valid": valid_count,
            "errors": error_count,
            "new_records": new_count,
            "exists_records": exists_count,
            "auto_creates": dedupe_creates
        }
    })

@router.post("/commit")
async def commit_import(request: Request):
    """Step 4: Execute the import with edited rows."""
    user = await require_auth(request)
    if not check_role(user, ["admin"]):
        raise HTTPException(403, "Hanya admin yang dapat melakukan import")
    
    body = await request.json()
    session_id = body.get("session_id")
    mapping = body.get("mapping", {})
    data_type = body.get("data_type", "production_po")
    edited_rows = body.get("edited_rows", {})  # {row_index: {field: value}}
    confirmed = body.get("confirmed", False)
    direct_rows = body.get("rows")  # For OCR path
    
    if not confirmed:
        raise HTTPException(400, "Konfirmasi diperlukan (confirmed: true)")
    
    db = get_db()
    
    # Get rows
    if direct_rows is not None:
        all_rows = direct_rows
    else:
        if not session_id:
            raise HTTPException(400, "session_id wajib")
        file_bytes, meta = load_session(session_id)
        ext = meta["ext"]
        df = parse_file_to_df(file_bytes, ext)
        header_row = detect_header_row(df)
        all_rows = apply_mapping_to_df(df, header_row, mapping, data_type)
    
    # Apply edits
    for idx_str, edits in edited_rows.items():
        idx = int(idx_str)
        if 0 <= idx < len(all_rows):
            all_rows[idx].update(edits)
    
    # Skip rows with _skip flag
    rows_to_import = [r for r in all_rows if not r.get("_skip")]
    
    # Commit by type
    if data_type == "production_po":
        result = await commit_production_po(rows_to_import, user, db)
    elif data_type == "products":
        result = await commit_products(rows_to_import, user, db)
    elif data_type == "accessories":
        result = await commit_accessories(rows_to_import, user, db)
    elif data_type == "vendors":
        result = await commit_vendors(rows_to_import, user, db)
    elif data_type == "buyers":
        result = await commit_buyers(rows_to_import, user, db)
    else:
        raise HTTPException(400, f"data_type tidak dikenal: {data_type}")
    
    # Log activity
    from auth import log_activity
    await log_activity(user["id"], user["name"], "Import", "SmartImport",
                       f"Smart Import {DATA_TYPE_LABELS.get(data_type, data_type)}: {result['created']} created, {result['updated']} updated")
    
    # Clean up session
    try:
        meta_path = f"{IMPORT_TMP_DIR}/{session_id}.meta.json"
        file_path = glob_session_file(session_id)
        if os.path.exists(meta_path): os.remove(meta_path)
        if file_path and os.path.exists(file_path): os.remove(file_path)
    except:
        pass
    
    return JSONResponse({
        "success": True,
        "data_type": data_type,
        "data_type_label": DATA_TYPE_LABELS.get(data_type, data_type),
        **result,
        "message": f"Import selesai: {result['created']} record baru, {result['updated']} sudah ada"
    })

def glob_session_file(session_id: str) -> Optional[str]:
    for ext in ALLOWED_TYPES.keys():
        path = f"{IMPORT_TMP_DIR}/{session_id}.{ext}"
        if os.path.exists(path):
            return path
    return None

# ─── Preset CRUD ─────────────────────────────────────────────────────────────

@router.get("/presets")
async def get_presets(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get("data_type"):
        query["data_type"] = sp["data_type"]
    presets = await db.import_presets.find(query, {"_id": 0}).sort("created_at", -1).to_list(None)
    return JSONResponse(serialize_doc(presets))

@router.post("/presets")
async def create_preset(request: Request):
    user = await require_auth(request)
    if not check_role(user, ["admin"]):
        raise HTTPException(403, "Hanya admin yang dapat menyimpan preset")
    db = get_db()
    body = await request.json()
    
    name = body.get("name", "").strip()
    data_type = body.get("data_type", "")
    mapping = body.get("mapping", {})
    columns_signature = sorted([k.lower() for k in mapping.keys()])
    
    if not name or not data_type or not mapping:
        raise HTTPException(400, "name, data_type, dan mapping wajib")
    
    preset = {
        "id": new_id(),
        "name": name,
        "data_type": data_type,
        "mapping": mapping,
        "columns_signature": columns_signature,
        "description": body.get("description", ""),
        "created_by": user["name"],
        "created_at": now(),
        "updated_at": now()
    }
    await db.import_presets.insert_one(preset)
    return JSONResponse(serialize_doc(preset), status_code=201)

@router.put("/presets/{preset_id}")
async def update_preset(preset_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ["admin"]):
        raise HTTPException(403, "Hanya admin yang dapat mengubah preset")
    db = get_db()
    body = await request.json()
    body.pop("_id", None); body.pop("id", None)
    if "mapping" in body:
        body["columns_signature"] = sorted([k.lower() for k in body["mapping"].keys()])
    body["updated_at"] = now()
    await db.import_presets.update_one({"id": preset_id}, {"$set": body})
    preset = await db.import_presets.find_one({"id": preset_id}, {"_id": 0})
    if not preset:
        raise HTTPException(404, "Preset tidak ditemukan")
    return JSONResponse(serialize_doc(preset))

@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ["admin"]):
        raise HTTPException(403, "Hanya admin yang dapat menghapus preset")
    db = get_db()
    await db.import_presets.delete_one({"id": preset_id})
    return JSONResponse({"success": True})

@router.get("/fields/{data_type}")
async def get_field_definitions(data_type: str, request: Request):
    """Get field definitions for a data type."""
    await require_auth(request)
    if data_type not in FIELD_DEFINITIONS:
        raise HTTPException(404, f"data_type tidak ditemukan: {data_type}")
    return JSONResponse({
        "data_type": data_type,
        "label": DATA_TYPE_LABELS.get(data_type, data_type),
        "fields": {k: {"label": v["label"], "required": v["required"], "type": v["type"]}
                   for k, v in FIELD_DEFINITIONS[data_type].items()}
    })
