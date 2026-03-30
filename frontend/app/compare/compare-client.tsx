'use client'

import { useCallback, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { GitCompare, Loader2, Sparkles } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ExportMenu } from '@/components/export/ExportMenu'
import { MetricExplainer } from '@/components/layout/metric-explainer'
import type { CsvSection } from '@/lib/export/csv-export'

type RepoRow = { id: string; name?: string; status?: string }

type TableRow = {
  category: string
  subcategory: string
  values: Record<string, string>
}

type CompareResponse = {
  comparison: {
    repositories: { id: string; name: string; has_architecture_cache: boolean }[]
    table: TableRow[]
  }
  scores: Record<
    string,
    {
      maintainability_normalized?: number
      scalability_normalized?: number
      complexity_normalized?: number
      maintainability?: number
      scalability?: number
      complexity_risk?: number
    }
  >
  insights: {
    summary: string
    key_differences: string[]
    recommendation: string
    trade_offs: string
    full_text: string
  }
}

const apiKey = () => process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'

async function fetchRepos(): Promise<RepoRow[]> {
  const res = await fetch('/api/repositories/', {
    headers: { Accept: 'application/json', 'X-API-Key': apiKey() },
  })
  if (!res.ok) throw new Error(await res.text())
  const data = await res.json()
  return Array.isArray(data.repositories) ? data.repositories : []
}

