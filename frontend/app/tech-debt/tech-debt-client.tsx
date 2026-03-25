'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import DebtVisualization from '@/components/tech-debt/DebtVisualization'
import DebtList from '@/components/tech-debt/DebtList'
import RemediationPlan from '@/components/tech-debt/RemediationPlan'

const LS_KEY = 'caa:lastRepositoryId'

export function TechDebtClient() {
  const searchParams = useSearchParams()
  const repoParam = searchParams.get('repo')

  const [repositoryId, setRepositoryId] = useState('')
  const [selectedTab, setSelectedTab] = useState<'overview' | 'items' | 'plan'>('overview')

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

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['tech-debt-metrics', repositoryId],
    queryFn: async () => {
      if (!repositoryId) return null
      try {
        const response = await api.get(`/tech-debt/metrics/${repositoryId}`)
        return response.data
      } catch (e: unknown) {
        const status = (e as { response?: { status?: number } })?.response?.status
        if (status === 404) return null
        throw e
      }
    },
    enabled: !!repositoryId,
    retry: false,
  })

  const { data: report, isLoading: reportLoading } = useQuery({
    queryKey: ['tech-debt-report', repositoryId],
    queryFn: async () => {
      if (!repositoryId) return null
      try {
        const response = await api.get(`/tech-debt/reports/${repositoryId}`)
        return response.data
      } catch (e: unknown) {
        const status = (e as { response?: { status?: number } })?.response?.status
        if (status === 404) return null
        throw e
      }
    },
    enabled: !!repositoryId,
    retry: false,
  })

  const chartMetrics = useMemo(() => {
    if (metrics) return metrics
    if (!report) return null
    return {
      total_debt_score: report.total_debt_score,
      debt_density: report.debt_density,
      total_items: report.total_items,
      category_scores: report.category_scores,
      items_by_category: report.items_by_category,
      items_by_severity: report.items_by_severity,
    }
  }, [metrics, report])

  const { mutate: runAnalysis, isPending: analysisPending } = useMutation({
    mutationFn: async (repoId: string) => {
      const response = await api.post('/tech-debt/analyze', {
        repository_id: repoId,
      })
      return response.data
    },
  })

  const handleAnalyze = () => {
    if (repositoryId) {
      runAnalysis(repositoryId)
    }
  }

  const tabs = [
    { id: 'overview' as const, label: 'Overview' },
    { id: 'items' as const, label: 'Debt items' },
    { id: 'plan' as const, label: 'Remediation' },
  ]

  return (
    <div className="space-y-8">
      <PageHeader
        title="Technical debt"
        description="Deep-dive into quality and architecture debt for a repository you have already analyzed."
        actions={
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
        }
      />

      <Card className="border-border/80 bg-card/50">
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Repository</CardTitle>
          <CardDescription>
            Use the analysis ID returned when you started analysis, or open this page from Analyze with a
            pre-filled link.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-2">
              <Label htmlFor="repo-id">Analysis ID</Label>
              <Input
                id="repo-id"
                type="text"
                value={repositoryId}
                onChange={(e) => setRepositoryId(e.target.value)}
                placeholder="e.g. 8f3c2a1b-…"
              />
            </div>
            <Button
              onClick={handleAnalyze}
              disabled={analysisPending || !repositoryId}
              className="sm:min-w-[140px]"
            >
              {analysisPending ? 'Running…' : 'Run tech-debt pass'}
            </Button>
            {repositoryId ? (
              <Link
                href={`/services?repo=${encodeURIComponent(repositoryId)}`}
                className={cn(
                  buttonVariants({ variant: 'outline', size: 'sm' }),
                  'sm:min-w-[140px] justify-center'
                )}
              >
                Service inventory
              </Link>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2 border-b border-border pb-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setSelectedTab(t.id)}
            className={cn(
              'rounded-md px-4 py-2 text-sm font-medium transition-colors',
              selectedTab === t.id
                ? 'bg-primary/15 text-primary'
                : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {metricsLoading || reportLoading ? (
        <div className="flex justify-center py-16 text-sm text-muted-foreground">Loading…</div>
      ) : report ? (
        <>
          {selectedTab === 'overview' && (
            <div className="space-y-6">
              <DebtVisualization metrics={chartMetrics} report={report} />

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Top priority</CardTitle>
                  <CardDescription>Highest-severity items from the latest report.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {report.debt_items?.slice(0, 5).map((item: any) => (
                    <div
                      key={item.id}
                      className="flex flex-col gap-2 rounded-lg border border-border/80 bg-background/40 p-4 sm:flex-row sm:items-start sm:justify-between"
                    >
                      <div className="space-y-1">
                        <p className="font-medium text-foreground">{item.title}</p>
                        <p className="text-sm text-muted-foreground">{item.description}</p>
                      </div>
                      <Badge
                        variant={
                          item.severity === 'critical' || item.severity === 'high'
                            ? 'destructive'
                            : item.severity === 'medium'
                              ? 'warning'
                              : 'muted'
                        }
                        className="shrink-0 uppercase"
                      >
                        {item.severity}
                      </Badge>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          )}

          {selectedTab === 'items' && <DebtList repositoryId={repositoryId} />}

          {selectedTab === 'plan' && <RemediationPlan repositoryId={repositoryId} />}
        </>
      ) : (
        <Card className="border-dashed border-border/80 bg-muted/20">
          <CardContent className="py-14 text-center text-sm text-muted-foreground">
            {repositoryId
              ? 'No tech debt report found for this ID yet. Run the pass above or complete a full repository analysis first.'
              : 'Enter a repository ID, or start from Analyze to paste a Git URL and get an ID.'}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
