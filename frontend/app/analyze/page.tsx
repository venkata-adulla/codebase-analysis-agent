'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  CheckCircle2,
  Copy,
  FolderGit2,
  Github,
  Loader2,
  Link2,
} from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { repositoryDisplayName } from '@/lib/repository-display'

const LS_KEY = 'caa:lastRepositoryId'

type SourceTab = 'url' | 'github' | 'local'

const terminalStatuses = new Set(['failed', 'completed', 'complete', 'error', 'done', 'success'])
const workflowStages = [
  'Planning Agent',
  'Code Browser Agent',
  'Dependency Mapper Agent',
  'Tech Debt Agent',
  'Documentation Agent',
  'Impact Agent',
  'Human Review Agent',
]

function isFailureStatus(status?: string | null) {
  const normalized = (status || '').toLowerCase()
  return normalized === 'failed' || normalized === 'error'
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="font-mono text-sm text-foreground break-all">{value}</span>
    </div>
  )
}

export default function AnalyzePage() {
  const [tab, setTab] = useState<SourceTab>('url')
  const [branch, setBranch] = useState('main')
  const [gitUrl, setGitUrl] = useState('')
  const [ghOwner, setGhOwner] = useState('')
  const [ghRepo, setGhRepo] = useState('')
  const [localPath, setLocalPath] = useState('')
  const [activeRepoId, setActiveRepoId] = useState<string | null>(null)

  const analyzeMutation = useMutation({
    mutationFn: async () => {
      if (tab === 'url') {
        const response = await api.post('/repositories/analyze', {
          repository_url: gitUrl.trim(),
          branch: branch.trim() || 'main',
        })
        return response.data as { repository_id: string; status: string; message?: string }
      }
      if (tab === 'github') {
        const response = await api.post('/repositories/analyze', {
          github_owner: ghOwner.trim(),
          github_repo: ghRepo.trim(),
          branch: branch.trim() || 'main',
        })
        return response.data as { repository_id: string; status: string; message?: string }
      }
      const response = await api.post('/repositories/analyze', {
        repository_path: localPath.trim(),
        branch: branch.trim() || 'main',
      })
      return response.data as { repository_id: string; status: string; message?: string }
    },
  })

  useEffect(() => {
    if (analyzeMutation.data?.repository_id) {
      const id = analyzeMutation.data.repository_id
      setActiveRepoId(id)
      try {
        localStorage.setItem(LS_KEY, id)
      } catch {
        /* ignore */
      }
    }
  }, [analyzeMutation.data?.repository_id])

  const { data: statusData } = useQuery({
    queryKey: ['repo-status', activeRepoId],
    queryFn: async () => {
      if (!activeRepoId) return null
      const res = await api.get(`/repositories/${activeRepoId}/status`)
      return res.data as {
        repository_id: string
        repository_name?: string
        status: string
        progress?: number
        message?: string
      }
    },
    enabled: !!activeRepoId,
    refetchInterval: (q) => {
      const s = q.state.data?.status?.toLowerCase()
      if (!s) return 1000
      if (terminalStatuses.has(s)) return false
      return 1000
    },
  })

  const canSubmit = useMemo(() => {
    if (analyzeMutation.isPending) return false
    if (tab === 'url') return gitUrl.trim().length > 5
    if (tab === 'github') return ghOwner.trim().length > 0 && ghRepo.trim().length > 0
    return localPath.trim().length > 1
  }, [tab, gitUrl, ghOwner, ghRepo, localPath, analyzeMutation.isPending])

  const copyId = async () => {
    if (!activeRepoId) return
    await navigator.clipboard.writeText(activeRepoId)
  }

  const status = statusData?.status?.toLowerCase() ?? analyzeMutation.data?.status?.toLowerCase()
  const progressPct = Math.round(
    Math.max(0, Math.min(100, (typeof statusData?.progress === 'number' ? statusData.progress : 0) * 100))
  )
  const runningMatch = statusData?.message?.match(/Running\s+(.+)\s+\((\d+)\/(\d+)\)/i)
  const runningStage = runningMatch?.[1]?.trim()
  const completedCount = runningMatch ? parseInt(runningMatch[2], 10) : (terminalStatuses.has(status || '') ? workflowStages.length : 0)

  return (
    <div className="space-y-8">
      <PageHeader
        title="Repository analysis"
        description="Clone or attach a repository and run the full multi-agent pipeline. You receive a repository ID for downstream tools (tech debt, impact, graph)."
        actions={
          <Link
            href="/dashboard"
            className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
          >
            View dashboard
          </Link>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="border-border/80 bg-card/50 lg:col-span-2">
          <CardHeader>
            <CardTitle>Connect a codebase</CardTitle>
            <CardDescription>
              HTTPS Git URLs work for most public repositories. GitHub API mode requires a token on
              the API server. Local path must be a valid Git checkout on the machine running the API.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex flex-wrap gap-2">
              {(
                [
                  { id: 'url' as const, label: 'Git URL', icon: Link2 },
                  { id: 'github' as const, label: 'GitHub', icon: Github },
                  { id: 'local' as const, label: 'Local path', icon: FolderGit2 },
                ] as const
              ).map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTab(id)}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors',
                    tab === id
                      ? 'border-primary/50 bg-primary/10 text-primary'
                      : 'border-border bg-background/40 text-muted-foreground hover:border-border hover:bg-muted/50 hover:text-foreground'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {tab === 'url' && (
                <div className="sm:col-span-2 space-y-2">
                  <Label htmlFor="git-url">Repository URL</Label>
                  <Input
                    id="git-url"
                    placeholder="https://github.com/org/project.git"
                    value={gitUrl}
                    onChange={(e) => setGitUrl(e.target.value)}
                    autoComplete="off"
                  />
                </div>
              )}
              {tab === 'github' && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="gh-owner">Owner</Label>
                    <Input
                      id="gh-owner"
                      placeholder="organization"
                      value={ghOwner}
                      onChange={(e) => setGhOwner(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="gh-repo">Repository</Label>
                    <Input
                      id="gh-repo"
                      placeholder="repo-name"
                      value={ghRepo}
                      onChange={(e) => setGhRepo(e.target.value)}
                    />
                  </div>
                </>
              )}
              {tab === 'local' && (
                <div className="sm:col-span-2 space-y-2">
                  <Label htmlFor="local-path">Absolute path</Label>
                  <Input
                    id="local-path"
                    placeholder="D:\path\to\repo or /home/user/repo"
                    value={localPath}
                    onChange={(e) => setLocalPath(e.target.value)}
                  />
                </div>
              )}
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="branch">Branch</Label>
                <Input
                  id="branch"
                  placeholder="main"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                />
              </div>
            </div>

            {analyzeMutation.isError && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
                {(analyzeMutation.error as Error)?.message || 'Request failed'}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <Button
                disabled={!canSubmit}
                onClick={() => analyzeMutation.mutate()}
                className="min-w-[140px] gap-2 shadow-glow"
              >
                {analyzeMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Queuing…
                  </>
                ) : (
                  <>
                    Start analysis
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
              {activeRepoId ? (
                <Button type="button" variant="ghost" size="sm" onClick={() => setActiveRepoId(null)}>
                  Clear result
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/80 bg-gradient-to-b from-card to-card/40">
          <CardHeader>
            <CardTitle className="text-base">Run status</CardTitle>
            <CardDescription>Live status from the orchestrator.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!activeRepoId && !analyzeMutation.isPending && (
              <p className="text-sm text-muted-foreground">
                Submit a repository to see queue and pipeline status here.
              </p>
            )}
            {analyzeMutation.isPending && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                Sending request…
              </div>
            )}
            {activeRepoId && (
              <>
                <div className="flex items-center justify-between gap-2">
                  <Badge
                    variant={
                      isFailureStatus(status)
                        ? 'destructive'
                        : terminalStatuses.has(status || '')
                          ? 'success'
                          : 'warning'
                    }
                    className="uppercase tracking-wide"
                  >
                    {status || 'queued'}
                  </Badge>
                  {!isFailureStatus(status) && terminalStatuses.has(status || '') && (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" aria-hidden />
                  )}
                </div>
                <StatusRow label="Analysis ID" value={activeRepoId} />
                {statusData?.repository_name ? (
                  <StatusRow
                    label="Repository"
                    value={repositoryDisplayName(statusData.repository_name, activeRepoId)}
                  />
                ) : null}
                <div className="flex flex-wrap gap-2 pt-2">
                  <Button type="button" variant="secondary" size="sm" className="gap-1" onClick={copyId}>
                    <Copy className="h-3.5 w-3.5" />
                    Copy analysis ID
                  </Button>
                  <Link
                    href={`/tech-debt?repo=${encodeURIComponent(activeRepoId)}`}
                    className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                  >
                    Tech debt
                  </Link>
                  <Link
                    href={`/impact-analysis?repo=${encodeURIComponent(activeRepoId)}`}
                    className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                  >
                    Impact
                  </Link>
                  <Link
                    href={`/services?repo=${encodeURIComponent(activeRepoId)}`}
                    className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                  >
                    Services
                  </Link>
                  <Link
                    href={`/dependency-graph?repo=${encodeURIComponent(activeRepoId)}`}
                    className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                  >
                    Graph
                  </Link>
                </div>
                {typeof statusData?.progress === 'number' && (
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Progress</span>
                      <span>{progressPct}%</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                    {statusData?.message ? (
                      <p className="text-xs text-muted-foreground">{statusData.message}</p>
                    ) : null}
                    {isFailureStatus(status) && statusData?.message ? (
                      <div className="rounded-md border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-300">
                        {statusData.message}
                      </div>
                    ) : null}
                    <div className="space-y-1 rounded-md border border-border/70 bg-muted/20 p-2">
                      {workflowStages.map((stage, idx) => {
                        const stageLower = stage.toLowerCase()
                        const isCurrent = !terminalStatuses.has(status || '') && runningStage?.toLowerCase() === stageLower
                        const isDone = idx < completedCount || (!isFailureStatus(status) && terminalStatuses.has(status || ''))
                        const isFailed = isFailureStatus(status) && idx >= completedCount
                        return (
                          <div
                            key={stage}
                            className={cn(
                              'text-xs',
                              isCurrent
                                ? 'text-primary'
                                : isFailed
                                  ? 'text-red-400/70'
                                  : isDone
                                    ? 'text-emerald-400'
                                    : 'text-muted-foreground/60'
                            )}
                          >
                            {isCurrent ? '▶ ' : isFailed ? '✗ ' : isDone ? '✓ ' : '• '}
                            {stage}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
