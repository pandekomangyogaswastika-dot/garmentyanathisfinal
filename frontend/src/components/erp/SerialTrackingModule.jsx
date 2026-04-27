import { useState, useEffect, useCallback, useRef } from 'react';
import { Search, Clock, Package, Truck, ClipboardCheck, Factory, BarChart3, ShoppingBag, RotateCcw, ChevronDown, ChevronRight, Users, List, Filter, Hash } from 'lucide-react';
import { apiGet } from '../../lib/api';

const STEP_ICONS = {
  'PO Created': Package, 'Vendor Shipment': Truck, 'Material Inspection': ClipboardCheck,
  'Material Request': Package, 'Production Job': Factory, 'Production Progress': BarChart3,
  'Buyer Dispatch': ShoppingBag, 'Production Return': RotateCcw,
};
const STEP_COLORS = {
  'PO Created': 'bg-blue-500', 'Vendor Shipment': 'bg-purple-500', 'Material Inspection': 'bg-emerald-500',
  'Material Request': 'bg-amber-500', 'Production Job': 'bg-indigo-500', 'Production Progress': 'bg-cyan-500',
  'Production Return': 'bg-rose-500',
};
function getStepIcon(step) {
  for (const [key, icon] of Object.entries(STEP_ICONS)) { if (step.includes(key)) return icon; }
  return Clock;
}
function getStepColor(step) {
  for (const [key, color] of Object.entries(STEP_COLORS)) { if (step.includes(key)) return color; }
  return 'bg-slate-500';
}

const STATUS_COLORS = {
  ongoing: 'bg-blue-100 text-blue-700 border-blue-200',
  completed: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  pending: 'bg-amber-100 text-amber-700 border-amber-200',
};
const STATUS_LABELS = { ongoing: 'Ongoing', completed: 'Selesai', pending: 'Menunggu' };

