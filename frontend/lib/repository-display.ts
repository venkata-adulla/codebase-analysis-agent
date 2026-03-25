export function repositoryDisplayName(name?: string | null, fallbackId?: string | null) {
  const raw = (name || '').trim()
  if (!raw) return (fallbackId || '').trim()

  const normalized = raw.replace(/\.git$/i, '')
  const slashParts = normalized.split('/').filter(Boolean)
  const tail = slashParts[slashParts.length - 1]

  if (/^https?:\/\//i.test(normalized) && tail) {
    return tail
  }
  return normalized
}
