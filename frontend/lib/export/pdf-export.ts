export type PdfSection = { heading: string; body: string }

export async function downloadAnalysisPdf(options: {
  title: string
  repoLabel: string
  repoId?: string
  sections: PdfSection[]
  imageElement?: HTMLElement | null
  fileBase: string
}): Promise<void> {
  const t0 = performance.now()
  const { default: JsPDF } = await import('jspdf')
  const doc = new JsPDF({ unit: 'pt', format: 'a4' })
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const margin = 48
  let y = margin

  doc.setFontSize(18)
  doc.setTextColor(30, 30, 30)
  doc.text(options.title, margin, y)
  y += 22
  doc.setFontSize(10)
  doc.setTextColor(80, 80, 80)
  doc.text(`Repository: ${options.repoLabel}`, margin, y)
  y += 14
  if (options.repoId) {
    doc.text(`Repository ID: ${options.repoId}`, margin, y)
    y += 14
  }
  doc.text(`Exported: ${new Date().toLocaleString()}`, margin, y)
  y += 24
  doc.setTextColor(40, 40, 40)

  if (options.imageElement) {
    try {
      const { toPng } = await import('html-to-image')
      const dataUrl = await toPng(options.imageElement, {
        pixelRatio: 2,
        cacheBust: true,
        backgroundColor: '#0b1220',
      })
      const imgW = pageW - 2 * margin
      const prop = doc.getImageProperties(dataUrl)
      const imgH = (prop.height * imgW) / prop.width
      const maxH = pageH - y - margin
      const drawH = Math.min(imgH, maxH)
      const drawW = drawH === imgH ? imgW : (prop.width * drawH) / prop.height
      if (y + drawH > pageH - margin) {
        doc.addPage()
        y = margin
      }
      doc.addImage(dataUrl, 'PNG', margin, y, drawW, drawH)
      y += drawH + 20
    } catch (e) {
      doc.setFontSize(10)
      doc.text('(Figure: could not capture visual — export JSON or PNG separately.)', margin, y)
      y += 20
      console.warn('[export] pdf image embed failed', e)
    }
  }

  doc.setFontSize(11)
  for (const sec of options.sections) {
    const block = `${sec.heading}\n\n${sec.body}`
    const lines = doc.splitTextToSize(block, pageW - 2 * margin)
    for (const line of lines) {
      if (y > pageH - margin) {
        doc.addPage()
        y = margin
      }
      doc.text(line, margin, y)
      y += 14
    }
    y += 12
  }

  doc.save(`${options.fileBase}.pdf`)
  console.info('[export]', 'pdf', options.fileBase, Math.round(performance.now() - t0), 'ms')
}
