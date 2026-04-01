'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, parseISO, startOfDay, startOfMonth, startOfWeek } from 'date-fns'
import { CalendarRange, GitCommit, GitMerge, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { ExportMenu } from '@/components/export/ExportMenu'
import { MetricExplainer } from '@/components/layout/metric-explainer'
import type { CsvSection } from '@/lib/export/csv-export'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useTemporalHeatmapStore } from '@/stores/temporal-heatmap-store'

type TimelineEvent = {
  id: string
  type: string
  timestamp: string
  author: string
  summary: string
  impacted_modules?: string[]
  meta?: Record<string, unknown>
}

type SampledComment = {
  pr: number
  pr_title?: string
  kind?: string
  author: string
  body_preview: string
  created_at?: string | null
}

type TemporalResponse = {
  repository_id: string
  timeline: TimelineEvent[]
  drift_metrics: {
    statements: string[]
    module_churn_30d?: Record<string, number>
    module_churn_window?: Record<string, number>
    commits_in_window?: number
    prs_in_window?: number
    comments_in_window?: number
    sample_limits?: { max_commits: number; max_prs: number; max_comments: number }
  }
  heatmap: {
    modules: {
      service_id: string
      name: string
      intensity: number
      change_count_30d?: number
      change_count_window?: number
    }[]
  }
  pr_insights: {
    large_prs: { number: number; title: string; changed_files: number; lines: number }[]
    hotfix_patterns: { number: number; title: string }[]
    repeat_files: { path: string; commits: number }[]
    recent_prs?: {
      number: number
      title: string
      author: string
      merged_at?: string | null
      changed_files: number
      commits: number
      additions: number
      deletions: number
      head_ref: string
      base_ref: string
      body_preview: string
    }[]
  }
  comment_insights: { themes: string[]; sampled: SampledComment[] }
  impact_evolution: {
    service_id: string
    name: string
    fan_in_out: number
    commits_30d_touching?: number
    commits_window_touching?: number
    risk_note: string
    risk_level: string
  }[]
  insights: { severity: string; title: string; detail: string }[]
  ai_summary?: {
    drift_summary: string
    risky_modules: string
    anomalies: string
  }
  debug?: {
    commits_processed?: number
    prs_loaded?: number
    comments_loaded?: number
    time_range?: { since?: string | null; until?: string | null; mode?: string; note?: string }
  }
}

function heatmapTouches(m: { change_count_window?: number; change_count_30d?: number }): number {
  return m.change_count_window ?? m.change_count_30d ?? 0
}

function impactTouches(r: { commits_window_touching?: number; commits_30d_touching?: number }): number {
  return r.commits_window_touching ?? r.commits_30d_touching ?? 0
}

const apiKey = () => process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'

function withTimeoutSignal(ms: number): AbortSignal {
  const c = new AbortController()
  const t = setTimeout(() => c.abort(), ms)
  c.signal.addEventListener('abort', () => clearTimeout(t), { once: true })
  return c.signal
}

