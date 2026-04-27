
import { useState, useEffect } from 'react';
import {
  LayoutDashboard, Package, Factory, ClipboardList, TrendingUp,
  FileText, CreditCard, BarChart3, Users, Activity, LogOut, Menu, X,
  Shirt, DollarSign, BookOpen, Truck, ChevronRight, ChevronDown, Pencil, RotateCcw,
  Clock, Shield, Gem, FileDown, Brain, Search
} from 'lucide-react';
import { apiGet } from '../../lib/api';

// ─── Menu Definition ─────────────────────────────────────────────────────────
// Dashboard is standalone (no section).
// Sections are collapsible accordion groups.
const GROUPS = [
  {
    id: 'master',
    label: 'Master Data',
    icon: Package,
    items: [
      { id: 'garments',    label: 'Vendor / Garmen', icon: Shirt,        perm: 'garments.view' },
      { id: 'buyers',      label: 'Data Buyer',       icon: Users,        perm: 'garments.view' },
      { id: 'products',    label: 'Data Produk',      icon: Package,      perm: 'products.view' },
      { id: 'accessories', label: 'Data Aksesoris',   icon: Gem,          perm: 'accessories.view' },
    ],
  },
  {
    id: 'produksi',
    label: 'Produksi',
    icon: Factory,
    items: [
      { id: 'production-po',        label: 'Production PO',      icon: ClipboardList, perm: 'po.view' },
      { id: 'vendor-shipments',     label: 'Vendor Shipment',    icon: Truck,         perm: 'shipment.view' },
      { id: 'buyer-shipments',      label: 'Buyer Shipment',     icon: Package,       perm: 'shipment.view' },
      { id: 'production-returns',   label: 'Retur Produksi',     icon: RotateCcw,     perm: 'po.view' },
      { id: 'work-orders',          label: 'Distribusi Kerja',   icon: Factory,       perm: 'jobs.view' },
      { id: 'production-monitoring',label: 'Monitoring Produksi',icon: BarChart3,     perm: 'jobs.view' },
      { id: 'overproduction',       label: 'Over/Under Produksi',icon: TrendingUp,    perm: 'jobs.view' },
      { id: 'serial-tracking',      label: 'Serial Tracking',    icon: Clock,         perm: 'dashboard.view' },
    ],
  },
  {
    id: 'keuangan',
    label: 'Keuangan',
    icon: DollarSign,
    items: [
      { id: 'accounts-payable',   label: 'Hutang Vendor (AP)',    icon: CreditCard,  perm: 'invoice.view' },
      { id: 'accounts-receivable',label: 'Piutang Buyer (AR)',    icon: TrendingUp,  perm: 'invoice.view' },
      { id: 'manual-invoice',     label: 'Invoice Manual',        icon: Pencil,      perm: 'invoice.create' },
      { id: 'invoice-approval',   label: 'Invoice Approval',      icon: Shield,      roles: ['superadmin', 'admin'], badge: 'pending_approvals' },
      { id: 'invoices',           label: 'Semua Invoice',         icon: FileText,    perm: 'invoice.view' },
      { id: 'payments',           label: 'Manajemen Pembayaran',  icon: DollarSign,  perm: 'payment.view' },
      { id: 'financial-recap',    label: 'Rekap Keuangan',        icon: BarChart3,   perm: 'report.view' },
    ],
  },
  {
    id: 'laporan',
    label: 'Laporan & Tools',
    icon: BarChart3,
    items: [
      { id: 'reports',      label: 'Laporan',          icon: BarChart3, perm: 'report.view' },
      { id: 'smart-import', label: 'Smart Import',     icon: Brain,     perm: 'po.view' },
      { id: 'help-guide',   label: 'Panduan',          icon: BookOpen },
    ],
  },
  {
    id: 'sistem',
    label: 'Sistem',
    icon: Shield,
    items: [
      { id: 'company-settings', label: 'Pengaturan Perusahaan', icon: Pencil,   roles: ['superadmin', 'admin'], perm: 'settings.manage' },
      { id: 'pdf-config',       label: 'Konfigurasi PDF',       icon: FileDown, roles: ['superadmin', 'admin'], perm: 'settings.manage' },
      { id: 'users',            label: 'Manajemen User',        icon: Users,    roles: ['superadmin'],          perm: 'users.manage' },
      { id: 'role-management',  label: 'Manajemen Role',        icon: Shield,   roles: ['superadmin'],          perm: 'roles.manage' },
      { id: 'activity-logs',    label: 'Log Aktivitas',         icon: Activity, roles: ['superadmin', 'admin'] },
    ],
  },
];

