import { repositoryDisplayName } from '@/lib/repository-display'
import { isLikelyUuid } from '@/lib/service-display'
import type { RawApiNode } from './model'

export function displayNodeName(
  node: Pick<RawApiNode, 'id' | 'name'>,
  repositoryName?: string,
  repositoryId?: string
) {
  const raw = (node.name || '').trim()
  if (raw && !isLikelyUuid(raw)) return raw
  const repoLabel = repositoryDisplayName(repositoryName, repositoryId)
  return repoLabel ? `Repository root (${repoLabel})` : 'Repository root'
}