async function fetchTemporal(qs: URLSearchParams): Promise<TemporalResponse> {
  // Same-origin ``/api/temporal-data`` is handled by ``app/api/temporal-data/route.ts`` (server proxy
  // with long timeout). Avoids Next dev rewrite ``ECONNRESET`` on slow/large temporal payloads.
  const res = await fetch(`/api/temporal-data?${qs.toString()}`, {
    headers: { Accept: 'application/json', 'X-API-Key': apiKey() },
    signal: withTimeoutSignal(120_000),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

type Zoom = 'day' | 'week' | 'month'

function bucketKey(ts: string, zoom: Zoom): string {
  const d = parseISO(ts)
  if (zoom === 'day') return format(startOfDay(d), 'yyyy-MM-dd')
  if (zoom === 'week') return format(startOfWeek(d, { weekStartsOn: 1 }), 'yyyy-MM-dd')
  return format(startOfMonth(d), 'yyyy-MM')
}

function bucketLabel(key: string, zoom: Zoom): string {
  const d = zoom === 'month' ? parseISO(`${key}-01`) : parseISO(key)
  if (Number.isNaN(d.getTime())) return key
  if (zoom === 'day') return format(d, 'MMM d, yyyy')
  if (zoom === 'week') return `Week of ${format(d, 'MMM d, yyyy')}`
  return format(d, 'MMMM yyyy')
}

function dayStartIso(value: string): string {
  return new Date(`${value}T00:00:00`).toISOString()
}

function dayEndIso(value: string): string {
  return new Date(`${value}T23:59:59.999`).toISOString()
}

export function TemporalClient() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const repoFromUrl = searchParams.get('repo') || ''

  const [repoInput, setRepoInput] = useState(repoFromUrl)
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [author, setAuthor] = useState('')
  const [moduleId, setModuleId] = useState('')
  const [zoom, setZoom] = useState<Zoom>('week')

  useEffect(() => {
    if (repoFromUrl) setRepoInput(repoFromUrl)
  }, [repoFromUrl])

  const repoId = repoInput.trim()

  const queryParams = useMemo(() => {
    const p = new URLSearchParams()
    if (!repoId) return p
    p.set('repoId', repoId)
    if (since) p.set('since', dayStartIso(since))
    if (until) p.set('until', dayEndIso(until))
    if (author.trim()) p.set('author', author.trim())
    if (moduleId.trim()) p.set('module', moduleId.trim())
    p.set('max_commits', '10')
    p.set('max_prs', '10')
    p.set('max_comments', '10')
    return p
  }, [repoId, since, until, author, moduleId])

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['temporal-data', queryParams.toString()],
    queryFn: () => fetchTemporal(queryParams),
    enabled: !!repoId,
    staleTime: 60_000,
  })

  const grouped = useMemo(() => {
    const ev = data?.timeline || []
    const m = new Map<string, TimelineEvent[]>()
    for (const e of ev) {
      if (!e.timestamp) continue
      const k = bucketKey(e.timestamp, zoom)
      if (!m.has(k)) m.set(k, [])
      m.get(k)!.push(e)
    }
    const keys = [...m.keys()].sort((a, b) => b.localeCompare(a))
    return keys.map((k) => ({ key: k, label: bucketLabel(k, zoom), events: m.get(k)! }))
  }, [data?.timeline, zoom])

  const setHeatmapOverlay = useTemporalHeatmapStore((s) => s.setOverlay)
  const temporalExportRef = useRef<HTMLDivElement>(null)

  const applyHeatmapToGraph = useCallback(() => {
    if (!data?.heatmap?.modules || !repoId) return
    setHeatmapOverlay(
      repoId,
      data.heatmap.modules.map((x) => ({ service_id: x.service_id, intensity: x.intensity }))
    )
    router.push(`/dependency-graph?repo=${encodeURIComponent(repoId)}`)
  }, [data?.heatmap?.modules, repoId, router, setHeatmapOverlay])

  return (
    <div className="space-y-8">
      <PageHeader
        title="Temporal view"
        description="Loads the 10 most recent sampled commits, merged PRs, and PR comments per request. Drift and heatmap reflect that sample only — optional heatmap overlay on the dependency graph."
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!repoId || isFetching}
              onClick={() => refetch()}
            >
              {isFetching ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1 h-4 w-4" />}
              Refresh
            </Button>
            {data && repoId ? (
              <ExportMenu
                analysisType="temporal"
                pageTitle="Temporal view"
                pageSlug="temporal"
                repoId={repoId}
                captureRef={temporalExportRef}
                getJsonData={() => ({
                  filters: {
                    since: since || null,
                    until: until || null,
                    author: author.trim() || null,
                    module: moduleId.trim() || null,
                    zoom,
                  },
                  data,
                })}
                getCsvSections={() => {
                  const sections: CsvSection[] = []
                  if (data.timeline?.length) {
                    sections.push({
                      name: 'Timeline events',
                      headers: ['id', 'type', 'timestamp', 'author', 'summary'],
                      rows: data.timeline.map((e) => [
                        e.id,
                        e.type,
                        e.timestamp,
                        e.author,
                        e.summary,
                      ]),
                    })
                  }
                  if (data.heatmap?.modules?.length) {
                    sections.push({
                      name: 'Heatmap modules',
                      headers: ['service_id', 'name', 'intensity', 'change_count_sample'],
                      rows: data.heatmap.modules.map((m) => [
                        m.service_id,
                        m.name,
                        m.intensity,
                        heatmapTouches(m),
                      ]),
                    })
                  }
                  if (data.impact_evolution?.length) {
                    sections.push({
                      name: 'Impact evolution',
                      headers: [
                        'service_id',
                        'name',
                        'fan_in_out',
                        'commits_sample_touching',
                        'risk_level',
                        'risk_note',
                      ],
                      rows: data.impact_evolution.map((r) => [
                        r.service_id,
                        r.name,
                        r.fan_in_out,
                        impactTouches(r),
                        r.risk_level,
                        r.risk_note,
                      ]),
                    })
                  }
                  if (data.insights?.length) {
                    sections.push({
                      name: 'Structured insights',
                      headers: ['severity', 'title', 'detail'],
                      rows: data.insights.map((i) => [i.severity, i.title, i.detail]),
                    })
                  }
                  return sections
                }}
                getPdfSections={() => {
                  const d = data
                  const ai = d.ai_summary
                  return [
                    {
                      heading: 'AI drift summary',
                      body:
                        [ai?.drift_summary, ai?.risky_modules ? `Risky modules: ${ai.risky_modules}` : '', ai?.anomalies ? `Anomalies: ${ai.anomalies}` : '']
                          .filter(Boolean)
                          .join('\n\n') || '—',
                    },
                    {
                      heading: 'Drift metrics',
                      body:
                        (d.drift_metrics?.statements || []).map((s) => `• ${s}`).join('\n') || 'No statements.',
                    },
                    {
                      heading: 'Timeline (bucket zoom)',
                      body: `Zoom: ${zoom}. Buckets: ${grouped.length}. Events shown in UI: ${d.timeline?.length ?? 0}.`,
                    },
                  ]
                }}
              />
            ) : null}
          </div>
        }
      />

      <div className="grid gap-4 rounded-xl border border-border bg-card/40 p-4 lg:grid-cols-2">
        <div className="space-y-2 lg:col-span-2">
          <label className="text-xs font-medium text-muted-foreground">Repository ID</label>
          <Input
            value={repoInput}
            onChange={(e) => setRepoInput(e.target.value)}
            placeholder="UUID (from Analyze or URL ?repo=)"
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">Since (optional)</label>
          <Input type="date" value={since} onChange={(e) => setSince(e.target.value)} />
        </div>
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">Until (optional)</label>
          <Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
        </div>
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">Author contains</label>
          <Input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Filter commits" />
        </div>
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">Module (service id)</label>
          <Input
            value={moduleId}
            onChange={(e) => setModuleId(e.target.value)}
            placeholder="Optional service UUID"
            className="font-mono text-xs"
          />
        </div>
        <div className="lg:col-span-2 text-[11px] text-muted-foreground">
          Date filters now use the browser's native calendar picker. `Since` covers the start of the selected day and
          `Until` covers the end of the selected day.
        </div>
      </div>

      {!repoId ? (
        <p className="text-sm text-muted-foreground">Enter a repository ID to load temporal data.</p>
      ) : isLoading ? (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Processing git history and PRs…
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {(error as Error)?.message}
        </div>
      ) : data ? (
        <>
          {data.debug?.time_range ? (
            <p className="text-[11px] text-muted-foreground">
              Window: {data.debug.time_range.since ?? '—'} → {data.debug.time_range.until ?? '—'}
              {data.debug.time_range.mode ? ` · ${data.debug.time_range.mode}` : ''}
              {data.debug.time_range.note ? ` — ${data.debug.time_range.note}` : ''} · Commits:{' '}
              {data.debug.commits_processed ?? '—'} · PRs: {data.debug.prs_loaded ?? '—'} · Comments:{' '}
              {data.debug.comments_loaded ?? '—'} · Sample caps:{' '}
              {data.drift_metrics?.sample_limits
                ? `${data.drift_metrics.sample_limits.max_commits}/${data.drift_metrics.sample_limits.max_prs}/${data.drift_metrics.sample_limits.max_comments}`
                : '10/10/10'}
            </p>
          ) : null}
          <MetricExplainer
            title="How to read temporal metrics"
            points={[
              'Intensity is relative churn within the sampled commits (10 by default), not a full repo history.',
              'Drift statements and heatmap use only those sampled commits plus up to 10 merged PRs and 10 PR comments.',
              'Risk level combines dependency graph connectivity with touches in the sampled commit window.',
            ]}
          />

          <section className="rounded-xl border border-border bg-gradient-to-br from-card/80 to-card/40 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">AI drift summary</h2>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {data.ai_summary?.drift_summary}
            </p>
            <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
              <p>
                <span className="font-medium text-foreground">Risky modules: </span>
                {data.ai_summary?.risky_modules}
              </p>
              <p>
                <span className="font-medium text-foreground">Anomalies: </span>
                {data.ai_summary?.anomalies}
              </p>
            </div>
          </section>

          {/* Timeline */}
          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">Timeline</h2>
              <div className="flex gap-1 rounded-lg border border-border bg-muted/30 p-0.5 text-xs">
                {(['day', 'week', 'month'] as const).map((z) => (
                  <button
                    key={z}
                    type="button"
                    className={cn(
                      'rounded-md px-2 py-1 capitalize',
                      zoom === z ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
                    )}
                    onClick={() => setZoom(z)}
                  >
                    {z}
                  </button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto pb-2">
              {grouped.length === 0 ? (
                <p className="text-xs text-muted-foreground">No commit or PR events matched the current filters.</p>
              ) : (
                <div className="flex min-w-max gap-4">
                  {grouped.map((col) => (
                    <div key={col.key} className="w-[220px] shrink-0 rounded-lg border border-border/80 bg-card/50 p-2">
                      <div className="mb-2 flex items-center gap-1 border-b border-border/60 pb-1 text-[11px] font-medium text-muted-foreground">
                        <CalendarRange className="h-3 w-3" />
                        {col.label}
                      </div>
                      <ul className="space-y-2">
                        {col.events.map((e) => (
                          <li
                            key={e.id}
                            className="rounded-md border border-border/50 bg-background/60 px-2 py-1.5 text-[11px]"
                          >
                          <div className="flex items-center gap-1 text-muted-foreground">
                            {e.type === 'pr_merge' ? (
                              <GitMerge className="h-3 w-3 shrink-0 text-violet-400" />
                            ) : (
                              <GitCommit className="h-3 w-3 shrink-0 text-sky-400" />
                            )}
                            <span className="truncate">{format(parseISO(e.timestamp), 'HH:mm')}</span>
                          </div>
                          <p className="mt-0.5 line-clamp-3 font-medium text-foreground">{e.summary}</p>
                          <p className="text-[10px] text-muted-foreground">{e.author}</p>
                          {e.type === 'commit' ? (
                            <p className="mt-0.5 text-[10px] text-muted-foreground">
                              SHA {(e.meta?.sha as string) || '—'} · {(e.meta?.files as number) || 0} file(s) ·{' '}
                              {(e.meta?.lines as number) || 0} changed lines
                            </p>
                          ) : (
                            <p className="mt-0.5 text-[10px] text-muted-foreground">
                              {(e.meta?.changed_files as number) || 0} file(s) · +{(e.meta?.additions as number) || 0} / -
                              {(e.meta?.deletions as number) || 0} · {(e.meta?.commits as number) || 0} commit(s)
                            </p>
                          )}
                          {e.impacted_modules?.length ? (
                            <p className="mt-0.5 text-[10px] text-primary/80">
                              Modules: {e.impacted_modules.slice(0, 4).join(', ')}
                              {e.impacted_modules.length > 4 ? '…' : ''}
                            </p>
                          ) : null}
                          {typeof e.meta?.body_preview === 'string' && e.meta.body_preview ? (
                            <p className="mt-1 line-clamp-4 text-[10px] text-muted-foreground/90">
                              {String(e.meta.body_preview)}
                            </p>
                          ) : null}
                          {Array.isArray(e.meta?.file_sample) && (e.meta?.file_sample as string[]).length > 0 ? (
                            <p className="mt-1 text-[10px] text-muted-foreground/80 break-all">
                              Files: {(e.meta?.file_sample as string[]).join(', ')}
                            </p>
                          ) : null}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-3">
            {/* Heatmap */}
            <section className="rounded-xl border border-border bg-card/50 p-4">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">Change heatmap</h2>
                <Button type="button" variant="secondary" size="sm" onClick={applyHeatmapToGraph}>
                  Show on graph
                </Button>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Red / amber rings = higher churn within the sampled commits. Stable modules stay cool-toned.
              </p>
              <ul className="mt-3 max-h-[320px] space-y-2 overflow-y-auto">
                {(data.heatmap?.modules || []).map((m) => (
                  <li key={m.service_id} className="flex items-center gap-2 text-xs">
                    <div
                      className="h-6 w-2 shrink-0 rounded-full"
                      style={{
                        background:
                          m.intensity > 0.55
                            ? 'hsl(0 70% 45%)'
                            : m.intensity > 0.25
                              ? 'hsl(35 80% 48%)'
                              : 'hsl(145 45% 38%)',
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{m.name}</div>
                      <div className="text-[10px] text-muted-foreground">
                        {heatmapTouches(m)} touches · {Math.round(m.intensity * 100)}% intensity
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              <Link
                href={`/dependency-graph?repo=${encodeURIComponent(repoId)}`}
                className="mt-3 inline-block text-xs text-primary hover:underline"
              >
                Open dependency graph
              </Link>
            </section>

            {/* Drift */}
            <section className="rounded-xl border border-border bg-card/50 p-4">
              <h2 className="text-sm font-semibold">Drift insights</h2>
              <ul className="mt-3 space-y-2 text-xs text-muted-foreground">
                {(data.drift_metrics?.statements || []).map((s, i) => (
                  <li key={i} className="rounded-lg border border-border/50 bg-background/50 px-2 py-1.5">
                    {s}
                  </li>
                ))}
              </ul>
              {!data.drift_metrics?.statements?.length ? (
                <p className="text-xs text-muted-foreground">No strong drift signals in this window.</p>
              ) : null}
            </section>

            {/* PR insights */}
            <section className="rounded-xl border border-border bg-card/50 p-4">
              <h2 className="text-sm font-semibold">PR &amp; commit insights</h2>
              <div className="mt-2 max-h-[320px] space-y-3 overflow-y-auto text-xs">
                <div>
                  <p className="font-medium text-foreground">Large PRs</p>
                  <ul className="mt-1 space-y-1 text-muted-foreground">
                    {(data.pr_insights?.large_prs || []).map((p) => (
                      <li key={p.number} className="break-words">
                        #{p.number} {p.title.slice(0, 80)}
                        {p.title.length > 80 ? '…' : ''} ({p.changed_files} files)
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-medium text-foreground">Recent merged PRs</p>
                  <ul className="mt-1 space-y-2 text-muted-foreground">
                    {(data.pr_insights?.recent_prs || []).slice(0, 10).map((p) => (
                      <li key={p.number} className="rounded-md border border-border/50 bg-background/50 px-2 py-1.5">
                        <p className="font-medium text-foreground">
                          #{p.number} {p.title}
                        </p>
                        <p className="text-[10px]">
                          {p.author || 'unknown'} · {p.changed_files} file(s) · {p.commits} commit(s) · +{p.additions} / -
                          {p.deletions}
                        </p>
                        {(p.head_ref || p.base_ref) && (
                          <p className="text-[10px] text-muted-foreground/80">
                            {p.head_ref || 'head'} → {p.base_ref || 'base'}
                          </p>
                        )}
                        {p.body_preview ? <p className="mt-1 line-clamp-4 text-[10px]">{p.body_preview}</p> : null}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-medium text-foreground">Hotfix-style titles</p>
                  <ul className="mt-1 space-y-1 text-muted-foreground">
                    {(data.pr_insights?.hotfix_patterns || []).map((p) => (
                      <li key={p.number} className="break-words">#{p.number} {p.title}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-medium text-foreground">Repeat churn files</p>
                  <ul className="mt-1 space-y-1 text-muted-foreground">
                    {(data.pr_insights?.repeat_files || []).map((f) => (
                      <li key={f.path} className="break-all">
                        {f.path} ({f.commits} commits)
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>
          </div>

          {/* Impact evolution + structured insights */}
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-border bg-card/50 p-4">
              <h2 className="text-sm font-semibold">Impact &amp; churn (services)</h2>
              <div className="mt-2 max-h-[280px] overflow-y-auto">
                <table className="w-full text-left text-[11px]">
                  <thead>
                    <tr className="text-muted-foreground">
                      <th className="py-1 pr-2">Module</th>
                      <th className="py-1 pr-2">Graph deg.</th>
                      <th className="py-1 pr-2">Sample touches</th>
                      <th className="py-1">Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.impact_evolution || []).map((row) => (
                      <tr key={row.service_id} className="border-t border-border/40">
                        <td className="py-1.5 pr-2 font-medium text-foreground">{row.name}</td>
                        <td className="py-1.5 pr-2">{row.fan_in_out}</td>
                        <td className="py-1.5 pr-2">{impactTouches(row)}</td>
                        <td className="py-1.5 capitalize text-muted-foreground">{row.risk_level}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="rounded-xl border border-border bg-card/50 p-4">
              <h2 className="text-sm font-semibold">Structured insights</h2>
              <ul className="mt-3 space-y-2">
                {(data.insights || []).map((ins, i) => (
                  <li
                    key={i}
                    className="rounded-lg border border-border/60 bg-background/50 px-2 py-2 text-xs"
                  >
                    <span
                      className={cn(
                        'mr-2 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase',
                        ins.severity === 'high'
                          ? 'bg-red-500/15 text-red-400'
                          : ins.severity === 'low'
                            ? 'bg-muted text-muted-foreground'
                            : 'bg-amber-500/15 text-amber-400'
                      )}
                    >
                      {ins.severity}
                    </span>
                    <span className="font-medium text-foreground">{ins.title}</span>
                    <p className="mt-1 text-muted-foreground">{ins.detail}</p>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          {(data.comment_insights?.themes?.length || 0) > 0 || (data.comment_insights?.sampled?.length || 0) > 0 ? (
            <section className="rounded-xl border border-border bg-card/50 p-4">
              <h2 className="text-sm font-semibold">Comment intelligence (sampled)</h2>
              {(data.comment_insights.themes || []).length > 0 ? (
                <ul className="mt-2 list-inside list-disc text-xs text-muted-foreground">
                  {data.comment_insights.themes.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              ) : null}
              {(data.comment_insights.sampled || []).length > 0 ? (
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {data.comment_insights.sampled.slice(0, 10).map((c, i) => (
                    <div key={`${c.pr}-${c.created_at || i}`} className="rounded-lg border border-border/60 bg-background/50 p-3">
                      <p className="text-[11px] font-medium text-foreground">
                        PR #{c.pr} {c.pr_title ? `· ${c.pr_title}` : ''}
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        {c.kind || 'comment'} · {c.author || 'unknown'}
                        {c.created_at ? ` · ${format(parseISO(c.created_at), 'MMM d, yyyy')}` : ''}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">{c.body_preview}</p>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
