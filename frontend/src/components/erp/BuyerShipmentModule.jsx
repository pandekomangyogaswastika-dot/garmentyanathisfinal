
import { useState, useEffect } from 'react';
import { Plus, Eye, Trash2, Package, CheckCircle, Clock, TruckIcon, Download, ChevronDown, ChevronRight, History } from 'lucide-react';
import { toast } from 'sonner';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import FileAttachmentPanel from './FileAttachmentPanel';
import ImportExportPanel from './ImportExportPanel';
import { apiGet, apiPost, apiDelete, apiFetch } from '../../lib/api';

export default function BuyerShipmentModule({ token, userRole, hasPerm = () => false }) {
  const [shipments, setShipments] = useState([]);
  const [pos, setPOs] = useState([]);
  const [poItems, setPoItems] = useState([]);
  const [selectedPO, setSelectedPO] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [detailData, setDetailData] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    shipment_number: '',
    po_id: '',
    shipment_date: new Date().toISOString().split('T')[0],
    notes: '',
    items: []
  });

  const isSuperAdmin = userRole === 'superadmin';
  const canCreate = ['superadmin', 'admin'].includes(userRole) || hasPerm('shipment.create');
  const canEdit = ['superadmin', 'admin'].includes(userRole) || hasPerm('shipment.create');

  useEffect(() => { fetchAll(); }, []);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [sData, pData] = await Promise.all([
        apiGet('/buyer-shipments'),
        apiGet('/production-pos?status=In Production'),
      ]);
      setShipments(Array.isArray(sData) ? sData : []);
      const allPOs = await apiGet('/production-pos');
      // Filter PO yang masih punya sisa untuk dikirim (remaining_qty_to_ship > 0)
      setPOs(Array.isArray(allPOs) ? allPOs.filter(p => 
        ['In Production', 'Completed', 'Distributed'].includes(p.status) && 
        (p.remaining_qty_to_ship || p.total_qty) > 0
      ) : []);
    } catch (e) {
      setShipments([]); setPOs([]);
    }
    setLoading(false);
  };

  const loadPOItems = async (poId) => {
    if (!poId) { setPoItems([]); setSelectedPO(null); setForm(f => ({...f, po_id: '', items: []})); return; }
    try {
      const data = await apiGet(`/po-items?po_id=${poId}`);
      const po = pos.find(p => p.id === poId);
      setSelectedPO(po);
      setPoItems(Array.isArray(data) ? data : []);
      const items = (Array.isArray(data) ? data : []).map(pi => ({
        po_item_id: pi.id,
        product_name: pi.product_name,
        sku: pi.sku || '',
        size: pi.size || '',
        color: pi.color || '',
        serial_number: pi.serial_number || '',
        ordered_qty: pi.qty,
        qty_shipped: '',
      }));
      setForm(f => ({...f, po_id: poId, items}));
    } catch (e) { setPoItems([]); }
  };

  const updateItemQty = (idx, val) => {
    const items = [...form.items];
    items[idx] = {...items[idx], qty_shipped: val};
    setForm(f => ({...f, items}));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.shipment_number.trim()) { toast.error('Nomor shipment wajib diisi'); return; }
    if (!form.po_id) { toast.error('Pilih PO terlebih dahulu'); return; }
    const validItems = form.items.filter(i => Number(i.qty_shipped) > 0);
    if (validItems.length === 0) { toast.error('Isi minimal 1 item dengan qty > 0'); return; }
    // Frontend guard against overproduction mistakenly flagged: keep as warning only,
    // backend will enforce the real cap against total_produced.
    for (const item of validItems) {
      if (Number(item.qty_shipped) > Number(item.ordered_qty)) {
        toast.warning(
          `${item.sku}: qty kirim (${item.qty_shipped}) melebihi qty PO (${item.ordered_qty}). ` +
          `Pastikan ada laporan OVERPRODUCTION variance yang mendukung.`
        );
      }
    }
    const payload = {
      ...form,
      items: validItems.map(i => ({...i, qty_shipped: Number(i.qty_shipped), ordered_qty: Number(i.ordered_qty)}))
    };
    try {
      const data = await apiPost('/buyer-shipments', payload);
      toast.success(`Shipment ${data.shipment_number || ''} berhasil dibuat`);
      setShowModal(false);
      fetchAll();
    } catch (err) { toast.error(err.message || 'Gagal membuat buyer shipment'); }
  };

  const openDetail = async (row) => {
    try {
      const data = await apiGet(`/buyer-shipments/${row.id}`);
      setDetailData(data);
      setShowDetail(true);
    } catch (e) { toast.error(e.message || 'Gagal memuat detail'); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/buyer-shipments/${confirmDelete.id}`);
      setConfirmDelete(null);
      fetchAll();
    } catch (e) { toast.error(e.message || 'Gagal menghapus'); }
  };

  const downloadPDF = async (row) => {
    try {
      const res = await apiFetch(`/export-pdf?type=buyer-shipment&id=${row.id}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Buyer-Shipment-${row.shipment_number || row.id}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error('Gagal mengunduh PDF: ' + (err.detail || `HTTP ${res.status}`));
      }
    } catch (e) { toast.error('Error: ' + e.message); }
  };

  const [expandedRows, setExpandedRows] = useState({});
  const toggleExpand = (id) => setExpandedRows(prev => ({ ...prev, [id]: !prev[id] }));

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';
  const fmtNum = (v) => (v || 0).toLocaleString('id-ID');

  const columns = [
    { key: 'shipment_number', label: 'No. Shipment', render: (v) => <span className="font-bold text-blue-700">{v}</span> },
    { key: 'po_number', label: 'No. PO', render: (v) => <span className="font-mono text-xs text-slate-700">{v || '-'}</span> },
    { key: 'customer_name', label: 'Customer' },
    { key: 'progress', label: 'Progres Pengiriman', render: (_, row) => {
      // Use backend-calculated totals (fixed ordered_qty denominator)
      const totalOrdered = row.total_ordered || 0;
      const totalShipped = row.total_shipped || 0;
      const remaining = row.remaining || 0;
      const progressPct = row.progress_pct || 0;
      const dispatchCount = row.dispatch_count || 0;
      
      return (
        <div className="min-w-[180px]">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="font-bold text-slate-700">{fmtNum(totalShipped)} / {fmtNum(totalOrdered)} pcs</span>
            <span className="font-bold text-blue-600">{progressPct}%</span>
          </div>
          <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full transition-all ${progressPct >= 100 ? 'bg-emerald-500' : progressPct > 0 ? 'bg-blue-500' : 'bg-slate-200'}`}
              style={{ width: `${Math.min(progressPct, 100)}%` }} />
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-400 mt-0.5">
            <span>Sisa: {fmtNum(remaining)} pcs</span>
            {dispatchCount > 0 && <span>{dispatchCount} dispatch</span>}
          </div>
        </div>
      );
    }},
    { key: 'status', label: 'Status', render: (_, row) => {
      const pct = row.progress_pct || 0;
      const s = pct >= 100 ? 'Fully Shipped' : pct > 0 ? 'Partially Shipped' : 'Pending';
      const color = s === 'Fully Shipped' ? 'bg-emerald-100 text-emerald-700' : 
                    s === 'Partially Shipped' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600';
      return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>{s}</span>;
    }},
    { key: 'actions', label: 'Aksi', render: (_, row) => (
      <div className="flex items-center gap-1">
        <button onClick={() => openDetail(row)} className="p-1.5 rounded hover:bg-blue-50 text-blue-600" title="Detail">
          <Eye className="w-4 h-4" />
        </button>
        <button onClick={() => downloadPDF(row)} className="p-1.5 rounded hover:bg-emerald-50 text-emerald-600" title="Download PDF">
          <Download className="w-4 h-4" />
        </button>
        {canCreate && (
          <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-500" title="Hapus">
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
    )}
  ];

  const expandedRow = (row) => {
    if (!expandedRows[row.id] || !row.items || row.items.length === 0) return null;
    
    // Group items by dispatch_seq
    const dispatchGroups = {};
    const poItemCumulative = {};
    
    for (const item of row.items) {
      const seq = item.dispatch_seq || 1;
      if (!dispatchGroups[seq]) {
        dispatchGroups[seq] = { dispatch_seq: seq, dispatch_date: item.dispatch_date || item.created_at, items: [], total_qty: 0 };
      }
      dispatchGroups[seq].items.push(item);
      dispatchGroups[seq].total_qty += item.qty_shipped || 0;
    }
    
    const dispatches = Object.values(dispatchGroups).sort((a, b) => a.dispatch_seq - b.dispatch_seq);
    let cumulativeTotal = 0;
    
    return (
      <div className="bg-blue-50/30 border-t border-blue-100 px-6 py-3">
        <p className="text-xs font-semibold text-blue-700 mb-3 uppercase tracking-wide flex items-center gap-1.5">
          <History className="w-3.5 h-3.5" /> Riwayat Dispatch ({dispatches.length} round)
        </p>
        <div className="space-y-3">
          {dispatches.map((d, di) => {
            cumulativeTotal += d.total_qty;
            return (
              <div key={d.dispatch_seq} className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 bg-slate-50 border-b border-slate-100">
                  <div className="flex items-center gap-3">
                    <span className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center">#{d.dispatch_seq}</span>
                    <div>
                      <p className="text-sm font-semibold text-slate-700">Dispatch #{d.dispatch_seq}</p>
                      <p className="text-[10px] text-slate-400">{fmtDate(d.dispatch_date)}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-emerald-700">+{fmtNum(d.total_qty)} pcs</p>
                    <p className="text-[10px] text-slate-400">Kumulatif: {fmtNum(cumulativeTotal)} / {fmtNum(row.total_ordered || 0)} pcs</p>
                  </div>
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="text-left py-1.5 px-3 text-amber-700 font-semibold">Serial</th>
                      <th className="text-left py-1.5 px-3 text-slate-500">SKU</th>
                      <th className="text-left py-1.5 px-3 text-slate-500">Produk</th>
                      <th className="text-left py-1.5 px-3 text-slate-500">Size/Warna</th>
                      <th className="text-right py-1.5 px-3 text-slate-500">Qty Kirim</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {d.items.map((item, idx) => (
                      <tr key={item.id || idx} className="hover:bg-blue-50/30">
                        <td className="py-1.5 px-3 font-mono text-amber-700 font-semibold">{item.serial_number || '—'}</td>
                        <td className="py-1.5 px-3 font-mono text-blue-700">{item.sku || '-'}</td>
                        <td className="py-1.5 px-3 text-slate-700">{item.product_name}</td>
                        <td className="py-1.5 px-3 text-slate-500">{item.size || '-'}/{item.color || '-'}</td>
                        <td className="py-1.5 px-3 text-right font-bold text-emerald-700">{fmtNum(item.qty_shipped)} pcs</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
        {/* Summary bar */}
        <div className="mt-3 bg-blue-100 rounded-lg p-3 flex items-center justify-between">
          <span className="text-xs font-semibold text-blue-800">Total Kumulatif</span>
          <span className="text-sm font-bold text-blue-800">{fmtNum(cumulativeTotal)} / {fmtNum(row.total_ordered || 0)} pcs ({row.progress_pct || 0}%)</span>
        </div>
      </div>
    );
  };

  // Summary stats using backend-calculated totals
  const totalShipmentCount = shipments.length;
  const fullyShipped = shipments.filter(s => (s.progress_pct || 0) >= 100).length;
  const partialShipped = shipments.filter(s => (s.progress_pct || 0) > 0 && (s.progress_pct || 0) < 100).length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Buyer Shipment</h1>
          <p className="text-slate-500 text-sm mt-1">Pengiriman produk jadi ke buyer — support partial shipment multi-dispatch</p>
        </div>
        {isSuperAdmin && <span className="flex items-center gap-1.5 px-2.5 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium"><span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>Mode Superadmin</span>}
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total Shipment', value: totalShipmentCount, icon: TruckIcon, color: 'text-blue-700', bg: 'bg-blue-50' },
          { label: 'Fully Shipped', value: fullyShipped, icon: CheckCircle, color: 'text-emerald-700', bg: 'bg-emerald-50' },
          { label: 'Partially Shipped', value: partialShipped, icon: Clock, color: 'text-amber-700', bg: 'bg-amber-50' },
        ].map(s => {
          const Icon = s.icon;
          return (
            <div key={s.label} className={`${s.bg} rounded-xl p-4 border border-transparent`}>
              <div className="flex items-center gap-3">
                <Icon className={`w-6 h-6 ${s.color}`} />
                <div>
                  <p className="text-xs text-slate-500">{s.label}</p>
                  <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        {canEdit && (
          <button onClick={() => { setShowModal(true); setForm({ shipment_number: '', po_id: '', shipment_date: new Date().toISOString().split('T')[0], notes: '', items: [] }); }}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 shadow-sm">
            <Plus className="w-4 h-4" /> Buat Buyer Shipment
          </button>
        )}
        <ImportExportPanel token={token} importType={null} exportType="buyer-shipments" />
      </div>

      <DataTable columns={columns} data={shipments} loading={loading}
        expandedRow={expandedRow}
        storageKey="buyerShipments"
        onRowClick={(row) => toggleExpand(row.id)} />

      {/* Create Modal */}
      {showModal && (
        <Modal title="Buat Buyer Shipment" onClose={() => setShowModal(false)} size="xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">No. Shipment *</label>
                <input type="text" required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  value={form.shipment_number} onChange={e => setForm(f => ({...f, shipment_number: e.target.value}))} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Tanggal</label>
                <input type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  value={form.shipment_date} onChange={e => setForm(f => ({...f, shipment_date: e.target.value}))} />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Pilih PO *</label>
              <select required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                value={form.po_id} onChange={e => loadPOItems(e.target.value)}>
                <option value="">-- Pilih PO --</option>
                {pos.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.po_number} | {p.vendor_name || ''} | {p.created_at ? new Date(p.created_at).toLocaleDateString('id-ID') : ''}
                  </option>
                ))}
              </select>
            </div>
            {form.items.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left px-3 py-2 text-xs text-slate-500">Serial</th>
                      <th className="text-left px-3 py-2 text-xs text-slate-500">SKU</th>
                      <th className="text-left px-3 py-2 text-xs text-slate-500">Produk</th>
                      <th className="text-left px-3 py-2 text-xs text-slate-500">Size/Warna</th>
                      <th className="text-right px-3 py-2 text-xs text-slate-500">Qty Order</th>
                      <th className="text-right px-3 py-2 text-xs text-slate-500">Qty Kirim *</th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.items.map((item, idx) => (
                      <tr key={idx} className="border-t border-slate-100">
                        <td className="px-3 py-2 font-mono text-xs text-amber-700">{item.serial_number || '-'}</td>
                        <td className="px-3 py-2 font-mono text-xs text-blue-600">{item.sku || '-'}</td>
                        <td className="px-3 py-2 text-slate-700">{item.product_name}</td>
                        <td className="px-3 py-2 text-slate-500">{item.size || '-'}/{item.color || '-'}</td>
                        <td className="px-3 py-2 text-right text-slate-600">{(item.ordered_qty || 0).toLocaleString('id-ID')}</td>
                        <td className="px-3 py-2 text-right">
                          <input type="number" min="0" max={item.ordered_qty}
                            className="w-24 border border-slate-200 rounded px-2 py-1 text-right text-sm"
                            value={item.qty_shipped} onChange={e => updateItemQty(idx, e.target.value)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Catatan</label>
              <textarea className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" rows="2"
                value={form.notes} onChange={e => setForm(f => ({...f, notes: e.target.value}))} />
            </div>
            <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">Simpan</button>
          </form>
        </Modal>
      )}

      {/* Detail Modal with Dispatch History */}
      {showDetail && detailData && (
        <Modal title={`Detail: ${detailData.shipment_number}`} onClose={() => setShowDetail(false)} size="xl">
          <div className="space-y-4">
            {/* Summary Card */}
            <div className="bg-gradient-to-r from-blue-50 to-emerald-50 rounded-xl p-4 border border-blue-100">
              <div className="grid grid-cols-4 gap-4 text-center">
                <div>
                  <p className="text-xs text-slate-500">Total Order</p>
                  <p className="text-xl font-bold text-slate-800">{fmtNum(detailData.total_ordered)} <span className="text-xs font-normal">pcs</span></p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Sudah Kirim</p>
                  <p className="text-xl font-bold text-emerald-700">{fmtNum(detailData.total_shipped)} <span className="text-xs font-normal">pcs</span></p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Sisa</p>
                  <p className="text-xl font-bold text-amber-700">{fmtNum(detailData.remaining)} <span className="text-xs font-normal">pcs</span></p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Progress</p>
                  <p className="text-xl font-bold text-blue-700">{detailData.progress_pct}%</p>
                </div>
              </div>
              <div className="w-full h-3 bg-white/70 rounded-full overflow-hidden mt-3">
                <div className={`h-full rounded-full transition-all ${detailData.progress_pct >= 100 ? 'bg-emerald-500' : 'bg-blue-500'}`}
                  style={{ width: `${Math.min(detailData.progress_pct || 0, 100)}%` }} />
              </div>
            </div>

            {/* Info grid */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { l: 'No. Shipment', v: <span className="font-bold text-blue-700">{detailData.shipment_number}</span> },
                { l: 'No. PO', v: detailData.po_number || '-' },
                { l: 'Customer', v: detailData.customer_name || '-' },
                { l: 'Vendor', v: detailData.vendor_name || '-' },
                { l: 'Dibuat', v: fmtDate(detailData.created_at) },
                { l: 'Status', v: <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                  (detailData.progress_pct || 0) >= 100 ? 'bg-emerald-100 text-emerald-700' :
                  (detailData.progress_pct || 0) > 0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'
                }`}>{(detailData.progress_pct || 0) >= 100 ? 'Fully Shipped' : (detailData.progress_pct || 0) > 0 ? 'Partially Shipped' : 'Pending'}</span> },
              ].map(it => (
                <div key={it.l} className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">{it.l}</p>
                  <div className="font-medium text-sm mt-0.5">{it.v}</div>
                </div>
              ))}
            </div>

            {/* Dispatch History */}
            {(detailData.dispatches || []).length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-semibold text-slate-700 flex items-center gap-2">
                    <History className="w-4 h-4 text-blue-500" />
                    Riwayat Dispatch ({detailData.dispatches.length} round)
                  </h4>
                  {/* Cumulative PDF Export (total, not per dispatch) */}
                  <button onClick={async () => {
                    try {
                      const res = await apiFetch(`/export-pdf?type=buyer-shipment&id=${detailData.id}`);
                      if (!res.ok) throw new Error('Export gagal');
                      const blob = await res.blob();
                      const url = window.URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `${detailData.shipment_number || 'Buyer-Shipment'}-Total.pdf`;
                      a.click();
                      window.URL.revokeObjectURL(url);
                    } catch (err) { toast.error('Error: ' + err.message); }
                  }} className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg font-medium hover:bg-blue-700 flex items-center gap-1" data-testid="export-cumulative-pdf">
                    PDF Total Kumulatif
                  </button>
                </div>
                <div className="space-y-2">
                  {(() => {
                    let cumulative = 0;
                    return detailData.dispatches.map((d, i) => {
                      cumulative += d.total_qty;
                      const remaining = Math.max(0, (detailData.total_ordered || 0) - cumulative);
                      return (
                        <div key={d.dispatch_seq} className="border border-slate-200 rounded-lg overflow-hidden">
                          <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50">
                            <div className="flex items-center gap-2">
                              <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">
                                {d.dispatch_seq}
                              </span>
                              <span className="text-sm font-semibold text-slate-700">Dispatch #{d.dispatch_seq}</span>
                              <span className="text-xs text-slate-400">· {fmtDate(d.dispatch_date)}</span>
                            </div>
                            <div className="flex items-center gap-3 text-xs">
                              <span className="text-emerald-700 font-bold">+{fmtNum(d.total_qty)} pcs</span>
                              <span className="text-blue-700">Kumulatif: {fmtNum(cumulative)}</span>
                              <span className="text-slate-500">Sisa: {fmtNum(remaining)}</span>
                              {/* Per-dispatch PDF button */}
                              <button onClick={async (e) => {
                                e.stopPropagation();
                                try {
                                  const res = await apiFetch(`/export-pdf?type=buyer-shipment-dispatch&id=${detailData.id}&dispatch=${d.dispatch_seq}`);
                                  if (!res.ok) throw new Error('Export gagal');
                                  const blob = await res.blob();
                                  const url = window.URL.createObjectURL(blob);
                                  const a = document.createElement('a');
                                  a.href = url;
                                  a.download = `${detailData.shipment_number || 'Dispatch'}-D${d.dispatch_seq}.pdf`;
                                  a.click();
                                  window.URL.revokeObjectURL(url);
                                } catch (err) { toast.error('Error: ' + err.message); }
                              }} className="px-2 py-1 bg-white border border-blue-300 text-blue-600 rounded text-[10px] font-medium hover:bg-blue-50 flex items-center gap-1" data-testid={`export-dispatch-${d.dispatch_seq}-pdf`}>
                                PDF D{d.dispatch_seq}
                              </button>
                            </div>
                          </div>
                          <table className="w-full text-xs">
                            <tbody>
                              {d.items.map((item, idx) => (
                                <tr key={item.id || idx} className="border-t border-slate-100 hover:bg-slate-50">
                                  <td className="py-1.5 px-3 font-mono text-amber-700 w-24">{item.serial_number || '—'}</td>
                                  <td className="py-1.5 px-3 font-mono text-blue-700 w-24">{item.sku || '-'}</td>
                                  <td className="py-1.5 px-3 text-slate-700">{item.product_name} <span className="text-slate-400">{item.size}/{item.color}</span></td>
                                  <td className="py-1.5 px-3 text-right font-bold text-emerald-700 w-28">{fmtNum(item.qty_shipped)} pcs</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    });
                  })()}
                </div>
              </div>
            )}

            {/* Summary Items (per SKU cumulative) */}
            {(detailData.summary_items || []).length > 0 && (
              <div>
                <h4 className="font-semibold text-slate-700 mb-2">Ringkasan per Item</h4>
                <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left px-3 py-2 text-xs text-slate-500">Serial</th>
                      <th className="text-left px-3 py-2 text-xs text-slate-500">SKU</th>
                      <th className="text-left px-3 py-2 text-xs text-slate-500">Produk</th>
                      <th className="text-right px-3 py-2 text-xs text-slate-500">Qty Order</th>
                      <th className="text-right px-3 py-2 text-xs text-slate-500">Total Kirim</th>
                      <th className="text-right px-3 py-2 text-xs text-slate-500">Sisa</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {detailData.summary_items.map((item, idx) => (
                      <tr key={idx}>
                        <td className="px-3 py-2 font-mono text-xs text-amber-700">{item.serial_number || '—'}</td>
                        <td className="px-3 py-2 font-mono text-xs text-blue-700">{item.sku || '-'}</td>
                        <td className="px-3 py-2">{item.product_name} <span className="text-xs text-slate-400">{item.size}/{item.color}</span></td>
                        <td className="px-3 py-2 text-right">{fmtNum(item.ordered_qty)}</td>
                        <td className="px-3 py-2 text-right font-bold text-emerald-700">{fmtNum(item.cumulative_shipped)}</td>
                        <td className="px-3 py-2 text-right font-bold text-amber-700">{fmtNum(Math.max(0, (item.ordered_qty || 0) - (item.cumulative_shipped || 0)))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <FileAttachmentPanel entityType="buyer_shipment" entityId={detailData.id} token={token} />
          </div>
        </Modal>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Hapus Buyer Shipment"
          message={`Yakin ingin menghapus shipment ${confirmDelete.shipment_number}?`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
