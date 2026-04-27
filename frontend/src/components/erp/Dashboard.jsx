import { useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend, LineChart, Line, Area, AreaChart } from 'recharts';
import { Package, Factory, FileText, DollarSign, AlertTriangle, TrendingUp, TrendingDown, Clock, Bell, ChevronDown, ChevronUp, X, Send, MessageSquare, ExternalLink, Calendar, Filter, RefreshCw, CheckCircle, XCircle, Truck, RotateCcw, Shield, Zap, Target, BarChart3 } from 'lucide-react';
import { apiGet, apiPost } from '../../lib/api';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#14b8a6'];
const fmt = (v) => 'Rp ' + (v || 0).toLocaleString('id-ID');
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }) : '-';
const fmtNum = (v) => (v || 0).toLocaleString('id-ID');

function ClipboardList({ className }) {
  return <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" /></svg>;
}

function KPICard({ title, value, subtitle, icon: Icon, color, onClick, detail, badge }) {
  return (
    <button onClick={onClick} className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm hover:shadow-lg hover:border-blue-300 transition-all text-left w-full group" data-testid={`kpi-${title.replace(/\s+/g, '-').toLowerCase()}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">{title}</p>
          <p className="text-xl font-bold text-slate-800 mt-0.5">{value}</p>
          {subtitle && <p className="text-xs text-slate-400 mt-0.5 truncate">{subtitle}</p>}
        </div>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${color} group-hover:scale-110 transition-transform`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
      </div>
      {badge && <div className="mt-2"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.color}`}>{badge.text}</span></div>}
      <div className="mt-2 flex items-center gap-1 text-xs text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity">
        <ExternalLink className="w-3 h-3" /> Klik untuk detail
      </div>
    </button>
  );
}

