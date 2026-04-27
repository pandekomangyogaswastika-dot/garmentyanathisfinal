
import { useState, useEffect } from 'react';
import { Plus, Eye, Pencil, Trash2, X, XCircle } from 'lucide-react';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import POWorkflowIndicator from './POWorkflowIndicator';
import FileAttachmentPanel from './FileAttachmentPanel';
import SearchableSelect from './SearchableSelect';
import ImportExportPanel from './ImportExportPanel';
import { apiGet, apiPost, apiPut, apiDelete, apiFetch } from '../../lib/api';

const STATUS_OPTIONS = ['Draft', 'Confirmed', 'Distributed', 'In Production', 'Completed', 'Closed'];
const CLOSE_REASONS = ['Under Production', 'Over Production', 'Price Adjustment', 'Customer Agreement', 'Other'];

export default function ProductionPOModule({ userRole, hasPerm = () => false }) {
  const [pos, setPOs] = useState([]);
  const [products, setProducts] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [buyers, setBuyers] = useState([]);
  const [accessories, setAccessories] = useState([]);
  const [variants, setVariants] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [showCloseModal, setShowCloseModal] = useState(false);
  const [editData, setEditData] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [closeTargetPO, setCloseTargetPO] = useState(null);
  const [filterStatus, setFilterStatus] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [closeForm, setCloseForm] = useState({ close_reason: CLOSE_REASONS[0], close_notes: '' });
  const [refetchKey, setRefetchKey] = useState(0);
  const [form, setForm] = useState({ po_number: '', customer_name: '', buyer_id: '', vendor_id: '', po_date: '', deadline: '', delivery_deadline: '', notes: '', items: [], po_accessories: [] });

  const isSuperAdmin = userRole === 'superadmin';
  const canEdit = ['superadmin', 'admin'].includes(userRole) || hasPerm('po.edit');
  const canCreate = userRole === 'superadmin' || hasPerm('production_po.create') || hasPerm('po.create');
  const canDelete = ['superadmin', 'admin'].includes(userRole) || hasPerm('po.delete');

  useEffect(() => { fetchProducts(); fetchVendors(); fetchBuyers(); fetchAccessories(); }, []);

  const refetchPOs = () => setRefetchKey((k) => k + 1);

  // Server-paginated fetcher (Phase 10C)
  const posFetcher = async ({ page, per_page, sort_by, sort_dir, search }) => {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('per_page', String(per_page));
    if (sort_by) params.set('sort_by', sort_by);
    if (sort_dir) params.set('sort_dir', sort_dir);
    if (search) params.set('search', search);
    if (filterStatus) params.set('status', filterStatus);
    const env = await apiGet(`/production-pos?${params.toString()}`);
    // Keep `pos` array around so `expandedRowRender` can show item details
    const items = Array.isArray(env?.items) ? env.items : (Array.isArray(env) ? env : []);
    setPOs(items);
    return env;
  };

  const fetchBuyers = async () => {
    try {
      const data = await apiGet('/buyers');
      setBuyers(Array.isArray(data) ? data.filter(b => b.status === 'active') : []);
    } catch (e) { console.error(e); }
  };

  const fetchAccessories = async () => {
    try {
      const data = await apiGet('/accessories');
      setAccessories(Array.isArray(data) ? data.filter(a => a.status === 'active') : []);
    } catch (e) { console.error(e); }
  };

  const fetchVendors = async () => {
    try {
      const data = await apiGet('/garments');
      setVendors(Array.isArray(data) ? data.filter(g => g.status === 'active') : []);
    } catch (e) { setVendors([]); }
  };

  const fetchProducts = async () => {
    try {
      const data = await apiGet('/products');
      setProducts(Array.isArray(data) ? data.filter(p => p.status === 'active') : []);
    } catch (e) { setProducts([]); }
  };

  const fetchVariantsForProduct = async (productId) => {
    if (!productId) { setVariants([]); return; }
    try {
      const data = await apiGet(`/product-variants?product_id=${productId}`);
      setVariants(Array.isArray(data) ? data : []);
    } catch (e) { setVariants([]); }
  };

  const openCreate = () => {
    setEditData(null);
    setForm({ po_number: '', customer_name: '', buyer_id: '', vendor_id: '', po_date: new Date().toISOString().split('T')[0], deadline: '', delivery_deadline: '', notes: '', items: [], po_accessories: [] });
    setShowModal(true);
  };

  const addItem = () => {
    setForm(f => ({ ...f, items: [...f.items, { product_id: '', product_name: '', variant_id: '', size: '', color: '', sku: '', qty: '', serial_number: '', selling_price_snapshot: '', cmt_price_snapshot: '' }] }));
  };

  const addAccessoryItem = () => {
    setForm(f => ({ ...f, po_accessories: [...(f.po_accessories || []), { accessory_id: '', accessory_name: '', accessory_code: '', qty_needed: '', unit: 'pcs', notes: '' }] }));
  };

  const removeAccessoryItem = (idx) => {
    setForm(f => ({ ...f, po_accessories: (f.po_accessories || []).filter((_, i) => i !== idx) }));
  };

  const updateAccessoryItem = (idx, field, value) => {
    const items = [...(form.po_accessories || [])];
    items[idx] = { ...items[idx], [field]: value };
    if (field === 'accessory_id') {
      const acc = accessories.find(a => a.id === value);
      if (acc) {
        // Support both canonical (accessory_name/accessory_code) and legacy (name/code) shapes.
        items[idx].accessory_name = acc.accessory_name || acc.name || '';
        items[idx].accessory_code = acc.accessory_code || acc.code || '';
        items[idx].unit = acc.unit || 'pcs';
      }
    }
    setForm(f => ({ ...f, po_accessories: items }));
  };

  const removeItem = (idx) => {
    setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  };

  const updateItem = async (idx, field, value) => {
    const newItems = [...form.items];
    newItems[idx] = { ...newItems[idx], [field]: value };
    if (field === 'product_id') {
      const product = products.find(p => p.id === value);
      newItems[idx].product_name = product?.product_name || '';
      newItems[idx].cmt_price_snapshot = product?.cmt_price || '';
      newItems[idx].selling_price_snapshot = product?.selling_price || '';
      newItems[idx].variant_id = ''; newItems[idx].size = ''; newItems[idx].color = ''; newItems[idx].sku = '';
      if (value) {
        try {
          const varData = await apiGet(`/product-variants?product_id=${value}`);
          setVariants(Array.isArray(varData) ? varData : []);
        } catch (e) { setVariants([]); }
      }
    }
    if (field === 'variant_id' && value) {
      const variant = variants.find(v => v.id === value);
      if (variant) { newItems[idx].size = variant.size; newItems[idx].color = variant.color; newItems[idx].sku = variant.sku; }
    }
    setForm(f => ({ ...f, items: newItems }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.items.length === 0) { alert('Tambahkan minimal 1 item produk'); return; }
    // Phase 8.6 — Send items + po_accessories together in the body (PUT supports delta update)
    const itemsPayload = form.items.map(it => ({
      ...it,
      qty: Number(it.qty),
      selling_price_snapshot: Number(it.selling_price_snapshot) || 0,
      cmt_price_snapshot: Number(it.cmt_price_snapshot) || 0,
    }));
    const accPayload = (form.po_accessories || [])
      .filter(a => a.accessory_name || a.accessory_id)
      .map(a => ({ ...a, qty_needed: Number(a.qty_needed) || 0 }));
    const payload = { ...form, items: itemsPayload, po_accessories: accPayload };
    try {
      const data = editData
        ? await apiPut(`/production-pos/${editData.id}`, payload)
        : await apiPost('/production-pos', payload);
      // For create path, backend doesn't accept po_accessories in POST; keep legacy secondary call
      if (!editData && accPayload.length > 0) {
        try {
          await apiPost('/po-accessories', { po_id: data.id, items: accPayload });
        } catch (e) { /* non-critical */ }
      }
      setShowModal(false);
      refetchPOs();
    } catch (err) { alert(err.message || 'Gagal menyimpan PO'); }
  };

  const openDetail = async (row) => {
    try {
      const data = await apiGet(`/production-pos/${row.id}`);
      setDetailData(data);
      setShowDetail(true);
    } catch (e) { alert(e.message || 'Gagal memuat detail'); }
  };

  const openEdit = async (row) => {
    // Phase 8.6 — Load full PO detail (items + po_accessories) so user can edit everything.
    try {
      const [poData, statsData] = await Promise.all([
        apiGet(`/production-pos/${row.id}`),
        apiGet(`/po-items-produced?po_id=${row.id}`),
      ]);
      const statsById = {};
      (Array.isArray(statsData) ? statsData : []).forEach(s => { statsById[s.id] = s; });
      // fetch variants list used by each item (for variant dropdown options)
      const allVariants = [];
      for (const it of (poData.items || [])) {
        if (it.product_id) {
          try {
            const vdata = await apiGet(`/product-variants?product_id=${it.product_id}`);
            if (Array.isArray(vdata)) allVariants.push(...vdata);
          } catch (e) { /* ignore */ }
        }
      }
      // dedup variants by id
      const variantMap = new Map();
      allVariants.forEach(v => { if (v && v.id) variantMap.set(v.id, v); });
      setVariants(Array.from(variantMap.values()));

      const mappedItems = (poData.items || []).map(it => {
        const st = statsById[it.id] || {};
        const sent_to_vendor = st.total_shipped || 0; // actually this is buyer; we also need vendor sent
        return {
          id: it.id,
          product_id: it.product_id || '',
          product_name: it.product_name || '',
          variant_id: it.variant_id || '',
          size: it.size || '',
          color: it.color || '',
          sku: it.sku || '',
          qty: it.qty || '',
          serial_number: it.serial_number || '',
          selling_price_snapshot: it.selling_price_snapshot || '',
          cmt_price_snapshot: it.cmt_price_snapshot || '',
          // guardrail hints
          __has_shipments: (st.total_shipped || 0) > 0 || (st.total_produced || 0) > 0,
          __min_qty: Math.max(st.total_shipped || 0, st.total_produced || 0),
        };
      });
      // Additionally fetch po-items to discover vendor-ship amount per item
      const piData = await apiGet(`/po-items?po_id=${row.id}`);
      const vendorSentById = {};
      (Array.isArray(piData) ? piData : []).forEach(pi => { vendorSentById[pi.id] = pi.total_sent_to_vendor || 0; });
      mappedItems.forEach(m => {
        const vendorSent = vendorSentById[m.id] || 0;
        if (vendorSent > 0) m.__has_shipments = true;
        m.__min_qty = Math.max(m.__min_qty || 0, vendorSent);
      });

      setEditData(poData);
      setForm({
        po_number: poData.po_number || '',
        customer_name: poData.customer_name || '',
        buyer_id: poData.buyer_id || '',
        vendor_id: poData.vendor_id || '',
        po_date: poData.po_date ? new Date(poData.po_date).toISOString().split('T')[0] : '',
        deadline: poData.deadline ? new Date(poData.deadline).toISOString().split('T')[0] : '',
        delivery_deadline: poData.delivery_deadline ? new Date(poData.delivery_deadline).toISOString().split('T')[0] : '',
        status: poData.status || 'Draft',
        notes: poData.notes || '',
        items: mappedItems,
        po_accessories: (poData.po_accessories || []).map(a => ({
          id: a.id,
          accessory_id: a.accessory_id || '',
          accessory_name: a.accessory_name || '',
          accessory_code: a.accessory_code || '',
          qty_needed: a.qty_needed || '',
          unit: a.unit || 'pcs',
          notes: a.notes || '',
        })),
      });
      setShowModal(true);
    } catch (err) {
      alert('Gagal memuat detail PO: ' + (err.message || err));
    }
  };

  const handleClosePO = async (e) => {
    e.preventDefault();
    try {
      await apiPost(`/production-pos/${closeTargetPO.id}/close`, closeForm);
      setShowCloseModal(false);
      refetchPOs();
    } catch (e) { alert(e.message || 'Gagal menutup PO'); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/production-pos/${confirmDelete.id}`);
      setConfirmDelete(null);
      refetchPOs();
    } catch (e) { alert(e.message || 'Gagal menghapus PO'); }
  };

  const [expandedPOs, setExpandedPOs] = useState({});
  const togglePO = (id) => setExpandedPOs(prev => ({ ...prev, [id]: !prev[id] }));

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';
  const fmt = (v) => v ? 'Rp ' + Number(v).toLocaleString('id-ID') : 'Rp 0';

  const columns = [
    { key: 'po_number', label: 'No. PO / Identifikasi', render: (v, row) => (
      <div>
        <span className="font-bold text-blue-700">{v}</span>
        <div className="text-xs text-slate-400 mt-0.5">
          {row.vendor_name ? <span className="text-purple-600">{row.vendor_name}</span> : <span>-</span>}
          {' · '}{fmtDate(row.po_date || row.created_at)}
        </div>
        {(row.serial_numbers || []).length > 0 && (
          <div className="text-xs text-emerald-600 mt-0.5 flex flex-wrap gap-1">
            {row.serial_numbers.slice(0, 3).map((sn, i) => (
              <span key={i} className="bg-emerald-50 px-1.5 py-0.5 rounded font-mono">{sn}</span>
            ))}
            {row.serial_numbers.length > 3 && <span className="text-slate-400">+{row.serial_numbers.length - 3} lagi</span>}
          </div>
        )}
      </div>
    )},
    { key: 'customer_name', label: 'Customer' },
    { key: 'item_count', label: 'Items', render: (v, row) => (
      <button onClick={(e) => { e.stopPropagation(); togglePO(row.id); }}
        className="flex items-center gap-1 px-2 py-0.5 bg-slate-100 text-slate-700 text-xs rounded-full font-medium hover:bg-blue-100 hover:text-blue-700 transition-colors">
        {expandedPOs[row.id] ? '▼' : '▶'} {v || 0} item
      </button>
    )},
    { key: 'total_qty', label: 'Total Qty', render: (v) => v?.toLocaleString('id-ID') },
    { key: 'deadline', label: 'Deadline Prod.', render: (v) => {
      if (!v) return '-';
      const isOverdue = new Date(v) < new Date();
      return <span className={isOverdue ? 'text-red-600 font-medium' : ''}>{fmtDate(v)}</span>;
    }},
    { key: 'delivery_deadline', label: 'Deadline Kirim', render: (v) => {
      if (!v) return '-';
      const isOverdue = new Date(v) < new Date();
      return <span className={isOverdue ? 'text-orange-600 font-medium' : 'text-slate-600'}>{fmtDate(v)}</span>;
    }},
    { key: 'status', label: 'Status / Workflow', render: (v, row) => (
      <div className="space-y-1.5">
        <StatusBadge status={v} />
        <POWorkflowIndicator status={v} compact={true} />
      </div>
    )},
    { key: 'created_by', label: 'Dibuat' },
    { key: 'actions', label: 'Aksi', render: (_, row) => (
      <div className="flex items-center gap-1">
        <button onClick={() => openDetail(row)} className="p-1.5 rounded hover:bg-blue-50 text-blue-600" title="Detail"><Eye className="w-4 h-4" /></button>
        {canEdit && (
          <>
            <button onClick={() => openEdit(row)} className="p-1.5 rounded hover:bg-amber-50 text-amber-600" title="Edit"><Pencil className="w-4 h-4" /></button>
            {!['Closed', 'Completed'].includes(row.status) && (
              <button onClick={() => { setCloseTargetPO(row); setCloseForm({ close_reason: CLOSE_REASONS[0], close_notes: '' }); setShowCloseModal(true); }}
                className="p-1.5 rounded hover:bg-orange-50 text-orange-500 text-xs" title="Tutup PO">Close</button>
            )}
            <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-500" title="Hapus"><Trash2 className="w-4 h-4" /></button>
          </>
        )}
      </div>
    )}
  ];

  // Custom expandable row render for DataTable
  const expandedRowRender = (row) => {
    if (!expandedPOs[row.id] || !row.items || row.items.length === 0) return null;
    return (
      <div className="bg-amber-50/30 border-t border-amber-100 px-6 py-3">
        <p className="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wide">Detail Item PO</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-amber-200">
                <th className="text-left py-1.5 pr-3 text-amber-700 font-semibold">Serial/Batch</th>
                <th className="text-left py-1.5 pr-3 text-slate-500 font-semibold">SKU</th>
                <th className="text-left py-1.5 pr-3 text-slate-500 font-semibold">Produk</th>
                <th className="text-left py-1.5 pr-3 text-slate-500 font-semibold">Size</th>
                <th className="text-left py-1.5 pr-3 text-slate-500 font-semibold">Warna</th>
                <th className="text-right py-1.5 text-slate-500 font-semibold">Qty</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-amber-100">
              {row.items.map(item => (
                <tr key={item.id} className="hover:bg-amber-50">
                  <td className="py-1.5 pr-3 font-mono text-amber-700 font-semibold">{item.serial_number || <span className="text-slate-300">—</span>}</td>
                  <td className="py-1.5 pr-3 font-mono text-blue-700">{item.sku || '-'}</td>
                  <td className="py-1.5 pr-3 text-slate-700">{item.product_name}</td>
                  <td className="py-1.5 pr-3 text-slate-500">{item.size || '-'}</td>
                  <td className="py-1.5 pr-3 text-slate-500">{item.color || '-'}</td>
                  <td className="py-1.5 text-right font-bold text-slate-700">{(item.qty || 0).toLocaleString('id-ID')} pcs</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div><h1 className="text-2xl font-bold text-slate-800">Production PO</h1><p className="text-slate-500 text-sm mt-1">Kelola pesanan produksi multi-item dengan varian produk</p></div>
        {isSuperAdmin && <span className="flex items-center gap-1.5 px-2.5 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium"><span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>Mode Superadmin</span>}
      </div>

      <div className="flex gap-2 flex-wrap">
        {['', ...STATUS_OPTIONS].map(s => (
          <button key={s} onClick={() => setFilterStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${filterStatus === s ? 'bg-blue-600 text-white border-blue-600' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}
            data-testid={`po-filter-${s || 'all'}`}>{s || 'Semua'}</button>
        ))}
      </div>

      <DataTable
        columns={columns}
        searchKeys={['po_number', 'customer_name']}
        expandedRow={expandedRowRender}
        storageKey="productionPOs"
        serverPagination={{
          fetcher: posFetcher,
          deps: [filterStatus, refetchKey],
          itemLabel: 'PO',
          initialSort: { key: 'created_at', dir: 'desc' },
          virtualize: true,
          virtualizeHeight: 650,
          estimatedRowHeight: 80,
        }}
        actions={
          <div className="flex items-center gap-2">
            <ImportExportPanel 
              importType="production-pos" 
              exportType="production-pos" 
              exportFilters={{ status: filterStatus }}
              onImportSuccess={() => refetchPOs()} 
            />
            {canCreate && (
              <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700" data-testid="create-po-btn"><Plus className="w-4 h-4" /> Buat PO</button>
            )}
          </div>
        }
      />

      {/* Create PO Modal */}
      {showModal && (
        <Modal title={editData ? `Edit PO: ${editData.po_number}` : 'Buat Production PO'} onClose={() => setShowModal(false)} size="xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            {editData && editData.status === 'Closed' && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm text-orange-700">
                ⚠️ PO ini berstatus <strong>Closed</strong>. Anda mengedit sebagai Superadmin.
              </div>
            )}
            {editData && (
              <div className="bg-slate-50 rounded-xl p-3">
                <p className="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wide">Status Workflow</p>
                <POWorkflowIndicator status={editData.status} />
                <p className="text-[11px] text-slate-500 mt-2">
                  🛡️ Guardrails aktif: item yang sudah memiliki shipment tidak dapat diubah SKU/Size/Color-nya, dan qty-nya tidak dapat lebih rendah dari total yang sudah dikirim/shipped.
                </p>
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Nomor PO * <span className="text-xs text-slate-400">(manual)</span></label>
                <input required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.po_number} onChange={e => setForm({...form, po_number: e.target.value})} placeholder="PO-2025-001" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Buyer / Customer *</label>
                <SearchableSelect
                  options={buyers.map(b => ({ value: b.id, label: b.buyer_name, sub: b.buyer_code }))}
                  value={form.buyer_id}
                  onChange={val => {
                    const buyer = buyers.find(b => b.id === val);
                    setForm({...form, buyer_id: val, customer_name: buyer?.buyer_name || ''});
                  }}
                  placeholder="— Pilih Buyer —"
                />
                {!form.buyer_id && (
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                    value={form.customer_name} onChange={e => setForm({...form, customer_name: e.target.value})} 
                    placeholder="Atau ketik nama customer manual" />
                )}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Vendor / Garmen <span className="text-xs text-slate-400">opsional</span></label>
              <SearchableSelect
                options={vendors.map(v => ({ value: v.id, label: v.garment_name, sub: v.garment_code }))}
                value={form.vendor_id}
                onChange={val => setForm({...form, vendor_id: val})}
                placeholder="— Pilih Vendor (opsional) —"
              />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Tanggal PO</label>
                <input type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.po_date} onChange={e => setForm({...form, po_date: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Deadline Produksi</label>
                <input type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.deadline} onChange={e => setForm({...form, deadline: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Deadline Pengiriman</label>
                <input type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.delivery_deadline} onChange={e => setForm({...form, delivery_deadline: e.target.value})} />
              </div>
            </div>

            {/* PO Items */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-semibold text-slate-700">Item Produk *</label>
                <button type="button" onClick={addItem} className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium">
                  <Plus className="w-3.5 h-3.5" /> Tambah Item
                </button>
              </div>
              {form.items.length === 0 && <p className="text-sm text-slate-400 italic text-center py-4 border border-dashed border-slate-200 rounded-lg">Klik "Tambah Item" untuk menambahkan produk ke PO</p>}
              <div className="space-y-3">
                {form.items.map((item, idx) => {
                  const hasShipments = !!item.__has_shipments;
                  const minQty = item.__min_qty || 0;
                  return (
                  <div key={idx} className={`border rounded-xl p-3 ${hasShipments ? 'border-amber-300 bg-amber-50/40' : 'border-slate-200 bg-slate-50'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-slate-600">
                        Item #{idx + 1}
                        {hasShipments && (
                          <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 uppercase tracking-wide">
                            🔒 sudah shipped (qty min: {minQty})
                          </span>
                        )}
                      </span>
                      {hasShipments ? (
                        <span className="text-xs text-slate-400" title="Tidak dapat dihapus karena sudah ada shipment/return">Tidak dapat dihapus</span>
                      ) : (
                        <button type="button" onClick={() => removeItem(idx)} className="text-red-400 hover:text-red-600"><X className="w-4 h-4" /></button>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Produk *</label>
                        <SearchableSelect
                          options={products.map(p => ({ value: p.id, label: p.product_name, sub: p.product_code }))}
                          value={item.product_id}
                          onChange={val => updateItem(idx, 'product_id', val)}
                          placeholder="Pilih Produk"
                          required
                          disabled={hasShipments}
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Varian / SKU</label>
                        <SearchableSelect
                          options={variants.filter(v => v.product_id === item.product_id).map(v => ({ value: v.id, label: v.sku, sub: `${v.size}/${v.color}` }))}
                          value={item.variant_id}
                          onChange={val => updateItem(idx, 'variant_id', val)}
                          placeholder="Pilih Varian (opsional)"
                          disabled={!item.product_id || hasShipments}
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-4 gap-2 mt-2">
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Size</label>
                        <input className="w-full border border-slate-200 rounded px-2 py-1.5 text-xs disabled:bg-slate-100 disabled:text-slate-500" value={item.size} onChange={e => updateItem(idx, 'size', e.target.value)} placeholder="M" disabled={hasShipments} />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Warna</label>
                        <input className="w-full border border-slate-200 rounded px-2 py-1.5 text-xs disabled:bg-slate-100 disabled:text-slate-500" value={item.color} onChange={e => updateItem(idx, 'color', e.target.value)} placeholder="Hitam" disabled={hasShipments} />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">SKU</label>
                        <input className="w-full border border-slate-200 rounded px-2 py-1.5 text-xs font-mono disabled:bg-slate-100 disabled:text-slate-500" value={item.sku} onChange={e => updateItem(idx, 'sku', e.target.value)} placeholder="PRD-BLK-M" disabled={hasShipments} />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Qty *{hasShipments && <span className="text-amber-700 ml-1">(min {minQty})</span>}</label>
                        <input required type="number" min={hasShipments ? minQty : 1} className="w-full border border-slate-200 rounded px-2 py-1.5 text-xs" value={item.qty} onChange={e => updateItem(idx, 'qty', e.target.value)} placeholder="100" />
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-2 mt-2">
                      <div className="col-span-1">
                        <label className="block text-xs text-slate-600 mb-1">No. Seri / Batch <span className="text-amber-500 font-semibold">*</span></label>
                        <input required className="w-full border border-amber-200 rounded px-2 py-1.5 text-xs font-mono bg-amber-50 focus:outline-none focus:ring-1 focus:ring-amber-400" value={item.serial_number || ''} onChange={e => updateItem(idx, 'serial_number', e.target.value)} placeholder="SN-2025-001" />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Selling Price (Rp)</label>
                        <input type="number" min="0" className="w-full border border-slate-200 rounded px-2 py-1.5 text-xs" value={item.selling_price_snapshot} onChange={e => updateItem(idx, 'selling_price_snapshot', e.target.value)} placeholder="85000" />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">CMT Price (Rp)</label>
                        <input type="number" min="0" className="w-full border border-slate-200 rounded px-2 py-1.5 text-xs" value={item.cmt_price_snapshot} onChange={e => updateItem(idx, 'cmt_price_snapshot', e.target.value)} placeholder="35000" />
                      </div>
                    </div>
                  </div>
                  );
                })}
              </div>
            </div>

            {form.items.length > 0 && (
              <div className="bg-blue-50 rounded-lg p-3 text-sm">
                <div className="flex justify-between text-blue-700">
                  <span>Total Item: <strong>{form.items.length}</strong></span>
                  <span>Total Qty: <strong>{form.items.reduce((s, i) => s + (Number(i.qty) || 0), 0).toLocaleString('id-ID')} pcs</strong></span>
                </div>
              </div>
            )}

            {/* PO Accessories Add-on */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-semibold text-slate-700">Aksesoris (Add-on)</label>
                <button type="button" onClick={addAccessoryItem} className="flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-800 font-medium">
                  <Plus className="w-3.5 h-3.5" /> Tambah Aksesoris
                </button>
              </div>
              {(form.po_accessories || []).length === 0 && <p className="text-xs text-slate-400 italic text-center py-2 border border-dashed border-slate-200 rounded-lg">Opsional — Klik "Tambah Aksesoris" untuk menambahkan</p>}
              <div className="space-y-2">
                {(form.po_accessories || []).map((acc, idx) => (
                  <div key={idx} className="flex items-center gap-2 border border-emerald-200 rounded-lg p-2 bg-emerald-50/50">
                    <div className="flex-1">
                      <SearchableSelect
                        options={accessories.map(a => ({ value: a.id, label: a.accessory_name || a.name, sub: a.accessory_code || a.code || a.category || '' }))}
                        value={acc.accessory_id}
                        onChange={val => updateAccessoryItem(idx, 'accessory_id', val)}
                        placeholder="Pilih Aksesoris"
                      />
                    </div>
                    <input type="number" min="1" className="w-24 border border-slate-200 rounded px-2 py-1.5 text-xs" 
                      value={acc.qty_needed} onChange={e => updateAccessoryItem(idx, 'qty_needed', e.target.value)} placeholder="Qty" />
                    <span className="text-xs text-slate-500 w-10">{acc.unit || 'pcs'}</span>
                    <input className="w-32 border border-slate-200 rounded px-2 py-1.5 text-xs" 
                      value={acc.notes || ''} onChange={e => updateAccessoryItem(idx, 'notes', e.target.value)} placeholder="Notes" />
                    <button type="button" onClick={() => removeAccessoryItem(idx)} className="text-red-400 hover:text-red-600"><X className="w-4 h-4" /></button>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Catatan</label>
              <textarea rows="2" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} />
            </div>
            {editData && (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Status</label>
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.status || editData.status} onChange={e => setForm({...form, status: e.target.value})}>
                  {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            )}
            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700">{editData ? 'Simpan Perubahan' : 'Buat PO'}</button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm hover:bg-slate-50">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Manual Close PO Modal */}
      {showCloseModal && closeTargetPO && (
        <Modal title={`Tutup PO Manual: ${closeTargetPO.po_number}`} onClose={() => setShowCloseModal(false)}>
          <form onSubmit={handleClosePO} className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-700">
              Tindakan ini akan mengubah status PO menjadi <strong>Closed</strong>. Pastikan alasan dituliskan dengan benar.
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Alasan Penutupan *</label>
              <select required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={closeForm.close_reason} onChange={e => setCloseForm({...closeForm, close_reason: e.target.value})}>
                {CLOSE_REASONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Keterangan Tambahan</label>
              <textarea rows="3" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={closeForm.close_notes} onChange={e => setCloseForm({...closeForm, close_notes: e.target.value})} placeholder="Jelaskan detail alasan penutupan PO..." />
            </div>
            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-orange-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-orange-700">Tutup PO</button>
              <button type="button" onClick={() => setShowCloseModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm hover:bg-slate-50">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Detail Modal */}
      {showDetail && detailData && (
        <Modal title={`Detail PO: ${detailData.po_number}`} onClose={() => setShowDetail(false)} size="xl">
          <div className="space-y-4">
            {/* PDF Export */}
            <div className="flex justify-end">
              <button
                onClick={async () => {
                  try {
                    const res = await apiFetch(`/export-pdf?type=production-po&id=${detailData.id}`);
                    if (!res.ok) { alert('Gagal export PDF'); return; }
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url; a.download = `SPP-${detailData.po_number}.pdf`; a.click();
                    URL.revokeObjectURL(url);
                  } catch (e) { alert('Gagal export PDF: ' + e.message); }
                }}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 font-medium">
                📄 Export PDF (SPP)
              </button>
            </div>
            {/* Workflow Indicator */}
            <div className="bg-slate-50 rounded-xl p-4">
              <p className="text-xs font-semibold text-slate-500 mb-3 uppercase tracking-wide">Status Workflow</p>
              <POWorkflowIndicator status={detailData.status} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              {[{l:'No. PO',v:<span className="font-bold text-blue-700">{detailData.po_number}</span>},
                {l:'Customer',v:detailData.customer_name},
                {l:'Vendor',v:detailData.vendor_name||'-'},
                {l:'Status',v:<StatusBadge status={detailData.status} />},
                {l:'Tgl. PO',v:fmtDate(detailData.po_date)},
                {l:'Deadline Produksi',v:fmtDate(detailData.deadline)},
                {l:'Deadline Kirim',v:fmtDate(detailData.delivery_deadline)},
                {l:'Dibuat',v:detailData.created_by}
              ].map(it => <div key={it.l} className="bg-slate-50 rounded-lg p-3"><p className="text-xs text-slate-500">{it.l}</p><div className="font-medium text-sm mt-0.5">{it.v}</div></div>)}
            </div>
            {detailData.close_reason && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
                <p className="text-sm font-semibold text-orange-700">Alasan Penutupan: {detailData.close_reason}</p>
                {detailData.close_notes && <p className="text-xs text-orange-600 mt-1">{detailData.close_notes}</p>}
                <p className="text-xs text-orange-500 mt-1">Ditutup oleh: {detailData.closed_by} pada {fmtDate(detailData.closed_at)}</p>
              </div>
            )}
            {detailData.items?.length > 0 && (
              <div className="space-y-3">
                <h4 className="font-semibold text-slate-700">Item PO ({detailData.items.length})</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="bg-slate-100">
                      <th className="text-left px-3 py-2 text-xs text-slate-600">Produk</th>
                      <th className="text-left px-3 py-2 text-xs text-slate-600">SKU</th>
                      <th className="text-left px-3 py-2 text-xs text-slate-600">No. Seri/Batch</th>
                      <th className="text-left px-3 py-2 text-xs text-slate-600">Size/Warna</th>
                      <th className="text-right px-3 py-2 text-xs text-slate-600">Qty</th>
                      <th className="text-right px-3 py-2 text-xs text-slate-600">Selling Price</th>
                      <th className="text-right px-3 py-2 text-xs text-slate-600">CMT Price</th>
                      <th className="text-right px-3 py-2 text-xs text-slate-600">Margin/pcs</th>
                    </tr></thead>
                    <tbody>{detailData.items.map(it => {
                      const marginPcs = (it.selling_price_snapshot || 0) - (it.cmt_price_snapshot || 0);
                      return (
                        <tr key={it.id} className="border-t border-slate-100">
                          <td className="px-3 py-2">{it.product_name}</td>
                          <td className="px-3 py-2 font-mono text-xs">{it.sku || '-'}</td>
                          <td className="px-3 py-2 font-mono text-xs text-amber-700 font-medium">{it.serial_number || <span className="text-slate-300">—</span>}</td>
                          <td className="px-3 py-2 text-xs">{it.size} / {it.color}</td>
                          <td className="px-3 py-2 text-right font-bold">{it.qty?.toLocaleString('id-ID')}</td>
                          <td className="px-3 py-2 text-right text-emerald-700">{fmt(it.selling_price_snapshot)}</td>
                          <td className="px-3 py-2 text-right text-amber-700">{fmt(it.cmt_price_snapshot)}</td>
                          <td className={`px-3 py-2 text-right font-medium ${marginPcs >= 0 ? 'text-blue-700' : 'text-red-600'}`}>{fmt(marginPcs)}</td>
                        </tr>
                      );
                    })}</tbody>
                    <tfoot><tr className="bg-slate-50 font-bold border-t-2 border-slate-200">
                      <td className="px-3 py-2" colSpan={3}>Total</td>
                      <td className="px-3 py-2 text-right">{detailData.items.reduce((s,i)=>s+(i.qty||0),0).toLocaleString('id-ID')} pcs</td>
                      <td className="px-3 py-2 text-right text-emerald-700">{fmt(detailData.items.reduce((s,i)=>s+(i.qty||0)*(i.selling_price_snapshot||0),0))}</td>
                      <td className="px-3 py-2 text-right text-amber-700">{fmt(detailData.items.reduce((s,i)=>s+(i.qty||0)*(i.cmt_price_snapshot||0),0))}</td>
                      <td className="px-3 py-2 text-right text-blue-700">{fmt(detailData.items.reduce((s,i)=>s+(i.qty||0)*((i.selling_price_snapshot||0)-(i.cmt_price_snapshot||0)),0))}</td>
                    </tr></tfoot>
                  </table>
                </div>

                {/* Financial Summary */}
                {(() => {
                  const totalSales = detailData.items.reduce((s,i)=>s+(i.qty||0)*(i.selling_price_snapshot||0),0);
                  const totalCMT = detailData.items.reduce((s,i)=>s+(i.qty||0)*(i.cmt_price_snapshot||0),0);
                  const grossMargin = totalSales - totalCMT;
                  const marginPct = totalSales > 0 ? Math.round((grossMargin / totalSales) * 100) : 0;
                  return (
                    <div className="grid grid-cols-3 gap-3">
                      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                        <p className="text-xs text-emerald-600 font-medium">Total Nilai Penjualan</p>
                        <p className="text-xl font-bold text-emerald-700 mt-1">{fmt(totalSales)}</p>
                        <p className="text-xs text-emerald-500 mt-0.5">Selling Price × Qty</p>
                      </div>
                      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                        <p className="text-xs text-amber-600 font-medium">Total Biaya Vendor (CMT)</p>
                        <p className="text-xl font-bold text-amber-700 mt-1">{fmt(totalCMT)}</p>
                        <p className="text-xs text-amber-500 mt-0.5">CMT Price × Qty</p>
                      </div>
                      <div className={`border rounded-xl p-4 ${grossMargin >= 0 ? 'bg-blue-50 border-blue-200' : 'bg-red-50 border-red-200'}`}>
                        <p className={`text-xs font-medium ${grossMargin >= 0 ? 'text-blue-600' : 'text-red-600'}`}>Est. Gross Margin</p>
                        <p className={`text-xl font-bold mt-1 ${grossMargin >= 0 ? 'text-blue-700' : 'text-red-600'}`}>{fmt(grossMargin)}</p>
                        <p className={`text-xs mt-0.5 ${grossMargin >= 0 ? 'text-blue-500' : 'text-red-500'}`}>{marginPct}% dari nilai penjualan</p>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}
            {/* PO Accessories Section */}
            {detailData.po_accessories?.length > 0 && (
              <div className="space-y-3">
                <h4 className="font-semibold text-slate-700 flex items-center gap-2">
                  <span className="w-5 h-5 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center text-xs font-bold">{detailData.po_accessories.length}</span>
                  Aksesoris PO
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="bg-emerald-50">
                      <th className="text-left px-3 py-2 text-xs text-emerald-700 font-semibold">#</th>
                      <th className="text-left px-3 py-2 text-xs text-emerald-700 font-semibold">Nama Aksesoris</th>
                      <th className="text-left px-3 py-2 text-xs text-emerald-700 font-semibold">Kode</th>
                      <th className="text-right px-3 py-2 text-xs text-emerald-700 font-semibold">Qty Dibutuhkan</th>
                      <th className="text-left px-3 py-2 text-xs text-emerald-700 font-semibold">Satuan</th>
                      <th className="text-left px-3 py-2 text-xs text-emerald-700 font-semibold">Catatan</th>
                    </tr></thead>
                    <tbody>{detailData.po_accessories.map((acc, idx) => (
                      <tr key={acc.id || idx} className="border-t border-emerald-100 hover:bg-emerald-50/30">
                        <td className="px-3 py-2 text-xs text-slate-400">{idx + 1}</td>
                        <td className="px-3 py-2 font-medium text-slate-700">{acc.accessory_name}</td>
                        <td className="px-3 py-2 font-mono text-xs text-emerald-700">{acc.accessory_code || '-'}</td>
                        <td className="px-3 py-2 text-right font-bold text-slate-800">{(acc.qty_needed || 0).toLocaleString('id-ID')}</td>
                        <td className="px-3 py-2 text-xs text-slate-500">{acc.unit || 'pcs'}</td>
                        <td className="px-3 py-2 text-xs text-slate-400">{acc.notes || '-'}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </div>
            )}

            {/* File Attachments */}
            <FileAttachmentPanel
              entityType="production_po"
              entityId={detailData.id}
              userRole={userRole}
            />
          </div>
        </Modal>
      )}

      {confirmDelete && <ConfirmDialog title="Hapus Production PO?" message={`PO "${confirmDelete.po_number}" beserta semua work order dan progres akan dihapus permanen.`} onConfirm={handleDelete} onCancel={() => setConfirmDelete(null)} />}
    </div>
  );
}
