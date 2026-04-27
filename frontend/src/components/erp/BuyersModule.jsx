import { useState, useEffect, useCallback } from 'react';
import { Plus, Edit2, Trash2, Users, Search, X, Eye, EyeOff } from 'lucide-react';
import { useSortableTable, SortableHeader } from './useSortableTable';
import { apiGet, apiPost, apiPut, apiDelete } from '../../lib/api';

export default function BuyersModule({ token, userRole }) {
  const [buyers, setBuyers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [form, setForm] = useState({ buyer_code: '', buyer_name: '', contact_person: '', phone: '', address: '', email: '' });
  const [search, setSearch] = useState('');
  const [showPw, setShowPw] = useState({});

  const fetchBuyers = useCallback(async () => {
    setLoading(true);
    try {
      const params = search ? `?search=${encodeURIComponent(search)}` : '';
      setBuyers(await apiGet(`/buyers${params}`));
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => { fetchBuyers(); }, [fetchBuyers]);

  // Phase 8.4 — sortable table
  const { sortedData: sortedBuyers, sortKey, sortDir, toggleSort } = useSortableTable(buyers, {
    storageKey: 'buyers',
    defaultKey: 'buyer_code',
    defaultDir: 'asc',
  });

  const handleSave = async () => {
    try {
      if (editItem) {
        await apiPut(`/buyers/${editItem.id}`, form);
      } else {
        await apiPost('/buyers', form);
      }
      fetchBuyers();
      setShowForm(false);
      setEditItem(null);
      setForm({ buyer_code: '', buyer_name: '', contact_person: '', phone: '', address: '', email: '' });
    } catch (e) { alert(e.message || 'Error'); }
  };

  const handleEdit = (item) => {
    setEditItem(item);
    setForm({ buyer_code: item.buyer_code || '', buyer_name: item.buyer_name || '', contact_person: item.contact_person || '', phone: item.phone || '', address: item.address || '', email: item.email || '' });
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus buyer ini? Akun portal buyer juga akan dihapus.')) return;
    try { await apiDelete(`/buyers/${id}`); } catch (e) {}
    fetchBuyers();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Data Buyer</h2>
          <p className="text-slate-500 text-sm mt-1">Kelola master data buyer — akun portal buyer otomatis dibuat</p>
        </div>
        <button onClick={() => { setShowForm(true); setEditItem(null); setForm({ buyer_code: '', buyer_name: '', contact_person: '', phone: '', address: '', email: '' }); }}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition" data-testid="add-buyer-btn">
          <Plus className="w-4 h-4" /> Tambah Buyer
        </button>
      </div>

      {/* Search */}
      <div className="flex items-center gap-2 border border-slate-200 rounded-lg px-3 py-2 bg-white max-w-md">
        <Search className="w-4 h-4 text-slate-400" />
        <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari buyer..."
               className="flex-1 bg-transparent text-sm focus:outline-none" data-testid="buyer-search" />
        {search && <button onClick={() => setSearch('')}><X className="w-4 h-4 text-slate-400" /></button>}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <SortableHeader columnKey="buyer_code" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Kode</SortableHeader>
              <SortableHeader columnKey="buyer_name" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Nama Buyer</SortableHeader>
              <SortableHeader columnKey="contact_person" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Contact</SortableHeader>
              <SortableHeader columnKey="phone" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Phone</SortableHeader>
              <SortableHeader columnKey="login_email" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Email Login</SortableHeader>
              <th className="text-left px-4 py-3 font-medium text-slate-600">Password</th>
              <th className="text-right px-4 py-3 font-medium text-slate-600">Aksi</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="7" className="text-center py-8 text-slate-400">Memuat...</td></tr>
            ) : sortedBuyers.length === 0 ? (
              <tr><td colSpan="7" className="text-center py-8 text-slate-400">Belum ada buyer</td></tr>
            ) : sortedBuyers.map(b => (
              <tr key={b.id} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-3 font-medium text-slate-800">{b.buyer_code || '-'}</td>
                <td className="px-4 py-3 font-medium">{b.buyer_name}</td>
                <td className="px-4 py-3">{b.contact_person || '-'}</td>
                <td className="px-4 py-3">{b.phone || '-'}</td>
                <td className="px-4 py-3 text-blue-600 text-xs">{b.login_email || '-'}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-mono">{showPw[b.id] ? b.buyer_password_plain || '-' : '********'}</span>
                    <button onClick={() => setShowPw(p => ({...p, [b.id]: !p[b.id]}))} className="text-slate-400 hover:text-slate-600">
                      {showPw[b.id] ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => handleEdit(b)} className="p-1 hover:bg-slate-100 rounded"><Edit2 className="w-4 h-4 text-slate-500" /></button>
                  {userRole === 'superadmin' && (
                    <button onClick={() => handleDelete(b.id)} className="p-1 hover:bg-red-50 rounded ml-1"><Trash2 className="w-4 h-4 text-red-500" /></button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal Form */}
      {showForm && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-slate-800 mb-4">{editItem ? 'Edit Buyer' : 'Tambah Buyer'}</h3>
            <p className="text-sm text-slate-500 mb-4">Akun portal buyer akan otomatis dibuat</p>
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Kode Buyer *</label>
                <input value={form.buyer_code} onChange={e => setForm({...form, buyer_code: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="BYR-001" data-testid="buyer-code" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Nama Buyer *</label>
                <input value={form.buyer_name} onChange={e => setForm({...form, buyer_name: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="PT Buyer Corp" data-testid="buyer-name" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Contact Person</label>
                <input value={form.contact_person} onChange={e => setForm({...form, contact_person: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="John Doe" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Telepon</label>
                <input value={form.phone} onChange={e => setForm({...form, phone: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="08123456789" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Alamat</label>
                <textarea value={form.address} onChange={e => setForm({...form, address: e.target.value})}
                          className="w-full border rounded-lg px-3 py-2 text-sm" rows="2" placeholder="Alamat lengkap..." />
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowForm(false)} className="flex-1 py-2 border rounded-lg text-sm text-slate-600 hover:bg-slate-50">Batal</button>
              <button onClick={handleSave} disabled={!form.buyer_code || !form.buyer_name} className="flex-1 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50" data-testid="save-buyer-btn">Simpan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