// Which group owns a given module id
function findGroup(moduleId) {
  for (const g of GROUPS) {
    if (g.items.some(i => i.id === moduleId)) return g.id;
  }
  return null;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function Sidebar({
  currentModule, onModuleChange, user, onLogout,
  collapsed, onToggle, pendingApprovalsCount
}) {
  const [userPerms, setUserPerms] = useState([]);
  // expanded: which group ids are open
  const [expanded, setExpanded] = useState(() => {
    const active = findGroup(currentModule);
    return active ? new Set([active]) : new Set(['produksi']);
  });

  // When active module changes, ensure its group is expanded
  useEffect(() => {
    const g = findGroup(currentModule);
    if (g) setExpanded(prev => new Set([...prev, g]));
  }, [currentModule]);

  // Fetch user permissions
  useEffect(() => {
    apiGet('/auth/me')
      .then(data => setUserPerms(data.permissions || []))
      .catch(() => {});
  }, [user?.id]);

  const canAccess = (item) => {
    if (item.roles && !item.roles.includes(user?.role)) return false;
    if (['superadmin', 'admin'].includes(user?.role)) return true;
    if (userPerms.includes('*')) return true;
    if (item.perm && userPerms.length > 0 && !userPerms.includes(item.perm)) return false;
    return true;
  };

  const toggleGroup = (groupId) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  return (
    <div
      className={`fixed left-0 top-0 h-full bg-slate-900 text-white transition-all duration-300 z-40 flex flex-col ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700 flex-shrink-0">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center">
              <Shirt className="w-5 h-5" />
            </div>
            <div>
              <div className="font-bold text-sm leading-tight">GARMENT ERP</div>
              <div className="text-slate-400 text-xs">Production System</div>
            </div>
          </div>
        )}
        {collapsed && (
          <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center mx-auto">
            <Shirt className="w-5 h-5" />
          </div>
        )}
        <button onClick={onToggle} className="text-slate-400 hover:text-white ml-auto p-1">
          {collapsed ? <Menu className="w-5 h-5" /> : <X className="w-5 h-5" />}
        </button>
      </div>

      {/* ── User Info ───────────────────────────────────────────────────── */}
      {!collapsed && (
        <div className="px-4 py-3 border-b border-slate-700 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0">
              {user?.name?.[0]?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{user?.name}</div>
              <div className="text-xs text-slate-400 capitalize">{user?.role}</div>
            </div>
          </div>
        </div>
      )}

      {/* ── Navigation ──────────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto py-2 scrollbar-thin scrollbar-thumb-slate-700">

        {/* Dashboard — standalone, always visible */}
        <NavItem
          item={{ id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard }}
          isActive={currentModule === 'dashboard'}
          collapsed={collapsed}
          onClick={() => onModuleChange('dashboard')}
        />

        {/* Divider */}
        {!collapsed && <div className="mx-3 my-1 border-t border-slate-800" />}

        {/* Collapsible Groups */}
        {GROUPS.map(group => {
          const visibleItems = group.items.filter(canAccess);
          if (visibleItems.length === 0) return null;

          const isOpen = expanded.has(group.id);
          const GroupIcon = group.icon;
          const activeInGroup = visibleItems.some(i => i.id === currentModule);
          const badgeCount = visibleItems.reduce((sum, item) => {
            return sum + (item.badge === 'pending_approvals' ? (pendingApprovalsCount || 0) : 0);
          }, 0);

          return (
            <div key={group.id}>
              {/* Group Header */}
              <button
                onClick={() => collapsed ? null : toggleGroup(group.id)}
                title={collapsed ? group.label : ''}
                className={`w-full flex items-center gap-3 px-3 py-2 text-xs font-semibold transition-colors rounded-lg mx-1 my-0.5 ${
                  activeInGroup
                    ? 'text-blue-300 bg-slate-800'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                } ${collapsed ? 'justify-center' : ''}`}
                style={{ width: collapsed ? 'calc(100% - 8px)' : 'calc(100% - 8px)' }}
              >
                <GroupIcon className={`w-4 h-4 flex-shrink-0 ${activeInGroup ? 'text-blue-400' : ''}`} />
                {!collapsed && (
                  <>
                    <span className="flex-1 text-left uppercase tracking-wider">{group.label}</span>
                    {badgeCount > 0 && (
                      <span className="px-1.5 py-0.5 bg-amber-500 text-white rounded-full text-xs font-bold">
                        {badgeCount}
                      </span>
                    )}
                    {isOpen
                      ? <ChevronDown className="w-3.5 h-3.5 flex-shrink-0 text-slate-500" />
                      : <ChevronRight className="w-3.5 h-3.5 flex-shrink-0 text-slate-500" />}
                  </>
                )}
                {collapsed && badgeCount > 0 && (
                  <span className="absolute top-0 right-0 w-2 h-2 bg-amber-500 rounded-full" />
                )}
              </button>

              {/* Group Items */}
              {(isOpen || collapsed) && visibleItems.map(item => {
                const itemBadge = item.badge === 'pending_approvals' ? pendingApprovalsCount : 0;
                return (
                  <NavItem
                    key={item.id}
                    item={item}
                    isActive={currentModule === item.id}
                    collapsed={collapsed}
                    indented={!collapsed}
                    badge={itemBadge}
                    onClick={() => onModuleChange(item.id)}
                  />
                );
              })}
            </div>
          );
        })}
      </nav>

      {/* ── Logout ──────────────────────────────────────────────────────── */}
      <div className="border-t border-slate-700 p-2 flex-shrink-0">
        <button
          onClick={onLogout}
          className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-slate-400 hover:bg-slate-800 hover:text-white rounded-lg transition-colors ${
            collapsed ? 'justify-center' : ''
          }`}
          title={collapsed ? 'Logout' : ''}
        >
          <LogOut className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>Logout</span>}
        </button>
      </div>
    </div>
  );
}

