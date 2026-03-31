'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useMutation, useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
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
import { MetricExplainer } from '@/components/layout/metric-explainer'
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
/** Must match backend ``WORKFLOW_SEQUENCE`` order (documentation before tech debt). */
const WORKFLOW_AGENTS: { id: string; label: string }[] = [
  { id: 'planning_agent', label: 'Planning Agent' },
  { id: 'code_browser_agent', label: 'Code Browser Agent' },
  { id: 'dependency_mapper_agent', label: 'Dependency Mapper Agent' },
  { id: 'documentation_agent', label: 'Documentation Agent' },
  { id: 'tech_debt_agent', label: 'Tech Debt Agent' },
  { id: 'impact_agent', label: 'Impact Agent' },
  { id: 'human_review_agent', label: 'Human Review Agent' },
]

/**
 * User-facing capabilities and which orchestrator agents must finish before each is available.
 * Status: completed when every listed agent is in completed_agents; blocked if the run fails first.
 */
const ANALYSIS_FEATURES: {
  id: string
  label: string
  hint: string
  /** Agent ids required (all must complete) */
  dependsOn: string[]
}[] = [
  {
    id: 'architecture',
    label: 'Architecture & stack',
    hint: 'Static stack + diagram',
    dependsOn: ['dependency_mapper_agent'],
  },
  {
    id: 'temporal',
    label: 'Temporal / git history',
    hint: 'Commits & drift',
    dependsOn: ['code_browser_agent'],
  },
  {
    id: 'tech_debt',
    label: 'Tech debt report',
    hint: 'Persisted after pipeline',
    dependsOn: ['tech_debt_agent'],
  },
  {
    id: 'impact',
    label: 'Impact analysis',
    hint: 'Blast-radius prep',
    dependsOn: ['impact_agent'],
  },
  {
    id: 'services',
    label: 'Service inventory',
    hint: 'From documentation step',
    dependsOn: ['documentation_agent'],
  },
  {
    id: 'graph',
    label: 'Dependency graph',
    hint: 'Neo4j-backed',
    dependsOn: ['dependency_mapper_agent'],
  },
  {
    id: 'compare',
    label: 'Cross-repo compare',
    hint: 'Optional',
    dependsOn: ['human_review_agent'],
  },
]

type FeatureRunStatus = 'completed' | 'in_progress' | 'pending' | 'blocked'

function computeFeatureStatus(
  dependsOn: string[],
  completedAgents: string[],
  currentAgent: string | null,
  pipelineFailed: boolean,
): FeatureRunStatus {
  const allMet = dependsOn.length > 0 && dependsOn.every((id) => completedAgents.includes(id))
  if (allMet) return 'completed'
  if (pipelineFailed) return 'blocked'
  const someMet = dependsOn.some((id) => completedAgents.includes(id))
  const currentTouches = currentAgent ? dependsOn.includes(currentAgent) : false
  if (currentTouches || someMet) return 'in_progress'
  return 'pending'
}

const analysisViews = [
  { label: 'Architecture', href: '/architecture', repoScoped: true },
  { label: 'Temporal', href: '/temporal', repoScoped: true },
  { label: 'Tech debt', href: '/tech-debt', repoScoped: true },
  { label: 'Impact', href: '/impact-analysis', repoScoped: true },
  { label: 'Services', href: '/services', repoScoped: true },
  { label: 'Graph', href: '/dependency-graph', repoScoped: true },
  { label: 'Human Review', href: '/agent-status', repoScoped: true },
  { label: 'Compare', href: '/compare', repoScoped: false },
]

function isFailureStatus(status?: string | null) {
  const normalized = (status || '').toLowerCase()
  return normalized === 'failed' || normalized === 'error'
}

