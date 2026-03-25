'use client'

import dagre from 'dagre'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  ReactFlowInstance,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { Network } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { repositoryDisplayName } from '@/lib/repository-display'
import { isLikelyUuid } from '@/lib/service-display'

const NODE_WIDTH = 180
const NODE_HEIGHT = 76
const ISOLATED_GRID_COLUMNS = 4
const ISOLATED_ROW_GAP = 110
const ISOLATED_COLUMN_GAP = 220
const STABLE_NODE_TYPES = Object.freeze({})
const STABLE_EDGE_TYPES = Object.freeze({})

type RawGraphNode = {
  id: string
  name?: string
  language?: string
  type?: string
  classification?: string
  entry_point_count?: number
  metadata?: Record<string, unknown>
}
type EdgeTooltipState = {
  x: number
  y: number
  source: string
  target: string
  type: string
  kind?: string
  original?: string
  via?: string[]
  depth?: number
}

function displayNodeName(
  node: Pick<RawGraphNode, 'id' | 'name'>,
  repositoryName?: string,
  repositoryId?: string
) {
  const raw = (node.name || '').trim()
  if (raw && !isLikelyUuid(raw)) return raw
  const repoLabel = repositoryDisplayName(repositoryName, repositoryId)
  return repoLabel ? `Repository root (${repoLabel})` : 'Repository root'
}

function normalizeLanguage(language?: string) {
  const value = (language || '').trim().toLowerCase()
  return value || 'unknown'
}

function displayClassification(value?: string) {
  const raw = (value || '').trim()
  if (!raw) return 'unknown'
  return raw.replace(/_/g, ' ')
}

function isPeripheralClassification(value?: string) {
  return ['example', 'test', 'documentation'].includes((value || '').trim().toLowerCase())
}

function isCoreClassification(value?: string) {
  return ['core_library', 'package_root', 'entrypoint'].includes((value || '').trim().toLowerCase())
}

function nodeStyle(language?: string, isIsolated?: boolean) {
  const normalized = normalizeLanguage(language)
  const palette: Record<string, { border: string; background: string; badge: string }> = {
    python: {
      border: 'hsl(200 75% 40%)',
      background: 'hsl(206 60% 13%)',
      badge: 'hsl(200 70% 55%)',
    },
    javascript: {
      border: 'hsl(48 90% 45%)',
      background: 'hsl(44 45% 12%)',
      badge: 'hsl(48 90% 55%)',
    },
    typescript: {
      border: 'hsl(215 75% 45%)',
      background: 'hsl(218 55% 13%)',
      badge: 'hsl(215 80% 60%)',
    },
    java: {
      border: 'hsl(12 70% 45%)',
      background: 'hsl(10 45% 12%)',
      badge: 'hsl(12 80% 60%)',
    },
    go: {
      border: 'hsl(188 70% 45%)',
      background: 'hsl(188 45% 12%)',
      badge: 'hsl(188 80% 60%)',
    },
    rust: {
      border: 'hsl(24 70% 45%)',
      background: 'hsl(20 45% 12%)',
      badge: 'hsl(24 85% 60%)',
    },
    unknown: {
      border: 'hsl(217 33% 22%)',
      background: 'hsl(222 47% 11%)',
      badge: 'hsl(220 10% 65%)',
    },
  }
  const colors = palette[normalized] || palette.unknown

  return {
    borderRadius: 10,
    border: `1px solid ${colors.border}`,
    background: colors.background,
    color: 'hsl(210 40% 98%)',
    fontSize: 12,
    padding: '10px 14px',
    width: NODE_WIDTH,
    minHeight: NODE_HEIGHT,
    boxShadow: isIsolated ? '0 0 0 1px rgba(255,255,255,0.03)' : '0 4px 16px rgba(0,0,0,0.18)',
    opacity: isIsolated ? 0.92 : 1,
  }
}

function edgeMetadata(edge: { metadata?: unknown }) {
  if (!edge.metadata) return {}
  if (typeof edge.metadata === 'string') {
    try {
      return JSON.parse(edge.metadata) as Record<string, unknown>
    } catch {
      return { raw: edge.metadata }
    }
  }
  if (typeof edge.metadata === 'object') return edge.metadata as Record<string, unknown>
  return { raw: String(edge.metadata) }
}

