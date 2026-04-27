import { useState, useEffect } from 'react';
import { ClipboardCheck, Clipboard, X, CheckCircle, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';

export default function VendorMaterialInspection({ token, user }) {
  const [shipments, setShipments] = useState([]);
  const [inspections, setInspections] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [selectedShipment, setSelectedShipment] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ inspection_date: new Date().toISOString().split('T')[0], overall_notes: '', items: [], accessory_items: [] });

  useEffect(() => { fetchShipments(); fetchInspections(); }, []);

  const fetchShipments = async () => {
    const res = await fetch('/api/vendor-shipments', { headers: { Authorization: `Bearer ${token}` } });
    const data = await res.json();
    const received = Array.isArray(data) ? data.filter(s => s.status === 'Received') : [];
    setShipments(received);
  };

  const fetchInspections = async () => {
    const res = await fetch('/api/vendor-material-inspections', { headers: { Authorization: `Bearer ${token}` } });
    const data = await res.json();
    setInspections(Array.isArray(data) ? data : []);
  };

  const openInspect = async (shipment) => {
    setSelectedShipment(shipment);
    const res = await fetch(`/api/vendor-shipments/${shipment.id}`, { headers: { Authorization: `Bearer ${token}` } });
    const data = await res.json();
    const items = (data.items || []).map(si => ({
      shipment_item_id: si.id,
      sku: si.sku || '',
      product_name: si.product_name || '',
      size: si.size || '',
      color: si.color || '',
      ordered_qty: si.qty_sent || 0,
      received_qty: si.qty_sent || 0,
      missing_qty: 0,
      condition_notes: ''
    }));
    
    // Load accessories for inspection
    // For additional accessory shipments, use accessory_items from shipment
    // For normal shipments, use po_accessories from linked PO
    let accessory_items = [];
    if (data.accessory_items && data.accessory_items.length > 0) {
      // This is an additional accessory shipment
      accessory_items = data.accessory_items.map(asi => ({
        accessory_id: asi.accessory_id || '',
        accessory_name: asi.accessory_name || '',
        accessory_code: asi.accessory_code || '',
        unit: asi.unit || 'pcs',
        ordered_qty: asi.qty_sent || 0,
        received_qty: asi.qty_sent || 0,
        missing_qty: 0,
        condition_notes: ''
      }));
    } else if (data.po_accessories && data.po_accessories.length > 0) {
      // Normal shipment with PO accessories
      accessory_items = data.po_accessories.map(acc => ({
        accessory_id: acc.accessory_id || acc.id || '',
        accessory_name: acc.accessory_name || '',
        accessory_code: acc.accessory_code || '',
        unit: acc.unit || 'pcs',
        ordered_qty: acc.qty_needed || 0,
        received_qty: acc.qty_needed || 0,
        missing_qty: 0,
        condition_notes: ''
      }));
    }
    
    setForm({ inspection_date: new Date().toISOString().split('T')[0], overall_notes: '', items, accessory_items });
    setShowModal(true);
  };

  const updateItem = (idx, field, value) => {
    const newItems = [...form.items];
    newItems[idx] = { ...newItems[idx], [field]: value };
    if (field === 'received_qty') {
      newItems[idx].missing_qty = Math.max(0, (newItems[idx].ordered_qty || 0) - (Number(value) || 0));
    }
    setForm(f => ({ ...f, items: newItems }));
  };

  const updateAccItem = (idx, field, value) => {
    const newItems = [...form.accessory_items];
    newItems[idx] = { ...newItems[idx], [field]: value };
    if (field === 'received_qty') {
      newItems[idx].missing_qty = Math.max(0, (newItems[idx].ordered_qty || 0) - (Number(value) || 0));
    }
    setForm(f => ({ ...f, accessory_items: newItems }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch('/api/vendor-material-inspections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ shipment_id: selectedShipment.id, ...form })
      });
      const data = await res.json();
      if (!res.ok) { toast.error(data.detail || data.error || 'Gagal menyimpan inspeksi'); return; }
      setShowModal(false);
      fetchShipments();
      fetchInspections();

      // If there are missing items (materials OR accessories), auto-prompt to create Additional Request
      const totalMissingMaterial = form.items.reduce((s, i) => s + (i.missing_qty || 0), 0);
      const totalMissingAccessory = (form.accessory_items || []).reduce((s, a) => s + (a.missing_qty || 0), 0);
      const totalMissing = totalMissingMaterial + totalMissingAccessory;
      
      if (totalMissing > 0) {
        let missingMsg = `Inspeksi berhasil disimpan!\n\n`;
        if (totalMissingMaterial > 0) missingMsg += `Terdeteksi ${totalMissingMaterial} pcs material MISSING.\n`;
        if (totalMissingAccessory > 0) missingMsg += `Terdeteksi ${totalMissingAccessory} pcs aksesoris MISSING.\n`;
        missingMsg += `\nApakah Anda ingin langsung mengajukan Permintaan Material Tambahan kepada ERP?`;
        
        const confirm = window.confirm(missingMsg);
        if (confirm) {
          const missingItems = form.items.filter(i => (i.missing_qty || 0) > 0).map(i => ({
            sku: i.sku, product_name: i.product_name, size: i.size, color: i.color,
            serial_number: i.serial_number || '',
            requested_qty: i.missing_qty, reason: `Missing dari inspeksi shipment ${selectedShipment.shipment_number}`
          }));
          const reqRes = await fetch('/api/material-requests', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({
              request_type: 'ADDITIONAL',
              original_shipment_id: selectedShipment.id,
              inspection_id: data.id,
              po_id: missingItems[0]?.po_id || '',
              reason: `Material missing setelah inspeksi shipment ${selectedShipment.shipment_number}`,
              items: missingItems
            })
          });
          const reqData = await reqRes.json();
          if (reqRes.ok) {
            toast.success(`Permintaan Tambahan ${reqData.request_number} berhasil diajukan ke ERP`);
          }
        }
      } else {
        toast.success('Inspeksi berhasil disimpan! Material & aksesoris lengkap — Anda dapat memulai produksi.');
      }
    } finally {
      setLoading(false);
    }
  };

  const openDetail = (insp) => {
    setDetailData(insp);
    setShowDetail(true);
  };

  const fmtDate = d => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  // Check if inspection is overdue (>3 days from shipment received)
  const isOverdue = (shipment) => {
    if (!shipment.updated_at) return false;
    const receivedDate = new Date(shipment.updated_at);
    const threeDaysLater = new Date(receivedDate.getTime() + 3 * 24 * 60 * 60 * 1000);
    return new Date() > threeDaysLater;
  };

  // Already inspected shipment IDs
  const inspectedShipmentIds = new Set(inspections.map(i => i.shipment_id));

  const pendingShipments = shipments.filter(s => !inspectedShipmentIds.has(s.id));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
          <ClipboardCheck className="w-6 h-6 text-emerald-600" />
          Inspeksi Material
        </h1>
        <p className="text-slate-500 text-sm mt-1">Laporkan hasil inspeksi material yang diterima (wajib dalam 3 hari)</p>
      </div>

      {pendingShipments.length > 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4">
          <p className="text-amber-800 font-semibold text-sm mb-2">⏰ Shipment Menunggu Inspeksi ({pendingShipments.length})</p>
          <div className="space-y-2">
            {pendingShipments.map(s => {
              const overdue = isOverdue(s);
              return (
                <div key={s.id} className={`flex items-center justify-between p-3 rounded-lg border ${overdue ? 'bg-red-50 border-red-200' : 'bg-white border-slate-200'}`}>
                  <div>
                    <p className={`font-semibold text-sm ${overdue ? 'text-red-700' : 'text-slate-800'}`}>
                      {s.shipment_number} {overdue && '⚠️ TERLAMBAT'}
                    </p>
                    <p className="text-xs text-slate-500">Diterima: {fmtDate(s.updated_at)} • Tipe: {s.shipment_type || 'NORMAL'}</p>
                  </div>
                  <button onClick={() => openInspect(s)} className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-medium hover:bg-emerald-700">
                    Inspeksi Sekarang
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Inspection History */}
      <div>
        <h3 className="font-semibold text-slate-700 mb-3">Riwayat Inspeksi ({inspections.length})</h3>
        {inspections.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-sm">Belum ada inspeksi yang dilakukan</div>
        ) : (
          <div className="space-y-2">
            {inspections.map(insp => (
              <div key={insp.id} className="bg-white border border-slate-200 rounded-xl p-4 flex items-center justify-between">
                <div>
                  <p className="font-semibold text-sm text-slate-800">{insp.shipment_number}</p>
                  <p className="text-xs text-slate-500">
                    Inspeksi: {fmtDate(insp.inspection_date)} •
                    Diterima: <span className="text-emerald-700 font-medium">{insp.total_received}</span> pcs •
                    Missing: <span className={`font-medium ${insp.total_missing > 0 ? 'text-red-600' : 'text-slate-500'}`}>{insp.total_missing}</span> pcs
                  </p>
                </div>
                <button onClick={() => openDetail(insp)} className="px-3 py-1.5 bg-slate-100 text-slate-700 rounded-lg text-xs font-medium hover:bg-slate-200">
                  Lihat Detail
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Inspection Form Modal */}
      {showModal && selectedShipment && (
        <Modal title={`Inspeksi: ${selectedShipment.shipment_number}`} onClose={() => setShowModal(false)} size="xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-sm text-emerald-800">
              Periksa setiap item material yang diterima. Isi jumlah yang benar-benar diterima dan jumlah yang missing/kurang.
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Tanggal Inspeksi</label>
              <input type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.inspection_date} onChange={e => setForm(f => ({ ...f, inspection_date: e.target.value }))} />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-100">
                    <th className="text-left px-3 py-2 text-xs">Produk / SKU</th>
                    <th className="text-right px-3 py-2 text-xs">Dikirim</th>
                    <th className="text-right px-3 py-2 text-xs text-emerald-700">Diterima *</th>
                    <th className="text-right px-3 py-2 text-xs text-red-600">Missing</th>
                    <th className="text-left px-3 py-2 text-xs">Kondisi / Catatan</th>
                  </tr>
                </thead>
                <tbody>
                  {form.items.map((item, idx) => (
                    <tr key={idx} className="border-t border-slate-100">
                      <td className="px-3 py-2">
                        <p className="font-medium text-xs">{item.product_name}</p>
                        <p className="text-xs text-slate-400 font-mono">{item.sku} {item.size}/{item.color}</p>
                      </td>
                      <td className="px-3 py-2 text-right text-slate-600 font-medium">{item.ordered_qty}</td>
                      <td className="px-3 py-2 text-right">
                        <input type="number" min="0" max={item.ordered_qty}
                          className="w-20 border border-emerald-200 rounded px-2 py-1 text-sm text-right focus:outline-none focus:ring-1 focus:ring-emerald-500"
                          value={item.received_qty}
                          onChange={e => updateItem(idx, 'received_qty', e.target.value)} />
                      </td>
                      <td className={`px-3 py-2 text-right font-semibold ${item.missing_qty > 0 ? 'text-red-600' : 'text-slate-400'}`}>
                        {item.missing_qty}
                      </td>
                      <td className="px-3 py-2">
                        <input className="w-full border border-slate-200 rounded px-2 py-1 text-xs" value={item.condition_notes} onChange={e => updateItem(idx, 'condition_notes', e.target.value)} placeholder="Kondisi barang..." />
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-slate-50 font-bold border-t-2 border-slate-200">
                  <tr>
                    <td className="px-3 py-2 text-sm">Total</td>
                    <td className="px-3 py-2 text-right">{form.items.reduce((s, i) => s + (i.ordered_qty || 0), 0)}</td>
                    <td className="px-3 py-2 text-right text-emerald-700">{form.items.reduce((s, i) => s + (Number(i.received_qty) || 0), 0)}</td>
                    <td className="px-3 py-2 text-right text-red-600">{form.items.reduce((s, i) => s + (i.missing_qty || 0), 0)}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Catatan Umum</label>
              <textarea rows="2" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={form.overall_notes} onChange={e => setForm(f => ({ ...f, overall_notes: e.target.value }))} placeholder="Catatan kondisi material secara umum..." />
            </div>

            {/* Accessories Inspection */}
            {form.accessory_items.length > 0 && (
              <div className="mt-3" data-testid="inspection-accessories">
                <label className="block text-sm font-semibold text-emerald-700 mb-2">Inspeksi Aksesoris ({form.accessory_items.length} item)</label>
                <div className="overflow-x-auto border border-emerald-200 rounded-xl">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-emerald-50">
                        <th className="text-left px-3 py-2 text-xs text-emerald-700">Aksesoris</th>
                        <th className="text-left px-3 py-2 text-xs text-emerald-700">Kode</th>
                        <th className="text-right px-3 py-2 text-xs text-slate-600">Qty Dibutuhkan</th>
                        <th className="text-right px-3 py-2 text-xs text-emerald-700">Diterima *</th>
                        <th className="text-right px-3 py-2 text-xs text-red-600">Missing</th>
                        <th className="text-left px-3 py-2 text-xs">Catatan</th>
                      </tr>
                    </thead>
                    <tbody>
                      {form.accessory_items.map((acc, idx) => (
                        <tr key={idx} className="border-t border-emerald-100">
                          <td className="px-3 py-2 font-medium text-xs text-slate-700">{acc.accessory_name}</td>
                          <td className="px-3 py-2 font-mono text-xs text-emerald-600">{acc.accessory_code}</td>
                          <td className="px-3 py-2 text-right text-slate-600 font-medium">{acc.ordered_qty} {acc.unit}</td>
                          <td className="px-3 py-2 text-right">
                            <input type="number" min="0" className="w-20 border border-emerald-200 rounded px-2 py-1 text-sm text-right focus:outline-none focus:ring-1 focus:ring-emerald-500" value={acc.received_qty} onChange={e => updateAccItem(idx, 'received_qty', e.target.value)} />
                          </td>
                          <td className={`px-3 py-2 text-right font-semibold ${acc.missing_qty > 0 ? 'text-red-600' : 'text-slate-400'}`}>{acc.missing_qty}</td>
                          <td className="px-3 py-2">
                            <input className="w-full border border-slate-200 rounded px-2 py-1 text-xs" value={acc.condition_notes} onChange={e => updateAccItem(idx, 'condition_notes', e.target.value)} placeholder="Kondisi aksesoris..." />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="bg-emerald-50 font-bold border-t-2 border-emerald-200">
                      <tr>
                        <td className="px-3 py-2 text-sm" colSpan="2">Total Aksesoris</td>
                        <td className="px-3 py-2 text-right">{form.accessory_items.reduce((s, i) => s + (i.ordered_qty || 0), 0)}</td>
                        <td className="px-3 py-2 text-right text-emerald-700">{form.accessory_items.reduce((s, i) => s + (Number(i.received_qty) || 0), 0)}</td>
                        <td className="px-3 py-2 text-right text-red-600">{form.accessory_items.reduce((s, i) => s + (i.missing_qty || 0), 0)}</td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <button type="submit" disabled={loading} className="flex-1 bg-emerald-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50">
                {loading ? 'Menyimpan...' : 'Kirim Laporan Inspeksi'}
              </button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm hover:bg-slate-50">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Detail Modal */}
      {showDetail && detailData && (
        <Modal title={`Detail Inspeksi: ${detailData.shipment_number}`} onClose={() => setShowDetail(false)} size="xl">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="grid grid-cols-3 gap-3 flex-1">
                <div className="bg-emerald-50 rounded-lg p-3 text-center">
                  <p className="text-xs text-emerald-600">Total Diterima</p>
                  <p className="text-2xl font-bold text-emerald-700">{detailData.total_received}</p>
                </div>
                <div className={`rounded-lg p-3 text-center ${detailData.total_missing > 0 ? 'bg-red-50' : 'bg-slate-50'}`}>
                  <p className={`text-xs ${detailData.total_missing > 0 ? 'text-red-600' : 'text-slate-500'}`}>Total Missing</p>
                  <p className={`text-2xl font-bold ${detailData.total_missing > 0 ? 'text-red-700' : 'text-slate-500'}`}>{detailData.total_missing}</p>
                </div>
                <div className="bg-slate-50 rounded-lg p-3 text-center">
                  <p className="text-xs text-slate-500">Tanggal Inspeksi</p>
                  <p className="text-sm font-bold text-slate-700">{fmtDate(detailData.inspection_date)}</p>
                </div>
              </div>
              <a href="#" onClick={async (e) => {
                e.preventDefault();
                try {
                  const res = await fetch(`/api/export-pdf?type=vendor-inspection&id=${detailData.id}`, { headers: { Authorization: `Bearer ${token}` } });
                  if (!res.ok) throw new Error('Export gagal');
                  const blob = await res.blob();
                  const url = window.URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `Inspeksi-${detailData.shipment_number || 'unknown'}.pdf`;
                  a.click();
                  window.URL.revokeObjectURL(url);
                } catch (err) { toast.error('Error: ' + err.message); }
              }}
                className="ml-3 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg font-medium hover:bg-blue-700 flex items-center gap-1.5 flex-shrink-0 cursor-pointer" data-testid="export-inspection-pdf">
                PDF Export
              </a>
            </div>
            {detailData.overall_notes && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                <strong>Catatan:</strong> {detailData.overall_notes}
              </div>
            )}
            {detailData.items?.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-100">
                      <th className="text-left px-3 py-2 text-xs">Produk / SKU</th>
                      <th className="text-right px-3 py-2 text-xs">Dikirim</th>
                      <th className="text-right px-3 py-2 text-xs text-emerald-700">Diterima</th>
                      <th className="text-right px-3 py-2 text-xs text-red-600">Missing</th>
                      <th className="text-left px-3 py-2 text-xs">Catatan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailData.items.map(item => (
                      <tr key={item.id} className="border-t border-slate-100">
                        <td className="px-3 py-2">
                          <p className="font-medium text-xs">{item.product_name}</p>
                          <p className="text-xs text-slate-400 font-mono">{item.sku} {item.size}/{item.color}</p>
                        </td>
                        <td className="px-3 py-2 text-right">{item.ordered_qty}</td>
                        <td className="px-3 py-2 text-right text-emerald-700 font-medium">{item.received_qty}</td>
                        <td className={`px-3 py-2 text-right font-medium ${item.missing_qty > 0 ? 'text-red-600' : 'text-slate-400'}`}>{item.missing_qty}</td>
                        <td className="px-3 py-2 text-xs text-slate-500">{item.condition_notes || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {/* Accessory items in detail */}
            {(detailData.accessory_items || []).length > 0 && (
              <div className="overflow-x-auto">
                <h5 className="text-sm font-semibold text-emerald-700 mb-2">Aksesoris ({detailData.accessory_items.length} item)</h5>
                <table className="w-full text-sm">
                  <thead><tr className="bg-emerald-50">
                    <th className="text-left px-3 py-2 text-xs text-emerald-700">Aksesoris</th>
                    <th className="text-left px-3 py-2 text-xs text-emerald-700">Kode</th>
                    <th className="text-right px-3 py-2 text-xs">Dibutuhkan</th>
                    <th className="text-right px-3 py-2 text-xs text-emerald-700">Diterima</th>
                    <th className="text-right px-3 py-2 text-xs text-red-600">Missing</th>
                    <th className="text-left px-3 py-2 text-xs">Catatan</th>
                  </tr></thead>
                  <tbody>{detailData.accessory_items.map(acc => (
                    <tr key={acc.id} className="border-t border-emerald-100">
                      <td className="px-3 py-2 font-medium text-xs">{acc.accessory_name}</td>
                      <td className="px-3 py-2 font-mono text-xs text-emerald-600">{acc.accessory_code || '-'}</td>
                      <td className="px-3 py-2 text-right">{acc.ordered_qty} {acc.unit || 'pcs'}</td>
                      <td className="px-3 py-2 text-right text-emerald-700 font-medium">{acc.received_qty}</td>
                      <td className={`px-3 py-2 text-right font-medium ${acc.missing_qty > 0 ? 'text-red-600' : 'text-slate-400'}`}>{acc.missing_qty}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{acc.condition_notes || '-'}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

// ─── VENDOR DEFECT REPORTS ─────────────────────────────────────────────────────


