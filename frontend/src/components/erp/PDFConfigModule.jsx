import { useState, useEffect, useCallback } from 'react';
import {
  FileDown, Plus, Trash2, Star, Check, X, Settings, Download,
  ChevronDown, ChevronRight, Save, Edit2, Info, GripVertical,
  RotateCw, Type, FileText, Layers, Copy, Lock
} from 'lucide-react';
import {
  DndContext, closestCenter, KeyboardSensor, PointerSensor,
  useSensor, useSensors
} from '@dnd-kit/core';
import {
  arrayMove, SortableContext, sortableKeyboardCoordinates,
  useSortable, verticalListSortingStrategy
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { apiGet, apiPost, apiPut, apiDelete, apiFetch } from '../../lib/api';

const PDF_TYPE_LABELS = {
  'production-po': 'SPP (Surat Perintah Produksi)',
  'vendor-shipment': 'Surat Jalan Material',
  'vendor-inspection': 'Laporan Inspeksi Material',
  'buyer-shipment': 'Surat Jalan Buyer (Summary)',
  'buyer-shipment-dispatch': 'Surat Jalan Buyer (Per Dispatch)',
  'production-return': 'Surat Retur Produksi',
  'material-request': 'Surat Permohonan Material',
  'production-report': 'Laporan Produksi Lengkap',
  'report-production': 'Report: Produksi',
  'report-progress': 'Report: Progres',
  'report-financial': 'Report: Keuangan',
  'report-shipment': 'Report: Pengiriman',
  'report-defect': 'Report: Defect',
  'report-return': 'Report: Retur',
  'report-missing-material': 'Report: Material Hilang',
  'report-replacement': 'Report: Pengganti',
  'report-accessory': 'Report: Aksesoris',
};

const PDF_TYPE_GROUPS = {
  'Documents': [
    'production-po', 'vendor-shipment', 'vendor-inspection',
    'buyer-shipment', 'buyer-shipment-dispatch',
    'production-return', 'material-request', 'production-report'
  ],
  'Reports': [
    'report-production', 'report-progress', 'report-financial',
    'report-shipment', 'report-defect', 'report-return',
    'report-missing-material', 'report-replacement', 'report-accessory'
  ],
};

// ─── Sortable Column Item ─────────────────────────────────────
function SortableColumn({ col, selected, required, onToggle }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: col.key });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  return (
    <div ref={setNodeRef} style={style}
         className={`flex items-center gap-2 px-2.5 py-2 rounded-lg border text-sm transition-all ${
           selected
             ? 'bg-blue-50 border-blue-300 text-blue-800'
             : 'bg-white border-slate-200 text-slate-500 opacity-60'
         } ${required ? 'ring-1 ring-amber-200' : ''}`}
         data-testid={`sortable-column-${col.key}`}>
      <button
        type="button"
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing touch-none text-slate-400 hover:text-slate-600"
        data-testid={`drag-handle-${col.key}`}
        aria-label={`Drag ${col.label}`}
      >
        <GripVertical className="w-4 h-4" />
      </button>
      <button
        type="button"
        onClick={() => onToggle(col.key)}
        disabled={required}
        className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 transition-colors ${
          selected ? 'bg-blue-600 text-white' : 'border border-slate-300 hover:border-blue-400'
        } ${required ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'}`}
        data-testid={`toggle-column-${col.key}`}
        aria-label={`Toggle ${col.label}`}
      >
        {selected && <Check className="w-3 h-3" />}
      </button>
      <span className="truncate flex-1">{col.label}</span>
      {required && <span className="text-xs text-amber-500 flex-shrink-0" title="Kolom wajib">*</span>}
    </div>
  );
}

