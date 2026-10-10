import {
  Activity, Award, BriefcaseBusiness, Crown, FileText, LayoutDashboard,
  Map, MessagesSquare, Sparkles, Target,
} from 'lucide-react';

export function isPlacementStaffRole(role) {
  return role === 'placement_staff' || role === 'admin';
}

export function getNavigationItems(role) {
  const items = [
    { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/resume', icon: FileText, label: 'Resume' },
    { path: '/gap', icon: Target, label: 'Skill Gap' },
    { path: '/roadmap', icon: Map, label: 'Roadmap' },
    { path: '/learn', icon: Activity, label: 'Learn & Practice' },
    { path: '/mastery', icon: Award, label: 'Skill Mastery' },
    { path: '/interview', icon: MessagesSquare, label: 'Interview' },
    { path: '/readiness', icon: Sparkles, label: 'Readiness' },
    { path: '/premium', icon: Crown, label: 'Premium' },
  ];
  if (isPlacementStaffRole(role)) {
    items.push({ path: '/placement', icon: BriefcaseBusiness, label: 'Placement Cell' });
  }
  return items;
}

export function buildPlacementQuery(filters, page = 1, pageSize = 25, sortBy = 'name', sortOrder = 'asc') {
  const params = { page, page_size: pageSize, sort_by: sortBy, sort_order: sortOrder };
  if (filters.branch.trim()) params.branch = filters.branch.trim();
  if (filters.semester) params.semester = Number(filters.semester);
  if (filters.target_role.trim()) params.target_role = filters.target_role.trim();
  return params;
}
