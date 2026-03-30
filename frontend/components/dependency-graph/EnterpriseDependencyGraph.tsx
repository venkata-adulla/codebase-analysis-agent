'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  MarkerType,
  type Edge,
  type Node,
  type ReactFlowInstance,
  useEdgesState,
  useNodesState,
  ReactFlowProvider,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { Sparkles } from 'lucide-react'
import { ExportMenu } from '@/components/export/ExportMenu'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { GraphSidebar } from './GraphSidebar'
import { GraphInsightsPanel } from './GraphInsightsPanel'
import { GraphFlowNode } from './GraphFlowNode'
import { collapseByPackage, mapRawToEdges, mapRawToServiceNodes, simplifyEdges } from '@/lib/graph/clustering'
import { layoutWithElk } from '@/lib/graph/elk-layout'
import { focusNeighborIds } from '@/lib/graph/focus'
import { couplingColor } from '@/lib/graph/metrics'
import type { GraphEdgeModel, GraphNodeModel, RawApiEdge, RawApiNode, ViewLevel } from '@/lib/graph/model'
import { useGraphExplorerStore } from '@/stores/graph-explorer-store'
import { useTemporalHeatmapStore } from '@/stores/temporal-heatmap-store'

const MAX_LAYOUT_NODES = 450
const NODE_TYPES = { graph: GraphFlowNode }

function applyDrillModule(
  drillId: string | null,
  viewLevel: ViewLevel,
  nodes: GraphNodeModel[],
  edges: GraphEdgeModel[]
) {
  if (!drillId || viewLevel !== 'module') return { nodes, edges }
  const center = nodes.find((n) => n.id === drillId)
  if (!center) return { nodes, edges }
  const pk = center.packageKey
  const keep = new Set<string>()
  for (const n of nodes) {
    if (n.packageKey === pk) keep.add(n.id)
  }
  for (const e of edges) {
    if (e.source === drillId || e.target === drillId) {
      keep.add(e.source)
      keep.add(e.target)
    }
  }
  const nn = nodes.filter((n) => keep.has(n.id))
  const ids = new Set(nn.map((n) => n.id))
  const ee = edges.filter((e) => ids.has(e.source) && ids.has(e.target))
  return { nodes: nn, edges: ee }
}

function applyFocus(
  enabled: boolean,
  selectedId: string | null,
  nodes: GraphNodeModel[],
  edges: GraphEdgeModel[]
) {
  if (!enabled || !selectedId) return { nodes, edges }
  const f = focusNeighborIds(selectedId, edges)
  const nn = nodes.filter((n) => f.has(n.id))
  const ids = new Set(nn.map((n) => n.id))
  const ee = edges.filter((e) => ids.has(e.source) && ids.has(e.target))
  return { nodes: nn, edges: ee }
}

function capNodesByDegree(nodes: GraphNodeModel[], edges: GraphEdgeModel[], max: number) {
  if (nodes.length <= max) return { nodes, edges, capped: false as const }
  const deg = new Map<string, number>()
  for (const n of nodes) deg.set(n.id, 0)
  for (const e of edges) {
    deg.set(e.source, (deg.get(e.source) || 0) + 1)
    deg.set(e.target, (deg.get(e.target) || 0) + 1)
  }
  const ranked = [...nodes].sort((a, b) => (deg.get(b.id) || 0) - (deg.get(a.id) || 0))
  const keep = new Set(ranked.slice(0, max).map((n) => n.id))
  const nn = nodes.filter((n) => keep.has(n.id))
  const ee = edges.filter((e) => keep.has(e.source) && keep.has(e.target))
  return { nodes: nn, edges: ee, capped: true as const }
}

