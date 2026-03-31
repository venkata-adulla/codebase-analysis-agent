'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useMutation } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { repositoryDisplayName } from '@/lib/repository-display'
import { ExportMenu } from '@/components/export/ExportMenu'
import { MetricExplainer } from '@/components/layout/metric-explainer'
import type { CsvSection } from '@/lib/export/csv-export'

const LS_KEY = 'caa:lastRepositoryId'

export function ImpactClient() {
  const searchParams = useSearchParams()
  const repoParam = searchParams.get('repo')

  const [changeDescription, setChangeDescription] = useState('')
  const [repositoryId, setRepositoryId] = useState('')

  useEffect(() => {
    if (repoParam) {
      setRepositoryId(repoParam)
      return
    }
    try {
      const ls = localStorage.getItem(LS_KEY)
      if (ls) setRepositoryId(ls)
    } catch {
      /* ignore */
    }
  }, [repoParam])

  const { data: analysis, mutate: runAnalysis, isPending } = useMutation({
    mutationFn: async (data: { repository_id: string; change_description: string }) => {
      const response = await api.post('/impact-analysis/analyze', data)
      return response.data
    },
  })

  const handleAnalyze = () => {
    if (repositoryId && changeDescription) {
      runAnalysis({
        repository_id: repositoryId,
        change_description: changeDescription,
      })
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Impact analysis"
        description="Describe a proposed change and assess blast radius using the dependency graph and service metadata."
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Link
              href="/analyze"
              className={cn(
                buttonVariants({ variant: 'outline', size: 'sm' }),
                'inline-flex items-center gap-1.5'
              )}
            >
              New analysis
              <ExternalLink className="h-3.5 w-3.5" />
            </Link>
            <ExportMenu
              analysisType="impact"
              pageTitle="Impact analysis"
              pageSlug="impact"
              repoId={repositoryId || undefined}
              repoName={analysis?.repository_name}
              getJsonData={() => ({
                repositoryId,
                changeDescription,
                analysis: analysis ?? null,
              })}
              {...(analysis
                ? {
                    getCsvSections: () => {
                      const sections: CsvSection[] = []
                      sections.push({
                        name: 'Summary',
                        headers: ['risk_level', 'total_impacted', 'risk_summary'],
                        rows: [
                          [
                            analysis.risk_level ?? '',
                            analysis.total_impacted ?? 0,
                            (analysis.risk_summary as string) || '',
                          ],
                        ],
                      })
                      if (analysis.impacted_services?.length) {
                        sections.push({
                          name: 'Impacted services',
                          headers: [
                            'service_name',
                            'impact_type',
                            'depth',
                            'classification',
                            'impact_score',
                            'reason',
                          ],
                          rows: analysis.impacted_services.map((s: Record<string, unknown>) => [
                            String(s.service_name ?? ''),
                            String(s.impact_type ?? ''),
                            s.depth != null ? String(s.depth) : '',
                            String(s.classification ?? ''),
                            s.impact_score != null ? String(s.impact_score) : '',
                            String(s.reason ?? ''),
                          ]),
                        })
                      }
                      if (analysis.recommendations?.length) {
                        sections.push({
                          name: 'Recommendations',
                          headers: ['text'],
                          rows: analysis.recommendations.map((r: string) => [r]),
                        })
                      }
                      return sections
                    },
                    getPdfSections: () => [
                      {
                        heading: 'Risk summary',
                        body: String(analysis.risk_summary || '—'),
                      },
                      {
                        heading: 'Graph summary',
                        body: JSON.stringify(analysis.graph_summary ?? {}, null, 2),
                      },
                      {
                        heading: 'What could break (overall)',
                        body:
                          (analysis.global_what_could_break || []).map((line: string) => `• ${line}`).join('\n') ||
                          '—',
                      },
                    ],
                  }
                : {})}
            />
          </div>
        }
      />

      <Card className="border-border/80 bg-card/50">
        <CardHeader>
          <CardTitle className="text-base">Run assessment</CardTitle>
          <CardDescription>
            Requires the analysis ID from a completed or in-progress run.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="impact-repo">Analysis ID</Label>
            <Input
              id="impact-repo"
              value={repositoryId}
              onChange={(e) => setRepositoryId(e.target.value)}
              placeholder="Paste analysis ID"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="change">Change description</Label>
            <textarea
              id="change"
              value={changeDescription}
              onChange={(e) => setChangeDescription(e.target.value)}
              className={cn(
                'min-h-[120px] w-full rounded-lg border border-input bg-background/60 px-3 py-2 text-sm text-foreground shadow-inner',
                'placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background'
              )}
              placeholder="Example: Replace synchronous HTTP calls in the billing service with async messaging…"
            />
          </div>

          <Button
            onClick={handleAnalyze}
            disabled={isPending || !repositoryId || !changeDescription.trim()}
          >
            {isPending ? 'Analyzing…' : 'Analyze impact'}
          </Button>
        </CardContent>
      </Card>

      {analysis && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Results</CardTitle>
            <CardDescription>
              Impact summary for the requested change.
              {analysis.repository_name ? (
                <span className="mt-1 block text-xs text-muted-foreground">
                  Repository: {repositoryDisplayName(analysis.repository_name, analysis.repository_id)}
                </span>
              ) : null}
              {analysis.repository_id_requested &&
                analysis.repository_id_requested !== analysis.repository_id && (
                  <span className="mt-1 block text-xs text-muted-foreground">
                    Resolved repository id: {analysis.repository_id}
                  </span>
                )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <MetricExplainer
              title="How to read impact metrics"
              points={[
                'Risk level summarizes predicted blast radius from dependency links and change context.',
                'Impact % per service is a heuristic score (0–100) estimating likelihood/severity of downstream breakage.',
                'Depth means graph distance from changed areas; deeper nodes are usually lower direct impact.',
              ]}
            />
            <div className="flex flex-wrap items-center gap-3">
              <Badge
                variant={
                  analysis.risk_level === 'critical' || analysis.risk_level === 'high'
                    ? 'destructive'
                    : analysis.risk_level === 'medium'
                      ? 'warning'
                      : 'success'
                }
                className="uppercase tracking-wide"
              >
                Risk: {analysis.risk_level}
              </Badge>
              {analysis.graph_summary?.service_count ? (
                <Badge variant="secondary">
                  {analysis.graph_summary.service_count} modules
                </Badge>
              ) : null}
              {analysis.graph_summary?.direct_edge_count ? (
                <Badge variant="secondary">
                  {analysis.graph_summary.direct_edge_count} direct links
                </Badge>
              ) : null}
              {analysis.graph_summary?.indirect_edge_count ? (
                <Badge variant="secondary">
                  {analysis.graph_summary.indirect_edge_count} indirect links
                </Badge>
              ) : null}
              {analysis.graph_summary?.entry_point_service_count ? (
                <Badge variant="secondary">
                  {analysis.graph_summary.entry_point_service_count} entry-point modules
                </Badge>
              ) : null}
            </div>

            {analysis.risk_summary ? (
              <div className="rounded-lg border border-border/60 bg-muted/20 p-4 text-sm leading-relaxed text-muted-foreground">
                {analysis.risk_summary}
              </div>
            ) : null}

            {analysis.global_what_could_break?.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-semibold text-foreground">What could break (overall)</h3>
                <ul className="list-inside list-disc space-y-1.5 text-sm text-muted-foreground">
                  {analysis.global_what_could_break.map((line: string, index: number) => (
                    <li key={index}>{line}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <h3 className="mb-3 text-sm font-semibold text-foreground">
                Impacted services ({analysis.total_impacted ?? 0})
              </h3>
              {(!analysis.impacted_services || analysis.impacted_services.length === 0) ? (
                <p className="text-sm text-muted-foreground">
                  No services in scope. Persist services via a full repository analysis, then try again.
                </p>
              ) : (
                <ul className="space-y-3">
                  {analysis.impacted_services.map((service: any, index: number) => (
                    <li
                      key={`${service.service_id}-${index}`}
                      className="rounded-lg border border-border/80 bg-background/40 p-4"
                    >
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium text-foreground">{service.service_name}</p>
                            {service.impact_type ? <Badge variant="outline">{service.impact_type}</Badge> : null}
                            {typeof service.depth === 'number' ? (
                              <Badge variant="secondary">depth {service.depth}</Badge>
                            ) : null}
                            {service.classification ? (
                              <Badge variant="secondary">{String(service.classification).replace(/_/g, ' ')}</Badge>
                            ) : null}
                          </div>
                          <p className="text-sm text-muted-foreground">{service.reason}</p>
                          {service.what_could_break?.length > 0 && (
                            <div className="mt-2">
                              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                Could break
                              </p>
                              <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
                                {service.what_could_break.map((w: string, i: number) => (
                                  <li key={i}>{w}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                        <span className="shrink-0 text-sm font-semibold tabular-nums text-primary">
                          {(Number(service.impact_score) * 100).toFixed(0)}% impact
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {analysis.recommendations && analysis.recommendations.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-semibold text-foreground">Recommendations</h3>
                <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                  {analysis.recommendations.map((rec: string, index: number) => (
                    <li key={index}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
