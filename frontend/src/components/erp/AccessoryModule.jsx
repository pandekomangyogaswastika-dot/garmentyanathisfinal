import { useState, useEffect, useCallback } from 'react';
import { Plus, Edit2, Trash2, Search, X } from 'lucide-react';
import { useSortableTable, SortableHeader } from './useSortableTable';
import { apiGet, apiPost, apiPut, apiDelete } from '../../lib/api';

const emptyForm = () => ({ accessory_name: '', accessory_code: '', category: '', unit: 'pcs', description: '' });

// Normalize a record coming from the API to always expose canonical fields
// (`accessory_name` / `accessory_code`). Legacy docs that still use
// `name` / `code` will be transparently mapped for display and editing.
const normalize = (acc = {}) => ({
  ...acc,
  accessory_name: acc.accessory_name || acc.name || '',
  accessory_code: acc.accessory_code || acc.code || '',
});

export default function AccessoryModule({ token, userRole }) {
  const [accessories, setAccessories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [search, setSearch] = useState('');

  const fetchAccessories = useCallback(async () => {
    setLoading(true);
    try {
      const params = search ? `?search=${encodeURIComponent(search)}` : '';
      const raw = await apiGet(`/accessories${params}`);
      setAccessories(Array.isArray(raw) ? raw.map(normalize) : []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => { fetchAccessories(); }, [fetchAccessories]);

  // Phase 8.4 — sortable table with persisted state
  const { sortedData: sortedAccessories, sortKey, sortDir, toggleSort } = useSortableTable(accessories, {
    storageKey: 'accessories',
    defaultKey: 'accessory_code',
    defaultDir: 'asc',
  });

  const handleSave = async () => {
    try {
      if (editItem) {
        await apiPut(`/accessories/${editItem.id}`, form);
      } else {
        await apiPost('/accessories', form);
      }
      fetchAccessories();
      setShowForm(false);
      setEditItem(null);
      setForm(emptyForm());
    } catch (e) { console.error(e); }
  };

  const handleEdit = (item) => {
    const n = normalize(item);
    setEditItem(item);
    setForm({
      accessory_name: n.accessory_name,
      accessory_code: n.accessory_code,
      category: item.category || '',
      unit: item.unit || 'pcs',
      description: item.description || '',
    });
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus aksesoris ini?')) return;
    try { await apiDelete(`/accessories/${id}`); } catch (e) {}
    fetchAccessories();
  };

  return (
    <div className="space-y-6" data-testid="accessory-module">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Data Aksesoris</h2>
          <p className="text-slate-500 text-sm mt-1">Kelola master data aksesoris untuk produksi garmen</p>
        </div>
        <button onClick={() => { setShowForm(true); setEditItem(null); setForm(emptyForm()); }}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition" data-testid="add-accessory-btn">
          <Plus className="w-4 h-4" /> Tambah Aksesoris
        </button>
      </div>

      {/* Search */}
      <div className="flex items-center gap-2 border border-slate-200 rounded-lg px-3 py-2 bg-white max-w-md">
        <Search className="w-4 h-4 text-slate-400" />
        <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari aksesoris..."
               className="flex-1 bg-transparent text-sm focus:outline-none" data-testid="accessory-search" />
        {search && <button onClick={() => setSearch('')}><X className="w-4 h-4 text-slate-400" /></button>}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <SortableHeader columnKey="accessory_code" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Kode</SortableHeader>
              <SortableHeader columnKey="accessory_name" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Nama</SortableHeader>
              <SortableHeader columnKey="category" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Kategori</SortableHeader>
              <SortableHeader columnKey="unit" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Unit</SortableHeader>
              <SortableHeader columnKey="status" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="px-4 py-3 font-medium text-slate-600">Status</SortableHeader>
              <th className="text-right px-4 py-3 font-medium text-slate-600">Aksi</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6" className="text-center py-8 text-slate-400">Memuat...</td></tr>
            ) : sortedAccessories.length === 0 ? (
              <tr><td colSpan="6" className="text-center py-8 text-slate-400">Belum ada aksesoris</td></tr>
            ) : sortedAccessories.map(acc => (
              <tr key={acc.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`acc-row-${acc.id}`}>
                <td className="px-4 py-3 font-medium text-slate-800">{acc.accessory_code || '-'}</td>
                <td className="px-4 py-3">{acc.accessory_name}</td>
                <td className="px-4 py-3">{acc.category || '-'}</td>
                <td className="px-4 py-3">{acc.unit || 'pcs'}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${acc.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                    {acc.status || 'active'}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => handleEdit(acc)} className="p-1 hover:bg-slate-100 rounded" data-testid={`edit-acc-${acc.id}`}><Edit2 className="w-4 h-4 text-slate-500" /></button>
                  {userRole === 'superadmin' && (
                    <button onClick={() => handleDelete(acc.id)} className="p-1 hover:bg-red-50 rounded ml-1" data-testid={`del-acc-${acc.id}`}><Trash2 className="w-4 h-4 text-red-500" /></button>
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
            <h3 className="text-lg font-bold text-slate-800 mb-4">{editItem ? 'Edit Aksesoris' : 'Tambah Aksesoris'}</h3>
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Kode Aksesoris</label>
                <input value={form.accessory_code} onChange={e => setForm({...form, accessory_code: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="ACC-001" data-testid="acc-code-input" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Nama Aksesoris *</label>
                <input value={form.accessory_name} onChange={e => setForm({...form, accessory_name: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Kancing" data-testid="acc-name-input" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Kategori</label>
                <input value={form.category} onChange={e => setForm({...form, category: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Trimming" data-testid="acc-category-input" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Unit</label>
                <select value={form.unit} onChange={e => setForm({...form, unit: e.target.value})}
                        className="w-full border rounded-lg px-3 py-2 text-sm" data-testid="acc-unit-input">
                  <option value="pcs">Pcs</option>
                  <option value="meter">Meter</option>
                  <option value="roll">Roll</option>
                  <option value="yard">Yard</option>
                  <option value="kg">Kg</option>
                  <option value="set">Set</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Deskripsi</label>
                <textarea value={form.description} onChange={e => setForm({...form, description: e.target.value})}
                          className="w-full border rounded-lg px-3 py-2 text-sm" rows="2" placeholder="Deskripsi..." data-testid="acc-description-input" />
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowForm(false)} className="flex-1 py-2 border rounded-lg text-sm text-slate-600 hover:bg-slate-50" data-testid="cancel-accessory-btn">Batal</button>
              <button onClick={handleSave} disabled={!form.accessory_name} className="flex-1 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50" data-testid="save-accessory-btn">Simpan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
