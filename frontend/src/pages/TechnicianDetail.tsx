import { useParams, useNavigate } from 'react-router-dom'
import { useTechnicianDetail } from '../api/hooks'
import TicketTable from '../components/TicketTable'
import ChartCard from '../components/ChartCard'
import { CHART_COLORS, BRAND } from '../utils/constants'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' },
  labelStyle: { color: '#9ca3af' },
  itemStyle: { color: '#d1d5db' },
  cursor: { fill: 'rgba(180, 155, 127, 0.1)' },
}

export default function TechnicianDetail() {
  const { techId } = useParams()
  const navigate = useNavigate()
  const { data, isLoading } = useTechnicianDetail(techId)

  if (isLoading) return <div className="text-gray-500">Loading...</div>
  if (data?.error) return <div className="text-red-400">{data.error}</div>

  const tech = data?.technician

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/technicians')}
          className="text-sm text-gray-500 hover:text-gray-300"
        >
          &larr; Back
        </button>
        <h2 className="text-xl font-bold">{tech?.name}</h2>
        <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded-full">{tech?.role}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Tickets by Category">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data?.categories || []} layout="vertical">
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="category" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={80} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {(data?.categories || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Tickets by Client">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data?.clients || []} layout="vertical">
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="client" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={120} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" fill={BRAND.gold} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div>
        <h3 className="text-lg font-semibold mb-3">
          Open Tickets
          <span className="text-xs text-gray-500 ml-2">({data?.open_tickets?.length || 0})</span>
        </h3>
        <TicketTable
          tickets={data?.open_tickets || []}
          emptyMessage="No open tickets assigned."
        />
      </div>
    </div>
  )
}
