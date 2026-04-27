import { useState, useEffect, useCallback } from 'react';
import { Shield, Plus, Edit2, Trash2, Check, X, ChevronDown, ChevronRight } from 'lucide-react';

export default function RoleManagementModule({ token, userRole }) {
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editRole, setEditRole] = useState(null);
  const [form, setForm] = useState({ name: '', description: '', permissions: [] });
  const [expandedRole, setExpandedRole] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [rolesRes, permsRes] = await Promise.all([
        fetch('/api/roles', { headers: { Authorization: `Bearer ${token}` } }),
        fetch('/api/permissions', { headers: { Authorization: `Bearer ${token}` } })
      ]);
      setRoles(await rolesRes.json());
      setPermissions(await permsRes.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSave = async () => {
    const method = editRole ? 'PUT' : 'POST';
    const url = editRole ? `/api/roles/${editRole.id}` : '/api/roles';
    try {
      const res = await fetch(url, {
        method, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(form)
      });
      if (res.ok) { fetchData(); setShowForm(false); setEditRole(null); }
      else { const d = await res.json(); alert(d.detail || d.error || 'Error'); }
    } catch (e) { console.error(e); }
  };

  const handleEdit = (role) => {
    setEditRole(role);
    setForm({
      name: role.name, description: role.description || '',
      permissions: (role.permissions || []).map(p => p.permission_key)
    });
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus role ini?')) return;
    await fetch(`/api/roles/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
    fetchData();
  };

  const togglePerm = (key) => {
    setForm(prev => ({
      ...prev,
      permissions: prev.permissions.includes(key)
        ? prev.permissions.filter(k => k !== key)
        : [...prev.permissions, key]
    }));
  };

  // Group permissions by module
  const permGroups = {};
  permissions.forEach(p => {
    if (!permGroups[p.module]) permGroups[p.module] = [];
    permGroups[p.module].push(p);
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Manajemen Role</h2>
          <p className="text-slate-500 text-sm mt-1">Kelola role dan permission untuk akses kontrol</p>
        </div>
        {userRole === 'superadmin' && (
          <button onClick={() => { setShowForm(true); setEditRole(null); setForm({ name: '', description: '', permissions: [] }); }}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700" data-testid="add-role-btn">
            <Plus className="w-4 h-4" /> Tambah Role
          </button>
        )}
      </div>

      {/* Roles List */}
      <div className="space-y-3">
        {loading ? (
          <div className="text-center py-8 text-slate-400">Memuat...</div>
        ) : roles.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-400">
            <Shield className="w-12 h-12 mx-auto mb-3 text-slate-200" />
            <p>Belum ada custom role</p>
            <p className="text-sm mt-1">Klik "Tambah Role" untuk membuat role baru</p>
          </div>
        ) : roles.map(role => (
          <div key={role.id} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 cursor-pointer hover:bg-slate-50"
                 onClick={() => setExpandedRole(expandedRole === role.id ? null : role.id)}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Shield className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-800">{role.name}</h3>
                  <p className="text-xs text-slate-400">{role.description || 'No description'} | {(role.permissions || []).length} permissions</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {userRole === 'superadmin' && (
                  <>
                    <button onClick={e => { e.stopPropagation(); handleEdit(role); }} className="p-1.5 hover:bg-slate-100 rounded"><Edit2 className="w-4 h-4 text-slate-500" /></button>
                    {!role.is_system && <button onClick={e => { e.stopPropagation(); handleDelete(role.id); }} className="p-1.5 hover:bg-red-50 rounded"><Trash2 className="w-4 h-4 text-red-500" /></button>}
                  </>
                )}
                {expandedRole === role.id ? <ChevronDown className="w-5 h-5 text-slate-400" /> : <ChevronRight className="w-5 h-5 text-slate-400" />}
              </div>
            </div>
            {expandedRole === role.id && (
              <div className="px-5 pb-4 border-t border-slate-100">
                <p className="text-xs text-slate-500 mt-3 mb-2">Permissions:</p>
                <div className="flex flex-wrap gap-2">
                  {(role.permissions || []).map(p => (
                    <span key={p.id || p.permission_key} className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded-md">
                      {p.permission_key}
                    </span>
                  ))}
                  {(role.permissions || []).length === 0 && <span className="text-xs text-slate-400">No permissions assigned</span>}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Create/Edit Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-slate-800 mb-4">{editRole ? 'Edit Role' : 'Tambah Role'}</h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Nama Role *</label>
                <input value={form.name} onChange={e => setForm({...form, name: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="e.g. QC Inspector" data-testid="role-name" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-1">Deskripsi</label>
                <input value={form.description} onChange={e => setForm({...form, description: e.target.value})}
                       className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Deskripsi role..." />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-600 block mb-2">Permissions ({form.permissions.length} dipilih)</label>
                <div className="space-y-3 max-h-60 overflow-y-auto border rounded-lg p-3">
                  {Object.entries(permGroups).map(([module, perms]) => (
                    <div key={module}>
                      <p className="text-xs font-semibold text-slate-500 uppercase mb-1">{module}</p>
                      <div className="flex flex-wrap gap-2">
                        {perms.map(p => (
                          <button key={p.key} type="button" onClick={() => togglePerm(p.key)}
                            className={`text-xs px-2.5 py-1 rounded-md border transition ${
                              form.permissions.includes(p.key)
                                ? 'bg-blue-600 text-white border-blue-600' 
                                : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300'
                            }`}>
                            {form.permissions.includes(p.key) && <Check className="w-3 h-3 inline mr-1" />}
                            {p.key.split('.')[1]}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowForm(false)} className="flex-1 py-2 border rounded-lg text-sm text-slate-600 hover:bg-slate-50">Batal</button>
              <button onClick={handleSave} disabled={!form.name} className="flex-1 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50" data-testid="save-role-btn">Simpan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
