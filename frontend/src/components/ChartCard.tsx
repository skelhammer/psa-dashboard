import { ReactNode } from 'react'
import { Download } from 'lucide-react'
import clsx from 'clsx'
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
    <div className={clsx('card animate-fade-in', className)}>
      <div className="flex items-center justify-between mb-5 pb-3 border-b border-white/[0.06]">
        <h3 className="text-sm font-semibold text-gray-300 tracking-wide">{title}</h3>
        {exportData && exportData.length > 0 && (
          <button
            onClick={handleExport}
            className="text-gray-600 hover:text-brand-primary transition-colors export-btn p-1.5 rounded-lg hover:bg-white/[0.06]"
            title="Download chart data as CSV"
          >
            <Download size={14} />
          </button>
        )}
      </div>
      {children}
    </div>
  )
}
