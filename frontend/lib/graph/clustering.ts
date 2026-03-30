import type { GraphEdgeModel, GraphNodeModel, RawApiEdge, RawApiNode } from './model'
import { edgeWeight, nodeSizeFromDegree, riskScoreForNode } from './metrics'
import { assignLayer } from './layers'
import { displayNodeName } from './display'

function requireDegrees(
  ids: string[],
  edges: RawApiEdge[]
): { outD: Map<string, number>; inD: Map<string, number> } {
  const outD = new Map<string, number>()
  const inD = new Map<string, number>()
  for (const id of ids) {
    outD.set(id, 0)
    inD.set(id, 0)
  }
  for (const e of edges) {
    if (!e.source || !e.target || e.source === e.target) continue
    if (!outD.has(e.source)) outD.set(e.source, 0)
    if (!inD.has(e.target)) inD.set(e.target, 0)
    outD.set(e.source, (outD.get(e.source) || 0) + 1)
    inD.set(e.target, (inD.get(e.target) || 0) + 1)
  }
  return { outD, inD }
}

/** Build service-level nodes from API + enrichment. */
export function mapRawToServiceNodes(
  rawNodes: RawApiNode[],
  edges: RawApiEdge[],
  enrichment: Map<string, { summary?: string | null }>,
  repoName?: string,
  repoId?: string
): GraphNodeModel[] {
  const ids = rawNodes.map((n) => n.id)
  const { outD, inD } = requireDegrees(ids, edges)
  const maxDeg = Math.max(1, ...ids.map((id) => (outD.get(id) || 0) + (inD.get(id) || 0)))

  return rawNodes.map((n) => {
    const label = displayNodeName(n, repoName, repoId)
    const layer = assignLayer(n, label)
    const pk = packageKeyFromName(label)
    const tdeg = (outD.get(n.id) || 0) + (inD.get(n.id) || 0)
    const { width, height } = nodeSizeFromDegree(tdeg, maxDeg)
    const en = enrichment.get(n.id)
    return {
      id: n.id,
      label,
      kind: 'service',
      layer,
      dependencyCount: outD.get(n.id) || 0,
      dependentsCount: inD.get(n.id) || 0,
      riskScore: riskScoreForNode(n.id, outD, inD, maxDeg),
      summary: en?.summary?.trim() || undefined,
      packageKey: pk,
      language: n.language,
      classification: n.classification,
      width,
      height,
    }
  })
}

function packageKeyFromName(name: string): string {
  const parts = name.split('.').filter(Boolean)
  if (parts.length <= 1) return parts[0] || 'root'
  return parts[0]
}

export function mapRawToEdges(
  rawEdges: RawApiEdge[],
  nodeIds: Set<string>
): GraphEdgeModel[] {
  const ids = [...nodeIds]
  const { outD, inD } = requireDegrees(ids, rawEdges)
  const maxDeg = Math.max(1, ...ids.map((id) => (outD.get(id) || 0) + (inD.get(id) || 0)))

  const result: GraphEdgeModel[] = []
  let i = 0
  for (const e of rawEdges) {
    if (!e.source || !e.target || e.source === e.target) continue
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue
    const w = edgeWeight(outD.get(e.source) || 0, inD.get(e.target) || 0, maxDeg)
    result.push({
      id: `e-${i++}`,
      source: e.source,
      target: e.target,
      weight: w,
      type: e.type || 'depends_on',
      kind: e.kind || 'direct',
    })
  }
  return result
}

/** Collapse nodes sharing a package key into one cluster node (inter-cluster edges only). */
export function collapseByPackage(
  nodes: GraphNodeModel[],
  edges: GraphEdgeModel[],
  expandedKeys: Set<string>
): { nodes: GraphNodeModel[]; edges: GraphEdgeModel[] } {
  const byKey = new Map<string, GraphNodeModel[]>()
  for (const n of nodes) {
    const k = n.packageKey || 'root'
    if (!byKey.has(k)) byKey.set(k, [])
    byKey.get(k)!.push(n)
  }

  const singletonKeys = new Set<string>()
  for (const [k, list] of byKey) {
    if (list.length <= 1) singletonKeys.add(k)
  }

  const idRemap = new Map<string, string>()

  for (const n of nodes) {
    const k = n.packageKey || 'root'
    if (singletonKeys.has(k) || expandedKeys.has(k)) {
      idRemap.set(n.id, n.id)
      continue
    }
    idRemap.set(n.id, `cluster:${k}`)
  }

  const clusterNodes: GraphNodeModel[] = []

  for (const [k, list] of byKey) {
    if (singletonKeys.has(k) || expandedKeys.has(k)) continue
    const memberIds = list.map((x) => x.id)
    const maxR = Math.max(...list.map((x) => x.riskScore))
    const sumDeg = list.reduce((a, x) => a + x.dependencyCount + x.dependentsCount, 0)
    clusterNodes.push({
      id: `cluster:${k}`,
      label: `${k} · ${list.length} modules`,
      kind: 'cluster',
      layer: 'core',
      dependencyCount: Math.round(sumDeg / 2),
      dependentsCount: Math.round(sumDeg / 2),
      riskScore: maxR,
      summary: undefined,
      packageKey: k,
      memberIds,
      width: 200,
      height: 64,
    })
  }

  const outNodes: GraphNodeModel[] = []
  for (const n of nodes) {
    const k = n.packageKey || 'root'
    if (singletonKeys.has(k) || expandedKeys.has(k)) {
      outNodes.push(n)
    }
  }
  outNodes.push(...clusterNodes)

  const seen = new Set<string>()
  const outEdges: GraphEdgeModel[] = []
  for (const e of edges) {
    const s = idRemap.get(e.source) || e.source
    const t = idRemap.get(e.target) || e.target
    if (s === t) continue
    const key = `${s}\0${t}`
    if (seen.has(key)) continue
    seen.add(key)
    outEdges.push({ ...e, id: `${s}-${t}-${outEdges.length}`, source: s, target: t })
  }

  return { nodes: outNodes, edges: outEdges }
}

/** Drop weakest edges by relative weight (progressive disclosure). */
export function simplifyEdges(edges: GraphEdgeModel[], keepRatio: number): GraphEdgeModel[] {
  if (edges.length === 0 || keepRatio >= 1) return edges
  const sorted = [...edges].sort((a, b) => b.weight - a.weight)
  const n = Math.min(sorted.length, Math.max(1, Math.ceil(sorted.length * keepRatio)))
  return sorted.slice(0, n)
}
