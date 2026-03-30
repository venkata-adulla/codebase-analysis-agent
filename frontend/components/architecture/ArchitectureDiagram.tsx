'use client'

import { useId, useMemo } from 'react'
import { cn } from '@/lib/utils'

export type ArchNode = {
  id: string
  label: string
  sublabel: string
  type: string
  x: number
  y: number
}

export type ArchEdge = {
  id: string
  source: string
  target: string
  label: string
}

const TYPE_RING: Record<string, string> = {
  frontend: 'ring-sky-500/40 bg-sky-500/10',
  backend: 'ring-violet-500/40 bg-violet-500/10',
  database: 'ring-emerald-500/40 bg-emerald-500/10',
  other: 'ring-amber-500/40 bg-amber-500/10',
}

/** Curved edge in viewBox 0–100; keeps arrows readable and avoids overlapping node centers awkwardly. */
function edgePath(x1: number, y1: number, x2: number, y2: number): string {
  const dx = x2 - x1
  const dy = y2 - y1
  const dist = Math.hypot(dx, dy) || 1
  // Control point offset: bend perpendicular to the chord
  const nx = -dy / dist
  const ny = dx / dist
  const bend = Math.min(12, dist * 0.35)
  const mx = (x1 + x2) / 2 + nx * bend
  const my = (y1 + y2) / 2 + ny * bend
  return `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`
}

export function ArchitectureDiagram({
  nodes,
  edges,
  className,
}: {
  nodes: ArchNode[]
  edges: ArchEdge[]
  className?: string
}) {
  const mid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes])

  if (!nodes.length) {
    return (
      <div
        className={cn(
          'flex min-h-[220px] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground',
          className
        )}
      >
        No diagram data — run analysis when a repository clone is available.
      </div>
    )
  }

  return (
    <div
      className={cn(
        'relative min-h-[min(52vh,440px)] w-full overflow-hidden rounded-xl border border-border/80 bg-card/40',
        className
      )}
    >
      <div className="pointer-events-none absolute inset-0 [background-image:radial-gradient(circle_at_1px_1px,hsl(215_25%_32%/0.22)_1px,transparent_0)] [background-size:22px_22px]" />
      {/*
        Use preserveAspectRatio="none" so viewBox 0–100 maps to the full SVG box. With "meet",
        the square viewBox is letterboxed inside a wide rectangle and edge endpoints no longer
        align with node positions set as left/top % of the same container.
      */}
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        className="absolute inset-0 z-0 h-full w-full text-primary/60"
        aria-hidden
      >
        <defs>
          <marker
            id={`arch-arrow-${mid}`}
            markerWidth="5"
            markerHeight="5"
            refX="4.2"
            refY="2.5"
            orient="auto"
            markerUnits="strokeWidth"
          >
            <path d="M0,0 L5,2.5 L0,5 z" fill="currentColor" className="text-primary/60" />
          </marker>
        </defs>
        {edges.map((e) => {
          const a = byId[e.source]
          const b = byId[e.target]
          if (!a || !b) return null
          const d = edgePath(a.x, a.y, b.x, b.y)
          const lx = (a.x + b.x) / 2
          const ly = (a.y + b.y) / 2
          return (
            <g key={e.id}>
              <path
                d={d}
                fill="none"
                stroke="currentColor"
                strokeWidth="0.85"
                className="text-primary/45"
                markerEnd={`url(#arch-arrow-${mid})`}
              />
              <text
                x={lx}
                y={ly - 3.2}
                fill="currentColor"
                className="text-[3.4px] font-medium text-muted-foreground"
                textAnchor="middle"
                style={{ textShadow: '0 0 8px hsl(var(--background) / 0.9)' }}
              >
                {e.label}
              </text>
            </g>
          )
        })}
      </svg>

      {nodes.map((n) => (
        <div
          key={n.id}
          className={cn(
            'pointer-events-none absolute z-10 max-w-[min(44%,180px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border px-3 py-2.5 text-center shadow-lg ring-1 backdrop-blur-[2px]',
            TYPE_RING[n.type] || 'ring-border bg-muted/30'
          )}
          style={{ left: `${n.x}%`, top: `${n.y}%` }}
        >
          <div className="text-[12px] font-semibold leading-snug text-foreground">{n.label}</div>
          <div className="mt-1 line-clamp-4 text-[10px] leading-snug text-muted-foreground">{n.sublabel}</div>
        </div>
      ))}
    </div>
  )
}
