import type { GraphEdgeModel } from './model'

/** 1-hop neighborhood for focus mode. */
export function focusNeighborIds(centerId: string, edges: GraphEdgeModel[]): Set<string> {
  const keep = new Set<string>([centerId])
  for (const e of edges) {
    if (e.source === centerId) keep.add(e.target)
    if (e.target === centerId) keep.add(e.source)
  }
  return keep
}
