import { Download, FileText } from 'lucide-react'
import { exportTableAsCSV, exportPageAsPDF } from '../utils/export'

interface ExportButtonsProps {
  csvData?: Record<string, any>[]
  csvFilename?: string
  csvColumns?: { key: string; label: string }[]
  pageTitle?: string
  onCSV?: () => void
}

export default function ExportButtons({
  csvData,
  csvFilename,
  csvColumns,
  pageTitle,
  onCSV,
}: ExportButtonsProps) {
  const handleCSV = () => {
    if (onCSV) {
      onCSV()
      return
    }
    if (!csvData?.length) return
    exportTableAsCSV(csvData, csvFilename || 'export', csvColumns)
  }

  const handlePDF = () => {
    exportPageAsPDF(pageTitle || 'PSA Dashboard')
  }

  const showCSV = onCSV || csvData
  const btnClass =
    'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-400 bg-white/[0.04] border border-white/[0.08] rounded-lg hover:bg-white/[0.08] hover:text-gray-200 hover:border-white/[0.12] transition-all duration-150 export-btn'

  return (
    <div className="flex items-center gap-1.5 export-btn">
      {showCSV && (
        <button onClick={handleCSV} className={btnClass} title="Export data as CSV">
          <Download className="w-3.5 h-3.5" />
          CSV
        </button>
      )}
      <button onClick={handlePDF} className={btnClass} title="Export page as PDF">
        <FileText className="w-3.5 h-3.5" />
        PDF
      </button>
    </div>
  )
}
