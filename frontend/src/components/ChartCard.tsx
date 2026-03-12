import { ReactNode } from 'react'
import { exportChartDataAsCSV } from '../utils/export'

interface ChartCardProps {
  title: string
  children: ReactNode
  className?: string
  exportData?: any[]
  exportFilename?: string
}

export default function ChartCard({ title, children, className, exportData, exportFilename }: ChartCardProps) {
  const handleExport = () => {
    if (exportData?.length) {
      exportChartDataAsCSV(exportData, exportFilename || 'chart_data')
    }
  }

  return (
    <div className={`card ${className || ''}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-400">{title}</h3>
        {exportData && exportData.length > 0 && (
          <button
            onClick={handleExport}
            className="text-gray-600 hover:text-gray-400 transition-colors export-btn"
            title="Download chart data as CSV"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" />
            </svg>
          </button>
        )}
      </div>
      {children}
    </div>
  )
}
