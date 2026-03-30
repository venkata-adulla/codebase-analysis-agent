import { downloadBlob } from '@/lib/export/download'

export type CsvSection = {
  name: string
  headers: string[]
  rows: (string | number | boolean | null | undefined)[][]
}

function escapeCell(v: unknown): string {
  const s = v === null || v === undefined ? '' : String(v)
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

export function sectionsToCsv(sections: CsvSection[]): string {
  const parts: string[] = []
  for (const sec of sections) {
    parts.push(`# ${sec.name}`)
    parts.push(sec.headers.map(escapeCell).join(','))
    for (const row of sec.rows) {
      parts.push(row.map(escapeCell).join(','))
    }
    parts.push('')
  }
  return parts.join('\r\n')
}

export function downloadCsv(sections: CsvSection[], fileBase: string) {
  const t0 = performance.now()
  const text = '\uFEFF' + sectionsToCsv(sections)
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' })
  downloadBlob(blob, `${fileBase}.csv`)
  console.info('[export]', 'csv', fileBase, text.length, 'chars', Math.round(performance.now() - t0), 'ms')
}