function analysisErrorMessage(error: unknown): string {
  if (isAxiosError(error)) {
    const raw = error.response?.data
    if (typeof raw === 'string' && raw.trim()) return raw
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  if (error instanceof Error && error.message) return error.message
  return 'Request failed'
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
        workflow?: string[]
        completed_agents?: string[]
        current_agent?: string | null
        agent_total?: number
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
  const completedAgents = statusData?.completed_agents ?? []
  const currentAgent = statusData?.current_agent ?? null
  const pipelineDone =
    terminalStatuses.has(status || '') && !isFailureStatus(status || '')

  const agentRowState = (agentId: string) => {
    const done =
      completedAgents.includes(agentId) ||
      (pipelineDone && !isFailureStatus(status || ''))
    const current =
      !pipelineDone &&
      !isFailureStatus(status || '') &&
      currentAgent === agentId
    const nextAfterCompleted = WORKFLOW_AGENTS[completedAgents.length]?.id
    const failed =
      isFailureStatus(status || '') && !done && agentId === nextAfterCompleted
    return { done, current, failed }
  }

  const pipelineFailed = isFailureStatus(status || '')

  const agentProgressPct = Math.round(
    (Math.min(completedAgents.length, WORKFLOW_AGENTS.length) / WORKFLOW_AGENTS.length) * 100,
  )

  const featureStatuses = ANALYSIS_FEATURES.map((f) => ({
    ...f,
    status: computeFeatureStatus(
      f.dependsOn,
      completedAgents,
      currentAgent,
      pipelineFailed,
    ),
  }))

  const featuresCompletedCount = featureStatuses.filter((f) => f.status === 'completed').length
  const featureProgressPct = Math.round((featuresCompletedCount / ANALYSIS_FEATURES.length) * 100)

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
                {analysisErrorMessage(analyzeMutation.error)}
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
                  {analysisViews.map((view) => (
                    <Link
                      key={view.label}
                      href={
                        view.repoScoped
                          ? `${view.href}?repo=${encodeURIComponent(activeRepoId)}`
                          : view.href
                      }
                      className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
                    >
                      {view.label}
                    </Link>
                  ))}
                </div>
                <div className="space-y-3">
                  <MetricExplainer
                    title="How to read progress metrics"
                    points={[
                      'Feature progress counts user-facing capabilities unlocked by completed agents.',
                      'Pipeline execution progress tracks how many orchestrator agents have completed.',
                      'A higher percentage means more analysis outputs are ready for downstream pages.',
                    ]}
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Feature progress</span>
                    <span>
                      {featuresCompletedCount}/{ANALYSIS_FEATURES.length} · {featureProgressPct}%
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-all"
                      style={{ width: `${featureProgressPct}%` }}
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

                  <div className="space-y-2 rounded-md border border-border/70 bg-muted/20 p-2">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                        Pipeline execution
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        {Math.min(completedAgents.length, WORKFLOW_AGENTS.length)}/{WORKFLOW_AGENTS.length}{' '}
                        · {agentProgressPct}%
                      </p>
                    </div>
                    <div className="space-y-1">
                      {WORKFLOW_AGENTS.map((agent) => {
                        const { done, current, failed } = agentRowState(agent.id)
                        return (
                          <div
                            key={agent.id}
                            className={cn(
                              'text-xs',
                              current
                                ? 'font-medium text-primary'
                                : failed
                                  ? 'text-red-400/80'
                                  : done
                                    ? 'text-emerald-400'
                                    : 'text-muted-foreground/60',
                            )}
                          >
                            {current ? '▶ ' : failed ? '✗ ' : done ? '✓ ' : '• '}
                            {agent.label}
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  <div className="space-y-2 rounded-md border border-border/70 bg-muted/15 p-2">
                    <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      Available features
                    </p>
                    <p className="text-[10px] text-muted-foreground/80">
                      Each capability unlocks when its required agents finish. Progress above reflects how
                      many features are ready.
                    </p>
                    <div className="space-y-2">
                      {featureStatuses.map((f) => {
                        const depNames = f.dependsOn
                          .map((id) => WORKFLOW_AGENTS.find((a) => a.id === id)?.label ?? id)
                          .join(' · ')
                        const st = f.status
                        const mark =
                          st === 'completed'
                            ? '✓'
                            : st === 'in_progress'
                              ? '◐'
                              : st === 'blocked'
                                ? '✗'
                                : '○'
                        return (
                          <div key={f.id} className="rounded border border-border/40 bg-background/30 px-2 py-1.5">
                            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                              <span
                                className={cn(
                                  'text-xs font-medium',
                                  st === 'completed' && 'text-emerald-400',
                                  st === 'in_progress' && 'text-primary',
                                  st === 'pending' && 'text-muted-foreground/70',
                                  st === 'blocked' && 'text-red-400/90',
                                )}
                              >
                                {mark} {f.label}
                              </span>
                              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                                {st === 'completed'
                                  ? 'Ready'
                                  : st === 'in_progress'
                                    ? 'In progress'
                                    : st === 'blocked'
                                      ? 'Blocked'
                                      : 'Pending'}
                              </span>
                            </div>
                            <p className="text-[10px] text-muted-foreground/80">{f.hint}</p>
                            <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                              After: {depNames}
                            </p>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
