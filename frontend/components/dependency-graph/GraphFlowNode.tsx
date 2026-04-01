'use client'

import { memo } from 'react'
import { Handle, Position, type NodeProps } from 'reactflow'
import type { GraphNodeModel } from '@/lib/graph/model'
import { couplingColor } from '@/lib/graph/metrics'
import { cn } from '@/lib/utils'

export type GraphFlowNodeData = {
  model: GraphNodeModel
  maxDeg: number
  dimmed: boolean
  highlighted: boolean
  /** 0–1 temporal churn overlay (optional). */
  churnIntensity?: number
}

function GraphFlowNodeInner({ data, selected }: NodeProps<GraphFlowNodeData>) {
  const m = data.model
  const deg = m.dependencyCount + m.dependentsCount
  const stroke = couplingColor(deg, data.maxDeg)
  const isCluster = m.kind === 'cluster'
  const churn = data.churnIntensity
  const churnRing =
    churn != null && churn > 0.15
      ? churn > 0.55
        ? 'ring-2 ring-destructive/55 ring-offset-1 ring-offset-background'
        : churn > 0.3
          ? 'ring-2 ring-[hsl(var(--warning))]/55 ring-offset-1 ring-offset-background'
          : 'ring-1 ring-success/40'
      : ''

  return (
    <div
      className={cn(
        'relative rounded-lg border bg-gradient-to-b px-3 py-2 text-center shadow-lg transition-all duration-200',
        selected ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : '',
        !selected && churnRing,
        data.highlighted ? 'scale-[1.02]' : '',
        data.dimmed ? 'opacity-[0.14] saturate-50' : 'opacity-100'
      )}
      style={{
        width: m.width,
        minHeight: m.height,
        borderColor: stroke,
        background: `linear-gradient(165deg, hsl(0 0% 100%) 0%, hsl(210 25% 96%) 100%)`,
        boxShadow: `inset 0 1px 0 hsl(210 40% 98%), 0 2px 12px hsl(222 47% 4% / 0.12)`,
      }}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !bg-muted-foreground" />
      <div className="text-xs font-semibold leading-tight text-foreground">{m.label}</div>
      <div className="mt-1 flex flex-wrap items-center justify-center gap-1 text-[10px] text-muted-foreground">
        <span className="rounded bg-muted/50 px-1 py-0">{m.layer}</span>
        {isCluster ? <span className="text-primary">cluster</span> : null}
        <span title="risk">R{m.riskScore}</span>
        {churn != null && churn > 0.05 ? (
          <span title="Temporal churn (recent sample)" className="text-[9px] text-[hsl(var(--warning))]">
            Δ{Math.round(churn * 100)}%
          </span>
        ) : null}
      </div>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-muted-foreground" />
    </div>
  )
}

export const GraphFlowNode = memo(GraphFlowNodeInner)
