
import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, CheckCircle } from 'lucide-react';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import { apiGet, apiPost, apiPut, apiDelete } from '../../lib/api';

export default function ProductionProgressModule({ userRole }) {
  const [workOrders, setWorkOrders] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedWO, setSelectedWO] = useState(null);
  const [progressHistory, setProgressHistory] = useState([]);
  const [editProgress, setEditProgress] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [form, setForm] = useState({ work_order_id: '', completed_quantity: '', progress_date: '', notes: '' });
  const [editForm, setEditForm] = useState({ completed_quantity: '', progress_date: '', notes: '' });

  const isSuperAdmin = userRole === 'superadmin';

  useEffect(() => { fetchWorkOrders(); }, []);

  const fetchWorkOrders = async () => {
    try {
      const data = await apiGet('/work-orders');
      setWorkOrders(Array.isArray(data) ? data : []);
    } catch (e) { setWorkOrders([]); }
  };

  const openProgressModal = async (wo) => {
    setSelectedWO(wo);
    setForm({ work_order_id: wo.id, completed_quantity: '', progress_date: new Date().toISOString().split('T')[0], notes: '' });
    try {
      const data = await apiGet(`/production-progress?work_order_id=${wo.id}`);
      setProgressHistory(Array.isArray(data) ? data : []);
    } catch (e) { setProgressHistory([]); }
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await apiPost('/production-progress', { ...form, completed_quantity: Number(form.completed_quantity) });
      setShowModal(false);
      fetchWorkOrders();
    } catch (e) { alert(e.message || 'Gagal menyimpan progress'); }
  };

  const openEditProgress = (p) => {
    setEditProgress(p);
    setEditForm({
      completed_quantity: p.completed_quantity,
      progress_date: new Date(p.progress_date).toISOString().split('T')[0],
      notes: p.notes || ''
    });
    setShowEditModal(true);
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    try {
      await apiPut(`/production-progress/${editProgress.id}`, { ...editForm, completed_quantity: Number(editForm.completed_quantity) });
      setShowEditModal(false);
      const data = await apiGet(`/production-progress?work_order_id=${editProgress.work_order_id}`);
      setProgressHistory(Array.isArray(data) ? data : []);
      fetchWorkOrders();
    } catch (e) { alert(e.message || 'Gagal mengubah progress'); }
  };

  const handleDeleteProgress = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/production-progress/${confirmDelete.id}`);
      setConfirmDelete(null);
      const data = await apiGet(`/production-progress?work_order_id=${confirmDelete.work_order_id}`);
      setProgressHistory(Array.isArray(data) ? data : []);
      fetchWorkOrders();
    } catch (e) { alert(e.message || 'Gagal menghapus progress'); }
  };

  const getProgressPct = (wo) => !wo.quantity ? 0 : Math.min(100, Math.round(((wo.completed_quantity||0)/wo.quantity)*100));
  const remaining = (wo) => Math.max(0, wo.quantity - (wo.completed_quantity||0));

  const columns = [
    { key: 'distribution_code', label: 'Kode', render: (v) => <span className="font-bold text-blue-700 text-xs">{v}</span> },
    { key: 'po_number', label: 'No. PO' },
    { key: 'serial_numbers', label: 'No. Seri', render: (v) => {
      const sns = Array.isArray(v) ? v : [];
      return sns.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {sns.map(sn => (
            <span key={sn} className="px-1.5 py-0.5 bg-amber-50 border border-amber-200 rounded text-xs font-mono text-amber-700 font-semibold">{sn}</span>
          ))}
        </div>
      ) : <span className="text-slate-300 text-xs">—</span>;
    }},
    { key: 'garment_name', label: 'Garmen' },
    { key: 'quantity', label: 'Target', render: (v) => v?.toLocaleString('id-ID') },
    { key: 'completed_quantity', label: 'Selesai', render: (v) => <span className="font-semibold text-emerald-700">{(v||0).toLocaleString('id-ID')}</span> },
    { key: 'remaining', label: 'Sisa', render: (_, row) => <span className="font-semibold text-orange-600">{remaining(row).toLocaleString('id-ID')}</span> },
    {
      key: 'progress_bar', label: 'Progress',
      render: (_, row) => (
        <div className="flex items-center gap-2 min-w-[140px]">
          <div className="flex-1 bg-slate-100 rounded-full h-2">
            <div className={`h-2 rounded-full ${getProgressPct(row)>=100?'bg-emerald-500':'bg-blue-500'}`}
              style={{ width: `${getProgressPct(row)}%` }} />
          </div>
          <span className="text-xs font-medium w-10">{getProgressPct(row)}%</span>
        </div>
      )
    },
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v} /> },
    {
      key: 'actions', label: 'Aksi',
      render: (_, row) => (
        <button
          onClick={() => openProgressModal(row)}
          disabled={row.status === 'Completed'}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            row.status === 'Completed' ? 'bg-slate-100 text-slate-400 cursor-not-allowed' : 'bg-blue-600 text-white hover:bg-blue-700'
          }`}>
          <Plus className="w-3.5 h-3.5" /> Input Progress
        </button>
      )
    }
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Progres Produksi</h1>
        <p className="text-slate-500 text-sm mt-1">Catat dan pantau perkembangan produksi harian</p>
      </div>

      <DataTable columns={columns} data={workOrders} searchKeys={['distribution_code', 'po_number', 'garment_name']} storageKey="productionProgress" />

      {/* Input Progress Modal */}
      {showModal && selectedWO && (
        <Modal title={`Input Progress: ${selectedWO.distribution_code}`} onClose={() => setShowModal(false)} size="lg">
          <div className="space-y-5">
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-blue-50 rounded-lg p-3"><p className="text-xs text-blue-600">Target</p><p className="font-bold text-blue-800">{selectedWO.quantity?.toLocaleString('id-ID')} pcs</p></div>
              <div className="bg-emerald-50 rounded-lg p-3"><p className="text-xs text-emerald-600">Selesai</p><p className="font-bold text-emerald-800">{(selectedWO.completed_quantity||0)?.toLocaleString('id-ID')} pcs</p></div>
              <div className="bg-orange-50 rounded-lg p-3"><p className="text-xs text-orange-600">Sisa</p><p className="font-bold text-orange-800">{remaining(selectedWO).toLocaleString('id-ID')} pcs</p></div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1"><span>Progress</span><span className="font-bold">{getProgressPct(selectedWO)}%</span></div>
              <div className="w-full bg-slate-100 rounded-full h-3">
                <div className="bg-blue-500 h-3 rounded-full" style={{ width: `${getProgressPct(selectedWO)}%` }} />
              </div>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4 border-t pt-4">
              <h4 className="font-semibold text-slate-700">Tambah Laporan Progress</h4>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Tanggal *</label>
                  <input required type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.progress_date} onChange={e => setForm({...form, progress_date: e.target.value})} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Jumlah Selesai *</label>
                  <input required type="number" min="1" max={remaining(selectedWO)}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.completed_quantity} onChange={e => setForm({...form, completed_quantity: e.target.value})}
                    placeholder={`Max: ${remaining(selectedWO)}`} />
                </div>
              </div>
              <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} placeholder="Catatan opsional..." />
              <div className="flex gap-3">
                <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700">Simpan Progress</button>
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm hover:bg-slate-50">Batal</button>
              </div>
            </form>

            {progressHistory.length > 0 && (
              <div className="border-t pt-4">
                <h4 className="font-semibold text-slate-700 mb-2">Riwayat Progress ({progressHistory.length})</h4>
                <div className="space-y-2 max-h-56 overflow-y-auto">
                  {progressHistory.map(p => (
                    <div key={p.id} className="flex items-center justify-between p-2.5 bg-slate-50 rounded-lg">
                      <div>
                        <span className="text-sm font-medium">{new Date(p.progress_date).toLocaleDateString('id-ID',{day:'numeric',month:'short',year:'numeric'})}</span>
                        {p.notes && <p className="text-xs text-slate-500">{p.notes}</p>}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-blue-700">{p.completed_quantity?.toLocaleString('id-ID')} pcs</span>
                        {isSuperAdmin && (
                          <div className="flex gap-1">
                            <button onClick={() => openEditProgress(p)} className="p-1 rounded hover:bg-amber-50 text-amber-500" title="Edit">
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => setConfirmDelete(p)} className="p-1 rounded hover:bg-red-50 text-red-500" title="Hapus">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Edit Progress Modal */}
      {showEditModal && editProgress && isSuperAdmin && (
        <Modal title="Edit Progress" onClose={() => setShowEditModal(false)} size="sm">
          <form onSubmit={handleEditSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Tanggal</label>
              <input type="date" required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={editForm.progress_date} onChange={e => setEditForm({...editForm, progress_date: e.target.value})} />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Jumlah Selesai</label>
              <input type="number" min="1" required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={editForm.completed_quantity} onChange={e => setEditForm({...editForm, completed_quantity: e.target.value})} />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Catatan</label>
              <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={editForm.notes} onChange={e => setEditForm({...editForm, notes: e.target.value})} />
            </div>
            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700">Simpan</button>
              <button type="button" onClick={() => setShowEditModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Hapus Data Progress?"
          message={`Data progress ${confirmDelete.completed_quantity} pcs pada ${new Date(confirmDelete.progress_date).toLocaleDateString('id-ID')} akan dihapus. Total selesai pada work order akan direcalculate.`}
          onConfirm={handleDeleteProgress}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
