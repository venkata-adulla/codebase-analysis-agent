'use client'

import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { GraphNodeModel } from '@/lib/graph/model'

type Props = {
  manualRepo: string
  onManualRepoChange: (v: string) => void
  onApplyRepo: () => void
  simplifiedView: boolean
  onSimplifiedView: (v: boolean) => void
  focusMode: boolean
  onFocusMode: (v: boolean) => void
  clustering: boolean
  onClustering: (v: boolean) => void
  nodes: GraphNodeModel[]
  selectedId: string | null
  onSelectNode: (id: string | null) => void
  search: string
  onSearch: (v: string) => void
}

export function GraphSidebar({
  manualRepo,
  onManualRepoChange,
  onApplyRepo,
  simplifiedView,
  onSimplifiedView,
  focusMode,
  onFocusMode,
  clustering,
  onClustering,
  nodes,
  selectedId,
  onSelectNode,
  search,
  onSearch,
}: Props) {
  const q = search.trim().toLowerCase()
  const filtered = q
    ? nodes.filter((n) => n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
    : nodes

  return (
    <aside className="flex h-full min-h-0 w-[280px] shrink-0 flex-col border-r border-border/80 bg-card/40">
      <div className="space-y-3 border-b border-border/60 p-4">
        <h2 className="text-sm font-semibold text-foreground">Scope</h2>
        <Label className="text-xs text-muted-foreground">Repository / token</Label>
        <Input
          value={manualRepo}
          onChange={(e) => onManualRepoChange(e.target.value)}
          placeholder="UUID or path segment"
          className="h-9"
        />
        <Button type="button" size="sm" className="w-full" onClick={onApplyRepo}>
          Apply
        </Button>
      </div>

      <div className="space-y-3 border-b border-border/60 p-4">
        <h2 className="text-sm font-semibold text-foreground">View</h2>
        <div className="flex flex-col gap-2">
          <Button
            type="button"
            size="sm"
            variant={simplifiedView ? 'default' : 'outline'}
            onClick={() => onSimplifiedView(true)}
          >
            Simplified (strong deps)
          </Button>
          <Button
            type="button"
            size="sm"
            variant={!simplifiedView ? 'default' : 'outline'}
            onClick={() => onSimplifiedView(false)}
          >
            Full dependency view
          </Button>
          <Button
            type="button"
            size="sm"
            variant={focusMode ? 'default' : 'outline'}
            onClick={() => onFocusMode(!focusMode)}
          >
            Focus mode (1-hop)
          </Button>
          <Button
            type="button"
            size="sm"
            variant={clustering ? 'default' : 'outline'}
            onClick={() => onClustering(!clustering)}
          >
            Package clusters
          </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col p-4">
        <h2 className="mb-2 text-sm font-semibold text-foreground">Services</h2>
        <div className="relative mb-2">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Filter…"
            className="h-8 pl-8 text-xs"
          />
        </div>
        <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1 text-xs">
          {filtered.map((n) => (
            <li key={n.id}>
              <button
                type="button"
                onClick={() => onSelectNode(n.id === selectedId ? null : n.id)}
                className={cn(
                  'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left transition-colors',
                  selectedId === n.id ? 'bg-primary/15 text-foreground' : 'hover:bg-muted/50'
                )}
              >
                <span className="truncate font-medium">{n.label}</span>
                <Badge variant="secondary" className="ml-1 shrink-0 text-[10px]">
                  {n.layer}
                </Badge>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  )
}