async function postCompare(repoIds: string[]): Promise<CompareResponse> {
  const res = await fetch('/api/compare-repos', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-API-Key': apiKey(),
    },
    body: JSON.stringify({ repoIds }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

function scoreColor(v: number | undefined, invert = false) {
  if (v == null || Number.isNaN(v)) return 'text-muted-foreground'
  const x = invert ? 100 - v : v
  if (x >= 70) return 'text-emerald-400'
  if (x >= 45) return 'text-amber-400'
  return 'text-red-400/90'
}

export function CompareClient() {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [result, setResult] = useState<CompareResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const compareExportRef = useRef<HTMLDivElement>(null)

  const { data: repos, isLoading: reposLoading } = useQuery({
    queryKey: ['repositories-list'],
    queryFn: fetchRepos,
  })

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }, [])

  const runCompare = useCallback(async () => {
    const ids = [...selected]
    if (ids.length < 2) {
      setErr('Select at least two repositories.')
      return
    }
    setErr(null)
    setLoading(true)
    try {
      const data = await postCompare(ids)
      setResult(data)
    } catch (e) {
      setResult(null)
      setErr(e instanceof Error ? e.message : 'Compare failed')
    } finally {
      setLoading(false)
    }
  }, [selected])

  const repoColumns = result?.comparison.repositories || []
  const colIds = useMemo(() => repoColumns.map((r) => r.id), [repoColumns])

  return (
    <div className="space-y-8">
      <PageHeader
        title="Compare repositories"
        description="Side-by-side view of architecture cache, stacks, style, graph metrics, and tech debt — with normalized scores and AI narrative. Run Architecture and analysis on each repo first for richest data."
        actions={
          result ? (
            <ExportMenu
              analysisType="compare_repos"
              pageTitle="Compare repositories"
              pageSlug="compare-repos"
              repoId={colIds[0]}
              repoName={`${colIds.length} repos`}
              captureRef={compareExportRef}
              getJsonData={() => ({
                selectedRepositoryIds: colIds,
                comparison: result.comparison,
                scores: result.scores,
                insights: result.insights,
              })}
              getCsvSections={() => {
                const sections: CsvSection[] = []
                const table = result.comparison.table
                if (table?.length && colIds.length) {
                  sections.push({
                    name: 'Comparison table',
                    headers: ['category', 'subcategory', ...colIds],
                    rows: table.map((row) => [
                      row.category,
                      row.subcategory,
                      ...colIds.map((id) => row.values[id] ?? ''),
                    ]),
                  })
                }
                sections.push({
                  name: 'Normalized scores',
                  headers: ['repository_id', 'maintainability', 'scalability', 'simplicity'],
                  rows: colIds.map((id) => {
                    const sc = result.scores[id] || {}
                    return [
                      id,
                      sc.maintainability_normalized ?? '',
                      sc.scalability_normalized ?? '',
                      sc.complexity_normalized ?? '',
                    ]
                  }),
                })
                return sections
              }}
              getPdfSections={() => [
                { heading: 'AI summary', body: result.insights.summary },
                {
                  heading: 'Key differences',
                  body: (result.insights.key_differences || []).map((d) => `• ${d}`).join('\n'),
                },
                { heading: 'Recommendation', body: result.insights.recommendation },
                { heading: 'Trade-offs', body: result.insights.trade_offs },
              ]}
            />
          ) : null
        }
      />

      <section className="rounded-xl border border-border bg-card/40 p-4">
        <h2 className="text-sm font-semibold">Select repositories (2+)</h2>
        {reposLoading ? (
          <p className="mt-2 text-sm text-muted-foreground">Loading repositories…</p>
        ) : (
          <ul className="mt-3 max-h-[240px] space-y-2 overflow-y-auto pr-1">
            {(repos || []).map((r) => (
              <li key={r.id}>
                <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-transparent px-2 py-1.5 hover:bg-muted/40">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={selected.has(r.id)}
                    onChange={() => toggle(r.id)}
                  />
                  <span className="min-w-0">
                    <span className="font-mono text-xs text-foreground">{r.id}</span>
                    <span className="ml-2 text-sm text-muted-foreground">{r.name || '—'}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="button" disabled={selected.size < 2 || loading} onClick={() => void runCompare()}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <GitCompare className="mr-2 h-4 w-4" />}
            Compare
          </Button>
          <span className="self-center text-xs text-muted-foreground">{selected.size} selected</span>
        </div>
        {err ? <p className="mt-2 text-sm text-destructive">{err}</p> : null}
      </section>

      {result ? (
        <div ref={compareExportRef} className="space-y-8">
          <section className="rounded-xl border border-border bg-gradient-to-br from-card/90 to-card/50 p-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">AI summary</h2>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{result.insights.summary}</p>
            <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-foreground/90">
              {(result.insights.key_differences || []).map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
            <p className="mt-3 text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Recommendation: </span>
              {result.insights.recommendation}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Trade-offs: </span>
              {result.insights.trade_offs}
            </p>
          </section>

          <section className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="sticky left-0 z-10 bg-muted/30 px-3 py-2 text-left font-medium">Category</th>
                  <th className="px-3 py-2 text-left font-medium">Aspect</th>
                  {colIds.map((id) => {
                    const meta = repoColumns.find((r) => r.id === id)
                    return (
                      <th key={id} className="min-w-[160px] px-3 py-2 text-left font-medium">
                        <div className="font-mono text-[11px] text-primary">{id.slice(0, 8)}…</div>
                        <div className="text-xs font-normal text-muted-foreground">{meta?.name || ''}</div>
                        {!meta?.has_architecture_cache ? (
                          <div className="text-[10px] text-amber-500">No arch cache</div>
                        ) : null}
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {result.comparison.table.map((row, idx) => {
                  const rowVals = colIds.map((c) => row.values[c] ?? '')
                  const distinct = new Set(rowVals.filter((x) => x && x !== '—')).size
                  const rowDiffers = distinct > 1
                  return (
                    <tr
                      key={`${row.category}-${row.subcategory}-${idx}`}
                      className={cn('border-b border-border/60', rowDiffers ? 'bg-amber-500/[0.04]' : '')}
                    >
                      <td className="sticky left-0 bg-background/95 px-3 py-2 text-muted-foreground">{row.category}</td>
                      <td className="px-3 py-2 text-foreground/90">{row.subcategory}</td>
                      {colIds.map((id) => {
                        const v = row.values[id] ?? '—'
                        return (
                          <td
                            key={id}
                            className={cn('px-3 py-2 align-top text-xs', v === '—' ? 'text-muted-foreground' : '')}
                          >
                            {v}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>

          <section className="grid gap-3 md:grid-cols-3">
            <div className="md:col-span-3">
              <MetricExplainer
                title="How to read comparison scores"
                points={[
                  'Normalized scores are on a 0–100 scale; higher is better for maintainability and scalability.',
                  'Simplicity is inverse complexity, so higher simplicity means lower structural complexity.',
                  'Raw risk/complexity index is not normalized; higher values indicate greater complexity risk.',
                ]}
              />
            </div>
            {colIds.map((id) => {
              const sc = result.scores[id] || {}
              const meta = repoColumns.find((r) => r.id === id)
              return (
                <div key={id} className="rounded-xl border border-border bg-card/50 p-4">
                  <h3 className="font-mono text-xs text-primary">{id.slice(0, 12)}…</h3>
                  <p className="text-xs text-muted-foreground">{meta?.name}</p>
                  <dl className="mt-3 space-y-2 text-xs">
                    <div className="flex justify-between gap-2">
                      <dt>Maintainability</dt>
                      <dd className={cn('font-semibold', scoreColor(sc.maintainability_normalized))}>
                        {sc.maintainability_normalized?.toFixed(0) ?? '—'}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt>Scalability</dt>
                      <dd className={cn('font-semibold', scoreColor(sc.scalability_normalized))}>
                        {sc.scalability_normalized?.toFixed(0) ?? '—'}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt>Simplicity (inv. complexity)</dt>
                      <dd className={cn('font-semibold', scoreColor(sc.complexity_normalized))}>
                        {sc.complexity_normalized?.toFixed(0) ?? '—'}
                      </dd>
                    </div>
                    <div className="border-t border-border/60 pt-2 text-[10px] text-muted-foreground">
                      Raw risk/complexity index: {sc.complexity_risk?.toFixed(1) ?? '—'} (higher = more complex)
                    </div>
                  </dl>
                </div>
              )
            })}
          </section>

          {result.insights.full_text ? (
            <section className="rounded-xl border border-border bg-card/40 p-4">
              <h2 className="text-sm font-semibold">Detailed narrative</h2>
              <div className="prose prose-invert prose-sm mt-3 max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.insights.full_text}</ReactMarkdown>
              </div>
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
