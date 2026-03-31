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

function sublabelTokens(text: string): string[] {
  return (text || '')
    .split(/[,|•]/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 4)
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

function layoutNodes(nodes: ArchNode[]): ArchNode[] {
  const byType: Record<string, ArchNode[]> = { frontend: [], backend: [], database: [], other: [] }
  for (const n of nodes) {
    if (byType[n.type]) byType[n.type].push(n)
    else byType.other.push(n)
  }
  const out: ArchNode[] = []
  const place = (arr: ArchNode[], y: number, xStart: number, step: number) => {
    arr.forEach((n, i) => out.push({ ...n, x: xStart + i * step, y }))
  }

  place(byType.frontend, 18, 50 - ((byType.frontend.length - 1) * 14) / 2, 14)
  place(byType.backend, 44, 50 - ((byType.backend.length - 1) * 16) / 2, 16)
  place(byType.database, 76, 50 - ((byType.database.length - 1) * 16) / 2, 16)
  place(byType.other, 44, 80, 12)
  return out
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
  const diagramId = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const mid = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const placedNodes = useMemo(() => layoutNodes(nodes), [nodes])
  const byId = useMemo(() => Object.fromEntries(placedNodes.map((n) => [n.id, n])), [placedNodes])

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
      data-diagram-id={diagramId}
      className={cn(
        'relative min-h-[min(52vh,440px)] w-full overflow-hidden rounded-xl border border-border/80 bg-card/40',
        className
      )}
    >
      <div className="pointer-events-none absolute inset-0 [background-image:radial-gradient(circle_at_1px_1px,hsl(215_25%_32%/0.22)_1px,transparent_0)] [background-size:22px_22px]" />
      <div className="pointer-events-none absolute inset-x-0 top-[8%] h-[20%] rounded-md border border-sky-500/15 bg-sky-500/[0.03]" />
      <div className="pointer-events-none absolute inset-x-0 top-[34%] h-[24%] rounded-md border border-violet-500/15 bg-violet-500/[0.03]" />
      <div className="pointer-events-none absolute inset-x-0 top-[66%] h-[20%] rounded-md border border-emerald-500/15 bg-emerald-500/[0.03]" />
      <div className="pointer-events-none absolute left-2 top-2 text-[10px] uppercase tracking-wide text-muted-foreground/80">
        Presentation / Entry
      </div>
      <div className="pointer-events-none absolute left-2 top-[38%] text-[10px] uppercase tracking-wide text-muted-foreground/80">
        Application / API
      </div>
      <div className="pointer-events-none absolute left-2 top-[70%] text-[10px] uppercase tracking-wide text-muted-foreground/80">
        Data / Persistence
      </div>
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
        {edges.map((e) => {
          const a = byId[e.source]
          const b = byId[e.target]
          if (!a || !b) return null
          const d = edgePath(a.x, a.y, b.x, b.y)
          return (
            <g key={e.id}>
              <path
                d={d}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.35"
                strokeLinecap="round"
                className="text-primary/45"
                strokeDasharray="2 1.2"
                strokeWidth="1"
                className="text-primary/50"
                markerEnd={`url(#arch-arrow-${mid})`}
              />
            </g>
          )
        })}
      </svg>

      {edges.map((e) => {
        const a = byId[e.source]
        const b = byId[e.target]
        if (!a || !b || !e.label) return null
        const lx = (a.x + b.x) / 2
        const ly = (a.y + b.y) / 2
        return (
          <div
            key={`label-${diagramId}-${e.id}`}
            key={`label-${e.id}`}
            className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-1/2 rounded-full border border-border/70 bg-background/80 px-2 py-0.5 text-[10px] text-muted-foreground shadow-sm"
            style={{ left: `${lx}%`, top: `${ly}%` }}
          >
            {e.label}
          </div>
        )
      })}

      {placedNodes.map((n) => (
        <div
          key={n.id}
          className={cn(
            'pointer-events-none absolute z-10 max-w-[min(40%,240px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border px-3 py-2.5 text-center shadow-lg ring-1 backdrop-blur-[2px]',
            'pointer-events-none absolute z-10 max-w-[min(44%,210px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border px-3 py-2.5 text-center shadow-lg ring-1 backdrop-blur-[2px]',
            TYPE_RING[n.type] || 'ring-border bg-muted/30'
          )}
          style={{ left: `${n.x}%`, top: `${n.y}%` }}
        >
          <div className="text-[12px] font-semibold leading-snug text-foreground">{n.label}</div>
          <div className="mt-1 line-clamp-2 text-[10px] leading-snug text-muted-foreground">{n.sublabel}</div>
          <div className="mt-2 flex flex-wrap items-center justify-center gap-1">
            {sublabelTokens(n.sublabel).map((token) => (
              <span
                key={`${n.id}-${token}`}
                className="rounded-full border border-border/60 bg-background/70 px-1.5 py-0.5 text-[9px] text-muted-foreground"
              >
                {token}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
