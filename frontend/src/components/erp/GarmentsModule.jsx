
import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, ToggleLeft, ToggleRight, Copy, CheckCircle } from 'lucide-react';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import ImportExportPanel from './ImportExportPanel';
import { apiGet, apiPost, apiPut, apiDelete } from '../../lib/api';

export default function GarmentsModule({ token, userRole }) {
  const [garments, setGarments] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showCredModal, setShowCredModal] = useState(false);
  const [editData, setEditData] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [newCredentials, setNewCredentials] = useState(null);
  const [copied, setCopied] = useState('');
  const [form, setForm] = useState({ garment_code: '', garment_name: '', location: '', contact_person: '', phone: '', monthly_capacity: '', status: 'active' });

  const isSuperAdmin = userRole === 'superadmin';

  useEffect(() => { fetchGarments(); }, []);

  const fetchGarments = async (search = '') => {
    try {
      const url = search ? `/garments?search=${search}` : '/garments';
      const data = await apiGet(url);
      setGarments(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
  };

  const openCreate = () => {
    setEditData(null);
    setForm({ garment_code: '', garment_name: '', location: '', contact_person: '', phone: '', status: 'active' });
    setShowModal(true);
  };

  const openEdit = (row) => {
    setEditData(row);
    setForm({ garment_code: row.garment_code, garment_name: row.garment_name, location: row.location || '', contact_person: row.contact_person || '', phone: row.phone || '', monthly_capacity: row.monthly_capacity || '', status: row.status });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const data = editData
        ? await apiPut(`/garments/${editData.id}`, form)
        : await apiPost('/garments', form);
      setShowModal(false);
      if (!editData && data.vendor_account) {
        setNewCredentials(data.vendor_account);
        setShowCredModal(true);
      }
      fetchGarments();
    } catch (err) {
      alert(err.message || 'Gagal menyimpan vendor');
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/garments/${confirmDelete.id}`);
    } catch (e) { console.error(e); }
    setConfirmDelete(null);
    fetchGarments();
  };

  const toggleStatus = async (row) => {
    const newStatus = row.status === 'active' ? 'inactive' : 'active';
    try {
      await apiPut(`/garments/${row.id}`, { status: newStatus });
      fetchGarments();
    } catch (e) { console.error(e); }
  };

  const copyText = (text, key) => {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(''), 2000);
  };

  const columns = [
    { key: 'garment_code', label: 'Kode', render: (v) => <span className="font-mono text-xs font-bold text-slate-700">{v}</span> },
    { key: 'garment_name', label: 'Nama Vendor' },
    { key: 'location', label: 'Lokasi' },
    { key: 'contact_person', label: 'Contact Person' },
    { key: 'phone', label: 'Telepon' },
    { key: 'monthly_capacity', label: 'Kapasitas/Bulan', render: (v) => v ? <span className="text-sm font-medium text-blue-700">{Number(v).toLocaleString('id-ID')} pcs</span> : <span className="text-xs text-slate-400">-</span> },
    { key: 'login_email', label: 'Login Vendor', render: (v) => v ? <span className="text-xs font-mono text-blue-600">{v}</span> : <span className="text-xs text-slate-400">-</span> },
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v} /> },
    {
      key: 'actions', label: 'Aksi',
      render: (_, row) => (
        isSuperAdmin ? (
          <div className="flex items-center gap-1">
            <button onClick={() => openEdit(row)} className="p-1.5 rounded hover:bg-blue-50 text-blue-600 transition-colors" title="Edit"><Pencil className="w-4 h-4" /></button>
            <button onClick={() => toggleStatus(row)} className={`p-1.5 rounded transition-colors ${row.status === 'active' ? 'hover:bg-amber-50 text-amber-500' : 'hover:bg-emerald-50 text-emerald-600'}`} title={row.status === 'active' ? 'Nonaktifkan' : 'Aktifkan'}>
              {row.status === 'active' ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
            </button>
            <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-500 transition-colors" title="Hapus"><Trash2 className="w-4 h-4" /></button>
          </div>
        ) : <span className="text-xs text-slate-400 italic">—</span>
      )
    }
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Data Garmen / Vendor</h1>
          <p className="text-slate-500 text-sm mt-1">Kelola data vendor — akun Vendor Portal dibuat otomatis</p>
        </div>
        {isSuperAdmin && <span className="flex items-center gap-1.5 px-2.5 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium"><span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>Mode Superadmin</span>}
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-700">
        <strong>Info:</strong> Setiap vendor baru yang ditambahkan akan otomatis mendapatkan akun Vendor Portal. Simpan kredensial yang ditampilkan setelah penambahan vendor.
      </div>

      <DataTable
        columns={columns}
        data={garments}
        searchKeys={['garment_code', 'garment_name', 'location']}
        onSearch={fetchGarments}
        storageKey="vendorsGarments"
        actions={
          <div className="flex items-center gap-2">
            <ImportExportPanel token={token} importType="garments" exportType={null} onImportSuccess={() => fetchGarments()} />
            {isSuperAdmin && (
              <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors">
                <Plus className="w-4 h-4" /> Tambah Vendor
              </button>
            )}
          </div>
        }
      />

      {showModal && (
        <Modal title={editData ? 'Edit Vendor Garmen' : 'Tambah Vendor Garmen'} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Kode Garmen *</label>
                <input required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.garment_code} onChange={e => setForm({...form, garment_code: e.target.value})} placeholder="GRM-001" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Nama Vendor *</label>
                <input required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.garment_name} onChange={e => setForm({...form, garment_name: e.target.value})} placeholder="CV. Nama Garmen" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Lokasi</label>
              <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.location} onChange={e => setForm({...form, location: e.target.value})} placeholder="Bandung" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Contact Person</label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.contact_person} onChange={e => setForm({...form, contact_person: e.target.value})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Telepon</label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Kapasitas Bulanan (pcs) <span className="text-xs text-slate-400">opsional</span></label>
              <input type="number" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.monthly_capacity} onChange={e => setForm({...form, monthly_capacity: e.target.value})} placeholder="5000" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Status</label>
              <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.status} onChange={e => setForm({...form, status: e.target.value})}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
            {!editData && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700">
                Akun Vendor Portal akan dibuat otomatis. Catat kredensial yang ditampilkan setelah menyimpan.
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700">{editData ? 'Simpan Perubahan' : 'Tambah Vendor'}</button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm hover:bg-slate-50">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Credentials Modal */}
      {showCredModal && newCredentials && (
        <Modal title="Akun Vendor Portal Berhasil Dibuat" onClose={() => { setShowCredModal(false); setNewCredentials(null); }}>
          <div className="space-y-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
              <div className="flex items-center gap-2 text-emerald-700 mb-3">
                <CheckCircle className="w-5 h-5" />
                <span className="font-semibold">Akun vendor berhasil dibuat!</span>
              </div>
              <p className="text-sm text-emerald-600 mb-4">Berikan kredensial berikut kepada vendor untuk login ke Vendor Portal:</p>
              <div className="space-y-3">
                <div className="bg-white rounded-lg p-3 border border-emerald-100">
                  <p className="text-xs text-slate-500 mb-1">Email Login</p>
                  <div className="flex items-center justify-between">
                    <code className="text-sm font-mono text-slate-800">{newCredentials.email}</code>
                    <button onClick={() => copyText(newCredentials.email, 'email')} className="text-blue-500 hover:text-blue-700">
                      {copied === 'email' ? <CheckCircle className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div className="bg-white rounded-lg p-3 border border-emerald-100">
                  <p className="text-xs text-slate-500 mb-1">Password</p>
                  <div className="flex items-center justify-between">
                    <code className="text-sm font-mono font-bold text-slate-800">{newCredentials.password}</code>
                    <button onClick={() => copyText(newCredentials.password, 'password')} className="text-blue-500 hover:text-blue-700">
                      {copied === 'password' ? <CheckCircle className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </div>
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700">
              ⚠️ Simpan kredensial ini sekarang. Password tidak dapat dilihat kembali setelah modal ini ditutup.
            </div>
            <button onClick={() => { setShowCredModal(false); setNewCredentials(null); }} className="w-full bg-blue-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700">Saya sudah menyimpan kredensial</button>
          </div>
        </Modal>
      )}

      {confirmDelete && <ConfirmDialog title="Hapus Vendor?" message={`Vendor "${confirmDelete.garment_name}" dan akun Vendor Portal-nya akan dihapus permanen.`} onConfirm={handleDelete} onCancel={() => setConfirmDelete(null)} />}
    </div>
  );
}
