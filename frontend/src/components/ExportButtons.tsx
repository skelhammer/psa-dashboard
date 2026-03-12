import { exportTableAsCSV, exportPageAsPDF } from '../utils/export'

interface ExportButtonsProps {
  csvData?: Record<string, any>[]
  csvFilename?: string
  csvColumns?: { key: string; label: string }[]
  pageTitle?: string
}

const btnClass =
  'bg-gray-800 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 transition-colors export-btn'

export default function ExportButtons({
  csvData,
  csvFilename,
  csvColumns,
  pageTitle,
}: ExportButtonsProps) {
  const handleCSV = () => {
    if (!csvData?.length) return
    exportTableAsCSV(csvData, csvFilename || 'export', csvColumns)
  }

  const handlePDF = () => {
    exportPageAsPDF(pageTitle || 'PSA Dashboard')
  }

  return (
    <div className="flex items-center gap-1.5 export-btn">
      {csvData && (
        <button onClick={handleCSV} className={btnClass} title="Export table data as CSV">
          CSV
        </button>
      )}
      <button onClick={handlePDF} className={btnClass} title="Export page as PDF">
        PDF
      </button>
    </div>
  )
}
