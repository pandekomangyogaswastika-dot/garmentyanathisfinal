const statusColors = {
  // General
  active: 'bg-emerald-100 text-emerald-700',
  inactive: 'bg-slate-100 text-slate-600',
  // PO Status
  Draft: 'bg-slate-100 text-slate-700',
  Distributed: 'bg-blue-100 text-blue-700',
  'In Production': 'bg-amber-100 text-amber-700',
  Completed: 'bg-emerald-100 text-emerald-700',
  Closed: 'bg-slate-100 text-slate-600',
  // Work Order Status
  Waiting: 'bg-slate-100 text-slate-600',
  'In Progress': 'bg-blue-100 text-blue-700',
  // Invoice Status
  Unpaid: 'bg-red-100 text-red-700',
  Partial: 'bg-amber-100 text-amber-700',
  Paid: 'bg-emerald-100 text-emerald-700',
};

export default function StatusBadge({ status }) {
  const color = statusColors[status] || 'bg-slate-100 text-slate-700';
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}
