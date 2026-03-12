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
  gold: '#B49B7F',
  goldLight: '#C9B59A',
  goldDark: '#9A8369',
  black: '#000000',
}

export const CHART_COLORS = [
  '#B49B7F', '#60A5FA', '#34D399', '#F87171',
  '#A78BFA', '#FBBF24', '#F472B6', '#2DD4BF',
]

export const DATE_RANGE_OPTIONS = [
  { value: 'today', label: 'Today' },
  { value: 'this_week', label: 'This Week' },
  { value: 'this_month', label: 'This Month' },
  { value: 'this_quarter', label: 'This Quarter' },
  { value: 'this_year', label: 'This Year' },
  { value: 'last_30', label: 'Last 30 Days' },
  { value: 'last_90', label: 'Last 90 Days' },
]
