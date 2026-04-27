import { useState, useCallback, useRef } from 'react';
import { toast } from 'sonner';
import {
  Upload, FileSpreadsheet, Image, FileText, ChevronRight, ChevronLeft,
  CheckCircle2, AlertCircle, Info, Zap, Brain, Save, Trash2, RefreshCw,
  Eye, Edit3, X, Plus, ArrowRight, Sparkles, Package, Users, Gem,
  Shirt, ClipboardList, BookOpen, Check, Loader2, ToggleLeft, ToggleRight,
  WifiOff
} from 'lucide-react';
import { apiGet, apiPost, apiDelete } from '../../lib/api';

const DATA_TYPES = [
  { id: 'production_po', label: 'Production PO', icon: ClipboardList, color: 'blue', desc: 'Import PO dengan item produk' },
  { id: 'products', label: 'Data Produk', icon: Package, color: 'emerald', desc: 'Katalog produk & harga' },
  { id: 'accessories', label: 'Data Aksesoris', icon: Gem, color: 'purple', desc: 'Katalog aksesoris' },
  { id: 'vendors', label: 'Data Vendor', icon: Shirt, color: 'orange', desc: 'Vendor/garmen & kontak' },
  { id: 'buyers', label: 'Data Buyer', icon: Users, color: 'rose', desc: 'Buyer/pelanggan & kontak' },
];

const COLOR_MAP = {
  blue: 'bg-blue-50 border-blue-200 text-blue-700',
  emerald: 'bg-emerald-50 border-emerald-200 text-emerald-700',
  purple: 'bg-purple-50 border-purple-200 text-purple-700',
  orange: 'bg-orange-50 border-orange-200 text-orange-700',
  rose: 'bg-rose-50 border-rose-200 text-rose-700',
};

const STEPS = [
  { id: 1, label: 'Upload', icon: Upload },
  { id: 2, label: 'Mapping', icon: Brain },
  { id: 3, label: 'Preview', icon: Eye },
  { id: 4, label: 'Konfirmasi', icon: CheckCircle2 },
  { id: 5, label: 'Selesai', icon: Sparkles },
];

