'use client'

import { useMemo } from 'react'
import * as d3 from 'd3'
import { Activity, AlertTriangle, GitBranch, Layers } from 'lucide-react'
import { MarkdownBody } from '@/components/markdown-body'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { GraphNodeModel } from '@/lib/graph/model'

type Props = {
  node: GraphNodeModel | null
  architectureSummary?: Record<string, unknown>
  onRequestFileLevel?: () => void
}

export function GraphInsightsPanel({ node, architectureSummary, onRequestFileLevel }: Props) {
  const riskBarWidth = useMemo(() => {
    if (!node) return 0
    return d3.scaleLinear().domain([0, 100]).range([4, 100]).clamp(true)(node.riskScore)
  }, [node])

  if (!node) {
    return (
      <aside className="flex h-full w-[300px] shrink-0 flex-col border-l border-border/80 bg-card/40 p-4">
        <p className="text-sm text-muted-foreground">Select a node to see AI summary, coupling, and impact context.</p>
        {architectureSummary?.service_count != null ? (
          <p className="mt-4 text-xs text-muted-foreground">
            Repository: {String(architectureSummary.service_count)} services indexed.
          </p>
        ) : null}
      </aside>
    )
  }

  return (
    <aside className="flex h-full w-[300px] shrink-0 flex-col overflow-y-auto border-l border-border/80 bg-card/40">
      <div className="border-b border-border/60 p-4">
        <h2 className="text-sm font-semibold text-foreground">Node insights</h2>
        <p className="mt-1 truncate text-xs text-muted-foreground" title={node.label}>
          {node.label}
        </p>
        <div className="mt-2 flex flex-wrap gap-1">
          <Badge variant="outline">{node.kind}</Badge>
          <Badge variant="secondary">{node.layer}</Badge>
          {node.kind === 'cluster' ? <Badge variant="default">Package group</Badge> : null}
        </div>
      </div>

      <div className="space-y-4 p-4 text-sm">
        <section>
          <h3 className="mb-1 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Layers className="h-3.5 w-3.5" />
            AI summary
          </h3>
          <div className="rounded-lg border border-border/50 bg-muted/20 p-2 text-xs leading-relaxed">
            {node.summary ? (
              <MarkdownBody compact>{node.summary}</MarkdownBody>
            ) : (
              <p className="text-muted-foreground">
                No AI summary stored. Run analysis with documentation enabled or open Service inventory.
              </p>
            )}
          </div>
        </section>

        <section>
          <h3 className="mb-2 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <GitBranch className="h-3.5 w-3.5" />
            Dependencies
          </h3>
          <ul className="space-y-1 text-xs text-muted-foreground">
            <li>
              <span className="text-foreground">Outgoing:</span> {node.dependencyCount}
            </li>
            <li>
              <span className="text-foreground">Incoming:</span> {node.dependentsCount}
            </li>
          </ul>
        </section>

        <section>
          <h3 className="mb-2 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <AlertTriangle className="h-3.5 w-3.5" />
            Risk & coupling
          </h3>
          <p className="text-xs text-muted-foreground">
            Risk score <span className="font-mono text-foreground">{node.riskScore}</span> / 100 (heuristic from graph
            degree).
          </p>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-600 via-amber-500 to-rose-600"
              style={{ width: `${riskBarWidth}%` }}
            />
          </div>
        </section>

        <section>
          <h3 className="mb-2 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Activity className="h-3.5 w-3.5" />
            Impact (preview)
          </h3>
          <p className="text-xs text-muted-foreground">
            Blast-radius and downstream impact use the same dependency edges shown on the canvas. Enable focus mode to
            isolate immediate neighbors.
          </p>
        </section>

        {node.kind === 'service' ? (
          <Button type="button" variant="outline" size="sm" className="w-full" disabled onClick={onRequestFileLevel}>
            File-level graph (lazy load)
          </Button>
        ) : null}
      </div>
    </aside>
  )
}
