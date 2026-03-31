'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ArchitectureDiagram } from '@/components/architecture/ArchitectureDiagram'
import { ExportMenu } from '@/components/export/ExportMenu'
import { MarkdownBody } from '@/components/markdown-body'
import { cn } from '@/lib/utils'

type StackItem = { name: string; category: string; confidence: number; source: string }

type ArchReport = {
  repository_id: string
  diagram: { nodes: unknown[]; edges: unknown[] }
  technology_stack: { items: StackItem[]; by_category: Record<string, StackItem[]> }
  coding_style: Record<string, unknown>
  risks_and_practices: {
    risks: { id: string; severity: string; title: string; detail: string; category: string }[]
    best_practices_observed: string[]
    best_practices_missing: string[]
  }
  narrative: {
    architecture_summary: string
    coding_style_summary: string
    risks_summary: string
    best_practices_summary: string
  }
  generated_at?: string
}

const apiKey = () => process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'

async function fetchArchitecture(repoId: string): Promise<ArchReport> {
  const res = await fetch(`/api/architecture/${encodeURIComponent(repoId)}`, {
    headers: { Accept: 'application/json', 'X-API-Key': apiKey() },
  })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || res.statusText)
  }
  return res.json()
}

async function postAnalyze(repoId: string, force: boolean): Promise<ArchReport> {
  const res = await fetch('/api/architecture/analyze', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-API-Key': apiKey(),
    },
    body: JSON.stringify({ repository_id: repoId, force_refresh: force }),
  })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || res.statusText)
  }
  return res.json()
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.min(100, Math.max(0, value * 100)))
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-primary/80 transition-[width]"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function confidenceBand(value: number): 'High confidence' | 'Medium confidence' | 'Low confidence' {
  if (value >= 0.8) return 'High confidence'
  if (value >= 0.6) return 'Medium confidence'
  return 'Low confidence'
}

function explainSource(raw: string): string {
  const source = (raw || '').toLowerCase()
  if (source.startsWith('pom.xml')) return 'Found in Java dependency/build file (pom.xml)'
  if (source.startsWith('package.json:dependencies')) return 'Found in runtime package dependencies'
  if (source.startsWith('package.json:devdependencies')) return 'Found in development-only package dependencies'
  if (source.startsWith('requirements.txt')) return 'Found in Python requirements file'
  if (source.startsWith('pyproject.toml')) return 'Found in Python project manifest'
  if (source.includes('docker-compose')) return 'Found in container/service configuration'
  if (source.includes('folder_structure')) return 'Inferred from repository folder layout (weaker evidence)'
  return `Detected from ${raw}`
}

function SeverityBadge({ s }: { s: string }) {
  const cls =
    s === 'high'
      ? 'bg-red-500/15 text-red-400 ring-red-500/30'
      : s === 'medium'
        ? 'bg-amber-500/15 text-amber-400 ring-amber-500/30'
        : 'bg-muted text-muted-foreground ring-border'
  return (
    <span className={cn('rounded-md px-1.5 py-0.5 text-[10px] font-medium ring-1', cls)}>{s}</span>
  )
}