function StepIndicator({ currentStep }) {
  return (
    <div className="flex items-center gap-0 mb-8" data-testid="step-indicator">
      {STEPS.map((step, idx) => {
        const Icon = step.icon;
        const isActive = currentStep === step.id;
        const isDone = currentStep > step.id;
        return (
          <div key={step.id} className="flex items-center">
            <div className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all ${
              isDone ? 'bg-emerald-100 text-emerald-700' :
              isActive ? 'bg-blue-600 text-white shadow-md' :
              'bg-slate-100 text-slate-400'
            }`}>
              {isDone ? <Check className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
              <span className="hidden sm:inline">{step.label}</span>
            </div>
            {idx < STEPS.length - 1 && (
              <div className={`w-8 h-0.5 mx-1 transition-colors ${isDone ? 'bg-emerald-300' : 'bg-slate-200'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function FileDropZone({ onFileSelected, disabled }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) onFileSelected(file);
  }, [onFileSelected]);

  const ACCEPTED = '.xlsx,.xls,.csv,.jpg,.jpeg,.png,.webp,.pdf';

  return (
    <div
      className={`border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all ${
        dragging ? 'border-blue-400 bg-blue-50' : 'border-slate-300 bg-slate-50 hover:border-blue-300 hover:bg-blue-50/50'
      } ${disabled ? 'opacity-50 pointer-events-none' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      data-testid="file-dropzone"
    >
      <input ref={inputRef} type="file" className="hidden" accept={ACCEPTED} onChange={e => e.target.files?.[0] && onFileSelected(e.target.files[0])} />
      <div className="flex flex-col items-center gap-3">
        <div className="w-16 h-16 rounded-2xl bg-blue-100 flex items-center justify-center">
          <Upload className="w-8 h-8 text-blue-600" />
        </div>
        <div>
          <p className="text-base font-semibold text-slate-700">Drag & drop atau klik untuk upload</p>
          <p className="text-sm text-slate-500 mt-1">Excel (.xlsx/.xls), CSV, Gambar (JPG/PNG/WebP), PDF</p>
        </div>
        <div className="flex gap-2 mt-2">
          {[{ icon: FileSpreadsheet, label: 'Excel/CSV', color: 'text-emerald-600 bg-emerald-50' },
            { icon: Image, label: 'Foto/Scan', color: 'text-blue-600 bg-blue-50' },
            { icon: FileText, label: 'PDF', color: 'text-rose-600 bg-rose-50' }].map(t => (
            <span key={t.label} className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${t.color}`}>
              <t.icon className="w-3.5 h-3.5" />
              {t.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  if (status === 'new') return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-700">✨ Baru</span>;
  if (status === 'exists') return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">🔄 Sudah Ada</span>;
  if (status === 'error') return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">⚠️ Error</span>;
  return null;
}

function ConfidenceBadge({ confidence, method }) {
  if (method === 'exact' || method === 'preset') return <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 font-medium">✓ Tepat</span>;
  if (method === 'llm') return <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 font-medium">🤖 AI</span>;
  if (confidence >= 85) return <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 font-medium">{confidence}%</span>;
  if (confidence >= 70) return <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-medium">{confidence}%</span>;
  return <span className="text-xs px-1.5 py-0.5 rounded bg-red-100 text-red-700 font-medium">{confidence || 0}%</span>;
}

export default function SmartImportModule() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');

  // Step 1 state
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedDataType, setSelectedDataType] = useState('production_po');
  const [sessionInfo, setSessionInfo] = useState(null);
  const [useAI, setUseAI] = useState(true);

  // Step 2 state
  const [analysisResult, setAnalysisResult] = useState(null);
  const [columnMapping, setColumnMapping] = useState({});
  const [enhancingLLM, setEnhancingLLM] = useState(false);
  const [isOCR, setIsOCR] = useState(false);
  const [ocrRows, setOcrRows] = useState(null);
  const [savePresetName, setSavePresetName] = useState('');
  const [showSavePreset, setShowSavePreset] = useState(false);

  // Step 3 state
  const [previewData, setPreviewData] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [editingRow, setEditingRow] = useState(null);
  const [editedRows, setEditedRows] = useState({});
  const [skippedRows, setSkippedRows] = useState(new Set());
  const [previewLoading, setPreviewLoading] = useState(false);

  // Step 5 state
  const [importResult, setImportResult] = useState(null);

  // Presets
  const [presets, setPresets] = useState([]);
  const [showPresets, setShowPresets] = useState(false);

  // ── Step 1: Upload ───────────────────────────────────────────────────────
  const handleUpload = async () => {
    if (!selectedFile) return toast.error('Pilih file terlebih dahulu');
    setLoading(true);
    setLoadingMsg('Mengupload file...');
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('data_type', selectedDataType);
      const data = await apiPost('/smart-import/upload', formData);
      setSessionInfo(data);
      toast.success(`File '${data.filename}' berhasil diupload`);
      await analyzeFile(data.session_id, data.file_type);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const analyzeFile = async (sessionId, fileType) => {
    setLoadingMsg('Menganalisis struktur file...');
    setLoading(true);
    try {
      if (fileType === 'image' || fileType === 'pdf') {
        setIsOCR(true);
        setStep(2);
        return;
      }
      // Excel/CSV
      const data = await apiPost('/smart-import/analyze', { session_id: sessionId, data_type: selectedDataType, use_llm: useAI });
      setAnalysisResult(data);
      // Initialize mapping from suggestions
      const initMapping = {};
      (data.headers || []).forEach(h => {
        initMapping[h] = data.mapping_suggestions?.[h]?.field || '';
      });
      setColumnMapping(initMapping);
      setIsOCR(false);
      setStep(2);
      // If preset matched, show info
      if (data.preset_match) {
        toast.success(`Preset "${data.preset_match.preset_name}" diterapkan otomatis!`);
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  // ── Step 2: LLM Enhance ──────────────────────────────────────────────────
  const handleEnhanceWithLLM = async () => {
    if (!sessionInfo) return;
    setEnhancingLLM(true);
    try {
      const data = await apiPost('/smart-import/enhance-mapping', {
        session_id: sessionInfo.session_id,
        headers: analysisResult?.headers || [],
        data_type: selectedDataType,
        sample_rows: analysisResult?.sample_rows || []
      });
      
      const enhanced = data.enhanced_mapping || {};
      setColumnMapping(prev => {
        const updated = { ...prev };
        Object.entries(enhanced).forEach(([h, m]) => {
          if (m.field && (!prev[h] || prev[h] === '')) {
            updated[h] = m.field;
          }
        });
        return updated;
      });
      // Update suggestions
      setAnalysisResult(prev => ({
        ...prev,
        mapping_suggestions: {
          ...prev.mapping_suggestions,
          ...Object.fromEntries(Object.entries(enhanced).map(([h, m]) => [h, m]))
        }
      }));
      toast.success('AI berhasil memperbaiki mapping kolom!');
    } catch (e) {
      toast.error(e.message);
    } finally {
      setEnhancingLLM(false);
    }
  };

  const handleRunOCR = async () => {
    if (!sessionInfo) return;
    setLoading(true);
    setLoadingMsg(useAI ? 'Mengekstrak data dengan AI Vision...' : 'Membaca tabel dari PDF...');
    try {
      const data = await apiPost('/smart-import/ocr', { session_id: sessionInfo.session_id, data_type: selectedDataType, use_llm: useAI });
      setOcrRows(data.rows || []);
      if (data.warnings?.length) data.warnings.forEach(w => toast.warning(w));
      toast.success(`Berhasil mengekstrak ${data.total} baris data`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSavePreset = async () => {
    if (!savePresetName.trim()) return toast.error('Nama preset wajib diisi');
    try {
      await apiPost('/smart-import/presets', {
        name: savePresetName,
        data_type: selectedDataType,
        mapping: columnMapping
      });
      toast.success(`Preset "${savePresetName}" tersimpan!`);
      setSavePresetName('');
      setShowSavePreset(false);
    } catch (e) {
      toast.error(e.message);
    }
  };

  // ── Step 3: Preview ──────────────────────────────────────────────────────
  const loadPreview = async (page = 1) => {
    setPreviewLoading(true);
    try {
      const body = { data_type: selectedDataType, page, per_page: 20 };
      if (ocrRows !== null) {
        body.rows = ocrRows;
      } else {
        body.session_id = sessionInfo?.session_id;
        body.mapping = columnMapping;
      }
      const data = await apiPost('/smart-import/preview', body);
      setPreviewData(data);
      setCurrentPage(page);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const goToPreview = async () => {
    // Validate mapping has at least one required field
    const requiredFields = Object.entries(analysisResult?.available_fields || {})
      .filter(([_, f]) => f.required).map(([k]) => k);
    if (!isOCR) {
      const mappedFields = Object.values(columnMapping).filter(Boolean);
      const missing = requiredFields.filter(f => !mappedFields.includes(f));
      if (missing.length > 0) {
        const labels = missing.map(f => analysisResult?.available_fields?.[f]?.label || f);
        toast.error(`Field wajib belum di-mapping: ${labels.join(', ')}`);
        return;
      }
    } else if (!ocrRows) {
      toast.error('Jalankan OCR terlebih dahulu');
      return;
    }
    setStep(3);
    await loadPreview(1);
  };

  const handleEditRow = (row) => {
    const editData = { ...row };
    delete editData._status;
    delete editData._errors;
    delete editData._auto_creates;
    delete editData._row_index;
    setEditingRow({ index: row._row_index, data: editData });
  };

  const handleSaveEdit = () => {
    const { index, data } = editingRow;
    setEditedRows(prev => ({ ...prev, [index]: data }));
    setEditingRow(null);
    // Re-load preview to show updated data
    loadPreview(currentPage);
  };

  const handleSkipRow = (rowIndex) => {
    setSkippedRows(prev => {
      const next = new Set(prev);
      if (next.has(rowIndex)) next.delete(rowIndex);
      else next.add(rowIndex);
      return next;
    });
  };

  // ── Step 4: Commit ──────────────────────────────────────────────────────
  const handleCommit = async () => {
    setLoading(true);
    setLoadingMsg('Mengimpor data...');
    try {
      const body = {
        data_type: selectedDataType,
        confirmed: true,
        edited_rows: editedRows,
      };
      if (ocrRows !== null) {
        body.rows = ocrRows.map((r, i) => skippedRows.has(i) ? { ...r, _skip: true } : r);
      } else {
        body.session_id = sessionInfo?.session_id;
        body.mapping = columnMapping;
      }
      const data = await apiPost('/smart-import/commit', body);
      setImportResult(data);
      setStep(5);
      toast.success(data.message);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const resetAll = () => {
    setStep(1);
    setSelectedFile(null);
    setSessionInfo(null);
    setAnalysisResult(null);
    setColumnMapping({});
    setIsOCR(false);
    setOcrRows(null);
    setPreviewData(null);
    setEditedRows({});
    setSkippedRows(new Set());
    setImportResult(null);
    setEditingRow(null);
    // keep useAI as user's preference
  };

  // ─── Render Steps ─────────────────────────────────────────────────────────
  const renderStep1 = () => (
    <div className="space-y-6">
      {/* AI Mode Toggle */}
      <div className={`flex items-center justify-between p-4 rounded-xl border-2 transition-all ${useAI ? 'border-purple-200 bg-purple-50' : 'border-slate-200 bg-slate-50'}`}>
        <div className="flex items-center gap-3">
          {useAI
            ? <Brain className="w-5 h-5 text-purple-600" />
            : <WifiOff className="w-5 h-5 text-slate-500" />}
          <div>
            <p className={`text-sm font-semibold ${useAI ? 'text-purple-800' : 'text-slate-700'}`}>
              {useAI ? 'Mode AI Aktif' : 'Mode Tanpa AI'}
            </p>
            <p className={`text-xs ${useAI ? 'text-purple-600' : 'text-slate-500'}`}>
              {useAI
                ? 'Fuzzy matching + LLM fallback + OCR untuk gambar/PDF'
                : 'Hanya fuzzy matching — Excel/CSV + PDF bertabel (tanpa biaya LLM)'}
            </p>
          </div>
        </div>
        <button
          onClick={() => setUseAI(v => !v)}
          data-testid="toggle-ai-mode"
          className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition-all ${
            useAI
              ? 'bg-purple-600 text-white hover:bg-purple-700'
              : 'bg-slate-200 text-slate-600 hover:bg-slate-300'
          }`}
        >
          {useAI ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
          {useAI ? 'ON' : 'OFF'}
        </button>
      </div>

      <div>
        <h3 className="text-base font-semibold text-slate-700 mb-3">1. Pilih Tipe Data</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {DATA_TYPES.map(dt => {
            const Icon = dt.icon;
            const isSelected = selectedDataType === dt.id;
            return (
              <button
                key={dt.id}
                onClick={() => setSelectedDataType(dt.id)}
                data-testid={`data-type-${dt.id}`}
                className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 text-center transition-all ${
                  isSelected ? `border-blue-500 bg-blue-50 shadow-sm` : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <Icon className={`w-7 h-7 ${isSelected ? 'text-blue-600' : 'text-slate-500'}`} />
                <span className={`text-xs font-semibold leading-tight ${isSelected ? 'text-blue-700' : 'text-slate-600'}`}>{dt.label}</span>
                <span className="text-xs text-slate-400 hidden md:block">{dt.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <h3 className="text-base font-semibold text-slate-700 mb-3">2. Upload File</h3>
        <FileDropZone onFileSelected={setSelectedFile} disabled={loading} />
      </div>

      {selectedFile && (
        <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-200">
          <FileSpreadsheet className="w-5 h-5 text-slate-500 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-700 truncate">{selectedFile.name}</p>
            <p className="text-xs text-slate-400">{(selectedFile.size / 1024).toFixed(1)} KB</p>
          </div>
          <button onClick={() => setSelectedFile(null)} className="p-1 hover:bg-slate-200 rounded">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>
      )}

      <button
        onClick={handleUpload}
        disabled={!selectedFile || loading}
        data-testid="btn-upload"
        className="w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" />{loadingMsg}</> : <><Zap className="w-4 h-4" />Analisis & Lanjutkan</>}
      </button>
    </div>
  );

  const renderStep2 = () => {
    if (isOCR) {
      const isImage = sessionInfo?.file_type === 'image';
      const noAIBlockedImage = !useAI && isImage;

      return (
        <div className="space-y-6">
          <div className={`p-4 rounded-xl border ${useAI ? 'bg-blue-50 border-blue-200' : 'bg-amber-50 border-amber-200'}`}>
            <div className="flex items-start gap-3">
              {useAI
                ? <Brain className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                : <WifiOff className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />}
              <div>
                <p className={`text-sm font-semibold ${useAI ? 'text-blue-800' : 'text-amber-800'}`}>
                  {useAI ? 'Mode OCR — AI Vision' : 'Mode Tanpa AI'}
                </p>
                <p className={`text-xs mt-0.5 ${useAI ? 'text-blue-600' : 'text-amber-700'}`}>
                  {useAI
                    ? 'File gambar/PDF akan diekstrak menggunakan AI Vision (GPT-4o). Proses ini memakan waktu 5-30 detik.'
                    : isImage
                      ? 'File gambar memerlukan Mode AI untuk OCR. Aktifkan "Mode AI" atau upload file Excel/CSV/PDF bertabel.'
                      : 'PDF akan dibaca menggunakan ekstraksi tabel — hanya bekerja untuk PDF dengan tabel terstruktur.'}
                </p>
              </div>
            </div>
          </div>

          {noAIBlockedImage ? (
            <div className="space-y-4">
              <div className="p-5 bg-slate-50 rounded-xl border border-slate-200 text-center">
                <Image className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                <p className="text-sm font-medium text-slate-600">File gambar tidak dapat diproses tanpa Mode AI</p>
                <p className="text-xs text-slate-400 mt-1">Aktifkan Mode AI atau gunakan file Excel/CSV</p>
              </div>
              <div className="flex gap-3">
                <button onClick={() => setStep(1)} className="flex-1 py-2.5 rounded-xl border border-slate-300 text-slate-600 font-medium flex items-center justify-center gap-2 hover:bg-slate-50">
                  <ChevronLeft className="w-4 h-4" />Kembali & Ubah Mode
                </button>
              </div>
            </div>
          ) : (
            <>
              {!ocrRows ? (
                <button
                  onClick={handleRunOCR}
                  disabled={loading}
                  data-testid="btn-run-ocr"
                  className={`w-full py-3 rounded-xl text-white font-semibold flex items-center justify-center gap-2 disabled:opacity-50 transition-colors ${useAI ? 'bg-purple-600 hover:bg-purple-700' : 'bg-blue-600 hover:bg-blue-700'}`}
                >
                  {loading
                    ? <><Loader2 className="w-4 h-4 animate-spin" />{loadingMsg}</>
                    : useAI
                      ? <><Sparkles className="w-4 h-4" />Ekstrak Data dengan AI</>
                      : <><FileText className="w-4 h-4" />Baca Tabel dari PDF</>}
                </button>
              ) : (
                <div className="space-y-4">
                  <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-200 flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                    <div>
                      <p className="text-sm font-semibold text-emerald-800">Berhasil mengekstrak {ocrRows.length} baris data</p>
                      <p className="text-xs text-emerald-600">Periksa hasil di langkah preview berikutnya</p>
                    </div>
                  </div>
                  <div className="overflow-x-auto rounded-xl border border-slate-200 max-h-64">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50">
                        <tr>
                          {Object.keys(ocrRows[0] || {}).slice(0, 8).map(k => (
                            <th key={k} className="px-3 py-2 text-left font-medium text-slate-500">{k}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {ocrRows.slice(0, 5).map((row, i) => (
                          <tr key={i} className="border-t border-slate-100">
                            {Object.values(row).slice(0, 8).map((v, j) => (
                              <td key={j} className="px-3 py-1.5 text-slate-700 truncate max-w-24">{String(v ?? '')}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button onClick={() => setStep(1)} className="flex-1 py-2.5 rounded-xl border border-slate-300 text-slate-600 font-medium flex items-center justify-center gap-2 hover:bg-slate-50">
                  <ChevronLeft className="w-4 h-4" />Kembali
                </button>
                <button
                  onClick={goToPreview}
                  disabled={!ocrRows || loading}
                  data-testid="btn-to-preview"
                  className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold flex items-center justify-center gap-2 disabled:opacity-50 transition-colors"
                >
                  Preview Data<ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </>
          )}
        </div>
      );
    }

    // Excel/CSV Mapping
    if (!analysisResult) return <div className="flex items-center justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>;

    const fields = analysisResult.available_fields || {};
    const fieldOptions = Object.entries(fields).map(([k, v]) => ({ value: k, label: `${v.label}${v.required ? ' *' : ''}` }));

    return (
      <div className="space-y-5">
        {/* Info bar */}
        <div className="flex flex-wrap gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 rounded-lg text-sm">
            <FileSpreadsheet className="w-4 h-4 text-slate-500" />
            <span className="text-slate-600 font-medium">{analysisResult.total_rows} baris data</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 rounded-lg text-sm">
            <Info className="w-4 h-4 text-slate-500" />
            <span className="text-slate-600">{analysisResult.headers?.length || 0} kolom terdeteksi</span>
          </div>
          {analysisResult.preset_match && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 rounded-lg text-sm border border-emerald-200">
              <Check className="w-4 h-4 text-emerald-600" />
              <span className="text-emerald-700 font-medium">Preset: {analysisResult.preset_match.preset_name}</span>
            </div>
          )}
        </div>

        {/* LLM Enhance button - only in AI mode */}
        {useAI && analysisResult.needs_llm_enhance && (
          <div className="flex items-center justify-between p-3 bg-purple-50 rounded-xl border border-purple-200">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple-600" />
              <span className="text-sm text-purple-700">{analysisResult.low_confidence_headers?.length} kolom perlu bantuan AI</span>
            </div>
            <button
              onClick={handleEnhanceWithLLM}
              disabled={enhancingLLM}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
              data-testid="btn-llm-enhance"
            >
              {enhancingLLM ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
              {enhancingLLM ? 'Memproses...' : 'Gunakan AI'}
            </button>
          </div>
        )}

        {/* Column Mapping Table */}
        <div className="rounded-xl border border-slate-200 overflow-hidden">
          <div className="bg-slate-50 px-4 py-2.5 border-b border-slate-200">
            <p className="text-sm font-semibold text-slate-700">Pemetaan Kolom</p>
            <p className="text-xs text-slate-500">Tentukan kolom file mana yang cocok dengan field sistem</p>
          </div>
          <div className="divide-y divide-slate-100 max-h-80 overflow-y-auto">
            {(analysisResult.headers || []).map(header => {
              const suggestion = analysisResult.mapping_suggestions?.[header] || {};
              const currentField = columnMapping[header] || '';
              const confidence = suggestion.confidence || 0;
              const method = suggestion.method || 'none';

              return (
                <div key={header} className="flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50">
                  {/* File column */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-700 truncate">{header}</p>
                    {analysisResult.sample_rows?.[0] && (
                      <p className="text-xs text-slate-400 truncate">
                        e.g. {analysisResult.sample_rows[0][analysisResult.headers.indexOf(header)]}
                      </p>
                    )}
                  </div>
                  {/* Arrow */}
                  <ArrowRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
                  {/* Field selector */}
                  <select
                    value={currentField}
                    onChange={e => setColumnMapping(prev => ({ ...prev, [header]: e.target.value }))}
                    className="flex-1 text-sm border border-slate-200 rounded-lg px-2 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-300"
                    data-testid={`mapping-select-${header}`}
                  >
                    <option value="">— Abaikan kolom ini —</option>
                    {fieldOptions.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                  {/* Confidence */}
                  {currentField && (
                    <ConfidenceBadge confidence={confidence} method={method} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Save as preset */}
        <div>
          <button
            onClick={() => setShowSavePreset(!showSavePreset)}
            className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
            data-testid="btn-toggle-save-preset"
          >
            <Save className="w-4 h-4" />
            Simpan mapping ini sebagai preset
          </button>
          {showSavePreset && (
            <div className="flex gap-2 mt-2">
              <input
                type="text"
                placeholder="Nama preset (e.g. Format Buyer PT ABC)"
                value={savePresetName}
                onChange={e => setSavePresetName(e.target.value)}
                className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-300"
                data-testid="input-preset-name"
              />
              <button
                onClick={handleSavePreset}
                className="px-3 py-1.5 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 font-medium"
                data-testid="btn-save-preset"
              >
                Simpan
              </button>
            </div>
          )}
        </div>

        <div className="flex gap-3">
          <button onClick={() => setStep(1)} className="flex-1 py-2.5 rounded-xl border border-slate-300 text-slate-600 font-medium flex items-center justify-center gap-2 hover:bg-slate-50">
            <ChevronLeft className="w-4 h-4" />Kembali
          </button>
          <button
            onClick={goToPreview}
            data-testid="btn-to-preview"
            className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold flex items-center justify-center gap-2 transition-colors"
          >
            Preview Data<ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  };

  const renderStep3 = () => {
    const summary = previewData?.summary || {};
    const rows = previewData?.rows || [];
    const allRowFields = rows.length > 0
      ? Object.keys(rows[0]).filter(k => !k.startsWith('_'))
      : [];

    return (
      <div className="space-y-4">
        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Total Baris', value: summary.total || 0, color: 'slate' },
            { label: 'Data Baru', value: summary.new_records || 0, color: 'blue' },
            { label: 'Sudah Ada', value: summary.exists_records || 0, color: 'amber' },
            { label: 'Error', value: summary.errors || 0, color: 'red' },
          ].map(card => (
            <div key={card.label} className={`p-3 rounded-xl border bg-${card.color === 'slate' ? 'slate-50 border-slate-200' : card.color + '-50 border-' + card.color + '-200'}`}>
              <p className={`text-2xl font-bold text-${card.color}-700`}>{card.value}</p>
              <p className={`text-xs text-${card.color}-500 mt-0.5`}>{card.label}</p>
            </div>
          ))}
        </div>

        {/* Auto-create summary */}
        {Object.keys(summary.auto_creates || {}).length > 0 && (
          <div className="p-3 bg-blue-50 rounded-xl border border-blue-200">
            <p className="text-sm font-semibold text-blue-800 flex items-center gap-2"><Plus className="w-4 h-4" />Auto-create yang akan dilakukan:</p>
            <div className="flex flex-wrap gap-2 mt-2">
              {Object.entries(summary.auto_creates).map(([entity, count]) => (
                <span key={entity} className="px-2.5 py-1 bg-white border border-blue-200 rounded-full text-xs font-medium text-blue-700">
                  {count} {entity} baru
                </span>
              ))}
            </div>
          </div>
        )}

        {previewLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-blue-500 mr-2" />
            <span className="text-slate-500">Memuat preview...</span>
          </div>
        ) : (
          <>
            {/* Data table */}
            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full text-xs" data-testid="preview-table">
                <thead className="bg-slate-50 border-b border-slate-200 sticky top-0">
                  <tr>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-500 w-8">#</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-500 w-24">Status</th>
                    {allRowFields.slice(0, 8).map(f => (
                      <th key={f} className="px-3 py-2.5 text-left font-semibold text-slate-500 min-w-24 capitalize">{f.replace(/_/g, ' ')}</th>
                    ))}
                    <th className="px-3 py-2.5 text-left font-semibold text-slate-500 w-24">Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((row, idx) => {
                    const rowIndex = row._row_index ?? idx;
                    const isSkipped = skippedRows.has(rowIndex);
                    const editOverride = editedRows[rowIndex];
                    const displayRow = editOverride ? { ...row, ...editOverride } : row;

                    return (
                      <tr
                        key={rowIndex}
                        className={`transition-colors ${isSkipped ? 'opacity-40' : 'hover:bg-slate-50'} ${row._status === 'error' ? 'bg-red-50/30' : ''}`}
                        data-testid={`preview-row-${rowIndex}`}
                      >
                        <td className="px-3 py-2 text-slate-400">{rowIndex + 1}</td>
                        <td className="px-3 py-2">
                          <StatusBadge status={row._status} />
                          {row._errors?.length > 0 && (
                            <div className="mt-1">
                              {row._errors.map((e, i) => (
                                <p key={i} className="text-xs text-red-500">{e}</p>
                              ))}
                            </div>
                          )}
                        </td>
                        {allRowFields.slice(0, 8).map(f => (
                          <td key={f} className="px-3 py-2 text-slate-700 max-w-32 truncate">
                            {editOverride?.[f] !== undefined
                              ? <span className="text-blue-700 font-medium">{String(editOverride[f] ?? '')}</span>
                              : String(displayRow[f] ?? '')}
                          </td>
                        ))}
                        <td className="px-3 py-2">
                          <div className="flex gap-1">
                            <button
                              onClick={() => handleEditRow(row)}
                              className="p-1 rounded hover:bg-blue-100 text-blue-600 transition-colors"
                              title="Edit baris"
                              data-testid={`btn-edit-row-${rowIndex}`}
                            >
                              <Edit3 className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleSkipRow(rowIndex)}
                              className={`p-1 rounded transition-colors ${isSkipped ? 'bg-amber-100 text-amber-600' : 'hover:bg-slate-100 text-slate-400'}`}
                              title={isSkipped ? 'Batalkan skip' : 'Lewati baris ini'}
                              data-testid={`btn-skip-row-${rowIndex}`}
                            >
                              {isSkipped ? <RefreshCw className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {previewData?.total_pages > 1 && (
              <div className="flex items-center justify-center gap-2">
                <button
                  onClick={() => loadPreview(currentPage - 1)}
                  disabled={currentPage <= 1 || previewLoading}
                  className="p-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-sm text-slate-600">Hal {currentPage} dari {previewData.total_pages}</span>
                <button
                  onClick={() => loadPreview(currentPage + 1)}
                  disabled={currentPage >= previewData.total_pages || previewLoading}
                  className="p-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </>
        )}

        <div className="flex gap-3">
          <button onClick={() => setStep(2)} className="flex-1 py-2.5 rounded-xl border border-slate-300 text-slate-600 font-medium flex items-center justify-center gap-2 hover:bg-slate-50">
            <ChevronLeft className="w-4 h-4" />Kembali
          </button>
          <button
            onClick={() => setStep(4)}
            disabled={!previewData || previewData.summary?.errors === previewData.summary?.total}
            data-testid="btn-to-confirm"
            className="flex-1 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold flex items-center justify-center gap-2 disabled:opacity-50 transition-colors"
          >
            Lanjut ke Konfirmasi<ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  };

  const renderStep4 = () => {
    const summary = previewData?.summary || {};
    const dataTypeLabel = DATA_TYPES.find(d => d.id === selectedDataType)?.label || selectedDataType;

    return (
      <div className="space-y-6">
        <div className="p-6 bg-amber-50 rounded-2xl border border-amber-200">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
              <AlertCircle className="w-6 h-6 text-amber-600" />
            </div>
            <div>
              <h3 className="text-base font-bold text-amber-800">Konfirmasi Import Data</h3>
              <p className="text-sm text-amber-700 mt-1">Tindakan ini akan memodifikasi database. Pastikan data sudah benar sebelum melanjutkan.</p>
            </div>
          </div>
        </div>

        <div className="p-5 bg-white rounded-2xl border border-slate-200 space-y-4">
          <h4 className="font-semibold text-slate-700">Ringkasan Import</h4>
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-slate-50 rounded-xl">
              <p className="text-xs text-slate-500">Tipe Data</p>
              <p className="text-sm font-semibold text-slate-700 mt-0.5">{dataTypeLabel}</p>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl">
              <p className="text-xs text-slate-500">Total Baris</p>
              <p className="text-sm font-semibold text-slate-700 mt-0.5">{summary.total || 0} baris</p>
            </div>
            <div className="p-3 bg-blue-50 rounded-xl">
              <p className="text-xs text-blue-600">Akan Dibuat</p>
              <p className="text-sm font-bold text-blue-700 mt-0.5">{summary.new_records || 0} record baru</p>
            </div>
            <div className="p-3 bg-amber-50 rounded-xl">
              <p className="text-xs text-amber-600">Sudah Ada</p>
              <p className="text-sm font-bold text-amber-700 mt-0.5">{summary.exists_records || 0} record exist</p>
            </div>
          </div>

          {Object.keys(summary.auto_creates || {}).length > 0 && (
            <div className="p-3 bg-blue-50 rounded-xl border border-blue-100">
              <p className="text-xs font-semibold text-blue-700 mb-2">Data Baru yang Akan Otomatis Dibuat:</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(summary.auto_creates).map(([e, c]) => (
                  <span key={e} className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-medium">{c} {e} baru</span>
                ))}
              </div>
            </div>
          )}

          {skippedRows.size > 0 && (
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
              <p className="text-xs text-slate-500">{skippedRows.size} baris akan dilewati</p>
            </div>
          )}

          {Object.keys(editedRows).length > 0 && (
            <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-100">
              <p className="text-xs text-emerald-700">{Object.keys(editedRows).length} baris telah diedit dan akan digunakan versi edit</p>
            </div>
          )}
        </div>

        <div className="flex gap-3">
          <button onClick={() => setStep(3)} className="flex-1 py-3 rounded-xl border border-slate-300 text-slate-600 font-medium flex items-center justify-center gap-2 hover:bg-slate-50">
            <ChevronLeft className="w-4 h-4" />Kembali Review
          </button>
          <button
            onClick={handleCommit}
            disabled={loading}
            data-testid="btn-confirm-import"
            className="flex-1 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold flex items-center justify-center gap-2 disabled:opacity-50 transition-colors shadow-md"
          >
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" />{loadingMsg}</> : <><CheckCircle2 className="w-5 h-5" />Ya, Import Sekarang</>}
          </button>
        </div>
      </div>
    );
  };

  const renderStep5 = () => {
    if (!importResult) return null;
    const hasErrors = importResult.errors?.length > 0;

    return (
      <div className="space-y-6 text-center">
        <div className={`w-20 h-20 mx-auto rounded-2xl flex items-center justify-center ${hasErrors ? 'bg-amber-100' : 'bg-emerald-100'}`}>
          {hasErrors ? <AlertCircle className="w-10 h-10 text-amber-600" /> : <CheckCircle2 className="w-10 h-10 text-emerald-600" />}
        </div>
        <div>
          <h3 className={`text-xl font-bold ${hasErrors ? 'text-amber-700' : 'text-emerald-700'}`}>
            {hasErrors ? 'Import Selesai dengan Beberapa Error' : 'Import Berhasil!'}
          </h3>
          <p className="text-slate-500 mt-1">{importResult.message}</p>
        </div>

        <div className="grid grid-cols-2 gap-3 text-left">
          <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-200">
            <p className="text-3xl font-bold text-emerald-700">{importResult.created}</p>
            <p className="text-sm text-emerald-600 mt-1">Record Dibuat</p>
          </div>
          <div className="p-4 bg-amber-50 rounded-xl border border-amber-200">
            <p className="text-3xl font-bold text-amber-700">{importResult.updated}</p>
            <p className="text-sm text-amber-600 mt-1">Sudah Ada</p>
          </div>
        </div>

        {importResult.errors?.length > 0 && (
          <div className="p-4 bg-red-50 rounded-xl border border-red-200 text-left">
            <p className="text-sm font-semibold text-red-700 mb-2">Error ({importResult.errors.length}):</p>
            <ul className="space-y-1">
              {importResult.errors.slice(0, 5).map((e, i) => (
                <li key={i} className="text-xs text-red-600">• {e}</li>
              ))}
              {importResult.errors.length > 5 && (
                <li className="text-xs text-red-400">...dan {importResult.errors.length - 5} error lainnya</li>
              )}
            </ul>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={resetAll}
            className="flex-1 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold flex items-center justify-center gap-2 transition-colors"
            data-testid="btn-import-again"
          >
            <RefreshCw className="w-4 h-4" />Import File Lain
          </button>
        </div>
      </div>
    );
  };

  // ── Edit Row Modal ───────────────────────────────────────────────────────
  const EditRowModal = () => {
    if (!editingRow) return null;
    const { index, data } = editingRow;
    const fieldDefs = analysisResult?.available_fields || {};
    const dataType = selectedDataType;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <h3 className="font-bold text-slate-800">Edit Baris #{index + 1}</h3>
            <button onClick={() => setEditingRow(null)} className="p-1 hover:bg-slate-100 rounded-lg">
              <X className="w-5 h-5 text-slate-500" />
            </button>
          </div>
          <div className="px-6 py-4 space-y-3 max-h-96 overflow-y-auto">
            {Object.keys(data).map(field => {
              const fieldInfo = fieldDefs[field] || { label: field };
              return (
                <div key={field}>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    {fieldInfo.label || field}
                    {fieldInfo.required && <span className="text-red-500 ml-1">*</span>}
                  </label>
                  <input
                    type={fieldInfo.type === 'number' ? 'number' : 'text'}
                    value={data[field] ?? ''}
                    onChange={e => setEditingRow(prev => ({
                      ...prev,
                      data: { ...prev.data, [field]: e.target.value }
                    }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                  />
                </div>
              );
            })}
          </div>
          <div className="flex gap-3 px-6 py-4 border-t border-slate-100">
            <button onClick={() => setEditingRow(null)} className="flex-1 py-2 rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-50 text-sm font-medium">
              Batal
            </button>
            <button
              onClick={handleSaveEdit}
              className="flex-1 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm"
              data-testid="btn-save-edit"
            >
              Simpan Perubahan
            </button>
          </div>
        </div>
      </div>
    );
  };

  // ── Presets Panel ─────────────────────────────────────────────────────────
  const loadPresets = async () => {
    try {
      const data = await apiGet(`/smart-import/presets?data_type=${selectedDataType}`);
      setPresets(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error('Gagal memuat preset');
    }
  };

  const deletePreset = async (id) => {
    if (!window.confirm) return;
    try {
      await apiDelete(`/smart-import/presets/${id}`);
      toast.success('Preset dihapus');
      loadPresets();
    } catch (e) {
      toast.error('Gagal menghapus preset');
    }
  };

  // ─── Main Render ─────────────────────────────────────────────────────────
  return (
    <div className="max-w-4xl mx-auto space-y-6" data-testid="smart-import-module">
      <EditRowModal />

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <Brain className="w-5 h-5 text-white" />
            </div>
            Smart Import
          </h1>
          <p className="text-sm text-slate-500 mt-1">Import data dari Excel, CSV, Foto/Scan, atau PDF dengan bantuan AI</p>
        </div>
        <button
          onClick={() => { setShowPresets(!showPresets); if (!showPresets) loadPresets(); }}
          className="flex items-center gap-2 px-3 py-2 border border-slate-200 rounded-xl text-sm text-slate-600 hover:bg-slate-50 transition-colors"
          data-testid="btn-show-presets"
        >
          <BookOpen className="w-4 h-4" />
          Preset
        </button>
      </div>

      {/* Presets Panel */}
      {showPresets && (
        <div className="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-slate-700 text-sm">Mapping Presets Tersimpan</h3>
            <button onClick={loadPresets} className="p-1 hover:bg-slate-100 rounded"><RefreshCw className="w-3.5 h-3.5 text-slate-500" /></button>
          </div>
          {presets.length === 0 ? (
            <p className="text-xs text-slate-400 text-center py-4">Belum ada preset tersimpan untuk tipe ini</p>
          ) : (
            <div className="space-y-2">
              {presets.map(p => (
                <div key={p.id} className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-700 truncate">{p.name}</p>
                    <p className="text-xs text-slate-400">{p.data_type} · {Object.keys(p.mapping || {}).length} kolom</p>
                  </div>
                  <button onClick={() => deletePreset(p.id)} className="p-1 hover:bg-red-100 rounded text-red-400 hover:text-red-600 transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Step indicator */}
      <StepIndicator currentStep={step} />

      {/* Step content */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}
        {step === 4 && renderStep4()}
        {step === 5 && renderStep5()}
      </div>

      {/* Tips / Guide */}
      {step === 1 && (
        <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200">
          <h4 className="text-sm font-semibold text-slate-600 mb-2 flex items-center gap-2"><Info className="w-4 h-4" />Tips Penggunaan</h4>
          <ul className="text-xs text-slate-500 space-y-1">
            <li>• <strong>Mode AI ON:</strong> Fuzzy matching + LLM fallback untuk kolom ambigu + OCR untuk gambar/PDF — hasil lebih akurat</li>
            <li>• <strong>Mode AI OFF:</strong> Hanya fuzzy matching — Excel/CSV + PDF bertabel bekerja tanpa biaya LLM, gambar tidak bisa diproses</li>
            <li>• <strong>Auto-create:</strong> Produk/vendor/buyer yang belum ada akan otomatis dibuat (tampil di preview)</li>
            <li>• <strong>Preset:</strong> Simpan mapping kolom untuk format file yang sering dipakai (upload kedua = 1-klik)</li>
            <li>• <strong>Edit preview:</strong> Semua baris bisa diedit sebelum import final dikonfirmasi</li>
          </ul>
        </div>
      )}
    </div>
  );
}
