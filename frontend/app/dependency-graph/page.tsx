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
import { repositoryDisplayName } from '@/lib/repository-display'
import { isLikelyUuid } from '@/lib/service-display'

const NODE_WIDTH = 180
const NODE_HEIGHT = 72
const ISOLATED_GRID_COLUMNS = 4
const ISOLATED_ROW_GAP = 110
const ISOLATED_COLUMN_GAP = 220

type RawGraphNode = { id: string; name?: string; language?: string; type?: string }
type EdgeTooltipState = {
  x: number
  y: number
  source: string
  target: string
  type: string
  original?: string
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
  graph.setGraph({
    rankdir: 'LR',
    ranksep: 110,
    nodesep: 40,
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
            <div className="text-[10px] uppercase tracking-wide text-white/65">{normalizeLanguage(node.language)}</div>
          </div>
        ),
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
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
              {normalizeLanguage(node.language)} · isolated
            </div>
          </div>
        ),
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
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
  const [edgeTooltip, setEdgeTooltip] = useState<EdgeTooltipState | null>(null)

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
  const dependencySummary = useMemo(() => {
    const repoLabel = graphData?.repository_name
      ? repositoryDisplayName(graphData.repository_name, graphData.repository_id || repositoryId)
      : repositoryId || 'this repository'
    const rawNodes: RawGraphNode[] = Array.isArray(graphData?.nodes) ? graphData.nodes : []
    const rawEdges = Array.isArray(graphData?.edges) ? graphData.edges : []
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
        lines: [`No services are loaded yet for ${repoLabel}. Run or refresh an analysis to populate this view.`],
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
  }, [graphData, repositoryId])

  useEffect(() => {
    if (!graphData?.nodes) {
      setNodes([])
      setEdges([])
      return
    }
    const rawNodes: RawGraphNode[] = Array.isArray(graphData.nodes) ? graphData.nodes : []
    const nodeIds = new Set(rawNodes.map((node: { id: string }) => node.id))

    const rawEdges = Array.isArray(graphData.edges) ? graphData.edges : []
    const flowEdges: Edge[] = rawEdges
      .filter(
        (edge: { source?: string; target?: string }) =>
          !!edge.source &&
          !!edge.target &&
          edge.source !== edge.target &&
          nodeIds.has(edge.source) &&
          nodeIds.has(edge.target)
      )
      .map((edge: { source: string; target: string; type?: string; metadata?: unknown }, i: number) => {
        const metadata = edgeMetadata(edge)
        const original = typeof metadata.original === 'string' ? metadata.original : undefined
        return {
          id: `${edge.source}-${edge.target}-${i}`,
          source: edge.source,
          target: edge.target,
          type: 'smoothstep',
          animated: true,
          label: edge.type || '',
          data: {
            source: edge.source,
            target: edge.target,
            type: edge.type || '',
            original,
          },
          labelBgPadding: [6, 3] as [number, number],
          labelBgBorderRadius: 6,
          labelBgStyle: { fill: 'hsl(222 47% 11% / 0.92)', color: 'white' },
          labelStyle: { fill: 'hsl(210 40% 98%)', fontSize: 10, fontWeight: 500 },
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
  }, [graphData, setNodes, setEdges])

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
          <CardTitle className="text-sm">Repository scope</CardTitle>
          <CardDescription>
            Paste the same id you use on Service inventory. The URL must be <code className="rounded bg-muted px-1 text-xs">?repo=…</code> — not{' '}
            <code className="rounded bg-muted px-1 text-xs">?=…</code>.
          </CardDescription>
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
                  const payload = (edge.data || {}) as Record<string, string | undefined>
                  setEdgeTooltip({
                    x: event.clientX - rect.left + 12,
                    y: event.clientY - rect.top + 12,
                    source: payload.source || edge.source,
                    target: payload.target || edge.target,
                    type: payload.type || String(edge.label || ''),
                    original: payload.original,
                  })
                }}
                onEdgeMouseMove={(event, edge) => {
                  if (!graphContainerRef.current) return
                  const rect = graphContainerRef.current.getBoundingClientRect()
                  const payload = (edge.data || {}) as Record<string, string | undefined>
                  setEdgeTooltip({
                    x: event.clientX - rect.left + 12,
                    y: event.clientY - rect.top + 12,
                    source: payload.source || edge.source,
                    target: payload.target || edge.target,
                    type: payload.type || String(edge.label || ''),
                    original: payload.original,
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