export default function SerialTrackingModule({ token }) {
  const [tab, setTab] = useState('list'); // 'list' or 'trace'
  const [serialList, setSerialList] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listFilter, setListFilter] = useState('all');
  const [listSearch, setListSearch] = useState('');
  const [expandedSerial, setExpandedSerial] = useState(null);
  const [traceData, setTraceData] = useState(null);

  // Trace states
  const [searchInput, setSearchInput] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expandedIdx, setExpandedIdx] = useState(new Set());
  const debounceRef = useRef(null);

  const fetchSerialList = useCallback(async () => {
    setListLoading(true);
    try {
      let url = `/serial-list?status=${listFilter}`;
      if (listSearch) url += `&search=${encodeURIComponent(listSearch)}`;
      setSerialList(await apiGet(url));
    } catch (e) { console.error(e); }
    finally { setListLoading(false); }
  }, [listFilter, listSearch]);

  useEffect(() => { fetchSerialList(); }, [listFilter]);
  useEffect(() => {
    const t = setTimeout(() => fetchSerialList(), 400);
    return () => clearTimeout(t);
  }, [listSearch]);

  const loadTraceForSerial = async (sn) => {
    if (expandedSerial === sn) { setExpandedSerial(null); setTraceData(null); return; }
    setExpandedSerial(sn);
    try {
      setTraceData(await apiGet(`/serial-trace?serial=${encodeURIComponent(sn)}`));
    } catch (e) { console.error(e); }
  };

  const fetchTrace = useCallback(async (sn) => {
    if (!sn.trim()) { setData(null); return; }
    setLoading(true);
    try {
      setData(await apiGet(`/serial-trace?serial=${encodeURIComponent(sn)}`));
      setExpandedIdx(new Set());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (tab !== 'trace') return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (searchInput.trim().length >= 2) {
      debounceRef.current = setTimeout(() => fetchTrace(searchInput), 500);
    } else { setData(null); }
    return () => clearTimeout(debounceRef.current);
  }, [searchInput, fetchTrace, tab]);

  const handleSearch = (e) => { e.preventDefault(); fetchTrace(searchInput); };
  const toggleExpand = (idx) => {
    setExpandedIdx(prev => { const next = new Set(prev); if (next.has(idx)) next.delete(idx); else next.add(idx); return next; });
  };
  const formatDate = (d) => {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
    catch { return d; }
  };
  const formatNum = (n) => (n || 0).toLocaleString('id-ID');
  const summary = data?.summary || {};
  const allItems = data?.all_items || [];
  const poInfo = data?.po_info || [];

  const ongoingCount = serialList.filter(s => s.status === 'ongoing').length;
  const completedCount = serialList.filter(s => s.status === 'completed').length;
  const pendingCount = serialList.filter(s => s.status === 'pending').length;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Serial Tracking</h2>
          <p className="text-slate-500 text-sm mt-1">Lacak dan monitor semua nomor serial dalam sistem</p>
        </div>
        <div className="flex bg-slate-100 rounded-lg p-0.5">
          <button onClick={() => setTab('list')} className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${tab === 'list' ? 'bg-white shadow-sm text-blue-700' : 'text-slate-600 hover:text-slate-800'}`} data-testid="tab-serial-list">
            <List className="w-4 h-4 inline mr-1.5" />Daftar Serial
          </button>
          <button onClick={() => setTab('trace')} className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${tab === 'trace' ? 'bg-white shadow-sm text-blue-700' : 'text-slate-600 hover:text-slate-800'}`} data-testid="tab-serial-trace">
            <Search className="w-4 h-4 inline mr-1.5" />Trace Timeline
          </button>
        </div>
      </div>

      {/* ═══════ SERIAL LIST TAB ═══════ */}
      {tab === 'list' && (
        <div className="space-y-4">
          {/* Status summary cards */}
          <div className="grid grid-cols-3 gap-3">
            <button onClick={() => setListFilter('ongoing')} className={`rounded-xl p-4 border text-left transition-all ${listFilter === 'ongoing' ? 'border-blue-300 bg-blue-50 shadow-md' : 'border-slate-200 bg-white hover:border-blue-200'}`}>
              <p className="text-2xl font-bold text-blue-700">{ongoingCount}</p>
              <p className="text-xs text-blue-600 font-medium mt-0.5">Ongoing</p>
              <div className="w-full bg-blue-100 rounded-full h-1.5 mt-2"><div className="bg-blue-500 h-1.5 rounded-full" style={{ width: `${serialList.length ? (ongoingCount / serialList.length * 100) : 0}%` }}></div></div>
            </button>
            <button onClick={() => setListFilter('completed')} className={`rounded-xl p-4 border text-left transition-all ${listFilter === 'completed' ? 'border-emerald-300 bg-emerald-50 shadow-md' : 'border-slate-200 bg-white hover:border-emerald-200'}`}>
              <p className="text-2xl font-bold text-emerald-700">{completedCount}</p>
              <p className="text-xs text-emerald-600 font-medium mt-0.5">Selesai</p>
              <div className="w-full bg-emerald-100 rounded-full h-1.5 mt-2"><div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: `${serialList.length ? (completedCount / serialList.length * 100) : 0}%` }}></div></div>
            </button>
            <button onClick={() => setListFilter('pending')} className={`rounded-xl p-4 border text-left transition-all ${listFilter === 'pending' ? 'border-amber-300 bg-amber-50 shadow-md' : 'border-slate-200 bg-white hover:border-amber-200'}`}>
              <p className="text-2xl font-bold text-amber-700">{pendingCount}</p>
              <p className="text-xs text-amber-600 font-medium mt-0.5">Menunggu</p>
              <div className="w-full bg-amber-100 rounded-full h-1.5 mt-2"><div className="bg-amber-500 h-1.5 rounded-full" style={{ width: `${serialList.length ? (pendingCount / serialList.length * 100) : 0}%` }}></div></div>
            </button>
          </div>

          {/* Search + filter bar */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input type="text" value={listSearch} onChange={e => setListSearch(e.target.value)} placeholder="Cari nomor serial, produk, PO..." className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white" data-testid="serial-list-search" />
            </div>
            <button onClick={() => setListFilter('all')} className={`px-4 py-2 rounded-xl text-sm font-medium border ${listFilter === 'all' ? 'bg-slate-800 text-white border-slate-800' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}>Semua</button>
          </div>

          {/* Serial list */}
          {listLoading ? (
            <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
          ) : serialList.length === 0 ? (
            <div className="text-center py-16 text-slate-400">
              <Hash className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Tidak ada serial number ditemukan</p>
            </div>
          ) : (
            <div className="space-y-2">
              {serialList.map((s, idx) => (
                <div key={`${s.serial_number}-${s.po_id}-${idx}`} className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:border-blue-200 transition-all">
                  <button onClick={() => loadTraceForSerial(s.serial_number)} className="w-full text-left p-4 flex items-center gap-4" data-testid={`serial-row-${idx}`}>
                    <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${s.status === 'ongoing' ? 'bg-blue-500 animate-pulse' : s.status === 'completed' ? 'bg-emerald-500' : 'bg-amber-400'}`}></div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-800 text-sm font-mono">{s.serial_number}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium border ${STATUS_COLORS[s.status]}`}>{STATUS_LABELS[s.status]}</span>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                        <span>{s.product_name}</span>
                        <span className="text-slate-300">|</span>
                        <span className="font-mono">{s.sku}</span>
                        <span className="text-slate-300">|</span>
                        <span>{s.size}/{s.color}</span>
                      </div>
                    </div>
                    <div className="hidden md:grid grid-cols-4 gap-4 text-center flex-shrink-0">
                      <div><p className="text-xs text-slate-400">Order</p><p className="text-sm font-bold text-slate-700">{formatNum(s.ordered_qty)}</p></div>
                      <div><p className="text-xs text-slate-400">Diterima</p><p className="text-sm font-bold text-emerald-600">{formatNum(s.received_qty)}</p></div>
                      <div><p className="text-xs text-slate-400">Produksi</p><p className="text-sm font-bold text-blue-600">{formatNum(s.produced_qty)}</p></div>
                      <div><p className="text-xs text-slate-400">Kirim</p><p className="text-sm font-bold text-purple-600">{formatNum(s.shipped_qty)}</p></div>
                    </div>
                    <div className="flex-shrink-0">
                      {expandedSerial === s.serial_number ? <ChevronDown className="w-5 h-5 text-slate-400" /> : <ChevronRight className="w-5 h-5 text-slate-400" />}
                    </div>
                  </button>

                  {/* Expanded detail with mini trace */}
                  {expandedSerial === s.serial_number && traceData && (
                    <div className="border-t border-slate-100 bg-slate-50 p-4">
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4">
                        <div className="bg-white rounded-lg p-2.5 border border-slate-100 text-center">
                          <p className="text-xs text-slate-400">PO</p><p className="text-sm font-bold text-slate-700">{s.po_number}</p>
                        </div>
                        <div className="bg-white rounded-lg p-2.5 border border-slate-100 text-center">
                          <p className="text-xs text-slate-400">Customer</p><p className="text-sm font-bold text-slate-700 truncate">{s.customer_name || '-'}</p>
                        </div>
                        <div className="bg-white rounded-lg p-2.5 border border-slate-100 text-center">
                          <p className="text-xs text-slate-400">Vendor</p><p className="text-sm font-bold text-slate-700 truncate">{s.vendor_name || '-'}</p>
                        </div>
                        <div className="bg-white rounded-lg p-2.5 border border-slate-100 text-center">
                          <p className="text-xs text-slate-400">PO Status</p><p className="text-sm font-bold text-blue-600">{s.po_status}</p>
                        </div>
                        <div className="bg-white rounded-lg p-2.5 border border-slate-100 text-center">
                          <p className="text-xs text-slate-400">Remaining</p><p className="text-sm font-bold text-amber-600">{formatNum(s.remaining_qty)} pcs</p>
                        </div>
                      </div>
                      {/* Mini timeline */}
                      {(traceData.timeline || []).length > 0 && (
                        <div>
                          <p className="text-xs font-semibold text-slate-600 mb-2">Timeline ({traceData.timeline.length} events)</p>
                          <div className="space-y-1.5 max-h-48 overflow-y-auto">
                            {traceData.timeline.map((ev, i) => {
                              const Icon = getStepIcon(ev.step);
                              const color = getStepColor(ev.step);
                              return (
                                <div key={i} className="flex items-center gap-2.5">
                                  <div className={`w-6 h-6 ${color} rounded-full flex items-center justify-center flex-shrink-0`}>
                                    <Icon className="w-3 h-3 text-white" />
                                  </div>
                                  <div className="flex-1 flex items-center justify-between">
                                    <span className="text-xs font-medium text-slate-700">{ev.step}</span>
                                    <div className="flex items-center gap-2">
                                      {ev.qty > 0 && <span className="text-[10px] bg-slate-100 px-1 rounded">Qty: {ev.qty}</span>}
                                      {ev.received_qty > 0 && <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1 rounded">+{ev.received_qty}</span>}
                                      <span className="text-[10px] text-slate-400">{formatDate(ev.date)}</span>
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      <button onClick={() => { setTab('trace'); setSearchInput(s.serial_number); fetchTrace(s.serial_number); }} className="mt-3 text-xs text-blue-600 hover:text-blue-800 font-medium">
                        Lihat Trace Lengkap →
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ═══════ TRACE TIMELINE TAB ═══════ */}
      {tab === 'trace' && (
        <div className="space-y-5">
          <form onSubmit={handleSearch} className="flex gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input type="text" value={searchInput} onChange={e => setSearchInput(e.target.value)} placeholder="Ketik nomor serial (contoh: SN-001) — otomatis mencari..." className="w-full pl-10 pr-4 py-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white" data-testid="serial-search-input" />
            </div>
            <button type="submit" disabled={loading || !searchInput.trim()} className="px-6 py-3 bg-blue-600 text-white rounded-xl font-medium text-sm hover:bg-blue-700 disabled:opacity-50 transition" data-testid="serial-search-btn">{loading ? 'Mencari...' : 'Lacak'}</button>
          </form>

          {data && (
            <div className="space-y-5">
              <div className="bg-white rounded-xl border border-slate-200 p-5">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"><Clock className="w-5 h-5 text-blue-600" /></div>
                  <div>
                    <h3 className="font-semibold text-slate-800">Serial: {data.serial_number}</h3>
                    <p className="text-sm text-slate-500">{data.po_count} PO | {data.po_item_count} item ditemukan | {data.timeline.length} event</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
                  <div className="bg-blue-50 rounded-lg p-3"><p className="text-xs text-blue-600 font-medium">Total Order</p><p className="text-lg font-bold text-blue-800">{formatNum(summary.total_ordered)} pcs</p></div>
                  <div className="bg-emerald-50 rounded-lg p-3"><p className="text-xs text-emerald-600 font-medium">Diproduksi</p><p className="text-lg font-bold text-emerald-800">{formatNum(summary.total_produced)} pcs</p></div>
                  <div className="bg-amber-50 rounded-lg p-3"><p className="text-xs text-amber-600 font-medium">Belum Diproduksi</p><p className="text-lg font-bold text-amber-800">{formatNum(summary.total_not_produced)} pcs</p></div>
                  <div className="bg-purple-50 rounded-lg p-3"><p className="text-xs text-purple-600 font-medium">Sudah Dikirim</p><p className="text-lg font-bold text-purple-800">{formatNum(summary.total_shipped)} pcs</p></div>
                  <div className="bg-rose-50 rounded-lg p-3"><p className="text-xs text-rose-600 font-medium">Belum Dikirim</p><p className="text-lg font-bold text-rose-800">{formatNum(summary.total_not_shipped)} pcs</p></div>
                  <div className="bg-slate-50 rounded-lg p-3"><p className="text-xs text-slate-600 font-medium">All Serials</p><p className="text-sm font-bold text-slate-800">{(summary.all_serials || []).join(', ') || '-'}</p></div>
                </div>
                <div className="flex flex-wrap gap-4 text-sm">
                  <div className="flex items-center gap-2"><Users className="w-4 h-4 text-slate-400" /><span className="text-slate-500">Buyer:</span><span className="font-medium text-slate-800">{summary.buyer || '-'}</span></div>
                  <div className="flex items-center gap-2"><Factory className="w-4 h-4 text-slate-400" /><span className="text-slate-500">Vendor:</span><span className="font-medium text-slate-800">{summary.vendors || '-'}</span></div>
                  {poInfo.map((p, i) => (
                    <div key={i} className="flex items-center gap-2"><Package className="w-4 h-4 text-slate-400" /><span className="text-slate-500">PO:</span><span className="font-medium text-slate-800">{p.po_number}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${p.status === 'Closed' ? 'bg-slate-100 text-slate-600' : 'bg-blue-100 text-blue-700'}`}>{p.status}</span></div>
                  ))}
                </div>
              </div>

              {/* All Items */}
              <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-200 bg-slate-50"><h4 className="font-semibold text-slate-700 text-sm">Semua Item ({allItems.length})</h4></div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 border-b"><tr>
                      <th className="text-left px-4 py-2 font-medium text-slate-600">Serial</th>
                      <th className="text-left px-4 py-2 font-medium text-slate-600">Product</th>
                      <th className="text-left px-4 py-2 font-medium text-slate-600">SKU</th>
                      <th className="text-left px-4 py-2 font-medium text-slate-600">Size</th>
                      <th className="text-left px-4 py-2 font-medium text-slate-600">Color</th>
                      <th className="text-right px-4 py-2 font-medium text-slate-600">Order</th>
                      <th className="text-right px-4 py-2 font-medium text-slate-600">Produced</th>
                      <th className="text-right px-4 py-2 font-medium text-slate-600">Shipped</th>
                      <th className="text-right px-4 py-2 font-medium text-slate-600">Remaining</th>
                    </tr></thead>
                    <tbody>
                      {allItems.map((item, idx) => (
                        <tr key={idx} className={`border-b border-slate-50 ${item.is_searched_serial ? 'bg-blue-50' : 'hover:bg-slate-50'}`}>
                          <td className="px-4 py-2 font-medium">{item.serial_number} {item.is_searched_serial && <span className="ml-1 text-xs bg-blue-200 text-blue-700 px-1 rounded">searched</span>}</td>
                          <td className="px-4 py-2">{item.product_name}</td>
                          <td className="px-4 py-2">{item.sku}</td>
                          <td className="px-4 py-2">{item.size}</td>
                          <td className="px-4 py-2">{item.color}</td>
                          <td className="px-4 py-2 text-right font-medium">{item.ordered_qty}</td>
                          <td className="px-4 py-2 text-right text-emerald-600 font-medium">{item.produced_qty}</td>
                          <td className="px-4 py-2 text-right text-purple-600 font-medium">{item.shipped_qty}</td>
                          <td className="px-4 py-2 text-right text-amber-600 font-medium">{item.not_produced}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Timeline */}
              {data.timeline.length > 0 && (
                <div>
                  <h4 className="font-semibold text-slate-700 mb-3">Timeline ({data.timeline.length} events)</h4>
                  <div className="relative">
                    <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-slate-200"></div>
                    <div className="space-y-3">
                      {data.timeline.map((event, idx) => {
                        const Icon = getStepIcon(event.step);
                        const color = getStepColor(event.step);
                        const isExpanded = expandedIdx.has(idx);
                        return (
                          <div key={idx} className="relative flex gap-4 pl-2">
                            <div className={`relative z-10 w-9 h-9 ${color} rounded-full flex items-center justify-center flex-shrink-0 shadow-sm`}><Icon className="w-4 h-4 text-white" /></div>
                            <div className="flex-1 bg-white rounded-xl border border-slate-200 p-3 hover:border-slate-300 transition cursor-pointer" onClick={() => toggleExpand(idx)}>
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="font-medium text-slate-800 text-sm">{event.step}</span>
                                  <span className="text-xs text-slate-400">{formatDate(event.date)}</span>
                                </div>
                                {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                              </div>
                              <div className="flex flex-wrap gap-1.5 mt-1.5">
                                {event.qty > 0 && <span className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">Qty: {event.qty}</span>}
                                {event.qty_sent > 0 && <span className="text-xs bg-purple-100 text-purple-600 px-1.5 py-0.5 rounded">Dikirim: {event.qty_sent}</span>}
                                {event.received_qty !== undefined && <span className="text-xs bg-emerald-100 text-emerald-600 px-1.5 py-0.5 rounded">Diterima: {event.received_qty}</span>}
                                {event.missing_qty > 0 && <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded">Missing: {event.missing_qty}</span>}
                                {event.produced_qty !== undefined && event.produced_qty > 0 && <span className="text-xs bg-cyan-100 text-cyan-600 px-1.5 py-0.5 rounded">Produksi: {event.produced_qty}</span>}
                                {event.completed_quantity > 0 && <span className="text-xs bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded">+{event.completed_quantity} pcs</span>}
                                {event.qty_shipped > 0 && <span className="text-xs bg-amber-100 text-amber-600 px-1.5 py-0.5 rounded">Kirim: {event.qty_shipped}</span>}
                                {event.return_qty > 0 && <span className="text-xs bg-rose-100 text-rose-600 px-1.5 py-0.5 rounded">Retur: {event.return_qty}</span>}
                                {event.status && <span className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">{event.status}</span>}
                                {event.po_number && <span className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">{event.po_number}</span>}
                                {event.shipment_number && <span className="text-xs bg-purple-50 text-purple-600 px-1.5 py-0.5 rounded">{event.shipment_number}</span>}
                              </div>
                              {isExpanded && (
                                <div className="mt-2 pt-2 border-t border-slate-100 grid grid-cols-2 gap-1.5">
                                  {Object.entries(event).filter(([k]) => !['step', 'date', 'module'].includes(k)).map(([k, v]) => (
                                    v !== null && v !== undefined && v !== '' && (
                                      <div key={k} className="text-xs"><span className="text-slate-400">{k.replace(/_/g, ' ')}:</span> <span className="text-slate-700 font-medium">{String(v)}</span></div>
                                    )
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {!data && !loading && tab === 'trace' && (
            <div className="text-center py-16">
              <Search className="w-16 h-16 text-slate-200 mx-auto mb-4" />
              <p className="text-slate-400 text-lg">Masukkan nomor serial untuk melacak</p>
              <p className="text-slate-300 text-sm mt-1">Otomatis mencari saat mengetik (min. 2 karakter)</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
