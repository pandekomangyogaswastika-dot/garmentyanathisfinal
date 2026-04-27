import { useState } from 'react';
import { Plus, Pencil, Trash2, ChevronDown, ChevronRight, Camera, Upload, Image } from 'lucide-react';
import DataTable from './DataTable';
import Modal from './Modal';
import StatusBadge from './StatusBadge';
import ConfirmDialog from './ConfirmDialog';
import ImportExportPanel from './ImportExportPanel';
import { apiGet, apiPost, apiPut, apiDelete } from '../../lib/api';

export default function ProductsModule({ userRole, hasPerm = () => false }) {
  const [showModal, setShowModal] = useState(false);
  const [showVariantModal, setShowVariantModal] = useState(false);
  const [editData, setEditData] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [confirmDeleteVariant, setConfirmDeleteVariant] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [variants, setVariants] = useState([]);
  const [expandedProduct, setExpandedProduct] = useState(null);
  const [variantForm, setVariantForm] = useState({ size: '', color: '', sku: '' });
  const [form, setForm] = useState({ product_code: '', product_name: '', category: '', cmt_price: '', selling_price: '', status: 'active' });
  const [uploading, setUploading] = useState(false);
  const [refetchKey, setRefetchKey] = useState(0);

  const isSuperAdmin = userRole === 'superadmin' || hasPerm('products.create');
  const canEdit = ['superadmin', 'admin'].includes(userRole) || hasPerm('products.edit');

  // Trigger DataTable serverPagination refetch after mutations
  const refetchProducts = () => setRefetchKey((k) => k + 1);

  // Server-paginated fetcher (Phase 10C)
  const productsFetcher = async ({ page, per_page, sort_by, sort_dir, search }) => {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('per_page', String(per_page));
    if (sort_by) params.set('sort_by', sort_by);
    if (sort_dir) params.set('sort_dir', sort_dir);
    if (search) params.set('search', search);
    return apiGet(`/products?${params.toString()}`);
  };

  const fetchVariants = async (productId) => {
    try {
      const data = await apiGet(`/product-variants?product_id=${productId}`);
      setVariants(Array.isArray(data) ? data : []);
    } catch (e) { setVariants([]); }
  };

  const toggleExpand = async (productId) => {
    if (expandedProduct === productId) { setExpandedProduct(null); return; }
    setExpandedProduct(productId);
    await fetchVariants(productId);
  };

  const openCreate = () => {
    setEditData(null);
    setForm({ product_code: '', product_name: '', category: '', cmt_price: '', selling_price: '', status: 'active' });
    setShowModal(true);
  };

  const openEdit = (row) => {
    setEditData(row);
    setForm({ product_code: row.product_code, product_name: row.product_name, category: row.category || '', cmt_price: row.cmt_price || '', selling_price: row.selling_price || '', status: row.status });
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const payload = { ...form, cmt_price: Number(form.cmt_price) || 0, selling_price: Number(form.selling_price) || 0 };
    try {
      if (editData) {
        await apiPut(`/products/${editData.id}`, payload);
      } else {
        await apiPost('/products', payload);
      }
      setShowModal(false);
      refetchProducts();
    } catch (e) { alert(e.message || 'Gagal menyimpan produk'); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await apiDelete(`/products/${confirmDelete.id}`);
      setConfirmDelete(null);
      refetchProducts();
    } catch (e) { alert(e.message || 'Gagal menghapus produk'); }
  };

  const handlePhotoUpload = async (productId, file) => {
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await apiPost(`/products/${productId}/photo`, formData);
      refetchProducts();
    } catch (e) { alert('Upload error: ' + e.message); }
    finally { setUploading(false); }
  };

  const openAddVariant = (product) => {
    setSelectedProduct(product);
    setVariantForm({ size: '', color: '', sku: '' });
    setShowVariantModal(true);
  };

  const handleAddVariant = async (e) => {
    e.preventDefault();
    try {
      await apiPost('/product-variants', { ...variantForm, product_id: selectedProduct.id });
      setShowVariantModal(false);
      await fetchVariants(selectedProduct.id);
    } catch (e) { alert(e.message || 'Gagal menambah varian'); }
  };

  const handleDeleteVariant = async () => {
    if (!confirmDeleteVariant) return;
    try {
      await apiDelete(`/product-variants/${confirmDeleteVariant.id}`);
      setConfirmDeleteVariant(null);
      if (expandedProduct) await fetchVariants(expandedProduct);
    } catch (e) { alert(e.message || 'Gagal menghapus varian'); }
  };

  const fmt = (v) => v ? 'Rp ' + Number(v).toLocaleString('id-ID') : '-';

  const ProductPhoto = ({ product, size = 'sm' }) => {
    const s = size === 'sm' ? 'w-8 h-8' : size === 'md' ? 'w-12 h-12' : 'w-24 h-24';
    if (product.photo_url) {
      return <img src={product.photo_url} alt={product.product_name} className={`${s} rounded-lg object-cover border border-slate-200`} />;
    }
    return <div className={`${s} rounded-lg bg-slate-100 flex items-center justify-center border border-slate-200`}><Image className={`${size === 'sm' ? 'w-3.5 h-3.5' : size === 'md' ? 'w-5 h-5' : 'w-8 h-8'} text-slate-300`} /></div>;
  };

  const columns = [
    { key: 'expand', label: '', render: (_, row) => (
      <button onClick={() => toggleExpand(row.id)} className="p-1 text-slate-400 hover:text-blue-600">
        {expandedProduct === row.id ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>
    )},
    { key: 'photo', label: 'Foto', render: (_, row) => <ProductPhoto product={row} size="sm" /> },
    { key: 'product_code', label: 'Kode', render: (v) => <span className="font-mono text-xs font-bold text-slate-700">{v}</span> },
    { key: 'product_name', label: 'Nama Produk' },
    { key: 'category', label: 'Kategori' },
    { key: 'cmt_price', label: 'CMT Price', render: (v) => <span className="font-medium text-amber-700">{fmt(v)}</span> },
    { key: 'selling_price', label: 'Selling Price', render: (v) => <span className="font-medium text-emerald-700">{fmt(v)}</span> },
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v} /> },
    {
      key: 'actions', label: 'Aksi',
      render: (_, row) => (
        <div className="flex items-center gap-1">
          <label className="p-1.5 rounded hover:bg-purple-50 text-purple-600 transition-colors cursor-pointer" title="Upload Foto">
            <Camera className="w-4 h-4" />
            <input type="file" accept="image/*" className="hidden" onChange={e => handlePhotoUpload(row.id, e.target.files[0])} />
          </label>
          <button onClick={() => openAddVariant(row)} className="p-1.5 rounded hover:bg-blue-50 text-blue-600 text-xs transition-colors" title="Tambah Varian">
            + Varian
          </button>
          {isSuperAdmin && (
            <>
              <button onClick={() => openEdit(row)} className="p-1.5 rounded hover:bg-amber-50 text-amber-600 transition-colors" title="Edit"><Pencil className="w-4 h-4" /></button>
              <button onClick={() => setConfirmDelete(row)} className="p-1.5 rounded hover:bg-red-50 text-red-500 transition-colors" title="Hapus"><Trash2 className="w-4 h-4" /></button>
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
          <h1 className="text-2xl font-bold text-slate-800">Data Produk</h1>
          <p className="text-slate-500 text-sm mt-1">Kelola produk, foto, harga CMT, harga jual, dan varian SKU</p>
        </div>
        {isSuperAdmin && <span className="flex items-center gap-1.5 px-2.5 py-1 bg-purple-100 text-purple-700 rounded-lg text-xs font-medium"><span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span>Mode Superadmin</span>}
      </div>

      <DataTable
        columns={columns}
        searchKeys={['product_code', 'product_name', 'category']}
        storageKey="products"
        serverPagination={{
          fetcher: productsFetcher,
          deps: [refetchKey],
          itemLabel: 'produk',
          initialSort: { key: 'created_at', dir: 'desc' },
          virtualize: true,
          virtualizeHeight: 600,
        }}
        expandedRow={(row) => expandedProduct === row.id ? (
          <div className="bg-slate-50 border-t border-slate-100 p-4">
            <div className="flex items-center gap-4 mb-4">
              <ProductPhoto product={row} size="lg" />
              <div>
                <h4 className="text-sm font-semibold text-slate-700">Varian Produk — {row.product_name}</h4>
                <p className="text-xs text-slate-400 mt-0.5">{row.category || 'Tanpa kategori'}</p>
                {canEdit && (
                  <label className="inline-flex items-center gap-1.5 mt-2 px-3 py-1.5 bg-purple-50 border border-purple-200 rounded-lg text-xs text-purple-700 cursor-pointer hover:bg-purple-100 transition-colors">
                    <Upload className="w-3.5 h-3.5" /> {uploading ? 'Uploading...' : 'Upload Foto'}
                    <input type="file" accept="image/*" className="hidden" onChange={e => handlePhotoUpload(row.id, e.target.files[0])} disabled={uploading} />
                  </label>
                )}
              </div>
            </div>
            {variants.filter(v => v.product_id === row.id).length === 0 ? (
              <p className="text-sm text-slate-400 italic">Belum ada varian. Klik "+ Varian" untuk menambahkan.</p>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                {variants.filter(v => v.product_id === row.id).map(v => (
                  <div key={v.id} className="bg-white border border-slate-200 rounded-lg p-2.5 flex items-start justify-between">
                    <div>
                      <p className="text-xs font-bold text-slate-800">{v.sku}</p>
                      <p className="text-xs text-slate-500">{v.size} / {v.color}</p>
                    </div>
                    {isSuperAdmin && (
                      <button onClick={() => setConfirmDeleteVariant(v)} className="text-red-400 hover:text-red-600 ml-1"><Trash2 className="w-3.5 h-3.5" /></button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}
        actions={
          <div className="flex items-center gap-2">
            <ImportExportPanel importType="products" exportType={null} onImportSuccess={() => refetchProducts()} />
            {isSuperAdmin && (
              <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700" data-testid="add-product-btn">
                <Plus className="w-4 h-4" /> Tambah Produk
              </button>
            )}
          </div>
        }
      />

      {/* Product Modal */}
      {showModal && (
        <Modal title={editData ? 'Edit Produk' : 'Tambah Produk'} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Kode Produk *</label>
                <input required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.product_code} onChange={e => setForm({...form, product_code: e.target.value})} placeholder="PRD-001" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Nama Produk *</label>
                <input required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.product_name} onChange={e => setForm({...form, product_name: e.target.value})} />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Kategori</label>
              <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.category} onChange={e => setForm({...form, category: e.target.value})} placeholder="Kemeja, Celana, Kaos..." />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">CMT Price (Rp)</label>
                <input type="number" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.cmt_price} onChange={e => setForm({...form, cmt_price: e.target.value})} placeholder="35000" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Selling Price (Rp)</label>
                <input type="number" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.selling_price} onChange={e => setForm({...form, selling_price: e.target.value})} placeholder="85000" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Status</label>
              <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.status} onChange={e => setForm({...form, status: e.target.value})}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
            <div className="flex gap-3 pt-2">
              <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700">{editData ? 'Simpan Perubahan' : 'Tambah Produk'}</button>
              <button type="button" onClick={() => setShowModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm hover:bg-slate-50">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Variant Modal */}
      {showVariantModal && selectedProduct && (
        <Modal title={`Tambah Varian — ${selectedProduct.product_name}`} onClose={() => setShowVariantModal(false)}>
          <form onSubmit={handleAddVariant} className="space-y-4">
            <div className="bg-blue-50 rounded-lg p-3 text-sm text-blue-700">
              <p>Kode Produk: <strong>{selectedProduct.product_code}</strong></p>
              <p className="text-xs mt-1 text-blue-600">Contoh SKU: {selectedProduct.product_code}-BLK-M</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Ukuran *</label>
                <input required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={variantForm.size} onChange={e => setVariantForm({...variantForm, size: e.target.value})} placeholder="S, M, L, XL..." />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Warna *</label>
                <input required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={variantForm.color} onChange={e => setVariantForm({...variantForm, color: e.target.value})} placeholder="Hitam, Putih..." />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">SKU *</label>
              <input required className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono" value={variantForm.sku} onChange={e => setVariantForm({...variantForm, sku: e.target.value})} placeholder={`${selectedProduct.product_code}-BLK-M`} />
            </div>
            <div className="flex gap-3">
              <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700">Tambah Varian</button>
              <button type="button" onClick={() => setShowVariantModal(false)} className="flex-1 border border-slate-200 py-2 rounded-lg text-sm hover:bg-slate-50">Batal</button>
            </div>
          </form>
        </Modal>
      )}

      {confirmDelete && <ConfirmDialog title="Hapus Produk?" message={`Produk "${confirmDelete.product_name}" dan semua variannya akan dihapus permanen.`} onConfirm={handleDelete} onCancel={() => setConfirmDelete(null)} />}
      {confirmDeleteVariant && <ConfirmDialog title="Hapus Varian?" message={`Varian SKU "${confirmDeleteVariant.sku}" (${confirmDeleteVariant.size}/${confirmDeleteVariant.color}) akan dihapus permanen.`} onConfirm={handleDeleteVariant} onCancel={() => setConfirmDeleteVariant(null)} />}
    </div>
  );
}
