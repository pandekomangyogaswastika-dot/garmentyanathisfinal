
import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Filter, Activity, Loader2 } from 'lucide-react';
import PaginationFooter from './PaginationFooter';

const ACTION_COLORS = {
  Create: 'bg-emerald-100 text-emerald-700',
  Update: 'bg-blue-100 text-blue-700',
  Delete: 'bg-red-100 text-red-700',
  Login: 'bg-purple-100 text-purple-700',
  'Auto Generate': 'bg-amber-100 text-amber-700',
};

const MODULE_ICONS = {
  'Production PO': '📋',
  'Work Order': '🏭',
  'Production Progress': '📈',
  'Garments': '👔',
  'Products': '📦',
  'Invoice': '🧾',
  'Payment': '💰',
  'User Management': '👤',
  'Auth': '🔐',
};

export default function ActivityLogModule({ token }) {
  const [logs, setLogs] = useState([]);
  const [users, setUsers] = useState([]);
  const [moduleOptions, setModuleOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterModule, setFilterModule] = useState('');
  const [filterUser, setFilterUser] = useState('');

  // Phase 10C — Server-side pagination state
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(20);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState({ Create: 0, Update: 0, Delete: 0, Login: 0 });

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('page', String(page));
      params.set('per_page', String(perPage));
      if (filterModule) params.set('module', filterModule);
      if (filterUser) params.set('user_id', filterUser);
      const res = await fetch(`/api/activity-logs?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      // Backend returns envelope when page/per_page provided
      if (data && Array.isArray(data.items)) {
        setLogs(data.items);
        setTotal(data.total || 0);
      } else if (Array.isArray(data)) {
        // Defensive: legacy array shape
        setLogs(data);
        setTotal(data.length);
      } else {
        setLogs([]);
        setTotal(0);
      }
    } catch (e) {
      console.error(e);
      setLogs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [token, page, perPage, filterModule, filterUser]);

  // Fetch action stats independently from current page (kept lightweight)
  const fetchStats = useCallback(async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const baseParams = new URLSearchParams();
      if (filterModule) baseParams.set('module', filterModule);
      if (filterUser) baseParams.set('user_id', filterUser);
      const actions = ['Create', 'Update', 'Delete', 'Login'];
      const results = await Promise.all(actions.map(async (action) => {
        const params = new URLSearchParams(baseParams);
        params.set('action', action);
        params.set('page', '1');
        params.set('per_page', '1');
        const res = await fetch(`/api/activity-logs?${params.toString()}`, { headers });
        const data = await res.json();
        return [action, (data && typeof data.total === 'number') ? data.total : (Array.isArray(data) ? data.length : 0)];
      }));
      const next = { Create: 0, Update: 0, Delete: 0, Login: 0 };
      results.forEach(([k, v]) => { next[k] = v; });
      setStats(next);
    } catch (e) { /* non-critical */ }
  }, [token, filterModule, filterUser]);

  // Fetch a small sample to populate module-filter buttons (one-time)
  const fetchModuleOptions = useCallback(async () => {
    try {
      const res = await fetch('/api/activity-logs?page=1&per_page=200', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      const items = Array.isArray(data?.items) ? data.items : (Array.isArray(data) ? data : []);
      setModuleOptions([...new Set(items.map(l => l.module).filter(Boolean))]);
    } catch (_) { /* ignore */ }
  }, [token]);

  const fetchUsers = useCallback(async () => {
    try {
      const res = await fetch('/api/users', { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      const items = Array.isArray(data?.items) ? data.items : (Array.isArray(data) ? data : []);
      setUsers(items);
    } catch (_) { setUsers([]); }
  }, [token]);

  useEffect(() => { fetchUsers(); fetchModuleOptions(); }, [fetchUsers, fetchModuleOptions]);
  useEffect(() => { fetchLogs(); }, [fetchLogs]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1); }, [filterModule, filterUser]);

  const formatDateTime = (d) => {
    if (!d) return '-';
    return new Date(d).toLocaleString('id-ID', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Log Aktivitas</h1>
          <p className="text-slate-500 text-sm mt-1">Rekam jejak semua aktivitas sistem</p>
        </div>
        <button onClick={() => { fetchLogs(); fetchStats(); }} className="flex items-center gap-2 px-3 py-2 border border-slate-200 rounded-lg text-sm hover:bg-slate-50" data-testid="activity-refresh">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Module filter */}
      <div className="flex flex-wrap gap-2 items-center">
        <Filter className="w-4 h-4 text-slate-500" />
        <button onClick={() => setFilterModule('')}
          className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${!filterModule ? 'bg-blue-600 text-white border-blue-600' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}
          data-testid="activity-module-all">
          Semua Modul
        </button>
        {moduleOptions.map(m => (
          <button key={m} onClick={() => setFilterModule(m)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              filterModule === m ? 'bg-blue-600 text-white border-blue-600' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
            data-testid={`activity-module-${m}`}>
            {MODULE_ICONS[m] || '📌'} {m}
          </button>
        ))}
      </div>

      {/* User Filter */}
      <div className="bg-white p-3 rounded-lg border border-slate-200">
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-slate-700 whitespace-nowrap">Filter User:</label>
          <select value={filterUser} onChange={(e) => setFilterUser(e.target.value)}
            className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm"
            data-testid="activity-user-filter">
            <option value="">Semua User</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.name} - {u.email}</option>)}
          </select>
          <button onClick={() => { setPage(1); fetchLogs(); fetchStats(); }} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 whitespace-nowrap">
            Terapkan Filter
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { action: 'Create', label: 'Dibuat', color: 'border-l-emerald-500' },
          { action: 'Update', label: 'Diubah', color: 'border-l-blue-500' },
          { action: 'Delete', label: 'Dihapus', color: 'border-l-red-500' },
          { action: 'Login', label: 'Login', color: 'border-l-purple-500' },
        ].map(s => (
          <div key={s.action} className={`bg-white rounded-xl border border-slate-200 border-l-4 ${s.color} p-4 shadow-sm`}>
            <p className="text-xs text-slate-500">{s.label}</p>
            <p className="text-2xl font-bold text-slate-800 mt-1" data-testid={`activity-stat-${s.action}`}>
              {(stats[s.action] || 0).toLocaleString('id-ID')}
            </p>
          </div>
        ))}
      </div>

      {/* Log List */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-100">
          <h3 className="font-semibold text-slate-700">
            <Activity className="w-4 h-4 inline mr-2 text-blue-500" />
            Aktivitas Terbaru ({total.toLocaleString('id-ID')})
          </h3>
        </div>
        <div className="divide-y divide-slate-100 max-h-[600px] overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="animate-spin h-8 w-8 text-blue-500" />
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-16 text-slate-400">Belum ada aktivitas</div>
          ) : (
            logs.map(log => (
              <div key={log.id} className="flex items-start gap-4 px-5 py-4 hover:bg-slate-50">
                <div className="w-9 h-9 rounded-full bg-blue-100 flex items-center justify-center text-sm flex-shrink-0">
                  {MODULE_ICONS[log.module] || <Activity className="w-4 h-4 text-blue-500" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm text-slate-800">{log.user_name}</span>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ACTION_COLORS[log.action] || 'bg-slate-100 text-slate-600'}`}>
                      {log.action}
                    </span>
                    <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded">{log.module}</span>
                  </div>
                  <p className="text-sm text-slate-600 mt-0.5">{log.details}</p>
                </div>
                <div className="text-xs text-slate-400 whitespace-nowrap flex-shrink-0">
                  {formatDateTime(log.timestamp)}
                </div>
              </div>
            ))
          )}
        </div>
        <PaginationFooter
          page={page}
          perPage={perPage}
          total={total}
          onPageChange={setPage}
          onPerPageChange={setPerPage}
          loading={loading}
          itemLabel="log"
          testIdPrefix="activity-pagination"
        />
      </div>
    </div>
  );
}
