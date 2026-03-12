import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'

/**
 * Escape a CSV cell value: wrap in quotes if it contains commas, quotes, or newlines.
 */
function escapeCSV(value: unknown): string {
  const str = value === null || value === undefined ? '' : String(value)
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

function triggerDownload(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename.endsWith('.csv') ? filename : `${filename}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * Export table data as CSV with optional column mapping.
 */
export function exportTableAsCSV(
  data: Record<string, any>[],
  filename: string,
  columns?: { key: string; label: string }[]
) {
  if (!data.length) return

  const cols = columns || Object.keys(data[0]).map(k => ({ key: k, label: k }))
  const header = cols.map(c => escapeCSV(c.label)).join(',')
  const rows = data.map(row =>
    cols.map(c => escapeCSV(row[c.key])).join(',')
  )
  triggerDownload([header, ...rows].join('\n'), filename)
}

/**
 * Export chart data (simple array of objects) as CSV.
 */
export function exportChartDataAsCSV(data: any[], filename: string) {
  if (!data.length) return

  const keys = Object.keys(data[0])
  const header = keys.map(k => escapeCSV(k)).join(',')
  const rows = data.map(row =>
    keys.map(k => escapeCSV(row[k])).join(',')
  )
  triggerDownload([header, ...rows].join('\n'), filename)
}

/**
 * Capture the main content area and export as a landscape PDF.
 */
export async function exportPageAsPDF(title: string) {
  const mainEl = document.querySelector('main')
  if (!mainEl) return

  const canvas = await html2canvas(mainEl as HTMLElement, {
    backgroundColor: '#030712',
    scale: 2,
    useCORS: true,
    logging: false,
  })

  const imgData = canvas.toDataURL('image/png')
  const pdf = new jsPDF({
    orientation: 'landscape',
    unit: 'mm',
    format: 'a4',
  })

  const pageWidth = pdf.internal.pageSize.getWidth()
  const pageHeight = pdf.internal.pageSize.getHeight()
  const margin = 10

  // Header
  pdf.setFontSize(14)
  pdf.setTextColor(40, 40, 40)
  pdf.text(title, margin, margin + 5)

  pdf.setFontSize(8)
  pdf.setTextColor(120, 120, 120)
  pdf.text(`Exported: ${new Date().toLocaleString()}`, margin, margin + 10)

  // Image
  const contentTop = margin + 15
  const availableWidth = pageWidth - margin * 2
  const availableHeight = pageHeight - contentTop - margin
  const imgRatio = canvas.width / canvas.height
  let imgWidth = availableWidth
  let imgHeight = imgWidth / imgRatio

  if (imgHeight > availableHeight) {
    imgHeight = availableHeight
    imgWidth = imgHeight * imgRatio
  }

  pdf.addImage(imgData, 'PNG', margin, contentTop, imgWidth, imgHeight)
  pdf.save(`${title.replace(/\s+/g, '_').toLowerCase()}.pdf`)
}
