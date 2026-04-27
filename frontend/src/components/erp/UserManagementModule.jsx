
import { useState, useEffect } from 'react';
import { Plus, Pencil, UserX, UserCheck, Trash2 } from 'lucide-react';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import { apiGet, apiPost, apiPut, apiDelete } from '../../lib/api';

const SYSTEM_ROLES = ['admin', 'vendor', 'buyer', 'superadmin'];

export default function UserManagementModule() {
  const [users, setUsers] = useState([]);
  const [customRoles, setCustomRoles] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [buyersList, setBuyersList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editData, setEditData] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'admin', status: 'active', vendor_id: '', buyer_id: '', customer_name: '' });

  useEffect(() => { fetchUsers(); fetchRoles(); fetchVendors(); fetchBuyers(); }, []);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await apiGet('/users');
      setUsers(Array.isArray(data) ? data : []);
    } catch (e) { setUsers([]); }
    setLoading(false);
  };

  const fetchRoles = async () => {
    try {
      const data = await apiGet('/roles');
      setCustomRoles(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
  };

  const fetchVendors = async () => {
    try {
      const data = await apiGet('/garments');
      setVendors(Array.isArray(data) ? data.filter(v => v.status === 'active') : []);
    } catch (e) { console.error(e); }
  };

  const fetchBuyers = async () => {
    try {
      const data = await apiGet('/buyers');
      setBuyersList(Array.isArray(data) ? data.filter(b => b.status === 'active') : []);
    } catch (e) { console.error(e); }
  };

  // All available roles: system + custom
  const allRoles = [...SYSTEM_ROLES, ...customRoles.map(r => r.name)];

  const openCreate = () => {
    setEditData(null);
    setForm({ name: '', email: '', password: '', role: 'admin', status: 'active', vendor_id: '', buyer_id: '', customer_name: '' });
    setShowModal(true);
  };

  const openEdit = (row) => {
    setEditData(row);
    setForm({ name: row.name, email: row.email, password: '', role: row.role, status: row.status, 
              vendor_id: row.vendor_id || '', buyer_id: row.buyer_id || '', customer_name: row.customer_name || '' });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const payload = { ...form };
    if (editData && !payload.password) delete payload.password;
    // Set customer_name from buyer if buyer role
    if (payload.role === 'buyer' && payload.buyer_id) {
      const buyer = buyersList.find(b => b.id === payload.buyer_id);
      if (buyer) payload.customer_name = buyer.buyer_name;
    }
    try {
      if (editData) {
        await apiPut(`/users/${editData.id}`, payload);
      } else {
        await apiPost('/users', payload);
      }
      setShowModal(false);
      fetchUsers();
    } catch (err) { alert(err.message || 'Gagal menyimpan user'); }
  };

  const toggleStatus = async (row) => {
    const newStatus = row.status === 'active' ? 'inactive' : 'active';
    try {
      await apiPut(`/users/${row.id}`, { status: newStatus });
      fetchUsers();
    } catch (e) { alert(e.message || 'Gagal mengubah status'); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/users/${confirmDelete.id}`);
      setConfirmDelete(null);
      fetchUsers();
    } catch (e) { alert(e.message || 'Gagal menghapus user'); }
  };

  const roleColors = {
    superadmin: 'bg-purple-100 text-purple-700', admin: 'bg-blue-100 text-blue-700',
    vendor: 'bg-emerald-100 text-emerald-700', buyer: 'bg-amber-100 text-amber-700',
    production: 'bg-cyan-100 text-cyan-700', finance: 'bg-orange-100 text-orange-700',
    management: 'bg-slate-100 text-slate-700',
  };

  const formatDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  const columns = [
    { key: 'avatar', label: '', render: (_, row) => (
      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold ${
        row.role === 'vendor' ? 'bg-emerald-600' : row.role === 'buyer' ? 'bg-amber-600' : 'bg-blue-600'
      }`}>{row.name?.[0]?.toUpperCase()}</div>
    )},
    { key: 'name', label: 'Nama' },
    { key: 'email', label: 'Email' },
    { key: 'role', label: 'Role', render: (v) => (
      <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${roleColors[v] || 'bg-indigo-100 text-indigo-700'}`}>{v}</span>
    )},
    { key: 'vendor_id', label: 'Link', render: (v, row) => {
      if (row.role === 'vendor' && v) return <span className="text-xs text-emerald-600">Vendor: {v.substring(0, 8)}...</span>;
      if (row.role === 'buyer' && row.buyer_id) return <span className="text-xs text-amber-600">Buyer: {row.customer_name || row.buyer_id?.substring(0, 8)}</span>;
      return '-';
    }},
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v} /> },
    { key: 'created_at', label: 'Dibuat', render: (v) => formatDate(v) },
    { key: 'actions', label: 'Aksi', render: (_, row) => (
      row.role !== 'superadmin' ? (
        <div className="flex items-center gap-1">
          <button onClick={() => openEdit(row)} className="p-1.5 rounded hover:bg-blue-50 text-blue-600" title="Edit"><Pencil className="w-4 h-4" /></button>
          <button onClick={() => toggleStatus(row)}
            className={`p-1.5 rounded ${row.status === 'active' ? 'hover:bg-amber-50 text-amber-500' : 'hover:bg-emerald-50 text-emerald-600'}`}
            title={row.status === 'active' ? 'Nonaktifkan' : 'Aktifkan'}>
            {row.status === 'active' ? <UserX className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
          </button>
          <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-500" title="Hapus"><Trash2 className="w-4 h-4" /></button>
        </div>
      ) : <span className="text-xs text-slate-400 italic">Protected</span>
    )}
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Manajemen User</h1>
          <p className="text-slate-500 text-sm mt-1">Kelola pengguna, role, dan hak akses sistem</p>
        </div>
        <span className="flex items-center gap-1.5 px-2.5 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span> Mode Superadmin
        </span>
      </div>

      {/* Role Legend */}
      <div className="flex flex-wrap gap-2">
        {[...Object.entries(roleColors), ...customRoles.map(r => [r.name, 'bg-indigo-100 text-indigo-700'])].map(([role, color]) => (
          <span key={role} className={`px-3 py-1 rounded-full text-xs font-medium capitalize ${color}`}>{role}</span>
        ))}
      </div>

      <DataTable columns={columns} data={users} searchKeys={['name', 'email', 'role']} storageKey="users"
        actions={
          <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700" data-testid="add-user-btn">
            <Plus className="w-4 h-4" /> Tambah User
          </button>
        }
      />

      {showModal && (
        <Modal title={editData ? 'Edit User' : 'Tambah User'} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Nama Lengkap *</label>
              <input required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.name} onChange={e => setForm({...form, name: e.target.value})} data-testid="user-name" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Email *</label>
              <input required type="email" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.email} onChange={e => setForm({...form, email: e.target.value})} data-testid="user-email" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Password {editData && <span className="text-slate-400 text-xs">(kosongkan jika tidak diubah)</span>}
              </label>
              <input type="password" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.password} onChange={e => setForm({...form, password: e.target.value})}
                placeholder={editData ? '--------' : 'Minimal 6 karakter'} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Role *</label>
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.role} onChange={e => setForm({...form, role: e.target.value})} data-testid="user-role">
                  <optgroup label="System Roles">
                    {SYSTEM_ROLES.map(r => <option key={r} value={r} className="capitalize">{r}</option>)}
                  </optgroup>
                  {customRoles.length > 0 && (
                    <optgroup label="Custom Roles">
                      {customRoles.map(r => <option key={r.name} value={r.name}>{r.name} ({(r.permissions || []).length} perms)</option>)}
                    </optgroup>
                  )}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Status</label>
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.status} onChange={e => setForm({...form, status: e.target.value})}>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>
            </div>

            {/* Vendor link for vendor role */}
            {form.role === 'vendor' && (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Link ke Vendor</label>
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.vendor_id} onChange={e => setForm({...form, vendor_id: e.target.value})}>
                  <option value="">— Pilih Vendor —</option>
                  {vendors.map(v => <option key={v.id} value={v.id}>{v.garment_name} ({v.garment_code})</option>)}
                </select>
              </div>
            )}

            {/* Buyer link for buyer role */}
            {form.role === 'buyer' && (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Link ke Buyer</label>
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.buyer_id} onChange={e => {
                    const buyer = buyersList.find(b => b.id === e.target.value);
                    setForm({...form, buyer_id: e.target.value, customer_name: buyer?.buyer_name || ''});
                  }}>
                  <option value="">— Pilih Buyer —</option>
                  {buyersList.map(b => <option key={b.id} value={b.id}>{b.buyer_name} ({b.buyer_code})</option>)}
                </select>
              </div>
            )}

            <div className="bg-amber-50 rounded-lg p-3 text-xs text-amber-700">
              {form.role === 'vendor' && 'Catatan: Akun vendor biasanya dibuat otomatis dari Data Vendor/Garmen'}
              {form.role === 'buyer' && 'Catatan: Akun buyer biasanya dibuat otomatis dari Data Buyer'}
              {!['vendor', 'buyer'].includes(form.role) && `Password default: User@123 | Role: ${form.role}`}
            </div>

            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700" data-testid="save-user-btn">
                {editData ? 'Simpan Perubahan' : 'Tambah User'}
              </button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm hover:bg-slate-50">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Hapus User?"
          message={`User "${confirmDelete.name}" (${confirmDelete.email}) akan dihapus permanen.`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