function InnerGraph() {
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const router = useRouter()
  const repoFromQuery = searchParams.get('repo') || ''
  const focusFromQuery = searchParams.get('focus') || ''
  const [manualRepo, setManualRepo] = useState('')
  const [listSearch, setListSearch] = useState('')
  const [explainOpen, setExplainOpen] = useState(false)
  const [clustering, setClustering] = useState(true)
  const layoutStarted = useRef(0)
  const rfInstance = useRef<ReactFlowInstance | null>(null)
  const graphExportRef = useRef<HTMLDivElement>(null)

  const {
    selectedNodeId,
    setSelected,
    focusMode,
    setFocusMode,
    simplifiedView,
    setSimplifiedView,
    expandedPackageKeys,
    togglePackageExpanded,
    viewLevel,
    setViewLevel,
    drillServiceId,
    setDrillServiceId,
    hoveredNodeId,
    setHoveredNodeId,
  } = useGraphExplorerStore()

  const temporalRepo = useTemporalHeatmapStore((s) => s.repoId)
  const temporalActive = useTemporalHeatmapStore((s) => s.active)
  const temporalById = useTemporalHeatmapStore((s) => s.byServiceId)

  useEffect(() => {
    setManualRepo(repoFromQuery)
  }, [repoFromQuery])

  const repositoryId = repoFromQuery

  useEffect(() => {
    if (!focusFromQuery || !repositoryId) return
    setSelected(focusFromQuery)
    setFocusMode(true)
  }, [focusFromQuery, repositoryId, setSelected, setFocusMode])

  const { data: graphData, isLoading, isError } = useQuery({
    queryKey: ['dependency-graph-v2', repositoryId],
    queryFn: async () => {
      const qs = repositoryId ? `?repository_id=${encodeURIComponent(repositoryId)}` : ''
      const apiKey = process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'
      const res = await fetch(`/api/dependencies/graph${qs}`, {
        headers: { Accept: 'application/json', 'X-API-Key': apiKey },
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    enabled: !!repositoryId,
    staleTime: 5 * 60 * 1000,
  })

  const { data: servicesData } = useQuery({
    queryKey: ['services-enrichment', repositoryId],
    enabled: !!repositoryId,
    queryFn: async () => {
      const apiKey = process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'
      const res = await fetch(
        `/api/services/?repository_id=${encodeURIComponent(repositoryId)}`,
        {
          headers: { Accept: 'application/json', 'X-API-Key': apiKey },
        }
      )
      if (!res.ok) return { services: [] }
      return res.json()
    },
    staleTime: 5 * 60 * 1000,
  })

  const enrichment = useMemo(() => {
    const m = new Map<string, { summary?: string | null }>()
    const rows = Array.isArray(servicesData?.services) ? servicesData.services : []
    for (const s of rows) {
      if (s?.id) m.set(s.id, { summary: s.summary })
    }
    return m
  }, [servicesData])

  const rawNodes: RawApiNode[] = Array.isArray(graphData?.nodes) ? graphData.nodes : []
  const rawEdges: RawApiEdge[] = Array.isArray(graphData?.edges) ? graphData.edges : []

  const baseGraph = useMemo(() => {
    const repoName = graphData?.repository_name
    const repoId = graphData?.repository_id || repositoryId
    const nodes = mapRawToServiceNodes(rawNodes, rawEdges, enrichment, repoName, repoId)
    const ids = new Set(nodes.map((n) => n.id))
    let edges = mapRawToEdges(rawEdges, ids)
    return { nodes, edges }
  }, [graphData, rawNodes, rawEdges, enrichment, repositoryId])

  const processed = useMemo(() => {
    let { nodes, edges } = baseGraph
    const expanded = new Set(expandedPackageKeys)
    if (clustering) {
      const c = collapseByPackage(nodes, edges, expanded)
      nodes = c.nodes
      edges = c.edges
    }
    if (simplifiedView) {
      edges = simplifyEdges(edges, 0.65)
    }
    const drilled = applyDrillModule(drillServiceId, viewLevel, nodes, edges)
    nodes = drilled.nodes
    edges = drilled.edges
    const focused = applyFocus(focusMode, selectedNodeId, nodes, edges)
    nodes = focused.nodes
    edges = focused.edges
    return capNodesByDegree(nodes, edges, MAX_LAYOUT_NODES)
  }, [
    baseGraph,
    clustering,
    simplifiedView,
    expandedPackageKeys,
    drillServiceId,
    viewLevel,
    focusMode,
    selectedNodeId,
  ])

  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map())
  const layoutKey = useMemo(
    () =>
      JSON.stringify({
        n: processed.nodes.map((x) => x.id),
        e: processed.edges.map((x) => [x.source, x.target]),
      }),
    [processed.nodes, processed.edges]
  )

  useEffect(() => {
    let cancelled = false
    if (processed.nodes.length === 0) {
      setPositions(new Map())
      return
    }
    layoutStarted.current = performance.now()
    ;(async () => {
      try {
        const pos = await layoutWithElk(processed.nodes, processed.edges)
        if (!cancelled) {
          setPositions(pos)
          const ms = Math.round(performance.now() - layoutStarted.current)
          // eslint-disable-next-line no-console
          console.info(
            '[DependencyGraph] ELK layout',
            { nodes: processed.nodes.length, edges: processed.edges.length, ms },
            `render-ready positions: ${pos.size}`
          )
        }
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error('[DependencyGraph] ELK layout failed', e)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [layoutKey, processed.nodes, processed.edges])

  const maxDeg = useMemo(() => {
    let m = 1
    for (const n of processed.nodes) {
      m = Math.max(m, n.dependencyCount + n.dependentsCount)
    }
    return m
  }, [processed.nodes])

  const modelById = useMemo(() => new Map(processed.nodes.map((n) => [n.id, n])), [processed.nodes])

  const churnById = useMemo(() => {
    if (!temporalActive || temporalRepo !== repositoryId) return {} as Record<string, number>
    return temporalById
  }, [temporalActive, temporalRepo, repositoryId, temporalById])

  const rfNodes: Node[] = useMemo(() => {
    const nodes = processed.nodes.map((n) => {
      const p = positions.get(n.id) ?? { x: 0, y: 0 }
      const dim =
        !!hoveredNodeId &&
        hoveredNodeId !== n.id &&
        !processed.edges.some(
          (e) =>
            (e.source === hoveredNodeId && e.target === n.id) ||
            (e.target === hoveredNodeId && e.source === n.id)
        )
      const hl = hoveredNodeId === n.id
      return {
        id: n.id,
        type: 'graph',
        selected: selectedNodeId === n.id,
        position: { x: p.x, y: p.y },
        data: {
          model: n,
          maxDeg,
          dimmed: !!hoveredNodeId && dim,
          highlighted: hl,
          churnIntensity: churnById[n.id],
        },
      } satisfies Node
    })
    return nodes
  }, [processed.nodes, positions, maxDeg, hoveredNodeId, processed.edges, selectedNodeId, churnById])

  const rfEdges: Edge[] = useMemo(() => {
    return processed.edges.map((e, i) => {
      const sw = 1 + Math.min(3, e.weight * 1.2)
      const src = modelById.get(e.source)
      const deg = src ? src.dependencyCount + src.dependentsCount : 0
      const baseStroke = couplingColor(deg, maxDeg)
      const touchesHover =
        hoveredNodeId && (e.source === hoveredNodeId || e.target === hoveredNodeId)
      const stroke = touchesHover ? 'hsl(210 85% 62%)' : baseStroke
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: 'default',
        pathOptions: { curvature: 0.22 + (i % 5) * 0.02 },
        animated: false,
        style: {
          stroke,
          strokeWidth: sw,
          opacity: hoveredNodeId ? (touchesHover ? 1 : 0.1) : 0.9,
        },
        markerEnd: { type: MarkerType.ArrowClosed, width: 8, height: 8, color: stroke },
        data: { weight: e.weight },
      } satisfies Edge
    })
  }, [processed.edges, hoveredNodeId, modelById, maxDeg])

  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges)

  useEffect(() => {
    setNodes(rfNodes)
  }, [rfNodes, setNodes])

  useEffect(() => {
    setEdges(rfEdges)
  }, [rfEdges, setEdges])

  useEffect(() => {
    if (rfNodes.length > 0 && rfInstance.current) {
      requestAnimationFrame(() => rfInstance.current?.fitView({ padding: 0.15, duration: 200 }))
    }
  }, [layoutKey, rfNodes.length])

  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      setSelected(node.id === selectedNodeId ? null : node.id)
    },
    [selectedNodeId, setSelected]
  )

  const onNodeDoubleClick = useCallback(
    (_: unknown, node: Node) => {
      const m = modelById.get(node.id)
      if (!m) return
      if (m.kind === 'cluster' && m.packageKey) {
        togglePackageExpanded(m.packageKey)
        return
      }
      setDrillServiceId(m.id)
      setViewLevel('module')
    },
    [modelById, setDrillServiceId, setViewLevel, togglePackageExpanded]
  )

  const selectedModel = selectedNodeId ? modelById.get(selectedNodeId) ?? null : null

  const applyRepo = () => {
    const id = manualRepo.trim()
    if (!id) router.push(pathname)
    else router.push(`${pathname}?repo=${encodeURIComponent(id)}`)
  }

  const explainText = useMemo(() => {
    const arch = (graphData?.architecture_summary || {}) as Record<string, unknown>
    const cycles = arch.cycle_count
    const svc = arch.service_count
    return [
      `Services discovered: ${svc ?? '—'}.`,
      typeof cycles === 'number' ? `Cycle count (approx.): ${cycles}.` : null,
      'Green / yellow / red nodes reflect relative coupling in the current view.',
      'Use simplified mode to hide weaker edges; expand package clusters to drill into modules.',
    ]
      .filter(Boolean)
      .join(' ')
  }, [graphData])

  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col gap-4">
      <PageHeader
        title="Dependency graph"
        description="Service-level map with ELK layering (API → core → utils). Expand clusters and drill modules on demand."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ExportMenu
              analysisType="dependency_graph"
              pageTitle="Dependency graph"
              pageSlug="dependency-graph"
              repoId={repositoryId || undefined}
              repoName={(graphData?.repository_name as string | undefined) || undefined}
              captureRef={graphExportRef}
              getJsonData={() => ({
                analysisType: 'dependency_graph',
                repoId: repositoryId,
                repository_name: graphData?.repository_name,
                repository_id: graphData?.repository_id ?? repositoryId,
                filters: {
                  viewLevel,
                  focusMode,
                  simplifiedView,
                  clustering,
                  drillServiceId,
                  expandedPackageKeys,
                },
                architecture_summary: graphData?.architecture_summary,
                stats: {
                  node_count: processed.nodes.length,
                  edge_count: processed.edges.length,
                  capped: 'capped' in processed ? processed.capped : false,
                },
                nodes: processed.nodes.map((n) => ({
                  id: n.id,
                  label: n.label,
                  kind: n.kind,
                  layer: n.layer,
                  packageKey: n.packageKey,
                  dependencyCount: n.dependencyCount,
                  dependentsCount: n.dependentsCount,
                  riskScore: n.riskScore,
                })),
                edges: processed.edges.map((e) => ({
                  source: e.source,
                  target: e.target,
                  weight: e.weight,
                  type: e.type,
                })),
              })}
              getCsvSections={() => [
                {
                  name: 'Visible graph nodes',
                  headers: [
                    'id',
                    'label',
                    'kind',
                    'layer',
                    'packageKey',
                    'dependencies',
                    'dependents',
                    'risk',
                  ],
                  rows: processed.nodes.map((n) => [
                    n.id,
                    n.label,
                    n.kind,
                    n.layer,
                    n.packageKey,
                    n.dependencyCount,
                    n.dependentsCount,
                    n.riskScore,
                  ]),
                },
                {
                  name: 'Visible edges',
                  headers: ['source', 'target', 'weight', 'type'],
                  rows: processed.edges.map((e) => [e.source, e.target, e.weight, e.type]),
                },
              ]}
              getPdfSections={() => [
                { heading: 'Summary', body: explainText },
                {
                  heading: 'Scale',
                  body: `Visible nodes: ${processed.nodes.length}. Visible edges: ${processed.edges.length}.`,
                },
              ]}
            />
            <Button type="button" variant="outline" size="sm" onClick={() => setExplainOpen(true)}>
              <Sparkles className="mr-1 h-4 w-4" />
              Explain this graph
            </Button>
          </div>
        }
      />

      {processed.capped ? (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          Showing top {MAX_LAYOUT_NODES} highest-degree services for layout performance. Narrow filters or scope.
        </p>
      ) : null}

      <div className="flex min-h-[640px] flex-1 overflow-hidden rounded-xl border border-border/80 bg-card/30">
        <GraphSidebar
          manualRepo={manualRepo}
          onManualRepoChange={setManualRepo}
          onApplyRepo={applyRepo}
          simplifiedView={simplifiedView}
          onSimplifiedView={setSimplifiedView}
          focusMode={focusMode}
          onFocusMode={setFocusMode}
          clustering={clustering}
          onClustering={setClustering}
          nodes={baseGraph.nodes}
          selectedId={selectedNodeId}
          onSelectNode={setSelected}
          search={listSearch}
          onSearch={setListSearch}
        />

        <div
          ref={graphExportRef}
          className="relative min-h-[560px] min-w-0 flex-1 bg-[hsl(222_47%_6%)] [background-image:radial-gradient(circle_at_1px_1px,hsl(215_25%_28%/0.35)_1px,transparent_0)] [background-size:22px_22px]"
        >
          {isLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading graph…</div>
          ) : isError ? (
            <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
              Could not load graph. Is the API running?
            </div>
          ) : nodes.length === 0 ? (
            <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
              No dependency data. Run an analysis with Neo4j-backed dependencies or use a repository with services.
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              onInit={(inst) => {
                rfInstance.current = inst
                inst.fitView({ padding: 0.15 })
              }}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              onNodeDoubleClick={onNodeDoubleClick}
              onNodeMouseEnter={(_, n) => setHoveredNodeId(n.id)}
              onNodeMouseLeave={() => setHoveredNodeId(null)}
              minZoom={0.08}
              maxZoom={1.8}
              onlyRenderVisibleElements
              proOptions={{ hideAttribution: true }}
              className="h-full"
            >
              <MiniMap
                className="!bg-card/90 !border-border"
                zoomable
                pannable
                maskColor="hsl(222 47% 6% / 0.5)"
              />
              <Controls className="!bg-card/95 !border-border !shadow-lg" />
              <Background gap={22} size={1} color="hsl(215 25% 28% / 0.4)" />
            </ReactFlow>
          )}
        </div>

        <GraphInsightsPanel
          node={selectedModel}
          architectureSummary={graphData?.architecture_summary as Record<string, unknown> | undefined}
        />
      </div>

      {explainOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm"
          role="dialog"
        >
          <div className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-xl border border-border bg-card p-6 shadow-2xl">
            <h3 className="text-lg font-semibold">Graph explanation</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{explainText}</p>
            <Button type="button" className="mt-6" onClick={() => setExplainOpen(false)}>
              Close
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        <span className="rounded-md border border-border/60 bg-muted/20 px-2 py-1">
          <span className="mr-2 text-muted-foreground">Level:</span>
          {(['service', 'module'] as const).map((lvl) => (
            <button
              key={lvl}
              type="button"
              className={`mr-1 rounded px-1.5 py-0.5 capitalize ${
                viewLevel === lvl ? 'bg-primary text-primary-foreground' : 'hover:bg-muted/50'
              }`}
              onClick={() => setViewLevel(lvl)}
            >
              {lvl}
            </button>
          ))}
          <button type="button" disabled className="cursor-not-allowed rounded px-1.5 py-0.5 opacity-50" title="Lazy load">
            file
          </button>
        </span>
        <span>
          View: <strong className="text-foreground">{viewLevel}</strong>
          {drillServiceId ? (
            <button
              type="button"
              className="ml-2 text-primary underline"
              onClick={() => {
                setDrillServiceId(null)
                setViewLevel('service')
              }}
            >
              Reset drill
            </button>
          ) : null}
        </span>
        <span>
          Nodes: <strong className="text-foreground">{processed.nodes.length}</strong> · Edges:{' '}
          <strong className="text-foreground">{processed.edges.length}</strong>
        </span>
      </div>
    </div>
  )
}

export function EnterpriseDependencyGraph() {
  return (
    <ReactFlowProvider>
      <InnerGraph />
    </ReactFlowProvider>
  )
}
