import { repositoryDisplayName } from '@/lib/repository-display'

/** Heuristic UUID (v1–v5 style) for display decisions only. */
const UUID_LIKE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function isLikelyUuid(s: string) {
  return UUID_LIKE.test((s || '').trim())
}

export function serviceDisplayName(service: {
  id: string
  name?: string
  path?: string
  repository_name?: string
  repository_id?: string
}) {
  const n = (service.name || '').trim()
  if (n && !isLikelyUuid(n)) return n
  if (service.path) {
    const parts = service.path.split(/[/\\]/).filter(Boolean)
    const base = parts[parts.length - 1]
    if (base && !isLikelyUuid(base)) return base
  }

  const repoLabel = repositoryDisplayName(service.repository_name, service.repository_id)
  if (repoLabel) return `Repository root (${repoLabel})`
  return 'Repository root'
}
