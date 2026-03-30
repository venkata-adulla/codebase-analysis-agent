import type { GraphEdgeModel, GraphNodeModel } from './model'
import { layerPartition } from './layers'

export async function layoutWithElk(
  nodes: GraphNodeModel[],
  edges: GraphEdgeModel[]
): Promise<Map<string, { x: number; y: number }>> {
  if (nodes.length === 0) return new Map()

  const ELK = (await import('elkjs/lib/elk.bundled.js')).default
  const elk = new ELK()

  const elkNodes = nodes.map((n) => ({
    id: n.id,
    width: Math.max(80, n.width),
    height: Math.max(40, n.height),
    layoutOptions: {
      'elk.partitioning.partition': layerPartition(n.layer),
    },
  }))

  const elkEdges = edges.map((e) => ({
    id: e.id,
    sources: [e.source],
    targets: [e.target],
  }))

  const baseLayout = {
    'elk.algorithm': 'layered',
    'elk.direction': 'DOWN',
    'elk.spacing.nodeNode': '56',
    'elk.layered.spacing.nodeNodeBetweenLayers': '80',
    'elk.layered.spacing.edgeNodeBetweenLayers': '28',
    'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
    'elk.layered.crossingMinimization.strategy': 'LAYER_BY_LAYER',
    'elk.partitioning.activate': 'true',
  }

  let graph = {
    id: 'root',
    layoutOptions: baseLayout,
    children: elkNodes,
    edges: elkEdges,
  }

  let laidOut: Awaited<ReturnType<typeof elk.layout>>
  try {
    laidOut = await elk.layout(graph as Parameters<typeof elk.layout>[0])
  } catch {
    const plainChildren = nodes.map((n) => ({
      id: n.id,
      width: Math.max(80, n.width),
      height: Math.max(40, n.height),
    }))
    graph = {
      id: 'root',
      layoutOptions: {
        'elk.algorithm': 'layered',
        'elk.direction': 'DOWN',
        'elk.spacing.nodeNode': '48',
        'elk.layered.spacing.nodeNodeBetweenLayers': '64',
      },
      children: plainChildren,
      edges: elkEdges,
    }
    laidOut = await elk.layout(graph as Parameters<typeof elk.layout>[0])
  }
  const raw = new Map<string, { x: number; y: number }>()

  const visit = (n: { id?: string; x?: number; y?: number; children?: unknown[] }) => {
    if (n.id && typeof n.x === 'number' && typeof n.y === 'number') {
      raw.set(n.id, { x: n.x, y: n.y })
    }
    if (n.children && Array.isArray(n.children)) {
      for (const c of n.children) visit(c as { id?: string; x?: number; y?: number; children?: unknown[] })
    }
  }
  visit(laidOut as { id?: string; x?: number; y?: number; children?: unknown[] })

  let minX = Infinity
  let minY = Infinity
  for (const p of raw.values()) {
    minX = Math.min(minX, p.x)
    minY = Math.min(minY, p.y)
  }
  if (!Number.isFinite(minX)) return raw

  const pos = new Map<string, { x: number; y: number }>()
  const pad = 48
  for (const [id, p] of raw) {
    pos.set(id, { x: p.x - minX + pad, y: p.y - minY + pad })
  }
  return pos
}