// ─── NavItem helper ────────────────────────────────────────────────────────────
function NavItem({ item, isActive, collapsed, indented, badge, onClick }) {
  const Icon = item.icon;
  return (
    <button
      onClick={onClick}
      data-testid={`nav-${item.id}`}
      title={collapsed ? item.label : ''}
      className={`w-full flex items-center gap-3 py-2 text-sm transition-colors rounded-lg mx-1 ${
        indented ? 'pl-8 pr-3' : 'px-3'
      } ${
        isActive
          ? 'bg-blue-600 text-white shadow-sm'
          : 'text-slate-300 hover:bg-slate-800 hover:text-white'
      } ${collapsed ? 'justify-center' : ''}
      `}
      style={{ width: 'calc(100% - 8px)' }}
    >
      <Icon className="w-4 h-4 flex-shrink-0" />
      {!collapsed && (
        <>
          <span className="flex-1 text-left truncate">{item.label}</span>
          {badge > 0 && (
            <span className="ml-auto px-2 py-0.5 bg-amber-500 text-white rounded-full text-xs font-bold flex-shrink-0">
              {badge}
            </span>
          )}
          {isActive && !badge && (
            <ChevronRight className="w-3.5 h-3.5 ml-auto flex-shrink-0 text-blue-200" />
          )}
        </>
      )}
    </button>
  );
}
