/** Enterprise dependency graph domain model (service → module → file). */

export type GraphLayer = 'api' | 'core' | 'utils'

export type GraphNodeKind = 'service' | 'module' | 'file' | 'cluster'

export interface GraphNodeModel {
  id: string
  label: string
  kind: GraphNodeKind
  layer: GraphLayer
  dependencyCount: number
  dependentsCount: number
  riskScore: number
  summary?: string
  /** Package / cluster key for grouping (e.g. "click"). */
  packageKey: string
  /** Member service ids when this is a collapsed cluster. */
  memberIds?: string[]
  language?: string
  classification?: string
  width: number
  height: number
}

export interface GraphEdgeModel {
  id: string
  source: string
  target: string
  weight: number
  type: string
  kind?: string
}

export type ViewLevel = 'service' | 'module' | 'file'

export interface RawApiNode {
  id: string
  name?: string
  language?: string
  classification?: string
  entry_point_count?: number
  metadata?: Record<string, unknown>
}

export interface RawApiEdge {
  source?: string
  target?: string
  type?: string
  kind?: string
  metadata?: unknown
}

export interface ServiceEnrichment {
  id: string
  summary?: string | null
  description?: string | null
}