function layoutGraph(
  rawNodes: RawGraphNode[],
  rawEdges: Edge[],
  repositoryName?: string,
  repositoryId?: string
) {
  const graph = new dagre.graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  const useVerticalLayout = rawNodes.length > 10 || rawEdges.length > 18
  graph.setGraph({
    rankdir: useVerticalLayout ? 'TB' : 'LR',
    ranksep: useVerticalLayout ? 70 : 110,
    nodesep: useVerticalLayout ? 28 : 40,
    marginx: 24,
    marginy: 24,
  })

  const connectedIds = new Set<string>()
  rawEdges.forEach((edge) => {
    connectedIds.add(edge.source)
    connectedIds.add(edge.target)
  })

  const connectedNodes = rawNodes.filter((node) => connectedIds.has(node.id))
  const isolatedNodes = rawNodes.filter((node) => !connectedIds.has(node.id))

  connectedNodes.forEach((node) => {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  })

  rawEdges.forEach((edge) => {
    graph.setEdge(edge.source, edge.target)
  })

  dagre.layout(graph)

  const positionedConnected: Node[] = connectedNodes.map((node) => {
    const position = graph.node(node.id)
    const displayName = displayNodeName(node, repositoryName, repositoryId)
    return {
      id: node.id,
      data: {
        label: (
          <div className="space-y-1" title={`${displayName} (${normalizeLanguage(node.language)})`}>
            <div className="truncate font-medium">{displayName}</div>
            <div className="text-[10px] uppercase tracking-wide text-white/65">
              {normalizeLanguage(node.language)} · {displayClassification(node.classification)}
            </div>
            {Number(node.entry_point_count || 0) > 0 ? (
              <div className="text-[10px] text-emerald-300">{node.entry_point_count} entry point(s)</div>
            ) : null}
          </div>
        ),
      },
      sourcePosition: useVerticalLayout ? Position.Bottom : Position.Right,
      targetPosition: useVerticalLayout ? Position.Top : Position.Left,
      position: {
        x: (position?.x || 0) - NODE_WIDTH / 2,
        y: (position?.y || 0) - NODE_HEIGHT / 2,
      },
      style: nodeStyle(node.language, false),
    } satisfies Node
  })

  const maxConnectedY =
    positionedConnected.length > 0
      ? Math.max(...positionedConnected.map((node) => node.position.y + NODE_HEIGHT))
      : 0
  const isolatedStartY = maxConnectedY + 120

  const positionedIsolated: Node[] = isolatedNodes.map((node, index) => {
    const displayName = displayNodeName(node, repositoryName, repositoryId)
    return {
      id: node.id,
      data: {
        label: (
          <div className="space-y-1" title={`${displayName} (${normalizeLanguage(node.language)})`}>
            <div className="truncate font-medium">{displayName}</div>
            <div className="text-[10px] uppercase tracking-wide text-white/65">
              {normalizeLanguage(node.language)} · {displayClassification(node.classification)} · isolated
            </div>
            {Number(node.entry_point_count || 0) > 0 ? (
              <div className="text-[10px] text-emerald-300">{node.entry_point_count} entry point(s)</div>
            ) : null}
          </div>
        ),
      },
      sourcePosition: useVerticalLayout ? Position.Bottom : Position.Right,
      targetPosition: useVerticalLayout ? Position.Top : Position.Left,
      position: {
        x: (index % ISOLATED_GRID_COLUMNS) * ISOLATED_COLUMN_GAP,
        y: isolatedStartY + Math.floor(index / ISOLATED_GRID_COLUMNS) * ISOLATED_ROW_GAP,
      },
      style: nodeStyle(node.language, true),
    }
  })

  return [...positionedConnected, ...positionedIsolated]
}

