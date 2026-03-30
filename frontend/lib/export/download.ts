export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function exportFileBase(pageSlug: string, repoId?: string) {
  const short = (repoId || 'no-repo').slice(0, 8)
  const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
  return `${pageSlug}-${short}-${ts}`
}
