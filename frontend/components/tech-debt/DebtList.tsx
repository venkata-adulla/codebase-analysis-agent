'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { cn } from '@/lib/utils'

interface DebtListProps {
  repositoryId: string
}

export default function DebtList({ repositoryId }: DebtListProps) {
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [severityFilter, setSeverityFilter] = useState<string>('')
  const [priorityFilter, setPriorityFilter] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['tech-debt-items', repositoryId, categoryFilter, severityFilter, priorityFilter],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (repositoryId) params.append('repository_id', repositoryId)
      if (categoryFilter) params.append('category', categoryFilter)
      if (severityFilter) params.append('severity', severityFilter)
      if (priorityFilter) params.append('priority', priorityFilter.toString())

      const response = await api.get(`/tech-debt/items?${params.toString()}`)
      return response.data
    },
    enabled: !!repositoryId,
  })

  const items = data?.items || []

  const categories = Array.from(new Set(items.map((item: any) => item.category)))
  const severities = ['critical', 'high', 'medium', 'low']

  if (isLoading) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>
    )
  }

  const selectClass =
    'w-full rounded-lg border border-input bg-background/60 px-3 py-2 text-sm text-foreground shadow-inner focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="rounded-xl border border-border/80 bg-card/50 p-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <label className="mb-2 block text-sm font-medium text-foreground">Category</label>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className={selectClass}
            >
              <option value="">All Categories</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-foreground">Severity</label>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className={selectClass}
            >
              <option value="">All Severities</option>
              {severities.map((sev) => (
                <option key={sev} value={sev}>
                  {sev.charAt(0).toUpperCase() + sev.slice(1)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-foreground">Priority</label>
            <select
              value={priorityFilter || ''}
              onChange={(e) => setPriorityFilter(e.target.value ? parseInt(e.target.value) : null)}
              className={selectClass}
            >
              <option value="">All Priorities</option>
              <option value="1">Priority 1 (Quick Wins)</option>
              <option value="2">Priority 2 (Strategic)</option>
              <option value="3">Priority 3 (Fill-ins)</option>
              <option value="4">Priority 4 (Avoid)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Items List */}
      <div className="space-y-3">
        {items.length > 0 ? (
          items.map((item: any) => (
            <div
              key={item.id}
              className="rounded-xl border border-border/80 bg-card/40 p-4 transition-shadow hover:border-border hover:shadow-md"
            >
              <div className="mb-2 flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-foreground">{item.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
                  {item.file_path && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {item.file_path}
                      {item.line_start && ` (lines ${item.line_start}-${item.line_end || item.line_start})`}
                    </p>
                  )}
                </div>
                <div className="ml-4 flex gap-2">
                  <span
                    className={cn(
                      'rounded px-2 py-1 text-xs font-semibold',
                      item.severity === 'critical' && 'bg-red-500/15 text-red-400',
                      item.severity === 'high' && 'bg-orange-500/15 text-orange-400',
                      item.severity === 'medium' && 'bg-amber-500/15 text-amber-400',
                      item.severity === 'low' && 'bg-emerald-500/15 text-emerald-400'
                    )}
                  >
                    {item.severity}
                  </span>
                  {item.priority && (
                    <span className="rounded bg-primary/15 px-2 py-1 text-xs font-medium text-primary">
                      P{item.priority}
                    </span>
                  )}
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-4 text-sm text-muted-foreground">
                <span>
                  Category: <span className="font-medium text-foreground">{item.category}</span>
                </span>
                <span>
                  Impact:{' '}
                  <span className="font-medium text-foreground">
                    {(item.impact_score * 100).toFixed(0)}%
                  </span>
                </span>
                <span>
                  Effort:{' '}
                  <span className="font-medium text-foreground">{item.effort_estimate || 'Unknown'}</span>
                </span>
                <span>
                  Status:{' '}
                  <span className="font-medium text-foreground">{item.status || 'open'}</span>
                </span>
              </div>
            </div>
          ))
        ) : (
          <div className="py-12 text-center text-muted-foreground">
            No debt items found matching the filters.
          </div>
        )}
      </div>

      {/* Summary */}
      {items.length > 0 && (
        <div className="rounded-xl border border-border/80 bg-muted/30 p-4">
          <p className="text-sm text-muted-foreground">
            Showing <span className="font-semibold text-foreground">{items.length}</span> debt item(s)
          </p>
        </div>
      )}
    </div>
  )
}