export default function DependencyGraphPage() {
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const router = useRouter()
  const repoFromQuery = searchParams.get('repo') || ''
  const [manualRepo, setManualRepo] = useState('')

  useEffect(() => {
    setManualRepo(repoFromQuery)
  }, [repoFromQuery])

  /** Fix common mistake: /dependency-graph?=uuid instead of ?repo=uuid */
  useEffect(() => {
    if (typeof window === 'undefined') return
    const search = window.location.search
    if (search.startsWith('?=') && search.length > 2) {
      const id = decodeURIComponent(search.slice(2).split('&')[0])
      if (id) {
        router.replace(`${pathname}?repo=${encodeURIComponent(id)}`)
      }
    }
  }, [pathname, router])

  const repositoryId = repoFromQuery
  const graphContainerRef = useRef<HTMLDivElement | null>(null)
  const reactFlowRef = useRef<ReactFlowInstance | null>(null)
  const [edgeTooltip, setEdgeTooltip] = useState<EdgeTooltipState | null>(null)
  const [showIndirectEdges, setShowIndirectEdges] = useState(false)
  const [showOnlyConnected, setShowOnlyConnected] = useState(false)
  const [hidePeripheral, setHidePeripheral] = useState(true)
  const [showCoreOnly, setShowCoreOnly] = useState(false)
  const [showEdgeLabels, setShowEdgeLabels] = useState(false)

  const { data: graphData, isLoading, isError } = useQuery({
    queryKey: ['dependency-graph', repositoryId],
    queryFn: async () => {
      const response = await api.get('/dependencies/graph', {
        params: repositoryId ? { repository_id: repositoryId } : undefined,
      })
      return response.data
    },
  })

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const fitViewOptions = useMemo(() => ({ padding: 0.2 }), [])
  const filterStats = useMemo(() => {
    const rawNodes: RawGraphNode[] = Array.isArray(graphData?.nodes) ? graphData.nodes : []
    const rawEdges = Array.isArray(graphData?.edges) ? graphData.edges : []
    const peripheralCount = rawNodes.filter((node) => isPeripheralClassification(node.classification)).length
    const nonCoreCount = rawNodes.filter((node) => !isCoreClassification(node.classification)).length
    const linkedIds = new Set<string>()
    rawEdges.forEach((edge: { source?: string; target?: string }) => {
      if (edge.source) linkedIds.add(edge.source)
      if (edge.target) linkedIds.add(edge.target)
    })
    const isolatedCount = rawNodes.filter((node) => !linkedIds.has(node.id)).length
    return { peripheralCount, nonCoreCount, isolatedCount }
  }, [graphData])
  const filteredGraph = useMemo(() => {
    const rawNodes: RawGraphNode[] = Array.isArray(graphData?.nodes) ? graphData.nodes : []
    const directEdges = Array.isArray(graphData?.edges) ? graphData.edges : []
    const indirectEdges = Array.isArray(graphData?.indirect_edges) ? graphData.indirect_edges : []

    let candidateNodes = rawNodes.filter((node) => {
      if (showCoreOnly) return isCoreClassification(node.classification)
      if (hidePeripheral && isPeripheralClassification(node.classification)) return false
      return true
    })

    let candidateIds = new Set(candidateNodes.map((node) => node.id))
    let candidateDirectEdges = directEdges.filter(
      (edge: { source?: string; target?: string }) =>
        !!edge.source && !!edge.target && candidateIds.has(edge.source) && candidateIds.has(edge.target)
    )
    let candidateIndirectEdges = indirectEdges.filter(
      (edge: { source?: string; target?: string }) =>
        !!edge.source && !!edge.target && candidateIds.has(edge.source) && candidateIds.has(edge.target)
    )

    if (showOnlyConnected) {
      const linkedIds = new Set<string>()
      ;[...candidateDirectEdges, ...candidateIndirectEdges].forEach((edge: { source: string; target: string }) => {
        linkedIds.add(edge.source)
        linkedIds.add(edge.target)
      })
      candidateNodes = candidateNodes.filter((node) => linkedIds.has(node.id))
      candidateIds = new Set(candidateNodes.map((node) => node.id))
      candidateDirectEdges = candidateDirectEdges.filter(
        (edge: { source: string; target: string }) => candidateIds.has(edge.source) && candidateIds.has(edge.target)
      )
      candidateIndirectEdges = candidateIndirectEdges.filter(
        (edge: { source: string; target: string }) => candidateIds.has(edge.source) && candidateIds.has(edge.target)
      )
    }

    return {
      nodes: candidateNodes,
      edges: candidateDirectEdges,
      indirectEdges: candidateIndirectEdges,
    }
  }, [graphData, hidePeripheral, showCoreOnly, showOnlyConnected])
  const dependencySummary = useMemo(() => {
    const repoLabel = graphData?.repository_name
      ? repositoryDisplayName(graphData.repository_name, graphData.repository_id || repositoryId)
      : repositoryId || 'this repository'
    const rawNodes = filteredGraph.nodes
    const rawEdges = filteredGraph.edges
    const validEdges = rawEdges.filter(
      (edge: { source?: string; target?: string }) =>
        !!edge.source && !!edge.target && edge.source !== edge.target
    )
    const names = new Map(
      rawNodes.map((node) => [
        node.id,
        displayNodeName(node, graphData?.repository_name, graphData?.repository_id || repositoryId),
      ])
    )
    const linkedIds = new Set<string>()
    validEdges.forEach((edge: { source: string; target: string }) => {
      linkedIds.add(edge.source)
      linkedIds.add(edge.target)
    })
    const isolated = rawNodes
      .filter((node) => !linkedIds.has(node.id))
      .map((node) => displayNodeName(node, graphData?.repository_name, graphData?.repository_id || repositoryId))
      .slice(0, 6)
    const sampleLinks = validEdges.slice(0, 4).map((edge: { source: string; target: string; type?: string }) => {
      const source = names.get(edge.source) || edge.source
      const target = names.get(edge.target) || edge.target
      return `${source} -> ${target}${edge.type ? ` (${edge.type})` : ''}`
    })

    if (!rawNodes.length) {
      return {
        title: 'Repository Dependency Summary',
        lines: [`No services are visible for ${repoLabel} with the current filters. Adjust the graph filters or rerun analysis.`],
      }
    }

    const lines = [
      `${repoLabel} currently has ${rawNodes.length} detected service${rawNodes.length === 1 ? '' : 's'} and ${validEdges.length} dependency link${validEdges.length === 1 ? '' : 's'} in the graph.`,
    ]

    if (sampleLinks.length > 0) {
      lines.push(`Current links include ${sampleLinks.join('; ')}.`)
    } else {
      lines.push('No direct dependency links are currently stored, so the services shown are isolated from one another.')
    }

    if (isolated.length > 0) {
      lines.push(
        `Isolated services with no detected links include ${isolated.join(', ')}${rawNodes.length - linkedIds.size > isolated.length ? ', and others' : ''}.`
      )
    }

    return {
      title: 'Repository Dependency Summary',
      lines,
    }
  }, [filteredGraph, graphData, repositoryId])

  const architectureSummary = useMemo(() => {
    const summary = (graphData?.architecture_summary || {}) as Record<string, any>
    const counts = summary.classification_counts || {}
    const topClassifications = Object.entries(counts)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, 4)

    return {
      serviceCount: Number(summary.service_count || 0),
      directEdgeCount: Number(summary.direct_edge_count || 0),
      indirectEdgeCount: Number(summary.indirect_edge_count || 0),
      isolatedCount: Number(summary.isolated_count || 0),
      entryPointServiceCount: Number(summary.entry_point_service_count || 0),
      cycleCount: Number(summary.cycle_count || 0),
      topClassifications,
    }
  }, [graphData])

  useEffect(() => {
    if (!graphData?.nodes) {
      setNodes([])
      setEdges([])
      return
    }
    const rawNodes: RawGraphNode[] = filteredGraph.nodes
    const nodeIds = new Set(rawNodes.map((node: { id: string }) => node.id))

    const rawEdges = filteredGraph.edges
    const rawIndirectEdges = showIndirectEdges ? filteredGraph.indirectEdges : []
    const flowEdges: Edge[] = [...rawEdges, ...rawIndirectEdges]
      .filter(
        (edge: { source?: string; target?: string }) =>
          !!edge.source &&
          !!edge.target &&
          edge.source !== edge.target &&
          nodeIds.has(edge.source) &&
          nodeIds.has(edge.target)
      )
      .map((edge: { source: string; target: string; type?: string; metadata?: unknown; depth?: number; kind?: string }, i: number) => {
        const metadata = edgeMetadata(edge)
        const original = typeof metadata.original === 'string' ? metadata.original : undefined
        const kind = typeof metadata.kind === 'string' ? metadata.kind : edge.kind || 'direct'
        const via = Array.isArray(metadata.via) ? metadata.via.filter((item): item is string => typeof item === 'string') : []
        const depth = typeof edge.depth === 'number' ? edge.depth : typeof metadata.depth === 'number' ? metadata.depth : undefined
        const isIndirect = kind === 'indirect'
        return {
          id: `${edge.source}-${edge.target}-${i}`,
          source: edge.source,
          target: edge.target,
          type: 'smoothstep',
          animated: !isIndirect,
          label: showEdgeLabels && !isIndirect ? edge.type || '' : '',
          data: {
            source: edge.source,
            target: edge.target,
            type: edge.type || '',
            original,
            kind,
            via,
            depth,
          },
          labelBgPadding: [6, 3] as [number, number],
          labelBgBorderRadius: 6,
          labelBgStyle: { fill: 'hsl(222 47% 11% / 0.92)', color: 'white' },
          labelStyle: { fill: 'hsl(210 40% 98%)', fontSize: 10, fontWeight: 500 },
          style: isIndirect ? { strokeDasharray: '6 4', opacity: 0.45 } : undefined,
          markerEnd: { type: MarkerType.ArrowClosed },
        } satisfies Edge
      })
    const flowNodes = layoutGraph(
      rawNodes,
      flowEdges,
      graphData?.repository_name,
      graphData?.repository_id || repositoryId
    )

    setNodes(flowNodes)
    setEdges(flowEdges)
    if (reactFlowRef.current) {
      requestAnimationFrame(() => {
        reactFlowRef.current?.fitView(fitViewOptions)
      })
    }
  }, [filteredGraph, fitViewOptions, graphData, repositoryId, setNodes, setEdges, showEdgeLabels, showIndirectEdges])

  const applyRepo = () => {
    const id = manualRepo.trim()
    if (!id) {
      router.push(pathname)
      return
    }
    router.push(`${pathname}?repo=${encodeURIComponent(id)}`)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dependency graph"
        description={
          repositoryId
            ? `Filtered using ?repo= (repository id, service id, or clone-folder segment).`
            : 'Neo4j-backed graph. Use ?repo= with the analysis repository id, a service id, or a path segment — same rules as Service inventory.'
        }
      />

      <Card className="border-border/80 bg-card/50">
        <CardContent className="flex flex-wrap items-center gap-3 py-3 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Legend</span>
          {[
            ['python', 'bg-[hsl(200_70%_55%)]'],
            ['javascript', 'bg-[hsl(48_90%_55%)]'],
            ['typescript', 'bg-[hsl(215_80%_60%)]'],
            ['java', 'bg-[hsl(12_80%_60%)]'],
            ['unknown', 'bg-[hsl(220_10%_65%)]'],
          ].map(([label, swatch]) => (
            <span key={label} className="inline-flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${swatch}`} />
              {label}
            </span>
          ))}
          <span className="inline-flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full border border-dashed border-white/40" />
            isolated service
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-0.5 w-6 bg-white/60" />
            direct dependency
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="h-0.5 w-6 border-t border-dashed border-white/60" />
            indirect dependency
          </span>
          <span className="inline-flex items-center gap-2 text-emerald-300">
            entry point highlighted in node details
          </span>
        </CardContent>
      </Card>

      <Card className="border-border/80 bg-card/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Graph Filters</CardTitle>
          <CardDescription>
            Narrow the view to core library structure or only linked modules when the repository contains many
            examples, tests, or docs.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={hidePeripheral ? 'default' : 'outline'}
            size="sm"
            disabled={filterStats.peripheralCount === 0}
            onClick={() => setHidePeripheral((value) => !value)}
          >
            {hidePeripheral ? 'Showing core-focused view' : 'Show all classifications'} ({filterStats.peripheralCount} peripheral)
          </Button>
          <Button
            type="button"
            variant={showCoreOnly ? 'default' : 'outline'}
            size="sm"
            disabled={filterStats.nonCoreCount === 0}
            onClick={() => setShowCoreOnly((value) => !value)}
          >
            {showCoreOnly ? 'Core modules only' : 'Include non-core modules'} ({filterStats.nonCoreCount} non-core)
          </Button>
          <Button
            type="button"
            variant={showOnlyConnected ? 'default' : 'outline'}
            size="sm"
            disabled={filterStats.isolatedCount === 0}
            onClick={() => setShowOnlyConnected((value) => !value)}
          >
            {showOnlyConnected ? 'Connected nodes only' : 'Include isolated nodes'} ({filterStats.isolatedCount} isolated)
          </Button>
          <Button
            type="button"
            variant={showIndirectEdges ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowIndirectEdges((value) => !value)}
          >
            {showIndirectEdges ? 'Hide indirect edges' : 'Show indirect edges'}
          </Button>
          <Button
            type="button"
            variant={showEdgeLabels ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowEdgeLabels((value) => !value)}
          >
            {showEdgeLabels ? 'Hide edge labels' : 'Show edge labels'}
          </Button>
        </CardContent>
        <CardContent className="pt-0 text-xs text-muted-foreground">
          {filterStats.peripheralCount === 0 && filterStats.isolatedCount === 0
            ? 'This repository currently resolves almost entirely to connected core modules, so some filters will not visibly change the graph.'
            : 'Filter effects depend on the classifications and isolated nodes detected for the current repository.'}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-4">
        <Card className="border-border/80 bg-card/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Services</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{architectureSummary.serviceCount}</CardContent>
        </Card>
        <Card className="border-border/80 bg-card/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Direct / Indirect</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <span className="block text-2xl font-semibold text-foreground">
              {architectureSummary.directEdgeCount} / {architectureSummary.indirectEdgeCount}
            </span>
            relationship links
          </CardContent>
        </Card>
        <Card className="border-border/80 bg-card/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Entry Points</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{architectureSummary.entryPointServiceCount}</CardContent>
        </Card>
        <Card className="border-border/80 bg-card/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Cycles / Isolated</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <span className="block text-2xl font-semibold text-foreground">
              {architectureSummary.cycleCount} / {architectureSummary.isolatedCount}
            </span>
            architectural risk signals
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/80 bg-card/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Module Classification</CardTitle>
          <CardDescription>
            Modules are heuristically grouped so library-style repositories can show core code, entry surfaces,
            tests/examples/docs, and package roots more clearly.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {architectureSummary.topClassifications.length > 0 ? (
            architectureSummary.topClassifications.map(([label, count]) => (
              <Badge key={label} variant="secondary" className="capitalize">
                {displayClassification(label)}: {String(count)}
              </Badge>
            ))
          ) : (
            <span className="text-sm text-muted-foreground">No classification data loaded yet.</span>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/80 bg-card/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">{dependencySummary.title}</CardTitle>
          <CardDescription className="leading-relaxed">
            {dependencySummary.lines.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </CardDescription>
        </CardHeader>
      </Card>

      <Card className="border-border/80 bg-card/50">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-sm">Repository scope</CardTitle>
              <CardDescription>
                Paste the same id you use on Service inventory. The URL must be <code className="rounded bg-muted px-1 text-xs">?repo=…</code> — not{' '}
                <code className="rounded bg-muted px-1 text-xs">?=…</code>.
              </CardDescription>
            </div>
            <span className="text-xs text-muted-foreground">
              Dense graphs default to direct edges only and hide labels until you enable them above.
            </span>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-2">
            <Label htmlFor="graph-repo">Filter by repository / token</Label>
            <Input
              id="graph-repo"
              value={manualRepo}
              onChange={(e) => setManualRepo(e.target.value)}
              placeholder="Repository UUID or service id"
            />
          </div>
          <Button type="button" onClick={applyRepo}>
            Apply
          </Button>
        </CardContent>
      </Card>

      {graphData?.graph_source && graphData.graph_source !== 'neo4j' && (
        <Card className="border-amber-500/35 bg-amber-500/[0.06]">
          <CardContent className="py-3 text-sm leading-relaxed text-muted-foreground">
            {graphData.graph_source === 'postgres_services' && (
              <p>{graphData.graph_note ? String(graphData.graph_note) : 'Services loaded from the database (Neo4j had no graph for this repo).'}</p>
            )}
            {graphData.graph_source === 'neo4j_unavailable' && (
              <p>
                Neo4j could not be reached; the API tried a database fallback.{' '}
                {graphData.graph_note ? (
                  <span className="opacity-80">({String(graphData.graph_note).slice(0, 200)})</span>
                ) : null}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="overflow-hidden border-border/80">
        <CardHeader className="border-b border-border/80 bg-card/50 pb-4">
          <div className="flex items-center gap-2">
            <Network className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-base">Topology</CardTitle>
              <CardDescription>
                Pan, zoom, and inspect nodes. The layout is directional, so upstream services appear to the left and
                their dependents flow to the right when Neo4j edges are available.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex h-[420px] items-center justify-center text-sm text-muted-foreground">
              Loading graph…
            </div>
          ) : isError ? (
            <div className="flex h-[420px] items-center justify-center px-6 text-center text-sm text-muted-foreground">
              Could not load the graph. Check that the API is running.
            </div>
          ) : nodes.length === 0 ? (
            <div className="flex h-[min(70vh,640px)] min-h-[420px] items-center justify-center px-6 text-center text-sm text-muted-foreground">
              No services found for this repository. Run a full analysis and confirm rows appear under Service inventory.
              When Neo4j is configured, dependency edges show here; otherwise only persisted services can appear as
              isolated nodes.
            </div>
          ) : (
            <div ref={graphContainerRef} className="relative h-[min(72vh,760px)] min-h-[420px] w-full bg-muted/20">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onInit={(instance) => {
                  reactFlowRef.current = instance
                  instance.fitView(fitViewOptions)
                }}
                nodeTypes={STABLE_NODE_TYPES}
                edgeTypes={STABLE_EDGE_TYPES}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                fitView
                fitViewOptions={fitViewOptions}
                nodesConnectable={false}
                nodesDraggable={true}
                elementsSelectable
                onEdgeMouseEnter={(event, edge) => {
                  if (!graphContainerRef.current) return
                  const rect = graphContainerRef.current.getBoundingClientRect()
                  const payload = (edge.data || {}) as Record<string, unknown>
                  setEdgeTooltip({
                    x: event.clientX - rect.left + 12,
                    y: event.clientY - rect.top + 12,
                    source: payload.source || edge.source,
                    target: payload.target || edge.target,
                    type: payload.type || String(edge.label || ''),
                    original: payload.original,
                    kind: payload.kind,
                    via: Array.isArray(payload.via) ? payload.via : undefined,
                    depth: typeof payload.depth === 'number' ? payload.depth : undefined,
                  })
                }}
                onEdgeMouseMove={(event, edge) => {
                  if (!graphContainerRef.current) return
                  const rect = graphContainerRef.current.getBoundingClientRect()
                  const payload = (edge.data || {}) as Record<string, unknown>
                  setEdgeTooltip({
                    x: event.clientX - rect.left + 12,
                    y: event.clientY - rect.top + 12,
                    source: payload.source || edge.source,
                    target: payload.target || edge.target,
                    type: payload.type || String(edge.label || ''),
                    original: payload.original,
                    kind: payload.kind,
                    via: Array.isArray(payload.via) ? payload.via : undefined,
                    depth: typeof payload.depth === 'number' ? payload.depth : undefined,
                  })
                }}
                onEdgeMouseLeave={() => setEdgeTooltip(null)}
                className="bg-transparent"
              >
                <Background gap={20} size={1} color="hsl(217 33% 22%)" />
                <Controls className="!m-3 !rounded-lg !border-border !bg-card !shadow-lg" />
                <MiniMap
                  className="!m-3 !rounded-lg !border-border !bg-card"
                  maskColor="hsl(222 47% 6% / 0.7)"
                />
              </ReactFlow>
              {edgeTooltip ? (
                <div
                  className="pointer-events-none absolute z-10 max-w-xs rounded-lg border border-border/80 bg-card/95 px-3 py-2 text-xs shadow-xl"
                  style={{ left: edgeTooltip.x, top: edgeTooltip.y }}
                >
                  <div className="font-medium text-foreground">{edgeTooltip.type || 'dependency'}</div>
                  <div className="mt-1 text-muted-foreground">
                    <span className="text-foreground">{edgeTooltip.source}</span>
                    <span className="px-1">&rarr;</span>
                    <span className="text-foreground">{edgeTooltip.target}</span>
                  </div>
                  {edgeTooltip.kind === 'indirect' && edgeTooltip.depth ? (
                    <div className="mt-1 text-muted-foreground">Indirect path depth: {edgeTooltip.depth}</div>
                  ) : null}
                  {edgeTooltip.via && edgeTooltip.via.length > 0 ? (
                    <div className="mt-1 text-muted-foreground">
                      via <span className="text-foreground">{edgeTooltip.via.join(' -> ')}</span>
                    </div>
                  ) : null}
                  {edgeTooltip.original ? (
                    <div className="mt-1 break-all text-muted-foreground">
                      from <span className="text-foreground">{edgeTooltip.original}</span>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
