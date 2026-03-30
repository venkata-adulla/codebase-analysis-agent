'use client'

import { useRef } from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, FolderGit2, GitBranch } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { MetricExplainer } from '@/components/layout/metric-explainer'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import { repositoryDisplayName } from '@/lib/repository-display'
import { cn } from '@/lib/utils'
import { ExportMenu } from '@/components/export/ExportMenu'
import type { CsvSection } from '@/lib/export/csv-export'

type RepoRow = { id: string; status?: string; progress?: number; name?: string }

export default function DashboardPage() {
  const dashboardExportRef = useRef<HTMLDivElement>(null)
  const { data: repositories, isLoading } = useQuery({
    queryKey: ['repositories'],
    queryFn: async () => {
      const response = await api.get('/repositories/')
      return (response.data.repositories || []) as RepoRow[]
    },
  })

  const statusVariant = (s?: string) => {
    const v = (s || '').toLowerCase()
    if (v === 'failed' || v === 'error') return 'destructive' as const
    if (v === 'completed' || v === 'complete' || v === 'success') return 'success' as const
    if (v === 'queued' || v === 'running') return 'warning' as const
    return 'muted' as const
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Dashboard"
        description="Track repository analyses initiated from this session. IDs are generated when you start a run from Analyze or the API."
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <ExportMenu
              analysisType="dashboard"
              pageTitle="Dashboard"
              pageSlug="dashboard"
              captureRef={dashboardExportRef}
              getJsonData={() => ({
                repositories: repositories ?? [],
              })}
              getCsvSections={() => {
                const rows = repositories ?? []
                const sections: CsvSection[] = [
                  {
                    name: 'Repositories',
                    headers: ['id', 'name', 'status', 'progress'],
                    rows: rows.map((r) => [
                      r.id,
                      r.name ?? '',
                      r.status ?? '',
                      r.progress != null ? Math.round(r.progress * 100) / 100 : '',
                    ]),
                  },
                ]
                return sections
              }}
              getPdfSections={() => {
                const list = repositories ?? []
                const active = list.filter((r) => ['queued', 'running'].includes((r.status || '').toLowerCase()))
                const done = list.filter((r) =>
                  ['completed', 'complete', 'success'].includes((r.status || '').toLowerCase())
                )
                return [
                  {
                    heading: 'Session summary',
                    body: `Total repositories in session: ${list.length}. Active/queued: ${active.length}. Completed: ${done.length}.`,
                  },
                ]
              }}
            />
            <Link
              href="/analyze"
              className={cn(buttonVariants({ size: 'sm' }), 'gap-2 shadow-glow')}
            >
              <GitBranch className="h-4 w-4" />
              Analyze repository
            </Link>
          </div>
        }
      />

      <div ref={dashboardExportRef} className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="border-border/80 bg-card/50">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardDescription>Repositories</CardDescription>
              <FolderGit2 className="h-4 w-4 text-muted-foreground" />
            </div>
            <CardTitle className="text-3xl tabular-nums">
              {isLoading ? '—' : repositories?.length ?? 0}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-border/80 bg-card/50">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardDescription>Active / queued</CardDescription>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </div>
            <CardTitle className="text-3xl tabular-nums">
              {isLoading
                ? '—'
                : repositories?.filter((r) =>
                    ['queued', 'running'].includes((r.status || '').toLowerCase())
                  ).length ?? 0}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-border/80 bg-card/50">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardDescription>Completed</CardDescription>
              <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </div>
            <CardTitle className="text-3xl tabular-nums">
              {isLoading
                ? '—'
                : repositories?.filter((r) =>
                    ['completed', 'complete', 'success'].includes((r.status || '').toLowerCase())
                  ).length ?? 0}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <div>
            <CardTitle className="text-base">Recent analyses</CardTitle>
            <CardDescription>
              In-memory session from the API process. Restarting the backend clears this list.
            </CardDescription>
          </div>
          <Link
            href="/analyze"
            className={cn(
              buttonVariants({ variant: 'ghost', size: 'sm' }),
              'text-primary hover:text-primary'
            )}
          >
            New analysis
            <ArrowRight className="ml-1 h-4 w-4" />
          </Link>
        </CardHeader>
        <CardContent>
          <MetricExplainer
            className="mb-4"
            title="How to read dashboard metrics"
            points={[
              'Progress % reflects pipeline completion status for that repository analysis run.',
              'Status badges indicate current run state (queued, running, completed, failed).',
            ]}
          />
          {isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>
          ) : repositories && repositories.length > 0 ? (
            <ul className="divide-y divide-border/80">
              {repositories.map((repo) => (
                <li
                  key={repo.id}
                  className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <p className="text-sm font-medium text-foreground break-all">
                      {repositoryDisplayName(repo.name, repo.id)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      <span className="font-mono break-all">{repo.id}</span>
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <Badge variant={statusVariant(repo.status)} className="uppercase">
                      {repo.status || 'unknown'}
                    </Badge>
                    {typeof repo.progress === 'number' && (
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {Math.round(repo.progress * 100)}%
                      </span>
                    )}
                    <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:justify-end">
                      <Link
                        href={`/tech-debt?repo=${encodeURIComponent(repo.id)}`}
                        className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                      >
                        Tech debt
                      </Link>
                      <Link
                        href={`/impact-analysis?repo=${encodeURIComponent(repo.id)}`}
                        className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                      >
                        Impact
                      </Link>
                      <Link
                        href={`/services?repo=${encodeURIComponent(repo.id)}`}
                        className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                      >
                        Services
                      </Link>
                      <Link
                        href={`/dependency-graph?repo=${encodeURIComponent(repo.id)}`}
                        className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                      >
                        Graph
                      </Link>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="rounded-xl border border-dashed border-border/80 bg-muted/20 py-14 text-center">
              <p className="mb-4 text-sm text-muted-foreground">
                No analyses yet. Start by cloning a repository from the Analyze workspace.
              </p>
              <Link href="/analyze" className={cn(buttonVariants({ size: 'sm' }), 'gap-2')}>
                <GitBranch className="h-4 w-4" />
                Go to Analyze
              </Link>
            </div>
          )}
        </CardContent>
      </Card>
      </div>
    </div>
  )
}
