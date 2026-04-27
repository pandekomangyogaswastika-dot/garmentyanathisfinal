import { useState, useEffect, useCallback, useRef } from 'react';
import './App.css';
import { apiGet } from './lib/api';
import Login from './components/erp/Login';
import Sidebar from './components/erp/Sidebar';
import Dashboard from './components/erp/Dashboard';
import GarmentsModule from './components/erp/GarmentsModule';
import ProductsModule from './components/erp/ProductsModule';
import ProductionPOModule from './components/erp/ProductionPOModule';
import VendorShipmentModule from './components/erp/VendorShipmentModule';
import BuyerShipmentModule from './components/erp/BuyerShipmentModule';
import WorkOrderModule from './components/erp/WorkOrderModule';
import ProductionProgressModule from './components/erp/ProductionProgressModule';
import ProductionMonitoringModule from './components/erp/ProductionMonitoringModule';
import OverproductionModule from './components/erp/OverproductionModule';
import InvoiceModule from './components/erp/InvoiceModule';
import PaymentModule from './components/erp/PaymentModule';
import FinancialRecapModule from './components/erp/FinancialRecapModule';
import ReportsModule from './components/erp/ReportsModule';
import UserManagementModule from './components/erp/UserManagementModule';
import ActivityLogModule from './components/erp/ActivityLogModule';
import HelpGuideModule from './components/erp/HelpGuideModule';
import VendorPortalApp from './components/erp/VendorPortalApp';
import AccountsPayableModule from './components/erp/AccountsPayableModule';
import AccountsReceivableModule from './components/erp/AccountsReceivableModule';
import ManualInvoiceModule from './components/erp/ManualInvoiceModule';
import ProductionReturnModule from './components/erp/ProductionReturnModule';
import CompanySettingsModule from './components/erp/CompanySettingsModule';
import SerialTrackingModule from './components/erp/SerialTrackingModule';
import AccessoryModule from './components/erp/AccessoryModule';
import RoleManagementModule from './components/erp/RoleManagementModule';
import BuyerPortalApp from './components/erp/BuyerPortalApp';
import BuyersModule from './components/erp/BuyersModule';
import PDFConfigModule from './components/erp/PDFConfigModule';
import ApprovalModule from './components/erp/ApprovalModule';
import SmartImportModule from './components/erp/SmartImportModule';
import { Search, X } from 'lucide-react';

