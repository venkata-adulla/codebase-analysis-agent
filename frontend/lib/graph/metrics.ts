import type { GraphEdgeModel, GraphNodeModel } from './model'

export function computeDegrees(
  nodeIds: string[],
  edges: Pick<GraphEdgeModel, 'source' | 'target'>[]
) {
  const outD = new Map<string, number>()
  const inD = new Map<string, number>()
  for (const id of nodeIds) {
    outD.set(id, 0)
    inD.set(id, 0)
  }
  for (const e of edges) {
    if (!outD.has(e.source)) outD.set(e.source, 0)
    if (!inD.has(e.target)) inD.set(e.target, 0)
    outD.set(e.source, (outD.get(e.source) || 0) + 1)
    inD.set(e.target, (inD.get(e.target) || 0) + 1)
  }
  return { outD, inD }
}

export function riskScoreForNode(
  id: string,
  outD: Map<string, number>,
  inD: Map<string, number>,
  maxDeg: number
): number {
  const o = outD.get(id) || 0
  const i = inD.get(id) || 0
  const t = o + i
  const norm = maxDeg > 0 ? t / maxDeg : 0
  return Math.min(100, Math.round(30 + norm * 70))
}

export function edgeWeight(
  outDegSource: number,
  inDegTarget: number,
  maxDeg: number
): number {
  const base = 1 + (outDegSource + inDegTarget) / Math.max(1, maxDeg * 2)
  return Math.round(base * 100) / 100
}

export function nodeSizeFromDegree(totalDegree: number, maxDeg: number) {
  const t = maxDeg > 0 ? totalDegree / maxDeg : 0
  const w = 168 + Math.min(72, Math.round(t * 72))
  const h = 52 + Math.min(28, Math.round(t * 28))
  return { width: w, height: h }
}

export function couplingColor(totalDegree: number, maxDeg: number): string {
  if (maxDeg <= 0) return 'hsl(142 45% 42%)'
  const t = totalDegree / maxDeg
  if (t < 0.33) return 'hsl(142 48% 40%)'
  if (t < 0.66) return 'hsl(48 90% 48%)'
  return 'hsl(0 72% 52%)'
}
