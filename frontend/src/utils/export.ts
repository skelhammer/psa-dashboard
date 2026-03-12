import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'

function humanizeKey(k: string): string {
  return k
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .replace(/\bPct\b/i, '%')
    .replace(/\bAvg\b/i, 'Avg.')
    .replace(/\bId\b/, 'ID')
}

function escapeCSV(value: unknown): string {
  const str = value === null || value === undefined ? '' : String(value)
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

function triggerDownload(content: string, filename: string, mime = 'text/csv;charset=utf-8;') {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function arrayToCSVLines(data: Record<string, any>[], columns?: { key: string; label: string }[]): string[] {
  if (!data.length) return []
  const cols = columns || Object.keys(data[0]).map(k => ({ key: k, label: humanizeKey(k) }))
  const header = cols.map(c => escapeCSV(c.label)).join(',')
  const rows = data.map(row => cols.map(c => escapeCSV(row[c.key])).join(','))
  return [header, ...rows]
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
  const lines = arrayToCSVLines(data, columns)
  triggerDownload(lines.join('\n'), filename.endsWith('.csv') ? filename : `${filename}.csv`)
}

/**
 * Export chart data as CSV.
 */
export function exportChartDataAsCSV(data: any[], filename: string) {
  if (!data.length) return
  const lines = arrayToCSVLines(data)
  triggerDownload(lines.join('\n'), filename.endsWith('.csv') ? filename : `${filename}.csv`)
}

/**
 * Export multiple named datasets into a single CSV with section headers.
 * Each section is separated by a blank line and preceded by a "--- Section Name ---" row.
 */
export function exportMultiSectionCSV(
  sections: { name: string; data: Record<string, any>[]; columns?: { key: string; label: string }[] }[],
  filename: string
) {
  const allLines: string[] = []
  for (const section of sections) {
    if (!section.data?.length) continue
    if (allLines.length > 0) allLines.push('') // blank line between sections
    allLines.push(escapeCSV(`--- ${section.name} ---`))
    allLines.push(...arrayToCSVLines(section.data, section.columns))
  }
  if (!allLines.length) return
  triggerDownload(allLines.join('\n'), filename.endsWith('.csv') ? filename : `${filename}.csv`)
}

/**
 * Capture the main content area and export as a portrait PDF.
 * Content that exceeds one page is split across multiple pages cleanly.
 */
export async function exportPageAsPDF(title: string) {
  const mainEl = document.querySelector('main') as HTMLElement | null
  if (!mainEl) return

  // Hide export buttons and force a consistent capture width
  const styleEl = document.createElement('style')
  styleEl.id = 'pdf-export-theme'
  styleEl.textContent = `
    .export-btn { display: none !important; }
    main, main * { color-adjust: exact; -webkit-print-color-adjust: exact; }
  `
  document.head.appendChild(styleEl)
  await new Promise(r => setTimeout(r, 100))

  // Use the element's actual client width (visible area, no scrollbar)
  const captureWidth = mainEl.clientWidth

  const canvas = await html2canvas(mainEl, {
    backgroundColor: '#09090B',
    scale: 2,
    useCORS: true,
    logging: false,
    width: captureWidth,
    windowWidth: captureWidth,
    scrollX: 0,
    scrollY: -mainEl.scrollTop,
  })

  styleEl.remove()

  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
  const pageWidth = pdf.internal.pageSize.getWidth()
  const pageHeight = pdf.internal.pageSize.getHeight()
  const margin = 10
  const headerHeight = 16
  const footerHeight = 6

  const availableWidth = pageWidth - margin * 2
  const contentTop = margin + headerHeight
  const availableHeight = pageHeight - contentTop - footerHeight

  // Scale image width to fit page, then figure out total rendered height
  const scale = availableWidth / canvas.width
  const totalImgHeightMm = canvas.height * scale

  // How many pages?
  const totalPages = Math.max(1, Math.ceil(totalImgHeightMm / availableHeight))
  // Pixels of source image per page
  const srcPixelsPerPage = availableHeight / scale

  const dateStr = new Date().toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })

  for (let page = 0; page < totalPages; page++) {
    if (page > 0) pdf.addPage()

    // Header
    pdf.setFontSize(13)
    pdf.setTextColor(40, 40, 40)
    pdf.text(title, margin, margin + 5)
    pdf.setFontSize(8)
    pdf.setTextColor(140, 140, 140)
    pdf.text(`Exported: ${dateStr}`, margin, margin + 10)
    if (totalPages > 1) {
      const pageLabel = `Page ${page + 1} of ${totalPages}`
      pdf.text(pageLabel, pageWidth - margin - pdf.getTextWidth(pageLabel), margin + 10)
    }
    pdf.setDrawColor(200, 200, 200)
    pdf.setLineWidth(0.2)
    pdf.line(margin, margin + 12, pageWidth - margin, margin + 12)

    // Slice the source canvas for this page
    const srcY = Math.round(page * srcPixelsPerPage)
    const srcH = Math.min(Math.round(srcPixelsPerPage), canvas.height - srcY)
    if (srcH <= 0) continue

    const slice = document.createElement('canvas')
    slice.width = canvas.width
    slice.height = srcH
    const ctx = slice.getContext('2d')
    if (ctx) {
      ctx.drawImage(canvas, 0, srcY, canvas.width, srcH, 0, 0, canvas.width, srcH)
    }

    const sliceHeightMm = srcH * scale
    pdf.addImage(slice.toDataURL('image/png'), 'PNG', margin, contentTop, availableWidth, sliceHeightMm)

    // Footer
    pdf.setFontSize(7)
    pdf.setTextColor(170, 170, 170)
    pdf.text('PSA Dashboard', margin, pageHeight - 3)
    const footerRight = 'Integotec'
    pdf.text(footerRight, pageWidth - margin - pdf.getTextWidth(footerRight), pageHeight - 3)
  }

  pdf.save(`${title.replace(/\s+/g, '_').toLowerCase()}_${new Date().toISOString().slice(0, 10)}.pdf`)
}
