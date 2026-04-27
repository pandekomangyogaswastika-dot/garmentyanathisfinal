import { useState, useEffect, useCallback } from 'react';
import { Package, Truck, BarChart3, FileText, LogOut, Search, Clock, ChevronRight, ChevronDown, Download } from 'lucide-react';
import { apiGet, apiFetch } from '../../lib/api';

const TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
  { id: 'pos', label: 'My POs', icon: Package },
  { id: 'shipments', label: 'Shipment History', icon: Truck },
  { id: 'serial', label: 'Serial Tracking', icon: Clock },
];

export default function BuyerPortalApp({ user, token, onLogout }) {
  const [tab, setTab] = useState('dashboard');
  const [dashboard, setDashboard] = useState(null);
  const [pos, setPos] = useState([]);
  const [shipments, setShipments] = useState([]);
  const [selectedShip, setSelectedShip] = useState(null);
  const [serialQuery, setSerialQuery] = useState('');
  const [serialData, setSerialData] = useState(null);
  const [loading, setLoading] = useState(false);

  const api = useCallback(async (path) => {
    return apiGet(`/buyer/portal/${path}`);
  }, []);

  const downloadDispatchPDF = useCallback(async (shipmentId, dispatchSeq) => {
    try {
      const res = await apiFetch(
        `/export-pdf?type=buyer-shipment-dispatch&shipment_id=${shipmentId}&dispatch_seq=${dispatchSeq}`
      );
      if (!res.ok) {
        let msg = `Gagal download PDF (HTTP ${res.status})`;
        try { const j = await res.json(); msg = j.detail || j.error || msg; } catch (_) {}
        alert(msg);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `buyer-shipment-dispatch-${dispatchSeq}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('Gagal download PDF: ' + (err.message || err));
    }
  }, []);

  useEffect(() => {
    if (tab === 'dashboard') api('dashboard').then(setDashboard);
    if (tab === 'pos') api('pos').then(setPos);
    if (tab === 'shipments') api('shipments').then(setShipments);
  }, [tab, api]);

  const viewShipDetail = async (id) => {
    const data = await api(`shipments/${id}`);
    setSelectedShip(data);
  };

  const searchSerial = async () => {
    if (!serialQuery.trim()) return;
    setLoading(true);
    const data = await api(`serial-trace?serial=${encodeURIComponent(serialQuery)}`);
    setSerialData(data);
    setLoading(false);
  };

  const formatDate = (d) => {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return d; }
  };

  const formatRp = (n) => `Rp ${(n || 0).toLocaleString('id-ID')}`;

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <div className="w-64 bg-emerald-900 text-white flex flex-col">
        <div className="p-4 border-b border-emerald-700">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center">
              <Package className="w-5 h-5" />
            </div>
            <div>
              <div className="font-bold text-sm">BUYER PORTAL</div>
              <div className="text-emerald-300 text-xs">Garment ERP</div>
            </div>
          </div>
        </div>
        <div className="px-4 py-3 border-b border-emerald-700">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-emerald-600 rounded-full flex items-center justify-center text-sm font-bold">
              {user?.name?.[0]?.toUpperCase() || 'B'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{user?.name}</div>
              <div className="text-xs text-emerald-300">{user?.customer_name || 'Buyer'}</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 py-2">
          {TABS.map(t => {
            const Icon = t.icon;
            return (
              <button key={t.id} onClick={() => { setTab(t.id); setSelectedShip(null); }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition ${tab === t.id ? 'bg-emerald-600 text-white' : 'text-emerald-200 hover:bg-emerald-800'}`}>
                <Icon className="w-5 h-5" /><span>{t.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="border-t border-emerald-700 p-2">
          <button onClick={onLogout} className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-emerald-200 hover:bg-emerald-800 rounded">
            <LogOut className="w-5 h-5" /><span>Logout</span>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* DASHBOARD */}
        {tab === 'dashboard' && dashboard && (
          <div className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-slate-800">Selamat Datang, {user?.name}</h2>
              <p className="text-slate-500 text-sm">{dashboard.customer_name}</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {[{ label: 'Total PO', value: dashboard.totalPOs, color: 'blue' },
                { label: 'PO Aktif', value: dashboard.activePOs, color: 'emerald' },
                { label: 'PO Selesai', value: dashboard.completedPOs, color: 'purple' },
                { label: 'Progress', value: `${dashboard.progressPct}%`, color: 'amber' },
              ].map((c, i) => (
                <div key={i} className="bg-white rounded-xl border border-slate-200 p-5">
                  <p className="text-sm text-slate-500">{c.label}</p>
                  <p className={`text-2xl font-bold text-${c.color}-600 mt-1`}>{c.value}</p>
                </div>
              ))}
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h3 className="font-semibold text-slate-800 mb-3">Ringkasan Pengiriman</h3>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div><span className="text-slate-400">Total Order:</span> <span className="font-medium">{dashboard.totalOrdered} pcs</span></div>
                <div><span className="text-slate-400">Sudah Dikirim:</span> <span className="font-medium text-emerald-600">{dashboard.totalShipped} pcs</span></div>
                <div><span className="text-slate-400">Total Dispatch:</span> <span className="font-medium">{dashboard.totalDispatches}</span></div>
              </div>
              <div className="mt-3 bg-slate-100 rounded-full h-3 overflow-hidden">
                <div className="bg-emerald-500 h-full rounded-full transition-all" style={{ width: `${dashboard.progressPct}%` }}></div>
              </div>
            </div>
          </div>
        )}

        {/* POs */}
        {tab === 'pos' && (
          <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">My Purchase Orders</h2>
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">PO Number</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Vendor</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Items</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Total Qty</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Status</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {pos.length === 0 ? (
                    <tr><td colSpan="6" className="text-center py-8 text-slate-400">Belum ada PO</td></tr>
                  ) : pos.map(po => (
                    <tr key={po.id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-blue-600">{po.po_number}</td>
                      <td className="px-4 py-3">{po.vendor_name || '-'}</td>
                      <td className="px-4 py-3">{po.item_count}</td>
                      <td className="px-4 py-3">{po.total_qty}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          po.status === 'Closed' ? 'bg-slate-100 text-slate-600' :
                          po.status === 'In Production' ? 'bg-blue-100 text-blue-700' :
                          po.status === 'Production Complete' ? 'bg-emerald-100 text-emerald-700' :
                          'bg-amber-100 text-amber-700'
                        }`}>{po.status}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{formatDate(po.po_date || po.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* SHIPMENTS */}
        {tab === 'shipments' && !selectedShip && (
          <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">Shipment History</h2>
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Shipment</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">PO</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Ordered</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Shipped</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Progress</th>
                    <th className="text-left px-4 py-3 font-medium text-slate-600">Dispatches</th>
                    <th className="text-right px-4 py-3 font-medium text-slate-600">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {shipments.length === 0 ? (
                    <tr><td colSpan="7" className="text-center py-8 text-slate-400">Belum ada shipment</td></tr>
                  ) : shipments.map(s => (
                    <tr key={s.id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium">{s.shipment_number}</td>
                      <td className="px-4 py-3">{s.po_number}</td>
                      <td className="px-4 py-3">{s.total_ordered}</td>
                      <td className="px-4 py-3 text-emerald-600 font-medium">{s.total_shipped}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-slate-100 rounded-full h-2 max-w-[80px]">
                            <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${s.progress_pct}%` }}></div>
                          </div>
                          <span className="text-xs text-slate-500">{s.progress_pct}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">{s.dispatch_count}</td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => viewShipDetail(s.id)} className="text-blue-600 hover:text-blue-800 text-sm" data-testid={`view-ship-${s.id}`}>
                          Detail <ChevronRight className="w-4 h-4 inline" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* SHIPMENT DETAIL */}
        {tab === 'shipments' && selectedShip && (
          <div className="space-y-4">
            <button onClick={() => setSelectedShip(null)} className="text-sm text-blue-600 hover:text-blue-800">&larr; Kembali ke daftar</button>
            <h2 className="text-2xl font-bold text-slate-800">Shipment: {selectedShip.shipment_number}</h2>
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div><span className="text-slate-400">PO:</span> <span className="font-medium">{selectedShip.po_number}</span></div>
                <div><span className="text-slate-400">Customer:</span> <span className="font-medium">{selectedShip.customer_name}</span></div>
                <div><span className="text-slate-400">Vendor:</span> <span className="font-medium">{selectedShip.vendor_name}</span></div>
                <div><span className="text-slate-400">Status:</span> <span className="font-medium">{selectedShip.ship_status}</span></div>
              </div>
            </div>
            {(selectedShip.dispatches || []).map(d => (
              <div key={d.dispatch_seq} className="bg-white rounded-xl border border-slate-200 p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-slate-800">Dispatch #{d.dispatch_seq} — {formatDate(d.dispatch_date)}</h3>
                  <button
                    type="button"
                    onClick={() => downloadDispatchPDF(selectedShip.id, d.dispatch_seq)}
                    className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800"
                    data-testid={`download-dispatch-pdf-${d.dispatch_seq}`}
                  >
                    <Download className="w-4 h-4" /> PDF
                  </button>
                </div>
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left px-3 py-2 text-slate-600">Product</th>
                      <th className="text-left px-3 py-2 text-slate-600">SKU</th>
                      <th className="text-left px-3 py-2 text-slate-600">Size</th>
                      <th className="text-left px-3 py-2 text-slate-600">Color</th>
                      <th className="text-right px-3 py-2 text-slate-600">Qty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(d.items || []).map((it, idx) => (
                      <tr key={idx} className="border-b border-slate-50">
                        <td className="px-3 py-2">{it.product_name}</td>
                        <td className="px-3 py-2">{it.sku}</td>
                        <td className="px-3 py-2">{it.size}</td>
                        <td className="px-3 py-2">{it.color}</td>
                        <td className="px-3 py-2 text-right font-medium">{it.qty_shipped}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="text-right text-sm font-medium text-slate-600 mt-2">Total: {d.total_qty} pcs</div>
              </div>
            ))}
          </div>
        )}

        {/* SERIAL TRACKING */}
        {tab === 'serial' && (
          <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">Serial Tracking</h2>
            <form onSubmit={e => { e.preventDefault(); searchSerial(); }} className="flex gap-3">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input type="text" value={serialQuery} onChange={e => setSerialQuery(e.target.value)}
                  placeholder="Masukkan nomor serial..." className="w-full pl-10 pr-4 py-3 border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white" />
              </div>
              <button type="submit" disabled={loading} className="px-6 py-3 bg-emerald-600 text-white rounded-xl text-sm hover:bg-emerald-700 disabled:opacity-50">
                {loading ? 'Mencari...' : 'Lacak'}
              </button>
            </form>
            {serialData && (
              <div className="space-y-3">
                <p className="text-sm text-slate-500">{serialData.timeline.length} event ditemukan untuk serial: <b>{serialData.serial_number}</b></p>
                {serialData.timeline.map((ev, i) => (
                  <div key={i} className="bg-white rounded-lg border border-slate-200 p-4">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-800 text-sm">{ev.step}</span>
                      <span className="text-xs text-slate-400">{formatDate(ev.date)}</span>
                    </div>
                    <div className="flex flex-wrap gap-2 mt-2">
                      {ev.qty > 0 && <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded">Qty: {ev.qty}</span>}
                      {ev.qty_shipped > 0 && <span className="text-xs bg-emerald-100 text-emerald-600 px-2 py-0.5 rounded">Shipped: {ev.qty_shipped}</span>}
                      {ev.status && <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">{ev.status}</span>}
                      {ev.po_number && <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">{ev.po_number}</span>}
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
}
