'use client'

import { useQuery } from '@tanstack/react-query'
import { useCallback } from 'react'
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { Network } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function DependencyGraphPage() {
  const { data: graphData, isLoading } = useQuery({
    queryKey: ['dependency-graph'],
    queryFn: async () => {
      const response = await api.get('/api/dependencies/graph')
      return response.data
    },
  })

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useQuery({
    queryKey: ['transform-graph', graphData],
    queryFn: () => {
      if (graphData?.nodes && graphData?.edges) {
        const flowNodes: Node[] = graphData.nodes.map((node: any, index: number) => ({
          id: node.id,
          data: { label: node.name || node.id },
          position: {
            x: (index % 5) * 200,
            y: Math.floor(index / 5) * 150,
          },
        }))

        const flowEdges: Edge[] = graphData.edges.map((edge: any) => ({
          id: `${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          label: edge.type || '',
        }))

        setNodes(flowNodes)
        setEdges(flowEdges)
      }
      return null
    },
    enabled: !!graphData,
  })

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dependency graph"
        description="Service-level dependencies and relationships loaded from the graph store."
      />

      <Card className="overflow-hidden border-border/80">
        <CardHeader className="border-b border-border/80 bg-card/50 pb-4">
          <div className="flex items-center gap-2">
            <Network className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-base">Topology</CardTitle>
              <CardDescription>Pan, zoom, and inspect nodes. Data reflects the latest graph API response.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex h-[420px] items-center justify-center text-sm text-muted-foreground">
              Loading graph…
            </div>
          ) : (
            <div className="h-[min(70vh,640px)] min-h-[420px] w-full bg-muted/20">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                fitView
                className="bg-transparent"
              >
                <Background gap={20} size={1} color="hsl(217 33% 22%)" />
                <Controls className="!m-3 !rounded-lg !border-border !bg-card !shadow-lg" />
                <MiniMap
                  className="!m-3 !rounded-lg !border-border !bg-card"
                  maskColor="hsl(222 47% 6% / 0.7)"
                />
              </ReactFlow>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