export function ArchitectureClient() {
  const searchParams = useSearchParams()
  const repoFromUrl = searchParams.get('repo') || ''
  const [repoInput, setRepoInput] = useState(repoFromUrl)
  const queryClient = useQueryClient()
  const diagramExportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (repoFromUrl) setRepoInput(repoFromUrl)
  }, [repoFromUrl])

  const repoId = repoInput.trim()

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['architecture', repoId],
    queryFn: () => fetchArchitecture(repoId),
    enabled: !!repoId,
    staleTime: 5 * 60 * 1000,
  })

  const analyzeMut = useMutation({
    mutationFn: (force: boolean) => postAnalyze(repoId, force),
    onSuccess: (report) => {
      queryClient.setQueryData(['architecture', repoId], report)
    },
  })

  const onApplyRepo = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['architecture', repoId] })
  }, [queryClient, repoId])

  const executiveNarrative = [
    String(data?.narrative?.architecture_summary || '').trim(),
    String(data?.narrative?.coding_style_summary || '').trim(),
    String(data?.narrative?.risks_summary || '').trim(),
    String(data?.narrative?.best_practices_summary || '').trim(),
  ]
    .filter(Boolean)
    .join('\n\n')

  return (
    <div className="space-y-8">
      <PageHeader
        title="Architecture"
        description="System-level view: detected stack, high-level component diagram, coding style signals, and risks — grounded in manifests, structure, and graph metrics."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {data && repoId ? (
              <ExportMenu
                analysisType="architecture"
                pageTitle="Architecture"
                pageSlug="architecture"
                repoId={repoId}
                captureRef={diagramExportRef}
                getJsonData={() => ({
                  analysisType: 'architecture',
                  repoId,
                  data,
                })}
                getCsvSections={() => {
                  const items = data.technology_stack?.items || []
                  const risks = data.risks_and_practices?.risks || []
                  return [
                    {
                      name: 'Technology stack',
                      headers: ['name', 'category', 'confidence', 'source'],
                      rows: items.map((i) => [i.name, i.category, i.confidence, i.source]),
                    },
                    {
                      name: 'Risks',
                      headers: ['severity', 'title', 'detail'],
                      rows: risks.map((r) => [r.severity, r.title, r.detail]),
                    },
                  ]
                }}
                getPdfSections={() => [
                  {
                    heading: 'Executive summary',
                    body: executiveNarrative,
                  },
                ]}
              />
            ) : null}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!repoId || analyzeMut.isPending}
              onClick={() => analyzeMut.mutate(true)}
            >
              {analyzeMut.isPending ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-1 h-4 w-4" />
              )}
              Refresh analysis
            </Button>
          </div>
        }
      />

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card/40 p-4 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1 space-y-2">
          <label className="text-xs font-medium text-muted-foreground" htmlFor="arch-repo">
            Repository ID
          </label>
          <Input
            id="arch-repo"
            value={repoInput}
            onChange={(e) => setRepoInput(e.target.value)}
            placeholder="UUID from Analyze or ?repo= in URL"
            className="font-mono text-sm"
          />
        </div>
        <Button type="button" variant="secondary" disabled={!repoId} onClick={onApplyRepo}>
          Load
        </Button>
      </div>

      {!repoId ? (
        <p className="text-sm text-muted-foreground">Enter a repository ID to load architecture intelligence.</p>
      ) : isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading architecture report…
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {(error as Error)?.message || 'Failed to load'}
        </div>
      ) : data ? (
        <>
          {data.generated_at ? (
            <p className="text-[11px] text-muted-foreground">
              Generated {new Date(data.generated_at).toLocaleString()}
              {isFetching ? ' · refreshing…' : ''}
            </p>
          ) : null}

          <section className="rounded-xl border border-border bg-card/50 p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-foreground">Executive summary</h2>
            <MarkdownBody className="mt-2 text-sm leading-relaxed">
              {executiveNarrative}
            </MarkdownBody>
            <div className="mt-3 rounded-lg border border-border/60 bg-background/40 p-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                How to read this page
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                <li>Percentages in Technology Stack are confidence levels, not usage share.</li>
                <li>Higher confidence means stronger evidence from repo files/manifests.</li>
                <li>“No strong signals” means the analyzer did not find enough static evidence.</li>
              </ul>
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted-foreground">
              System architecture (logical view)
            </h2>
            <div ref={diagramExportRef}>
              <ArchitectureDiagram
                nodes={data.diagram?.nodes as never}
                edges={data.diagram?.edges as never}
                className="min-h-[280px]"
              />
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Simplified service-level view derived from manifests — not the full dependency graph.
            </p>
          </section>

          <div className="grid gap-4 lg:grid-cols-3">
            <section className="rounded-xl border border-border bg-card/50 p-4 shadow-sm">
              <h2 className="text-sm font-semibold">Detected technologies (confidence)</h2>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Confidence indicates how strongly repository evidence suggests a technology is present.
              </p>
              <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
                <span className="rounded-full border border-border/70 px-2 py-0.5">High confidence: 80–100%</span>
                <span className="rounded-full border border-border/70 px-2 py-0.5">Medium: 60–79%</span>
                <span className="rounded-full border border-border/70 px-2 py-0.5">Low: &lt;60%</span>
              </div>
              <div className="mt-4 space-y-4">
                {(['frontend', 'backend', 'database', 'other'] as const).map((cat) => {
                  const rows = data.technology_stack?.by_category?.[cat] || []
                  if (!rows.length) {
                    return (
                      <div key={cat}>
                        <div className="text-xs font-medium capitalize text-foreground/90">{cat}</div>
                        <p className="text-[11px] text-muted-foreground">No strong signals</p>
                      </div>
                    )
                  }
                  return (
                    <div key={cat}>
                      <div className="text-xs font-medium capitalize text-foreground/90">{cat}</div>
                      <ul className="mt-2 space-y-2">
                        {rows.map((item) => (
                          <li key={`${cat}-${item.name}-${item.source}`} className="space-y-1">
                            <div className="flex items-center justify-between gap-2 text-xs">
                              <span className="font-medium text-foreground">{item.name}</span>
                              <div className="flex shrink-0 items-center gap-1.5 text-[10px] text-muted-foreground">
                                <span>{Math.round(item.confidence * 100)}%</span>
                                <span className="rounded-full border border-border/70 px-1.5 py-0.5">
                                  {confidenceBand(item.confidence)}
                                </span>
                              </div>
                            </div>
                            <ConfidenceBar value={item.confidence} />
                            <p className="text-[10px] text-muted-foreground/80">{explainSource(item.source)}</p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )
                })}
              </div>
            </section>

            <section className="rounded-xl border border-border bg-card/50 p-4 shadow-sm">
              <h2 className="text-sm font-semibold">Coding style</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {data.narrative?.coding_style_summary}
              </p>
              <dl className="mt-4 space-y-2 text-xs">
                <div className="flex justify-between gap-2 border-t border-border/60 pt-2">
                  <dt className="text-muted-foreground">Style label</dt>
                  <dd className="font-medium text-foreground">{String(data.coding_style?.label ?? '—')}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Class ratio (est.)</dt>
                  <dd>{Number(data.coding_style?.class_ratio ?? 0).toFixed(2)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Avg. function size (est.)</dt>
                  <dd>{Number(data.coding_style?.avg_function_lines_estimate ?? 0).toFixed(0)} lines</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Modularity hint</dt>
                  <dd className="capitalize">{String(data.coding_style?.modularity_hint ?? '—')}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Files sampled</dt>
                  <dd>{Number(data.coding_style?.files_sampled ?? 0)}</dd>
                </div>
              </dl>
            </section>

            <section className="rounded-xl border border-border bg-card/50 p-4 shadow-sm">
              <h2 className="text-sm font-semibold">Risks &amp; best practices</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {data.narrative?.risks_summary}
              </p>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                {data.narrative?.best_practices_summary}
              </p>
              <div className="mt-4 space-y-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Risks</h3>
                {(data.risks_and_practices?.risks || []).length === 0 ? (
                  <p className="text-xs text-muted-foreground">No automated risk flags.</p>
                ) : (
                  <ul className="space-y-2">
                    {data.risks_and_practices.risks.map((r) => (
                      <li
                        key={r.id}
                        className="rounded-lg border border-border/70 bg-background/50 px-2.5 py-2 text-xs"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <SeverityBadge s={r.severity} />
                          <span className="font-medium text-foreground">{r.title}</span>
                        </div>
                        <p className="mt-1 text-[11px] text-muted-foreground">{r.detail}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div>
                  <h3 className="text-[11px] font-semibold text-emerald-500/90">Observed</h3>
                  <ul className="mt-1 list-inside list-disc text-[11px] text-muted-foreground">
                    {(data.risks_and_practices?.best_practices_observed || []).map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="text-[11px] font-semibold text-amber-500/90">Gaps</h3>
                  <ul className="mt-1 list-inside list-disc text-[11px] text-muted-foreground">
                    {(data.risks_and_practices?.best_practices_missing || []).map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>
          </div>

          <Button type="button" variant="ghost" size="sm" className="text-xs" onClick={() => refetch()}>
            Reload from cache
          </Button>
        </>
      ) : null}
    </div>
  )
}