function App() {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [currentModule, setCurrentModule] = useState('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [paymentPrefill, setPaymentPrefill] = useState(null);
  const [loading, setLoading] = useState(true);

  // Approval badge polling
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState(0);

  // Global search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchRef = useRef(null);
  const searchTimeout = useRef(null);

  useEffect(() => {
    const savedToken = localStorage.getItem('erp_token');
    const savedUser = localStorage.getItem('erp_user');
    if (savedToken && savedUser) {
      try {
        setToken(savedToken);
        setUser(JSON.parse(savedUser));
      } catch (e) {
        localStorage.removeItem('erp_token');
        localStorage.removeItem('erp_user');
      }
    }
    setLoading(false);
  }, []);

  // Polling for pending approval count (only for superadmin/admin)
  useEffect(() => {
    if (!token || !user) return;
    if (!['superadmin', 'admin'].includes(user.role)) return;

    const fetchPendingCount = async () => {
      try {
        const data = await apiGet('/invoice-edit-requests?status=Pending');
        setPendingApprovalsCount(Array.isArray(data) ? data.length : 0);
      } catch (e) {
        console.error('Error fetching pending approvals:', e);
      }
    };

    fetchPendingCount(); // Initial fetch
    const interval = setInterval(fetchPendingCount, 30000); // Poll every 30s

    return () => clearInterval(interval);
  }, [token, user]);


  const handleLogin = useCallback((tokenData, userData) => {
    setToken(tokenData);
    setUser(userData);
    localStorage.setItem('erp_token', tokenData);
    localStorage.setItem('erp_user', JSON.stringify(userData));
    if (userData.role === 'vendor') {
      setCurrentModule('vendor-dashboard');
    } else {
      setCurrentModule('dashboard');
    }
  }, []);

  const handleLogout = useCallback(() => {
    setToken(null);
    setUser(null);
    setCurrentModule('dashboard');
    setPaymentPrefill(null);
    localStorage.removeItem('erp_token');
    localStorage.removeItem('erp_user');
  }, []);

  const handleNavigate = useCallback((module, data = null) => {
    if (module === 'payments' && data) setPaymentPrefill(data);
    setCurrentModule(module);
  }, []);

  // Global search
  const handleSearchInput = useCallback((q) => {
    setSearchQuery(q);
    if (!q.trim()) { setSearchResults([]); setSearchOpen(false); return; }
    setSearchOpen(true);
    clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const data = await apiGet(`/global-search?q=${encodeURIComponent(q)}`);
        setSearchResults(data.results || []);
      } catch (e) {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
  }, [token]);

  const handleSearchSelect = (result) => {
    setCurrentModule(result.module);
    setSearchQuery('');
    setSearchResults([]);
    setSearchOpen(false);
  };

  // Close search on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-50">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!token || !user) {
    return <Login onLogin={handleLogin} />;
  }

  // VENDOR PORTAL
  if (user.role === 'vendor') {
    return <VendorPortalApp user={user} token={token} onLogout={handleLogout} />;
  }

  // BUYER PORTAL
  if (user.role === 'buyer') {
    return <BuyerPortalApp user={user} token={token} onLogout={handleLogout} />;
  }

  // MAIN ERP SYSTEM
  const userPerms = user?.permissions || [];
  const hasPerm = (key) => {
    if (user?.role === 'superadmin') return true;
    return userPerms.includes(key) || userPerms.includes(key.split('.')[0] + '.*');
  };
  const renderModule = () => {
    switch (currentModule) {
      case 'dashboard': return <Dashboard token={token} onNavigate={handleNavigate} />;
      case 'garments': return <GarmentsModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'buyers': return <BuyersModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'products': return <ProductsModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'production-po': return <ProductionPOModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'vendor-shipments': return <VendorShipmentModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'buyer-shipments': return <BuyerShipmentModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'work-orders': return <WorkOrderModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'production-progress': return <ProductionProgressModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'production-monitoring': return <ProductionMonitoringModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'overproduction': return <OverproductionModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'production-returns': return <ProductionReturnModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'accounts-payable': return <AccountsPayableModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'accounts-receivable': return <AccountsReceivableModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'manual-invoice': return <ManualInvoiceModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'invoice-approval': return <ApprovalModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'invoices': return <InvoiceModule token={token} userRole={user?.role} onNavigate={handleNavigate} hasPerm={hasPerm} />;
      case 'payments': return <PaymentModule userRole={user?.role} prefillInvoice={paymentPrefill} hasPerm={hasPerm} />;
      case 'financial-recap': return <FinancialRecapModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'reports': return <ReportsModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'users': return <UserManagementModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'activity-logs': return <ActivityLogModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'company-settings': return <CompanySettingsModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'serial-tracking': return <SerialTrackingModule token={token} />;
      case 'accessories': return <AccessoryModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'role-management': return <RoleManagementModule token={token} userRole={user?.role} hasPerm={hasPerm} />;
      case 'pdf-config': return <PDFConfigModule userRole={user?.role} hasPerm={hasPerm} />;
      case 'smart-import': return <SmartImportModule />;
      case 'help-guide': return <HelpGuideModule />;
      default: return <Dashboard token={token} userRole={user?.role} />;
    }
  };

  const TYPE_COLORS = {
    'PO': 'bg-blue-100 text-blue-700',
    'Vendor': 'bg-purple-100 text-purple-700',
    'Produk': 'bg-emerald-100 text-emerald-700',
    'SKU': 'bg-amber-100 text-amber-700',
  };

  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar
        currentModule={currentModule}
        onModuleChange={setCurrentModule}
        user={user}
        onLogout={handleLogout}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        pendingApprovalsCount={pendingApprovalsCount}
      />
      <div className={`flex-1 flex flex-col min-h-0 transition-all duration-300 ${sidebarCollapsed ? 'ml-16' : 'ml-64'}`}>
        {/* Top bar */}
        <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between flex-shrink-0 gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div>
              <p className="text-sm font-semibold text-slate-800 capitalize">
                {currentModule.replace(/-/g, ' ')}
              </p>
              <p className="text-xs text-slate-400">Garment Production Management System</p>
            </div>
          </div>

          {/* Global Search */}
          <div ref={searchRef} className="relative flex-1 max-w-md">
            <div className="flex items-center gap-2 border border-slate-200 rounded-lg px-3 py-2 bg-slate-50 focus-within:bg-white focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
              <Search className="w-4 h-4 text-slate-400 flex-shrink-0" />
              <input
                type="text"
                placeholder="Cari PO, SKU, Vendor, Produk..."
                className="flex-1 bg-transparent text-sm text-slate-700 placeholder-slate-400 focus:outline-none"
                value={searchQuery}
                onChange={e => handleSearchInput(e.target.value)}
                onFocus={() => searchQuery && setSearchOpen(true)}
                data-testid="global-search-input"
              />
              {searchQuery && (
                <button onClick={() => { setSearchQuery(''); setSearchResults([]); setSearchOpen(false); }} data-testid="search-clear">
                  <X className="w-4 h-4 text-slate-400 hover:text-slate-600" />
                </button>
              )}
            </div>

            {/* Search dropdown */}
            {searchOpen && (
              <div className="absolute top-full mt-1 left-0 right-0 bg-white rounded-xl border border-slate-200 shadow-xl z-50 overflow-hidden">
                {searchLoading ? (
                  <div className="px-4 py-3 text-sm text-slate-500 text-center">Mencari...</div>
                ) : searchResults.length === 0 ? (
                  <div className="px-4 py-3 text-sm text-slate-400 text-center">Tidak ada hasil untuk "{searchQuery}"</div>
                ) : (
                  <div className="max-h-80 overflow-y-auto">
                    {searchResults.map((r, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSearchSelect(r)}
                        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50 text-left transition-colors border-b border-slate-50 last:border-0"
                        data-testid={`search-result-${idx}`}
                      >
                        <span className={`px-1.5 py-0.5 rounded text-xs font-medium flex-shrink-0 ${TYPE_COLORS[r.type] || 'bg-slate-100 text-slate-600'}`}>
                          {r.type}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">{r.label}</p>
                          {r.sub && <p className="text-xs text-slate-400 truncate">{r.sub}</p>}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold">
                {user?.name?.[0]?.toUpperCase()}
              </div>
              <div className="hidden md:block">
                <p className="text-sm font-medium text-slate-700">{user?.name}</p>
                <p className="text-xs text-slate-400 capitalize">{user?.role}</p>
              </div>
            </div>
          </div>
        </header>
        {/* Content */}
        <main className="flex-1 overflow-y-auto p-6">
          {renderModule()}
        </main>
      </div>
    </div>
  );
}

export default App;