export default function PDFConfigModule({ userRole }) {
  const [configs, setConfigs] = useState([]);
  const [columns, setColumns] = useState([]);
  const [selectedType, setSelectedType] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editConfig, setEditConfig] = useState(null);
  // Form state
  const [formName, setFormName] = useState('');
  const [formColumns, setFormColumns] = useState([]); // ordered array of selected keys
  const [formDefault, setFormDefault] = useState(false);
  const [formOrientation, setFormOrientation] = useState('auto');
  const [formUseCS, setFormUseCS] = useState(true);
  const [formCustomTitle, setFormCustomTitle] = useState('');
  const [formCustomHeader1, setFormCustomHeader1] = useState('');
  const [formCustomHeader2, setFormCustomHeader2] = useState('');
  const [formCustomFooter, setFormCustomFooter] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState({ Documents: true, Reports: true });
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const canEdit = ['superadmin', 'admin'].includes((userRole || '').toLowerCase());

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const fetchConfigs = useCallback(async () => {
    try {
      const data = await apiGet('/pdf-export-configs');
      setConfigs(Array.isArray(data) ? data : []);
    } catch (e) { console.error('Failed to fetch PDF configs:', e); }
  }, []);

  const fetchColumns = useCallback(async (type) => {
    if (!type) { setColumns([]); return []; }
    try {
      const data = await apiGet(`/pdf-export-columns?type=${type}`);
      const cols = data.columns || [];
      setColumns(cols);
      return cols;
    } catch (e) {
      setColumns([]); return [];
    }
  }, []);

  useEffect(() => { fetchConfigs(); }, [fetchConfigs]);

  const resetForm = () => {
    setEditConfig(null);
    setFormName('');
    setFormDefault(false);
    setFormColumns([]);
    setFormOrientation('auto');
    setFormUseCS(true);
    setFormCustomTitle('');
    setFormCustomHeader1('');
    setFormCustomHeader2('');
    setFormCustomFooter('');
    setShowAdvanced(false);
  };

  const openCreateModal = async (type) => {
    resetForm();
    setSelectedType(type);
    const cols = await fetchColumns(type);
    // Preselect all columns by default in definition order
    setFormColumns(cols.map(c => c.key));
    setShowModal(true);
  };

  const openEditModal = async (cfg) => {
    resetForm();
    setSelectedType(cfg.pdf_type);
    setEditConfig(cfg);
    setFormName(cfg.name || '');
    setFormDefault(cfg.is_default || false);
    setFormColumns(cfg.columns || []);
    setFormOrientation(cfg.page_orientation || 'auto');
    setFormUseCS(cfg.use_company_settings !== false);
    setFormCustomTitle(cfg.custom_title || '');
    setFormCustomHeader1(cfg.custom_header_line1 || '');
    setFormCustomHeader2(cfg.custom_header_line2 || '');
    setFormCustomFooter(cfg.custom_footer_text || '');
    const hasOverrides = cfg.custom_title || cfg.custom_header_line1 || cfg.custom_header_line2 || cfg.custom_footer_text || cfg.page_orientation !== 'auto';
    setShowAdvanced(!!hasOverrides);
    await fetchColumns(cfg.pdf_type);
    setShowModal(true);
  };

  const openDuplicateModal = async (cfg) => {
    await openEditModal(cfg);
    setEditConfig(null); // treat as new
    setFormName(`${cfg.name} (Salinan)`);
    setFormDefault(false);
  };

  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    // Reorder formColumns
    const oldIndex = formColumns.indexOf(active.id);
    const newIndex = formColumns.indexOf(over.id);
    if (oldIndex >= 0 && newIndex >= 0) {
      setFormColumns(arrayMove(formColumns, oldIndex, newIndex));
    } else if (oldIndex < 0 && newIndex >= 0) {
      // Dragging an unselected column onto selected area — add it at newIndex
      const newArr = [...formColumns];
      newArr.splice(newIndex, 0, active.id);
      setFormColumns(newArr);
    }
  };

  const toggleColumn = (key) => {
    const col = columns.find(c => c.key === key);
    if (col?.required) return; // Can't toggle required off
    setFormColumns(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  };

  const selectAll = () => setFormColumns(columns.map(c => c.key));
  const deselectOptional = () => setFormColumns(columns.filter(c => c.required).map(c => c.key));

  const handleSave = async () => {
    if (!formName.trim()) { alert('Nama preset harus diisi'); return; }
    if (formColumns.length === 0) { alert('Pilih minimal 1 kolom'); return; }
    setSaving(true);
    try {
      const body = {
        pdf_type: selectedType,
        name: formName,
        columns: formColumns,
        is_default: formDefault,
        page_orientation: formOrientation,
        use_company_settings: formUseCS,
        custom_title: formCustomTitle.trim(),
        custom_header_line1: formCustomHeader1.trim(),
        custom_header_line2: formCustomHeader2.trim(),
        custom_footer_text: formCustomFooter.trim(),
      };
      if (editConfig) {
        await apiPut(`/pdf-export-configs/${editConfig.id}`, body);
      } else {
        await apiPost('/pdf-export-configs', body);
      }
      setShowModal(false);
      fetchConfigs();
    } catch (e) {
      alert('Error: ' + (e.message || 'Gagal menyimpan'));
    }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Hapus preset PDF ini?')) return;
    try {
      await apiDelete(`/pdf-export-configs/${id}`);
      fetchConfigs();
    } catch (e) { alert('Error: ' + (e.message || 'Gagal menghapus')); }
  };

  const handleSetDefault = async (cfg) => {
    try {
      await apiPut(`/pdf-export-configs/${cfg.id}`, { is_default: !cfg.is_default });
      fetchConfigs();
    } catch (e) { alert('Error: ' + (e.message || 'Gagal menyimpan')); }
  };

  const handleTestExport = async (type) => {
    setTestResult(null);
    try {
      const defaultConfig = configs.find(c => c.pdf_type === type && c.is_default);
      let url = `/export-pdf?type=${type}`;
      if (defaultConfig) url += `&config_id=${defaultConfig.id}`;
      const res = await apiFetch(url);
      if (res.ok) {
        const blob = await res.blob();
        const burl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = burl;
        a.download = `test_${type}.pdf`;
        a.click();
        URL.revokeObjectURL(burl);
        setTestResult({ type, ok: true, msg: 'PDF ter-download berhasil' });
      } else {
        const err = await res.json().catch(() => ({}));
        setTestResult({ type, ok: false, msg: err.detail || `HTTP ${res.status}` });
      }
    } catch (e) {
      setTestResult({ type, ok: false, msg: e.message });
    }
  };

  const getConfigsForType = (t) => configs.filter(c => c.pdf_type === t);
  const getDefaultForType = (t) => configs.find(c => c.pdf_type === t && c.is_default);
  const toggleGroup = (g) => setExpandedGroups(p => ({ ...p, [g]: !p[g] }));

  // Build ordered list for drag-drop area: selected columns first (in order), then unselected columns
  const orderedSelected = formColumns
    .map(k => columns.find(c => c.key === k))
    .filter(Boolean);
  const unselectedCols = columns.filter(c => !formColumns.includes(c.key));

  return (
    <div className="space-y-6" data-testid="pdf-config-module">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-3" data-testid="pdf-config-title">
            <div className="p-2 bg-blue-50 rounded-lg">
              <Settings className="w-6 h-6 text-blue-600" />
            </div>
            Konfigurasi Export PDF
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Atur kolom, urutan, header/footer, dan orientasi setiap jenis dokumen PDF. Preset default akan digunakan otomatis saat export.
          </p>
          {!canEdit && (
            <div className="mt-2 inline-flex items-center gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5">
              <Lock className="w-3.5 h-3.5" />
              Mode read-only — hanya Admin/Superadmin yang bisa mengubah preset.
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-50 rounded-lg px-3 py-2 flex-shrink-0" data-testid="preset-count-badge">
          <Info className="w-4 h-4" />
          <span>{configs.length} preset tersimpan</span>
        </div>
      </div>

      {/* PDF Types Grid */}
      {Object.entries(PDF_TYPE_GROUPS).map(([group, types]) => (
        <div key={group} className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <button
            type="button"
            onClick={() => toggleGroup(group)}
            className="w-full flex items-center justify-between px-5 py-3.5 bg-slate-50 hover:bg-slate-100 transition-colors"
            data-testid={`group-toggle-${group.toLowerCase()}`}
          >
            <div className="flex items-center gap-3">
              {expandedGroups[group] ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
              <span className="text-sm font-semibold text-slate-700 uppercase tracking-wide">{group}</span>
              <span className="text-xs bg-slate-200 text-slate-600 rounded-full px-2 py-0.5">{types.length}</span>
            </div>
          </button>
          {expandedGroups[group] && (
            <div className="divide-y divide-slate-100">
              {types.map(type => {
                const typeConfigs = getConfigsForType(type);
                const defaultCfg = getDefaultForType(type);
                return (
                  <div key={type} className="px-5 py-4 hover:bg-slate-50/50 transition-colors" data-testid={`pdf-type-row-${type}`}>
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <FileDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
                          <span className="text-sm font-medium text-slate-800">{PDF_TYPE_LABELS[type] || type}</span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-2">
                          {defaultCfg ? (
                            <span className="inline-flex items-center gap-1 text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-2 py-0.5">
                              <Star className="w-3 h-3 fill-current" />
                              Default: {defaultCfg.name} ({defaultCfg.columns?.length} kolom)
                            </span>
                          ) : (
                            <span className="text-xs text-slate-400">Semua kolom (default sistem)</span>
                          )}
                          {typeConfigs.length > 0 && (
                            <span className="text-xs text-slate-400">{typeConfigs.length} preset</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <button
                          type="button"
                          onClick={() => handleTestExport(type)}
                          className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title="Test Export PDF"
                          data-testid={`test-export-${type}`}
                        >
                          <Download className="w-4 h-4" />
                        </button>
                        {canEdit && (
                          <button
                            type="button"
                            onClick={() => openCreateModal(type)}
                            className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg px-3 py-1.5 transition-colors"
                            data-testid={`create-preset-${type}`}
                          >
                            <Plus className="w-3.5 h-3.5" />
                            Buat Preset
                          </button>
                        )}
                      </div>
                    </div>
                    {typeConfigs.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {typeConfigs.map(cfg => (
                          <div key={cfg.id} className="flex items-center justify-between bg-white border border-slate-200 rounded-lg px-3 py-2" data-testid={`preset-card-${cfg.id}`}>
                            <div className="flex items-center gap-3 min-w-0 flex-1">
                              <button
                                type="button"
                                onClick={() => canEdit && handleSetDefault(cfg)}
                                disabled={!canEdit}
                                className={`p-1 rounded-md transition-colors ${cfg.is_default ? 'text-amber-500 bg-amber-50' : 'text-slate-300 hover:text-amber-400 hover:bg-amber-50'} ${!canEdit ? 'cursor-not-allowed opacity-60' : ''}`}
                                title={cfg.is_default ? 'Default preset' : 'Set as default'}
                                data-testid={`toggle-default-${cfg.id}`}
                              >
                                <Star className={`w-4 h-4 ${cfg.is_default ? 'fill-current' : ''}`} />
                              </button>
                              <div className="min-w-0 flex-1">
                                <p className="text-sm font-medium text-slate-700 truncate">{cfg.name}</p>
                                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-400 mt-0.5">
                                  <span>{cfg.columns?.length || 0} kolom</span>
                                  {cfg.page_orientation && cfg.page_orientation !== 'auto' && (
                                    <span className="inline-flex items-center gap-1">
                                      <RotateCw className="w-3 h-3" />
                                      {cfg.page_orientation === 'landscape' ? 'Landscape' : 'Portrait'}
                                    </span>
                                  )}
                                  {(cfg.custom_title || cfg.custom_header_line1 || cfg.custom_footer_text) && (
                                    <span className="inline-flex items-center gap-1 text-blue-500">
                                      <Type className="w-3 h-3" />
                                      Custom header/footer
                                    </span>
                                  )}
                                  {cfg.use_company_settings === false && (
                                    <span className="text-slate-500 italic">Override Company Settings</span>
                                  )}
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-1 flex-shrink-0">
                              {canEdit && (
                                <>
                                  <button type="button" onClick={() => openDuplicateModal(cfg)} className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="Duplikat" data-testid={`duplicate-preset-${cfg.id}`}>
                                    <Copy className="w-3.5 h-3.5" />
                                  </button>
                                  <button type="button" onClick={() => openEditModal(cfg)} className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors" title="Edit" data-testid={`edit-preset-${cfg.id}`}>
                                    <Edit2 className="w-3.5 h-3.5" />
                                  </button>
                                  <button type="button" onClick={() => handleDelete(cfg.id)} className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Hapus" data-testid={`delete-preset-${cfg.id}`}>
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                </>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}

      {/* Test Result Toast */}
      {testResult && (
        <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border max-w-sm ${
          testResult.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-red-50 border-red-200 text-red-800'
        }`} data-testid="test-result-toast">
          {testResult.ok ? <Check className="w-5 h-5 text-emerald-500 flex-shrink-0" /> : <X className="w-5 h-5 text-red-500 flex-shrink-0" />}
          <div className="min-w-0">
            <p className="text-sm font-medium">{testResult.ok ? 'Export Berhasil' : 'Export Gagal'}</p>
            <p className="text-xs opacity-80 truncate">{testResult.msg}</p>
          </div>
          <button type="button" onClick={() => setTestResult(null)} className="p-1 hover:bg-black/5 rounded flex-shrink-0" data-testid="close-test-toast"><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="preset-modal-backdrop">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col" data-testid="preset-modal">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between flex-shrink-0">
              <div>
                <h2 className="text-lg font-bold text-slate-800" data-testid="modal-title">
                  {editConfig ? 'Edit Preset' : 'Buat Preset Baru'}
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">{PDF_TYPE_LABELS[selectedType] || selectedType}</p>
              </div>
              <button type="button" onClick={() => setShowModal(false)} className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors" data-testid="modal-close" aria-label="Close">
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
              {/* Basic info */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-slate-700 mb-1">Nama Preset</label>
                  <input type="text" value={formName} onChange={e => setFormName(e.target.value)}
                    placeholder="contoh: Ringkas, Lengkap, Client A"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-400 focus:border-blue-400 outline-none"
                    data-testid="preset-name-input" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Default?</label>
                  <button type="button" onClick={() => setFormDefault(!formDefault)}
                    className={`flex items-center gap-2 px-3 py-2 w-full rounded-lg border text-sm transition-colors ${
                      formDefault ? 'bg-amber-50 border-amber-300 text-amber-700' : 'bg-white border-slate-300 text-slate-500 hover:border-slate-400'
                    }`}
                    data-testid="preset-default-toggle">
                    <Star className={`w-4 h-4 ${formDefault ? 'fill-current text-amber-500' : ''}`} />
                    {formDefault ? 'Set Default' : 'Not Default'}
                  </button>
                </div>
              </div>

              {/* Column Selector — Drag & Drop */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                    <Layers className="w-4 h-4 text-slate-400" />
                    Kolom & Urutan
                    <span className="text-xs text-slate-400 font-normal">({formColumns.length}/{columns.length} dipilih)</span>
                  </label>
                  <div className="flex gap-2 text-xs">
                    <button type="button" onClick={selectAll} className="text-blue-600 hover:text-blue-800" data-testid="select-all-columns">Pilih Semua</button>
                    <span className="text-slate-300">|</span>
                    <button type="button" onClick={deselectOptional} className="text-slate-500 hover:text-slate-700" data-testid="deselect-optional">Hanya Wajib</button>
                  </div>
                </div>
                <div className="bg-slate-50 rounded-lg border border-slate-200 p-3 space-y-3">
                  {/* Selected columns — sortable */}
                  <div>
                    <p className="text-xs font-medium text-slate-600 mb-2 flex items-center gap-1.5">
                      <GripVertical className="w-3 h-3 text-slate-400" />
                      Kolom dipilih (drag untuk ubah urutan)
                    </p>
                    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                      <SortableContext items={formColumns} strategy={verticalListSortingStrategy}>
                        <div className="space-y-1.5" data-testid="selected-columns-list">
                          {orderedSelected.length === 0 && (
                            <p className="text-xs text-slate-400 italic py-2">Belum ada kolom dipilih.</p>
                          )}
                          {orderedSelected.map(col => (
                            <SortableColumn
                              key={col.key}
                              col={col}
                              selected={true}
                              required={!!col.required}
                              onToggle={toggleColumn}
                            />
                          ))}
                        </div>
                      </SortableContext>
                    </DndContext>
                  </div>
                  {/* Unselected columns */}
                  {unselectedCols.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-slate-500 mb-2">Kolom tersedia (klik untuk tambah)</p>
                      <div className="grid grid-cols-2 gap-1.5" data-testid="unselected-columns-grid">
                        {unselectedCols.map(col => (
                          <button key={col.key} type="button" onClick={() => toggleColumn(col.key)}
                            className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-dashed border-slate-300 text-sm text-slate-500 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 transition-colors text-left"
                            data-testid={`add-column-${col.key}`}>
                            <Plus className="w-3.5 h-3.5 flex-shrink-0" />
                            <span className="truncate">{col.label}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <p className="text-xs text-slate-400 flex items-center gap-1 pt-1">
                    <span className="text-amber-500">*</span> Kolom wajib tidak bisa dihapus
                  </p>
                </div>
              </div>

              {/* Advanced: Header/Footer + Orientation */}
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <button type="button" onClick={() => setShowAdvanced(!showAdvanced)}
                  className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors"
                  data-testid="toggle-advanced">
                  <span className="text-sm font-medium text-slate-700 flex items-center gap-2">
                    {showAdvanced ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    Opsi Lanjutan: Header, Footer & Orientasi
                  </span>
                  {showAdvanced && (
                    <span className="text-xs text-slate-500">Opsional</span>
                  )}
                </button>
                {showAdvanced && (
                  <div className="p-4 space-y-4 bg-white">
                    {/* Orientation */}
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-2 flex items-center gap-2">
                        <RotateCw className="w-4 h-4 text-slate-400" />
                        Orientasi Halaman
                      </label>
                      <div className="grid grid-cols-3 gap-2" data-testid="orientation-selector">
                        {[
                          { v: 'auto', label: 'Auto', desc: 'Ikuti default sistem' },
                          { v: 'portrait', label: 'Portrait', desc: 'Vertikal' },
                          { v: 'landscape', label: 'Landscape', desc: 'Horizontal' },
                        ].map(o => (
                          <button type="button" key={o.v} onClick={() => setFormOrientation(o.v)}
                            className={`px-3 py-2.5 rounded-lg border text-left transition-colors ${
                              formOrientation === o.v
                                ? 'bg-blue-50 border-blue-400 text-blue-800'
                                : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'
                            }`}
                            data-testid={`orientation-${o.v}`}>
                            <div className="text-sm font-medium">{o.label}</div>
                            <div className="text-xs opacity-70 mt-0.5">{o.desc}</div>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Use Company Settings toggle */}
                    <div className="flex items-start gap-3 bg-slate-50 rounded-lg p-3">
                      <button type="button" onClick={() => setFormUseCS(!formUseCS)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 mt-0.5 ${formUseCS ? 'bg-emerald-600' : 'bg-slate-300'}`}
                        data-testid="use-company-settings-toggle">
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow ${formUseCS ? 'translate-x-6' : 'translate-x-1'}`} />
                      </button>
                      <div className="flex-1">
                        <div className="text-sm font-medium text-slate-700">Pakai Header/Footer dari Pengaturan Perusahaan</div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          {formUseCS
                            ? 'Default: header/footer dari Pengaturan Perusahaan akan dipakai. Field di bawah (jika diisi) akan menimpa nilai tersebut.'
                            : 'Mode override penuh: HANYA field di bawah yang dipakai. Pengaturan Perusahaan diabaikan.'}
                        </div>
                      </div>
                    </div>

                    {/* Custom Title */}
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1 flex items-center gap-2">
                        <Type className="w-4 h-4 text-slate-400" />
                        Override Judul Dokumen
                      </label>
                      <input type="text" value={formCustomTitle} onChange={e => setFormCustomTitle(e.target.value)}
                        placeholder="kosong = pakai judul default (mis: Surat Perintah Produksi)"
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-400 focus:border-blue-400 outline-none"
                        data-testid="custom-title-input" />
                    </div>

                    {/* Custom Header Lines */}
                    <div className="grid grid-cols-1 gap-3">
                      <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1 flex items-center gap-2">
                          <FileText className="w-4 h-4 text-slate-400" />
                          Override Header Line 1
                        </label>
                        <input type="text" value={formCustomHeader1} onChange={e => setFormCustomHeader1(e.target.value)}
                          placeholder="mis: Tagline atau alamat cabang khusus"
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-400 focus:border-blue-400 outline-none"
                          data-testid="custom-header1-input" />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">Override Header Line 2</label>
                        <input type="text" value={formCustomHeader2} onChange={e => setFormCustomHeader2(e.target.value)}
                          placeholder="mis: Sertifikasi atau catatan tambahan"
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-400 focus:border-blue-400 outline-none"
                          data-testid="custom-header2-input" />
                      </div>
                    </div>

                    {/* Custom Footer */}
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Override Footer</label>
                      <textarea value={formCustomFooter} onChange={e => setFormCustomFooter(e.target.value)} rows="2"
                        placeholder="mis: Catatan kaki atau disclaimer khusus"
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-400 focus:border-blue-400 outline-none"
                        data-testid="custom-footer-input" />
                    </div>

                    <p className="text-xs text-slate-400 flex items-start gap-1">
                      <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                      <span>Field yang dikosongkan akan otomatis pakai dari Pengaturan Perusahaan (bila toggle aktif). Logo, alamat, dan kontak perusahaan selalu dari Pengaturan Perusahaan.</span>
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="px-6 py-4 border-t border-slate-200 flex items-center justify-end gap-3 bg-slate-50 flex-shrink-0">
              <button type="button" onClick={() => setShowModal(false)}
                className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 rounded-lg transition-colors"
                data-testid="modal-cancel">Batal</button>
              <button type="button" onClick={handleSave} disabled={saving || !canEdit}
                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                data-testid="modal-save">
                <Save className="w-4 h-4" />
                {saving ? 'Menyimpan...' : editConfig ? 'Simpan Perubahan' : 'Simpan Preset'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
