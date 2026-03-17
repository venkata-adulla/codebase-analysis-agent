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
import api from '@/lib/api'

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

  // Transform API data to React Flow format
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

  if (isLoading) {
    return (
      <div className="min-h-screen p-8">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-8">Dependency Graph</h1>
          <div className="text-center py-12">Loading...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Dependency Graph</h1>
        <div style={{ width: '100%', height: '600px', border: '1px solid #ccc' }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>
      </div>
    </div>
  )
}
