
import { useState, useEffect, useCallback } from 'react';
import { Eye, Pencil, Trash2 } from 'lucide-react';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import { apiFetch, apiGet, apiPut, apiDelete } from '../../lib/api';

export default function InvoiceModule({ token, userRole, onNavigate }) {
  const [showDetail, setShowDetail] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [detailData, setDetailData] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [filterStatus, setFilterStatus] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [refetchKey, setRefetchKey] = useState(0);
  const [stats, setStats] = useState({ totalUnpaid: 0, totalPartial: 0 });

  const isSuperAdmin = userRole === 'superadmin';

  const refetchInvoices = () => setRefetchKey((k) => k + 1);

  // Server-paginated fetcher (Phase 10C)
  const invoicesFetcher = useCallback(async ({ page, per_page, sort_by, sort_dir, search }) => {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('per_page', String(per_page));
    if (sort_by) params.set('sort_by', sort_by);
    if (sort_dir) params.set('sort_dir', sort_dir);
    if (search) params.set('search', search);
    if (filterStatus) params.set('status', filterStatus);
    return apiGet(`/invoices?${params.toString()}`);
  }, [filterStatus]);

  // Lightweight stats fetcher
  const fetchStats = useCallback(async () => {
    try {
      const [unpaidData, partialData] = await Promise.all([
        apiGet('/invoices?status=Unpaid&page=1&per_page=200'),
        apiGet('/invoices?status=Partial&page=1&per_page=200'),
      ]);
      const unpaidItems = Array.isArray(unpaidData?.items) ? unpaidData.items : (Array.isArray(unpaidData) ? unpaidData : []);
      const partialItems = Array.isArray(partialData?.items) ? partialData.items : (Array.isArray(partialData) ? partialData : []);
      const totalUnpaid = unpaidItems.reduce((s, i) => s + (i.total_amount || 0), 0);
      const totalPartial = partialItems.reduce((s, i) => s + ((i.total_amount || 0) - (i.total_paid || 0)), 0);
      setStats({ totalUnpaid, totalPartial });
    } catch (e) { console.error('stats fetch failed', e); }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats, refetchKey]);

  const openDetail = async (row) => {
    try {
      const data = await apiGet(`/invoices/${row.id}`);
      setDetailData(data);
      setShowDetail(true);
    } catch (e) { console.error(e); }
  };

  const openEdit = (row) => {
    setEditForm({ ...row });
    setShowEdit(true);
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    try {
      await apiPut(`/invoices/${editForm.id}`, editForm);
      alert('✅ Invoice berhasil diupdate');
      setShowEdit(false);
      refetchInvoices();
    } catch (err) {
      alert(`❌ Gagal update invoice: ${err.message}`);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/invoices/${confirmDelete.id}`);
    } catch (e) { console.error(e); }
    setConfirmDelete(null);
    refetchInvoices();
  };

  const fmt = (v) => 'Rp ' + (v||0).toLocaleString('id-ID');
  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('id-ID') : '-';

  const columns = [
    { key: 'invoice_number', label: 'No. Invoice', render: (v) => <span className="font-bold text-blue-700">{v}</span> },
    { key: 'po_number', label: 'No. PO' },
    { key: 'garment_name', label: 'Garmen' },
    { key: 'produced_quantity', label: 'Qty', render: (v) => v?.toLocaleString('id-ID') },
    { key: 'cmt_price', label: 'CMT/pcs', render: (v) => fmt(v) },
    { key: 'total_amount', label: 'Total', render: (v) => <span className="font-bold">{fmt(v)}</span> },
    { key: 'total_paid', label: 'Terbayar', render: (v) => <span className="text-emerald-700 font-medium">{fmt(v)}</span> },
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v} /> },
    { key: 'created_at', label: 'Tanggal', render: (v) => fmtDate(v) },
    {
      key: 'actions', label: 'Aksi', sortable: false,
      render: (_, row) => (
        <div className="flex items-center gap-1">
          <button onClick={() => openDetail(row)} className="p-1.5 rounded hover:bg-blue-50 text-blue-600" title="Detail" data-testid={`invoice-detail-${row.id}`}>
            <Eye className="w-4 h-4" />
          </button>
          {isSuperAdmin && (
            <>
              <button onClick={() => openEdit(row)} className="p-1.5 rounded hover:bg-amber-50 text-amber-600" title="Edit">
                <Pencil className="w-4 h-4" />
              </button>
              <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-500" title="Hapus">
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      )
    }
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Manajemen Invoice</h1>
          <p className="text-slate-500 text-sm mt-1">Kelola semua invoice vendor dan buyer — Manual & Adjustment</p>
        </div>
        {isSuperAdmin && (
          <span className="flex items-center gap-1.5 px-2.5 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>
            Mode Superadmin
          </span>
        )}
      </div>

      {(stats.totalUnpaid > 0 || stats.totalPartial > 0) && (
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-red-50 border border-red-200 rounded-xl p-4">
            <p className="text-sm text-red-600">Belum Dibayar</p>
            <p className="text-xl font-bold text-red-700 mt-1" data-testid="invoice-stat-unpaid">{fmt(stats.totalUnpaid)}</p>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
            <p className="text-sm text-amber-600">Sebagian Dibayar</p>
            <p className="text-xl font-bold text-amber-700 mt-1" data-testid="invoice-stat-partial">{fmt(stats.totalPartial)}</p>
          </div>
        </div>
      )}

      <div className="flex gap-2">
        {['','Unpaid','Partial','Paid'].map(s => (
          <button key={s} onClick={() => setFilterStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              filterStatus===s ? 'bg-blue-600 text-white border-blue-600' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
            data-testid={`invoice-filter-${s || 'all'}`}>{s || 'Semua'}</button>
        ))}
      </div>

      <DataTable
        columns={columns}
        searchKeys={['invoice_number','garment_name','po_number']}
        storageKey="invoices"
        serverPagination={{
          fetcher: invoicesFetcher,
          deps: [filterStatus, refetchKey],
          itemLabel: 'invoice',
          initialSort: { key: 'created_at', dir: 'desc' },
          virtualize: true,
          virtualizeHeight: 600,
        }}
      />

      {showEdit && isSuperAdmin && (
        <Modal title="Edit Invoice" onClose={() => setShowEdit(false)}>
          <form onSubmit={handleEditSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-50 rounded-lg p-3"><p className="text-xs text-slate-500">No. Invoice</p><p className="font-bold">{editForm.invoice_number}</p></div>
              <div className="bg-slate-50 rounded-lg p-3"><p className="text-xs text-slate-500">Garmen</p><p className="font-medium">{editForm.garment_name}</p></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Qty Produksi</label>
                <input type="number" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={editForm.produced_quantity||''} onChange={e => setEditForm({...editForm, produced_quantity: Number(e.target.value), total_amount: Number(e.target.value)*(editForm.cmt_price||0)})} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">CMT Price</label>
                <input type="number" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={editForm.cmt_price||''} onChange={e => setEditForm({...editForm, cmt_price: Number(e.target.value), total_amount: (editForm.produced_quantity||0)*Number(e.target.value)})} />
              </div>
            </div>
            <div className="bg-blue-50 rounded-lg p-3 text-sm">
              Total: <span className="font-bold">{fmt(editForm.total_amount)}</span>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Status</label>
              <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={editForm.status} onChange={e => setEditForm({...editForm, status: e.target.value})}>
                <option value="Unpaid">Unpaid</option>
                <option value="Partial">Partial</option>
                <option value="Paid">Paid</option>
              </select>
            </div>
            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700">Simpan</button>
              <button type="button" onClick={() => setShowEdit(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {showDetail && detailData && (
        <Modal title={`Invoice: ${detailData.invoice_number}`} onClose={() => setShowDetail(false)} size="lg">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              {[{l:'No. Invoice',v:detailData.invoice_number},{l:'No. PO',v:detailData.po_number},
                {l:'Garmen',v:detailData.garment_name},{l:'Produk',v:detailData.product_name},
                {l:'Qty Diproduksi',v:`${detailData.produced_quantity?.toLocaleString('id-ID')} pcs`},
                {l:'CMT Price',v:fmt(detailData.cmt_price)}].map(item => (
                <div key={item.l} className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">{item.l}</p>
                  <p className="font-medium text-sm mt-0.5">{item.v}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-blue-50 rounded-lg p-3"><p className="text-xs text-blue-600">Total Invoice</p><p className="font-bold text-blue-800">{fmt(detailData.total_amount)}</p></div>
              <div className="bg-emerald-50 rounded-lg p-3"><p className="text-xs text-emerald-600">Terbayar</p><p className="font-bold text-emerald-800">{fmt(detailData.total_paid)}</p></div>
              <div className="bg-orange-50 rounded-lg p-3"><p className="text-xs text-orange-600">Sisa</p><p className="font-bold text-orange-800">{fmt((detailData.total_amount||0)-(detailData.total_paid||0))}</p></div>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm font-medium text-slate-700">Status:</span>
              <StatusBadge status={detailData.status} />
            </div>
            {detailData.payments?.length > 0 && (
              <div>
                <h4 className="font-semibold text-slate-700 mb-2">Riwayat Pembayaran</h4>
                <div className="space-y-2">
                  {detailData.payments.map(p => (
                    <div key={p.id} className="flex justify-between items-center p-2.5 border border-slate-200 rounded-lg">
                      <div>
                        <p className="text-sm font-medium">{fmtDate(p.payment_date)}</p>
                        <p className="text-xs text-slate-500">{p.payment_method} {p.reference && `- ${p.reference}`}</p>
                      </div>
                      <span className="font-bold text-emerald-700">{fmt(p.amount)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {detailData.status !== 'Paid' && (
              <button onClick={() => { setShowDetail(false); onNavigate && onNavigate('payments', detailData); }}
                className="w-full bg-emerald-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-emerald-700">
                Catat Pembayaran
              </button>
            )}
          </div>
        </Modal>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Hapus Invoice?"
          message={`Invoice "${confirmDelete.invoice_number}" dan semua data pembayaran terkait akan dihapus permanen.`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
