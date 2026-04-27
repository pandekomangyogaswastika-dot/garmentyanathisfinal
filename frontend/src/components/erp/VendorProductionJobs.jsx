import { useState, useEffect } from 'react';
import { Plus, Search, AlertTriangle, Briefcase, X, Download, ChevronDown, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import Modal from './Modal';
import { MiniBar } from './VendorShared';

export default function VendorProductionJobs({ token, user }) {
  const [jobs, setJobs] = useState([]);
  const [receivedShipments, setReceivedShipments] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [detailJob, setDetailJob] = useState(null);
  const [selectedShipment, setSelectedShipment] = useState(null);
  const [form, setForm] = useState({ vendor_shipment_id: '', notes: '' });
  const [loading, setLoading] = useState(false);
  const [expandedJobs, setExpandedJobs] = useState({});
  const [searchShipment, setSearchShipment] = useState('');
  const [jobSearch, setJobSearch] = useState('');

  useEffect(() => { fetchAll(); }, []);

  const fetchAll = async () => {
    const [jRes, sRes] = await Promise.all([
      fetch('/api/production-jobs', { headers: { Authorization: `Bearer ${token}` } }),
      fetch('/api/vendor-shipments', { headers: { Authorization: `Bearer ${token}` } }),
    ]);
    const [jData, sData] = await Promise.all([jRes.json(), sRes.json()]);
    setJobs(Array.isArray(jData) ? jData : []);
    const allShipments = Array.isArray(sData) ? sData : [];
    const existingJobShipmentIds = new Set((Array.isArray(jData) ? jData : []).map(j => j.vendor_shipment_id));
    setReceivedShipments(allShipments.filter(s => s.status === 'Received' && !existingJobShipmentIds.has(s.id) && s.inspection_status === 'Inspected' && !s.parent_shipment_id));
  };

  const loadShipmentPreview = async (shipmentId) => {
    const ship = receivedShipments.find(s => s.id === shipmentId);
    setSelectedShipment(ship || null);
    setForm(f => ({ ...f, vendor_shipment_id: shipmentId }));
    if (shipmentId && !ship?.items?.length) {
      const res = await fetch(`/api/vendor-shipment-items?shipment_id=${shipmentId}`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (Array.isArray(data)) setSelectedShipment(prev => prev ? { ...prev, items: data } : ship);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.vendor_shipment_id) { toast.error('Pilih shipment terlebih dahulu'); return; }
    setLoading(true);
    const res = await fetch('/api/production-jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ ...form, vendor_id: user.vendor_id })
    });
    const data = await res.json();
    setLoading(false);
    if (!res.ok) { toast.error(data.detail || data.error || 'Gagal membuat Production Job'); return; }
    setShowModal(false);
    fetchAll();
  };

  const openDetail = async (job) => {
    const res = await fetch(`/api/production-jobs/${job.id}`, { headers: { Authorization: `Bearer ${token}` } });
    const data = await res.json();
    setDetailJob(data);
    setShowDetail(true);
  };

  const toggleJob = (jobId) => setExpandedJobs(prev => ({ ...prev, [jobId]: !prev[jobId] }));

  const fmtDate = d => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Pekerjaan Produksi</h1>
          <p className="text-slate-500 text-sm mt-1">Buat Job Produksi dari bahan yang sudah diterima & diinspeksi. Qty otomatis = Material Diterima.</p>
        </div>
        <button
          onClick={() => { setForm({ vendor_shipment_id: '', notes: '' }); setSelectedShipment(null); setShowModal(true); }}
          disabled={receivedShipments.length === 0}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Plus className="w-4 h-4" /> Buat Job Produksi
        </button>
      </div>

      {receivedShipments.length === 0 && jobs.length === 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-700">
          <p className="font-semibold">Belum ada bahan yang bisa diproses</p>
          <p className="mt-1 text-amber-600">Pastikan ada Vendor Shipment yang sudah dikonfirmasi diterima <strong>dan</strong> diinspeksi di menu <strong>Penerimaan Material</strong>.</p>
        </div>
      )}

      {receivedShipments.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-sm text-blue-700">
          <p className="font-semibold">✅ {receivedShipments.length} Shipment siap dibuatkan Job Produksi</p>
          <p className="text-xs mt-0.5 text-blue-600">Qty production job = qty material yang diterima (bukan qty PO)</p>
        </div>
      )}

      <div className="space-y-3">
        {jobs.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
            <Briefcase className="w-12 h-12 mx-auto mb-3 text-slate-300" />
            <p className="text-slate-400 font-medium">Belum ada Production Job</p>
            <p className="text-xs text-slate-400 mt-1">Konfirmasi penerimaan & inspeksi bahan, lalu buat Job Produksi</p>
          </div>
        ) : jobs.map(job => {
          const isExpanded = expandedJobs[job.id];
          const isOverdue = job.deadline && new Date(job.deadline) < new Date() && job.status !== 'Completed';
          const hasChildren = (job.child_jobs || []).length > 0;
          return (
            <div key={job.id} className={`bg-white rounded-xl border shadow-sm ${job.status === 'Completed' ? 'border-emerald-200' : 'border-slate-200'}`}>
              <div className="p-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="font-bold text-slate-800 text-lg">{job.job_number}</span>
                      {hasChildren && (
                        <span className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full text-xs font-medium">
                          +{job.child_jobs.length} child job
                        </span>
                      )}
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${job.status === 'Completed' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'}`}>
                        {job.status}
                      </span>
                      {isOverdue && (
                        <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded-full text-xs font-medium flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" /> Overdue
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">
                      PO: <strong>{job.po_number || '-'}</strong> • Shipment: {job.shipment_number} • Customer: {job.customer_name || '-'}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Deadline: {fmtDate(job.deadline)} • {job.item_count || 0} SKU
                    </p>
                    {/* Serial Numbers */}
                    {(job.serial_numbers || []).length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {job.serial_numbers.map(sn => (
                          <span key={sn} className="px-2 py-0.5 bg-amber-50 border border-amber-200 rounded text-xs font-mono text-amber-700 font-semibold">
                            Serial: {sn}
                          </span>
                        ))}
                      </div>
                    )}
                    {/* Progress Bar (parent + children combined) */}
                    {(job.total_available || 0) > 0 && (
                      <div className="mt-3 max-w-xs">
                        <div className="flex justify-between text-xs text-slate-500 mb-1">
                          <span>Progress (incl. child jobs)</span>
                          <span>{(job.total_produced || 0).toLocaleString('id-ID')} / {(job.total_available || 0).toLocaleString('id-ID')} pcs</span>
                        </div>
                        <MiniBar pct={job.progress_pct || 0} />
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 ml-4">
                    <button onClick={() => toggleJob(job.id)}
                      className="px-3 py-1.5 border border-slate-200 text-slate-600 rounded-lg text-xs hover:bg-slate-50">
                      {isExpanded ? '▲ Tutup' : '▼ Detail'}
                    </button>
                    <button onClick={() => openDetail(job)}
                      className="px-3 py-1.5 border border-blue-200 text-blue-600 rounded-lg text-xs hover:bg-blue-50">
                      Detail Lengkap
                    </button>
                  </div>
                </div>

                {/* Expandable Item Detail */}
                {isExpanded && (
                  <div className="mt-4 border-t border-slate-100 pt-4">
                    <div className="overflow-x-auto rounded-xl border border-slate-200">
                      <table className="w-full text-xs">
                        <thead className="bg-slate-50">
                          <tr>
                            {['Serial', 'SKU', 'Produk', 'Size', 'Warna', 'Qty PO', 'Diterima', 'Diproduksi', 'Sisa', 'Progress'].map(h => (
                              <th key={h} className={`text-left px-3 py-2 font-semibold ${h === 'Serial' ? 'text-amber-600' : 'text-slate-500'}`}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(job.child_jobs || []).length > 0 && (
                            <tr><td colSpan={10} className="px-3 py-1 bg-blue-50 text-xs text-blue-600 font-semibold">Job Utama</td></tr>
                          )}
                          {/* Note: parent job items shown in detail modal */}
                          <tr><td colSpan={10} className="px-3 py-2 text-center text-slate-400 text-xs">Klik "Detail Lengkap" untuk melihat semua item</td></tr>
                        </tbody>
                      </table>
                    </div>
                    {/* Child jobs */}
                    {(job.child_jobs || []).length > 0 && (
                      <div className="mt-3 space-y-2">
                        <p className="text-xs font-semibold text-slate-500">Child Jobs (Auto-dibuat dari shipment tambahan):</p>
                        {job.child_jobs.map(child => (
                          <div key={child.id} className="ml-6 pl-4 border-l-2 border-purple-200 bg-purple-50/30 rounded-r-lg p-3">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-purple-700 text-sm">{child.job_number}</span>
                              <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${child.shipment_type === 'ADDITIONAL' ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700'}`}>
                                {child.shipment_type}
                              </span>
                              <span className={`px-1.5 py-0.5 rounded text-xs ${child.status === 'Completed' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                                {child.status}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Create Modal */}
      {showModal && (
        <Modal title="Buat Job Produksi" onClose={() => setShowModal(false)} size="lg">
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
              <p className="font-medium">Qty produksi = Material yang DITERIMA (bukan qty PO)</p>
              <p className="text-xs mt-1">Jika material kurang karena ada yang hilang/cacat, sistem akan membuat Child Job otomatis saat shipment tambahan diterima dan diinspeksi.</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Pilih Shipment yang Diterima & Diinspeksi *</label>
              {/* Search Input */}
              <input
                type="text"
                placeholder="🔍 Cari nomor shipment, PO, atau tanggal..."
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 mb-2"
                value={searchShipment}
                onChange={e => setSearchShipment(e.target.value)}
              />
              <select required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                value={form.vendor_shipment_id} onChange={e => loadShipmentPreview(e.target.value)}>
                <option value="">— Pilih Shipment ({receivedShipments.filter(s => {
                  const q = searchShipment.toLowerCase();
                  return !q || s.shipment_number?.toLowerCase().includes(q) || s.po_number?.toLowerCase().includes(q);
                }).length} tersedia) —</option>
                {/* Group: Shipment NORMAL */}
                {receivedShipments.filter(s => {
                  const q = searchShipment.toLowerCase();
                  return (!s.shipment_type || s.shipment_type === 'NORMAL') && (!q || s.shipment_number?.toLowerCase().includes(q) || s.po_number?.toLowerCase().includes(q) || fmtDate(s.shipment_date).includes(q));
                }).length > 0 && (
                  <optgroup label="── Shipment Normal ──">
                    {receivedShipments.filter(s => {
                      const q = searchShipment.toLowerCase();
                      return (!s.shipment_type || s.shipment_type === 'NORMAL') && (!q || s.shipment_number?.toLowerCase().includes(q) || s.po_number?.toLowerCase().includes(q) || fmtDate(s.shipment_date).includes(q));
                    }).map(s => (
                      <option key={s.id} value={s.id}>
                        {s.shipment_number} | PO: {s.po_number || '-'} | {fmtDate(s.shipment_date)} | {(s.items || []).length} item
                      </option>
                    ))}
                  </optgroup>
                )}
                {/* Group: Shipment ADDITIONAL */}
                {receivedShipments.filter(s => {
                  const q = searchShipment.toLowerCase();
                  return s.shipment_type === 'ADDITIONAL' && (!q || s.shipment_number?.toLowerCase().includes(q) || s.po_number?.toLowerCase().includes(q));
                }).length > 0 && (
                  <optgroup label="── Shipment Tambahan (Additional) ──">
                    {receivedShipments.filter(s => {
                      const q = searchShipment.toLowerCase();
                      return s.shipment_type === 'ADDITIONAL' && (!q || s.shipment_number?.toLowerCase().includes(q) || s.po_number?.toLowerCase().includes(q));
                    }).map(s => (
                      <option key={s.id} value={s.id}>
                        ➕ {s.shipment_number} | PO: {s.po_number || '-'} | {fmtDate(s.shipment_date)} | {(s.items || []).length} item
                      </option>
                    ))}
                  </optgroup>
                )}
                {/* Group: Shipment REPLACEMENT */}
                {receivedShipments.filter(s => {
                  const q = searchShipment.toLowerCase();
                  return s.shipment_type === 'REPLACEMENT' && (!q || s.shipment_number?.toLowerCase().includes(q) || s.po_number?.toLowerCase().includes(q));
                }).length > 0 && (
                  <optgroup label="── Shipment Pengganti (Replacement) ──">
                    {receivedShipments.filter(s => {
                      const q = searchShipment.toLowerCase();
                      return s.shipment_type === 'REPLACEMENT' && (!q || s.shipment_number?.toLowerCase().includes(q) || s.po_number?.toLowerCase().includes(q));
                    }).map(s => (
                      <option key={s.id} value={s.id}>
                        🔄 {s.shipment_number} | PO: {s.po_number || '-'} | {fmtDate(s.shipment_date)} | {(s.items || []).length} item
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              {receivedShipments.length === 0 && (
                <p className="text-xs text-amber-600 mt-1">Tidak ada shipment yang siap. Konfirmasi penerimaan & inspeksi di menu Penerimaan Material.</p>
              )}
            </div>

            {selectedShipment && (
              <div className="bg-slate-50 rounded-xl p-4 space-y-3">
                <p className="text-sm font-semibold text-slate-700">Preview: {selectedShipment.shipment_number}</p>
                <div className="space-y-2">
                  {(selectedShipment.items || []).map((item, idx) => (
                    <div key={item.id || idx} className="bg-white rounded-lg p-3 border border-slate-200">
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="font-bold text-slate-800 text-sm">{item.product_name}</p>
                          <p className="text-slate-500 font-mono text-xs mt-0.5">SKU: {item.sku || '-'} · {item.size || '-'}/{item.color || '-'}</p>
                          {item.serial_number && (
                            <p className="text-amber-700 font-mono text-xs mt-0.5 font-semibold">Serial: {item.serial_number}</p>
                          )}
                        </div>
                        <div className="text-right">
                          <p className="text-blue-700 font-bold text-sm">{(item.qty_sent || 0).toLocaleString('id-ID')} pcs</p>
                          <p className="text-slate-400 text-xs mt-0.5">🔒 Terkunci</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-2 text-xs text-amber-700">
                  ⚠️ Qty job = qty material diterima dari inspeksi. Vendor hanya bisa input progress.
                </div>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Catatan (opsional)</label>
              <textarea rows="2" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Catatan tambahan..." />
            </div>

            <div className="flex gap-3">
              <button type="submit" disabled={loading || !form.vendor_shipment_id}
                className="flex-1 bg-emerald-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50">
                {loading ? 'Membuat...' : 'Buat Job Produksi'}
              </button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm hover:bg-slate-50">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Detail Modal */}
      {showDetail && detailJob && (
        <Modal title={`Detail Job: ${detailJob.job_number}`} onClose={() => setShowDetail(false)} size="xl">
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              {[
                { l: 'No. Job', v: <span className="font-bold text-blue-700">{detailJob.job_number}</span> },
                { l: 'Status', v: <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${detailJob.status === 'Completed' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'}`}>{detailJob.status}</span> },
                { l: 'PO', v: detailJob.po_number || '-' },
                { l: 'Shipment', v: detailJob.shipment_number },
                { l: 'Customer', v: detailJob.customer_name || '-' },
                { l: 'Deadline', v: fmtDate(detailJob.deadline) },
              ].map(it => (
                <div key={it.l} className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">{it.l}</p>
                  <div className="font-medium text-sm mt-0.5">{it.v}</div>
                </div>
              ))}
            </div>
            {/* Child jobs info */}
            {(detailJob.child_jobs || []).length > 0 && (
              <div className="bg-purple-50 border border-purple-200 rounded-xl p-3">
                <p className="text-sm font-semibold text-purple-700 mb-2">Child Jobs ({detailJob.child_jobs.length})</p>
                <div className="space-y-1">
                  {detailJob.child_jobs.map(c => (
                    <div key={c.id} className="flex items-center gap-2 text-xs">
                      <span className="font-bold text-purple-600">{c.job_number}</span>
                      <span className={`px-1.5 py-0.5 rounded ${c.shipment_type === 'ADDITIONAL' ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700'}`}>{c.shipment_type}</span>
                      <span className="text-slate-500">{c.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {(detailJob.items || []).length > 0 && (
              <div>
                <h4 className="font-semibold text-slate-700 mb-2">Item Produksi (Terkunci 🔒)</h4>
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        {['Serial 🏷️', 'Produk', 'SKU 🔒', 'Size 🔒', 'Warna 🔒', 'Qty PO 🔒', 'Tersedia 🔒', 'Diproduksi', 'Sisa', 'Progress'].map(h => (
                          <th key={h} className={`text-left px-3 py-2 text-xs font-semibold ${h === 'Serial 🏷️' ? 'text-amber-600' : 'text-slate-500'}`}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detailJob.items.map(item => {
                        const avail = item.available_qty ?? item.shipment_qty ?? 0;
                        const pct = avail > 0 ? Math.round((item.produced_qty / avail) * 100) : 0;
                        return (
                          <tr key={item.id} className="border-t border-slate-100 hover:bg-slate-50">
                            <td className="px-3 py-2.5 font-mono text-xs text-amber-700 font-semibold bg-amber-50/30">{item.serial_number || <span className="text-slate-300">—</span>}</td>
                            <td className="px-3 py-2.5 font-medium">{item.product_name}</td>
                            <td className="px-3 py-2.5 font-mono text-xs text-blue-700">{item.sku || '-'}</td>
                            <td className="px-3 py-2.5 text-xs text-center">{item.size || '-'}</td>
                            <td className="px-3 py-2.5 text-xs text-center">{item.color || '-'}</td>
                            <td className="px-3 py-2.5 text-right text-slate-500">{(item.ordered_qty || 0).toLocaleString('id-ID')}</td>
                            <td className="px-3 py-2.5 text-right font-medium text-blue-700">{avail.toLocaleString('id-ID')}</td>
                            <td className="px-3 py-2.5 text-right font-bold text-emerald-700">{(item.produced_qty || 0).toLocaleString('id-ID')}</td>
                            <td className="px-3 py-2.5 text-right text-orange-600">{Math.max(0, avail - item.produced_qty).toLocaleString('id-ID')}</td>
                            <td className="px-3 py-2.5 min-w-28"><MiniBar pct={pct} /></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

// ─── VENDOR PROGRESS (per SKU from Production Job) ───────────────────────────