function DrilldownModal({ title, children, onClose, onNavigate, navLabel }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <h3 className="text-lg font-bold text-slate-800">{title}</h3>
          <div className="flex items-center gap-2">
            {onNavigate && navLabel && (
              <button onClick={onNavigate} className="text-xs text-blue-600 hover:text-blue-800 bg-blue-50 px-3 py-1.5 rounded-lg font-medium flex items-center gap-1">
                <ExternalLink className="w-3 h-3" /> {navLabel}
              </button>
            )}
            <button onClick={onClose} className="p-1.5 hover:bg-slate-100 rounded-lg"><X className="w-5 h-5 text-slate-400" /></button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white rounded-lg shadow-lg border border-slate-200 p-3 text-sm">
        <p className="font-semibold text-slate-700 mb-1">{label}</p>
        {payload.map((p, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: p.color }}></div>
            <span className="text-slate-600">{p.name}:</span>
            <span className="font-bold text-slate-800">{fmtNum(p.value)}</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

export default function Dashboard({ token, onNavigate }) {
  const [metrics, setMetrics] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drilldown, setDrilldown] = useState(null);
  const [showReminder, setShowReminder] = useState(false);
  const [reminders, setReminders] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [reminderForm, setReminderForm] = useState({ vendor_id: '', subject: '', message: '', po_number: '', priority: 'normal' });
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [showAnalytics, setShowAnalytics] = useState(true);

  const fetchMetrics = useCallback(async () => {
    try {
      setMetrics(await apiGet('/dashboard'));
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  const fetchAnalytics = useCallback(async () => {
    try {
      let url = '/dashboard/analytics';
      const params = [];
      if (dateFrom) params.push(`from=${dateFrom}`);
      if (dateTo) params.push(`to=${dateTo}`);
      if (params.length) url += '?' + params.join('&');
      setAnalytics(await apiGet(url));
    } catch (e) { console.error(e); }
  }, [dateFrom, dateTo]);

  const fetchReminders = useCallback(async () => {
    try { setReminders(await apiGet('/reminders')); } catch (e) {}
  }, []);

  const fetchVendors = useCallback(async () => {
    try { setVendors(await apiGet('/garments')); } catch (e) {}
  }, []);

  useEffect(() => { fetchMetrics(); fetchReminders(); fetchVendors(); fetchAnalytics(); }, []);
  useEffect(() => { fetchAnalytics(); }, [dateFrom, dateTo]);

  const nav = (module) => { if (onNavigate) onNavigate(module); };

  const sendReminder = async () => {
    if (!reminderForm.vendor_id || !reminderForm.subject) { alert('Vendor dan subject harus diisi'); return; }
    try {
      await apiPost('/reminders', reminderForm);
      setShowReminder(false);
      setReminderForm({ vendor_id: '', subject: '', message: '', po_number: '', priority: 'normal' });
      fetchReminders();
      alert('Reminder terkirim!');
    } catch (e) { alert('Error: ' + e.message); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div></div>;

  const woStatusData = (metrics?.woStatus || []).map(s => ({ name: s._id || 'Unknown', value: s.count }));
  const topGarments = metrics?.topGarments || [];
  const totalAlerts = (metrics?.alerts?.overduePos?.length || 0) + (metrics?.alerts?.nearDeadlinePos?.length || 0) + (metrics?.alerts?.unpaidInvoices?.length || 0);
  const pendingReminders = reminders.filter(r => r.status === 'pending');
  const respondedReminders = reminders.filter(r => r.status === 'responded');
  const deadlineDist = analytics?.deadlineDistribution || {};
  const shipStatus = analytics?.shipmentStatus || [];
  const weeklyTP = analytics?.weeklyThroughput || [];
  const prodComp = analytics?.productCompletion || [];
  const vendorLT = analytics?.vendorLeadTimes || [];
  const defectR = analytics?.defectRates || [];

  return (
    <div className="space-y-5" data-testid="dashboard">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Dashboard</h1>
          <p className="text-slate-500 text-sm">Ikhtisar operasional & analitik produksi garmen</p>
        </div>
        <div className="flex items-center gap-2">
          {totalAlerts > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg">
              <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
              <span className="text-xs font-medium text-red-700">{totalAlerts} peringatan</span>
            </div>
          )}
          <button onClick={() => setShowReminder(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-lg text-xs font-medium text-blue-700 hover:bg-blue-100" data-testid="send-reminder-btn">
            <Bell className="w-3.5 h-3.5" /> Kirim Reminder
          </button>
          <button onClick={() => { fetchMetrics(); fetchAnalytics(); }} className="p-1.5 hover:bg-slate-100 rounded-lg" title="Refresh">
            <RefreshCw className="w-4 h-4 text-slate-400" />
          </button>
        </div>
      </div>

      {/* Compact Alert Bar */}
      {totalAlerts > 0 && (
        <div className="flex flex-wrap gap-2">
          {(metrics?.alerts?.overduePos || []).map(po => (
            <div key={po.id} className="flex items-center gap-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-xs">
              <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
              <span className="text-red-700"><strong>{po.po_number}</strong> terlambat</span>
            </div>
          ))}
          {(metrics?.alerts?.nearDeadlinePos || []).map(po => (
            <div key={po.id} className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-lg text-xs">
              <Clock className="w-3.5 h-3.5 text-amber-500" />
              <span className="text-amber-700"><strong>{po.po_number}</strong> deadline segera</span>
            </div>
          ))}
          {(metrics?.alerts?.unpaidInvoices || []).slice(0, 3).map(inv => (
            <div key={inv.id} className="flex items-center gap-2 px-3 py-1.5 bg-orange-50 border border-orange-200 rounded-lg text-xs">
              <FileText className="w-3.5 h-3.5 text-orange-500" />
              <span className="text-orange-700"><strong>{inv.invoice_number}</strong> {inv.status}</span>
            </div>
          ))}
        </div>
      )}

      {/* KPI Cards - Row 1 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard title="Total PO" value={metrics?.totalPOs || 0} subtitle={`${metrics?.activePOs || 0} aktif`} icon={ClipboardList} color="bg-blue-500" onClick={() => setDrilldown('po')} badge={metrics?.delayedPOs > 0 ? { text: `${metrics.delayedPOs} terlambat`, color: 'bg-red-100 text-red-700' } : null} />
        <KPICard title="Active Jobs" value={metrics?.activeJobs || 0} subtitle="Production jobs berjalan" icon={Factory} color="bg-emerald-500" onClick={() => setDrilldown('jobs')} />
        <KPICard title="Progress Produksi" value={`${metrics?.globalProgressPct || 0}%`} subtitle={`${fmtNum(metrics?.totalProducedGlobal)} / ${fmtNum(metrics?.totalAvailableGlobal)} pcs`} icon={TrendingUp} color="bg-teal-500" onClick={() => setDrilldown('progress')} />
        <KPICard title="On-Time Rate" value={`${metrics?.onTimeRate || 0}%`} subtitle="PO selesai tepat waktu" icon={Target} color="bg-indigo-500" onClick={() => setDrilldown('ontime')} />
      </div>

      {/* KPI Cards - Row 2 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard title="Pending Shipment" value={metrics?.pendingShipments || 0} subtitle="Material belum diterima" icon={Truck} color="bg-amber-500" onClick={() => nav('vendor-shipments')} />
        <KPICard title="Req. Tambahan" value={metrics?.pendingAdditionalRequests || 0} subtitle="Menunggu persetujuan" icon={AlertTriangle} color="bg-orange-500" onClick={() => nav('vendor-shipments')} />
        <KPICard title="Retur Produksi" value={metrics?.pendingReturns || 0} subtitle="Dalam proses" icon={RotateCcw} color="bg-purple-500" onClick={() => nav('production-returns')} />
        <KPICard title="Reminders" value={pendingReminders.length} subtitle={`${respondedReminders.length} dibalas`} icon={Bell} color="bg-cyan-500" onClick={() => setDrilldown('reminders')} badge={respondedReminders.length > 0 ? { text: `${respondedReminders.length} respon baru`, color: 'bg-emerald-100 text-emerald-700' } : null} />
      </div>

      {/* KPI Cards - Row 3: Financial */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard title="Invoice AR" value={fmt(metrics?.totalInvoicedAR)} subtitle={`Outstanding: ${fmt(metrics?.outstandingAR)}`} icon={FileText} color="bg-blue-400" onClick={() => nav('accounts-receivable')} />
        <KPICard title="Invoice AP" value={fmt(metrics?.totalInvoicedAP)} subtitle={`Outstanding: ${fmt(metrics?.outstandingAP)}`} icon={FileText} color="bg-purple-500" onClick={() => nav('accounts-payable')} />
        <KPICard title="Outstanding" value={fmt(metrics?.outstanding)} subtitle={`AR: ${fmt(metrics?.outstandingAR)} | AP: ${fmt(metrics?.outstandingAP)}`} icon={DollarSign} color="bg-orange-500" onClick={() => nav('invoices')} />
        <KPICard title="Gross Margin" value={fmt(metrics?.grossMargin)} subtitle={`Revenue: ${fmt(metrics?.totalRevenue)}`} icon={Zap} color="bg-emerald-600" onClick={() => nav('financial-recap')} />
      </div>

      {/* Analytics Section with Date Filter */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-600" />
            <h3 className="font-bold text-slate-800">Analitik Lanjutan</h3>
            <button onClick={() => setShowAnalytics(!showAnalytics)} className="text-xs text-slate-400 hover:text-slate-600">
              {showAnalytics ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
          </div>
          <div className="flex items-center gap-2" data-testid="date-filter">
            <Calendar className="w-4 h-4 text-slate-400" />
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none" />
            <span className="text-xs text-slate-400">s/d</span>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none" />
            {(dateFrom || dateTo) && <button onClick={() => { setDateFrom(''); setDateTo(''); }} className="text-xs text-red-500 hover:text-red-700"><X className="w-3.5 h-3.5" /></button>}
          </div>
        </div>

        {showAnalytics && (
          <div className="space-y-4">
            {/* Row 1: Weekly Throughput + Deadline Distribution + Shipment Status */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 bg-gradient-to-br from-slate-50 to-blue-50/30 rounded-xl p-4 border border-slate-100">
                <h4 className="font-semibold text-slate-700 text-sm mb-3">Throughput Produksi Mingguan</h4>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={weeklyTP}>
                    <defs>
                      <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.9}/>
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0.7}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#64748b' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="qty" name="Produksi (pcs)" fill="url(#barGrad)" radius={[6,6,0,0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="bg-gradient-to-br from-slate-50 to-amber-50/30 rounded-xl p-4 border border-slate-100">
                <h4 className="font-semibold text-slate-700 text-sm mb-3">Distribusi Deadline PO</h4>
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-red-50 rounded-lg p-3 text-center border border-red-100">
                    <p className="text-2xl font-bold text-red-600">{deadlineDist.overdue || 0}</p>
                    <p className="text-[10px] text-red-500 font-medium mt-0.5">Overdue</p>
                  </div>
                  <div className="bg-amber-50 rounded-lg p-3 text-center border border-amber-100">
                    <p className="text-2xl font-bold text-amber-600">{deadlineDist.thisWeek || 0}</p>
                    <p className="text-[10px] text-amber-500 font-medium mt-0.5">Minggu Ini</p>
                  </div>
                  <div className="bg-blue-50 rounded-lg p-3 text-center border border-blue-100">
                    <p className="text-2xl font-bold text-blue-600">{deadlineDist.nextWeek || 0}</p>
                    <p className="text-[10px] text-blue-500 font-medium mt-0.5">Minggu Depan</p>
                  </div>
                  <div className="bg-emerald-50 rounded-lg p-3 text-center border border-emerald-100">
                    <p className="text-2xl font-bold text-emerald-600">{deadlineDist.later || 0}</p>
                    <p className="text-[10px] text-emerald-500 font-medium mt-0.5">Nanti</p>
                  </div>
                </div>
                {shipStatus.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-100">
                    <p className="text-xs font-semibold text-slate-600 mb-1.5">Status Pengiriman</p>
                    {shipStatus.map((s, i) => (
                      <div key={s.status} className="flex items-center justify-between text-xs py-0.5">
                        <div className="flex items-center gap-1.5">
                          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }}></div>
                          <span className="text-slate-600">{s.status}</span>
                        </div>
                        <span className="font-bold text-slate-700">{s.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Row 2: Production Completion + Vendor Lead Time + Defect Rate */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Product Completion */}
              <div className="bg-gradient-to-br from-slate-50 to-emerald-50/30 rounded-xl p-4 border border-slate-100">
                <h4 className="font-semibold text-slate-700 text-sm mb-3">Tingkat Penyelesaian Produk</h4>
                {prodComp.length > 0 ? (
                  <div className="space-y-2.5">
                    {prodComp.slice(0, 6).map((p, i) => (
                      <div key={i}>
                        <div className="flex justify-between text-xs mb-0.5">
                          <span className="text-slate-600 truncate max-w-[140px]">{p.product}</span>
                          <span className="font-bold text-slate-700">{p.rate}%</span>
                        </div>
                        <div className="w-full bg-slate-100 rounded-full h-2">
                          <div className="h-2 rounded-full transition-all" style={{ width: `${Math.min(100, p.rate)}%`, backgroundColor: p.rate >= 80 ? '#10b981' : p.rate >= 50 ? '#f59e0b' : '#ef4444' }} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-xs text-slate-400 text-center py-6">Belum ada data</p>}
              </div>

              {/* Vendor Lead Time */}
              <div className="bg-gradient-to-br from-slate-50 to-purple-50/30 rounded-xl p-4 border border-slate-100">
                <h4 className="font-semibold text-slate-700 text-sm mb-3">Lead Time Vendor (hari)</h4>
                {vendorLT.length > 0 ? (
                  <div className="space-y-2">
                    {vendorLT.slice(0, 6).map((v, i) => (
                      <div key={i} className="flex items-center justify-between p-2 bg-white rounded-lg border border-slate-100">
                        <div>
                          <span className="text-xs font-medium text-slate-700">{v.vendor}</span>
                          <span className="text-[10px] text-slate-400 ml-1.5">({v.shipment_count} shipment)</span>
                        </div>
                        <span className={`text-sm font-bold ${v.avg_days <= 3 ? 'text-emerald-600' : v.avg_days <= 7 ? 'text-amber-600' : 'text-red-600'}`}>{v.avg_days}d</span>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-xs text-slate-400 text-center py-6">Belum ada data</p>}
              </div>

              {/* Defect Rate */}
              <div className="bg-gradient-to-br from-slate-50 to-rose-50/30 rounded-xl p-4 border border-slate-100">
                <h4 className="font-semibold text-slate-700 text-sm mb-3">Tingkat Material Missing</h4>
                {defectR.length > 0 ? (
                  <div className="space-y-2">
                    {defectR.slice(0, 6).map((d, i) => (
                      <div key={i} className="flex items-center justify-between p-2 bg-white rounded-lg border border-slate-100">
                        <div>
                          <span className="text-xs font-medium text-slate-700">{d.vendor}</span>
                          <div className="text-[10px] text-slate-400">Diterima: {fmtNum(d.total_received)} | Missing: {fmtNum(d.total_missing)}</div>
                        </div>
                        <span className={`text-sm font-bold ${d.missing_rate <= 2 ? 'text-emerald-600' : d.missing_rate <= 5 ? 'text-amber-600' : 'text-red-600'}`}>{d.missing_rate}%</span>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-xs text-slate-400 text-center py-6">Belum ada data inspeksi</p>}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Original Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <h3 className="font-semibold text-slate-700 text-sm mb-3">Tren Produksi 6 Bulan</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={metrics?.monthlyData || []}>
              <defs>
                <linearGradient id="colorProd" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#64748b' }} />
              <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="pos" name="PO" fill="#3b82f6" radius={[3,3,0,0]} />
              <Area type="monotone" dataKey="production" name="Produksi" stroke="#10b981" fill="url(#colorProd)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <h3 className="font-semibold text-slate-700 text-sm mb-3">Status Job Produksi</h3>
          {woStatusData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={140}>
                <PieChart>
                  <Pie data={woStatusData} cx="50%" cy="50%" innerRadius={35} outerRadius={60} paddingAngle={5} dataKey="value">
                    {woStatusData.map((e, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-2">
                {woStatusData.map((e, i) => (
                  <div key={e.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }}></div>
                      <span className="text-slate-600">{e.name}</span>
                    </div>
                    <span className="font-bold text-slate-700">{e.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : <div className="flex items-center justify-center h-32 text-slate-400 text-xs">Belum ada data job produksi</div>}
        </div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <h3 className="font-semibold text-slate-700 text-sm mb-3">Top Vendor by Produksi</h3>
          {topGarments.length > 0 ? (
            <div className="space-y-2.5">
              {topGarments.map((g, i) => (
                <div key={i} className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0">{i + 1}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between text-xs mb-0.5">
                      <span className="text-slate-700 font-medium truncate">{g._id || 'Unknown'}</span>
                      <span className="text-slate-500 font-semibold">{fmtNum(g.total_qty)} pcs</span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-1.5">
                      <div className="bg-blue-500 h-1.5 rounded-full transition-all" style={{ width: `${Math.min(100, (g.total_qty / (topGarments[0]?.total_qty || 1)) * 100)}%` }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : <div className="flex items-center justify-center h-24 text-slate-400 text-xs">Belum ada data produksi vendor</div>}
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <h3 className="font-semibold text-slate-700 text-sm mb-3">Status PO</h3>
          <div className="space-y-1.5">
            {Object.entries(metrics?.poStatusCounts || {}).filter(([, v]) => v > 0).map(([status, count]) => {
              const statusColors = { Draft: 'bg-slate-100 text-slate-600', Confirmed: 'bg-blue-100 text-blue-700', Distributed: 'bg-indigo-100 text-indigo-700', 'In Production': 'bg-emerald-100 text-emerald-700', 'Production Complete': 'bg-teal-100 text-teal-700', Closed: 'bg-slate-200 text-slate-500' };
              return (
                <div key={status} className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 cursor-pointer" onClick={() => nav('production-po')}>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusColors[status] || 'bg-slate-100 text-slate-600'}`}>{status}</span>
                  <span className="text-sm font-bold text-slate-700">{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-slate-700 text-sm">Reminder Vendor</h3>
            <button onClick={() => setShowReminder(true)} className="text-xs text-blue-600 hover:text-blue-800 font-medium">+ Kirim</button>
          </div>
          {reminders.length > 0 ? (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {reminders.slice(0, 5).map(r => (
                <div key={r.id} className={`p-2.5 rounded-lg border text-xs ${r.status === 'responded' ? 'border-emerald-200 bg-emerald-50' : r.status === 'pending' ? 'border-amber-200 bg-amber-50' : 'border-slate-200'}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-slate-700 truncate">{r.vendor_name}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${r.status === 'responded' ? 'bg-emerald-200 text-emerald-800' : 'bg-amber-200 text-amber-800'}`}>{r.status === 'responded' ? 'Dibalas' : 'Menunggu'}</span>
                  </div>
                  <p className="text-slate-600 mt-0.5 truncate">{r.subject}</p>
                  {r.response && <p className="text-emerald-700 mt-1 italic">Respon: {r.response}</p>}
                </div>
              ))}
            </div>
          ) : <div className="flex items-center justify-center h-24 text-slate-400 text-xs">Belum ada reminder</div>}
        </div>
      </div>

      {/* Drilldown Modals */}
      {drilldown === 'po' && (
        <DrilldownModal title="Detail PO" onClose={() => setDrilldown(null)} onNavigate={() => { setDrilldown(null); nav('production-po'); }} navLabel="Buka Production PO">
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="bg-blue-50 rounded-lg p-3"><p className="text-xl font-bold text-blue-700">{metrics?.totalPOs || 0}</p><p className="text-xs text-blue-600">Total PO</p></div>
              <div className="bg-emerald-50 rounded-lg p-3"><p className="text-xl font-bold text-emerald-700">{metrics?.activePOs || 0}</p><p className="text-xs text-emerald-600">Aktif</p></div>
              <div className="bg-red-50 rounded-lg p-3"><p className="text-xl font-bold text-red-700">{metrics?.delayedPOs || 0}</p><p className="text-xs text-red-600">Terlambat</p></div>
            </div>
            <h4 className="text-sm font-semibold text-slate-700 mt-3">Status Breakdown:</h4>
            {(metrics?.poStatusList || []).map(s => (
              <div key={s.status} className="border border-slate-200 rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-700">{s.status}</span>
                  <span className="text-sm font-bold text-slate-800">{s.count}</span>
                </div>
                {s.samples?.slice(0, 3).map(po => (
                  <div key={po.id} className="text-xs text-slate-500 mt-1">{po.po_number} — {po.customer_name || 'N/A'}</div>
                ))}
              </div>
            ))}
          </div>
        </DrilldownModal>
      )}

      {drilldown === 'progress' && (
        <DrilldownModal title="Progress Produksi" onClose={() => setDrilldown(null)} onNavigate={() => { setDrilldown(null); nav('production-monitoring'); }} navLabel="Monitoring Produksi">
          <div className="space-y-3">
            <div className="bg-teal-50 rounded-xl p-4 text-center">
              <p className="text-3xl font-bold text-teal-700">{metrics?.globalProgressPct || 0}%</p>
              <p className="text-sm text-teal-600 mt-1">{fmtNum(metrics?.totalProducedGlobal)} dari {fmtNum(metrics?.totalAvailableGlobal)} pcs</p>
              <div className="w-full bg-teal-200 rounded-full h-3 mt-3">
                <div className="bg-teal-600 h-3 rounded-full transition-all" style={{ width: `${metrics?.globalProgressPct || 0}%` }} />
              </div>
            </div>
          </div>
        </DrilldownModal>
      )}

      {drilldown === 'reminders' && (
        <DrilldownModal title="Semua Reminder" onClose={() => setDrilldown(null)}>
          <div className="space-y-2">
            {reminders.length === 0 ? <p className="text-sm text-slate-400">Belum ada reminder</p> : reminders.map(r => (
              <div key={r.id} className={`p-3 rounded-lg border ${r.status === 'responded' ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`}>
                <div className="flex justify-between"><span className="text-sm font-semibold text-slate-700">{r.vendor_name}</span><span className="text-xs text-slate-400">{fmtDate(r.created_at)}</span></div>
                <p className="text-sm text-slate-600 mt-0.5">{r.subject}</p>
                {r.response && <div className="mt-2 p-2 bg-white rounded border border-emerald-200"><p className="text-xs text-emerald-700"><strong>Respon vendor:</strong> {r.response}</p></div>}
              </div>
            ))}
          </div>
        </DrilldownModal>
      )}

      {drilldown === 'jobs' && (
        <DrilldownModal title="Production Jobs" onClose={() => setDrilldown(null)} onNavigate={() => { setDrilldown(null); nav('work-orders'); }} navLabel="Distribusi Kerja">
          <div className="space-y-3">
            <div className="bg-emerald-50 rounded-xl p-4 text-center">
              <p className="text-3xl font-bold text-emerald-700">{metrics?.activeJobs || 0}</p>
              <p className="text-sm text-emerald-600">Jobs aktif sedang berjalan</p>
            </div>
            {woStatusData.length > 0 && woStatusData.map((s, i) => (
              <div key={s.name} className="flex items-center justify-between p-2 bg-slate-50 rounded-lg">
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }}></div><span className="text-sm text-slate-600">{s.name}</span></div>
                <span className="font-bold">{s.value}</span>
              </div>
            ))}
          </div>
        </DrilldownModal>
      )}

      {drilldown === 'ontime' && (
        <DrilldownModal title="On-Time Delivery Rate" onClose={() => setDrilldown(null)}>
          <div className="bg-indigo-50 rounded-xl p-6 text-center">
            <p className="text-4xl font-bold text-indigo-700">{metrics?.onTimeRate || 0}%</p>
            <p className="text-sm text-indigo-600 mt-1">PO diselesaikan sebelum atau tepat deadline</p>
          </div>
        </DrilldownModal>
      )}

      {/* Send Reminder Modal */}
      {showReminder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => setShowReminder(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden" onClick={e => e.stopPropagation()} data-testid="reminder-modal">
            <div className="px-5 py-4 border-b border-slate-200 bg-blue-50">
              <h3 className="font-bold text-slate-800 flex items-center gap-2"><Send className="w-4 h-4 text-blue-600" /> Kirim Reminder ke Vendor</h3>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1">Vendor</label>
                <select value={reminderForm.vendor_id} onChange={e => setReminderForm(f => ({ ...f, vendor_id: e.target.value }))} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm" data-testid="reminder-vendor">
                  <option value="">Pilih vendor...</option>
                  {vendors.map(v => <option key={v.id} value={v.id}>{v.garment_name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1">Subject</label>
                <input value={reminderForm.subject} onChange={e => setReminderForm(f => ({ ...f, subject: e.target.value }))} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm" placeholder="e.g., Update progres produksi" data-testid="reminder-subject" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1">No PO (opsional)</label>
                <input value={reminderForm.po_number} onChange={e => setReminderForm(f => ({ ...f, po_number: e.target.value }))} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm" placeholder="PO-001" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1">Pesan</label>
                <textarea value={reminderForm.message} onChange={e => setReminderForm(f => ({ ...f, message: e.target.value }))} className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm h-20 resize-none" placeholder="Detail reminder..." data-testid="reminder-message" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 block mb-1">Prioritas</label>
                <div className="flex gap-2">
                  {['normal', 'high', 'urgent'].map(p => (
                    <button key={p} onClick={() => setReminderForm(f => ({ ...f, priority: p }))} className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${reminderForm.priority === p ? (p === 'urgent' ? 'bg-red-100 border-red-300 text-red-700' : p === 'high' ? 'bg-amber-100 border-amber-300 text-amber-700' : 'bg-blue-100 border-blue-300 text-blue-700') : 'bg-white border-slate-200 text-slate-500'}`}>
                      {p === 'urgent' ? 'Urgent' : p === 'high' ? 'High' : 'Normal'}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="px-5 py-3 border-t border-slate-200 flex justify-end gap-2 bg-slate-50">
              <button onClick={() => setShowReminder(false)} className="px-4 py-2 text-sm text-slate-600 rounded-lg">Batal</button>
              <button onClick={sendReminder} className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg font-medium hover:bg-blue-700 flex items-center gap-1.5" data-testid="send-reminder-submit"><Send className="w-3.5 h-3.5" /> Kirim</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
