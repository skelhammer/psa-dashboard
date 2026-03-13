export const PRIORITY_COLORS: Record<string, string> = {
  Critical: 'text-red-400 bg-red-400/10 border-red-400/30',
  Urgent: 'text-red-400 bg-red-400/10 border-red-400/30',
  High: 'text-orange-400 bg-orange-400/10 border-orange-400/30',
  Medium: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  Low: 'text-blue-400 bg-blue-400/10 border-blue-400/30',
  'Very Low': 'text-gray-400 bg-gray-400/10 border-gray-400/30',
}

export const STATUS_COLORS: Record<string, string> = {
  Open: 'text-green-400',
  'Customer Replied': 'text-cyan-400',
  'Under Investigation': 'text-purple-400',
  'On Hold': 'text-gray-400',
  'Waiting on Customer': 'text-yellow-400',
  'Waiting on third party': 'text-yellow-400',
  'Waiting on Order': 'text-yellow-400',
  Scheduled: 'text-blue-400',
  Resolved: 'text-emerald-400',
  Closed: 'text-gray-500',
}

export const BRAND = {
  primary: '#3B82F6',
  primaryLight: '#60A5FA',
  primaryDark: '#2563EB',
  accent: '#06B6D4',
  accentLight: '#22D3EE',
}

export const CHART_COLORS = [
  '#3B82F6', '#06B6D4', '#10B981', '#F59E0B',
  '#8B5CF6', '#EC4899', '#F97316', '#14B8A6',
]

export const DATE_RANGE_OPTIONS = [
  { value: 'today', label: 'Today' },
  { value: 'this_week', label: 'This Week' },
  { value: 'this_month', label: 'This Month' },
  { value: 'this_quarter', label: 'This Quarter' },
  { value: 'this_year', label: 'This Year' },
  { value: 'last_30', label: 'Last 30 Days' },
  { value: 'last_90', label: 'Last 90 Days' },
  { value: 'custom', label: 'Custom Range' },
]
