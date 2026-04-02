'use client'

import { Suspense, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, CheckCircle2, Clock } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ExportMenu } from '@/components/export/ExportMenu'
import type { CsvSection } from '@/lib/export/csv-export'

function AgentStatusPageContent() {
  const queryClient = useQueryClient()
  const [feedback, setFeedback] = useState<string | null>(null)
  const humanReviewExportRef = useRef<HTMLDivElement>(null)
  const searchParams = useSearchParams()
  const repositoryId = searchParams.get('repo') || ''

  const { data: checkpoints, isLoading } = useQuery({
    queryKey: ['human-review-checkpoints', repositoryId],
    queryFn: async () => {
      try {
        const response = await api.get('/human-review/checkpoints', {
          params: repositoryId ? { repository_id: repositoryId } : undefined,
        })
        return response.data.checkpoints || []
      } catch {
        return []
      }
    },
    refetchInterval: 5000,
  })

  const resolveMutation = useMutation({
    mutationFn: async ({ checkpointId, response }: { checkpointId: string; response: string }) => {
      await api.post(`/human-review/checkpoints/${encodeURIComponent(checkpointId)}/resolve`, {
        response,
      })
    },
    onSuccess: (_data, variables) => {
      setFeedback(
        `Recorded “${variables.response}” for checkpoint ${variables.checkpointId.slice(0, 8)}… — saved on this server session for audit.`
      )
      queryClient.invalidateQueries({ queryKey: ['human-review-checkpoints'] })
    },
    onError: () => {
      setFeedback('Could not record the response. Check that the API is running and try again.')
    },
  })

  const pending = checkpoints?.filter((c: any) => c.status === 'pending') || []
  const resolved = checkpoints?.filter((c: any) => c.status === 'resolved') || []

  return (
    <div className="space-y-8">
      <PageHeader
        title="Human Review Checkpoints"
        description="This page currently shows human-facing checkpoints opened by the `human_review_agent`. There is no separate agent-self-review UI yet; your decision is stored on the running API for traceability and operator follow-up."
        actions={
          <ExportMenu
            analysisType="human_review"
            pageTitle="Human review checkpoints"
            pageSlug="human-review"
            repoId={repositoryId || undefined}
            captureRef={humanReviewExportRef}
            getJsonData={() => ({
              repositoryFilter: repositoryId || null,
              checkpoints: checkpoints ?? [],
            })}
            getCsvSections={() => {
              const list = checkpoints ?? []
              const sections: CsvSection[] = [
                {
                  name: 'All checkpoints',
                  headers: ['id', 'status', 'agent', 'reason', 'question', 'response'],
                  rows: list.map((c: Record<string, unknown>) => [
                    String(c.id ?? ''),
                    String(c.status ?? ''),
                    String(c.agent ?? ''),
                    String(c.reason ?? ''),
                    String(c.question ?? ''),
                    String(c.response ?? ''),
                  ]),
                },
              ]
              return sections
            }}
            getPdfSections={() => {
              const pendingC = checkpoints?.filter((c: { status?: string }) => c.status === 'pending') ?? []
              const resolvedC = checkpoints?.filter((c: { status?: string }) => c.status === 'resolved') ?? []
              return [
                {
                  heading: 'Summary',
                  body: `Filter: ${repositoryId || 'all repositories'}. Pending: ${pendingC.length}. Resolved: ${resolvedC.length}.`,
                },
                {
                  heading: 'Pending (preview)',
                  body:
                    pendingC
                      .slice(0, 12)
                      .map(
                        (c: { question?: string; agent?: string }) =>
                          `• [${c.agent}] ${(c.question || '').slice(0, 200)}`
                      )
                      .join('\n') || 'None.',
                },
              ]
            }}
          />
        }
      />

      {feedback && (
        <div
          role="status"
          className="rounded-lg border border-border/80 bg-muted/30 px-4 py-3 text-sm text-foreground"
        >
          {feedback}
        </div>
      )}

      {isLoading ? (
        <div className="py-20 text-center text-sm text-muted-foreground">Loading…</div>
      ) : (
        <div ref={humanReviewExportRef} className="grid gap-6 lg:grid-cols-2">
          <Card className="border-border/80">
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Clock className="h-5 w-5 text-[hsl(var(--warning))]" />
                  <CardTitle className="text-base">Pending</CardTitle>
                </div>
                <Badge variant="warning">{pending.length}</Badge>
              </div>
              <CardDescription>Awaiting input from an operator.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {pending.length > 0 ? (
                pending.map((checkpoint: any) => (
                  <div
                    key={checkpoint.id}
                    className="rounded-xl border border-border/80 bg-card/50 p-4"
                  >
                    <div className="mb-2 flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Bot className="h-4 w-4 shrink-0 text-primary" />
                        <p className="font-semibold text-foreground">{checkpoint.agent}</p>
                      </div>
                      <Badge variant="warning" className="shrink-0">
                        Pending
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{checkpoint.reason}</p>
                    <p className="mt-3 text-sm text-foreground">{checkpoint.question}</p>
                    {checkpoint.context?.summary ? (
                      <p className="mt-2 text-sm text-muted-foreground">{checkpoint.context.summary}</p>
                    ) : null}
                    {Array.isArray(checkpoint.context?.ambiguous_dependencies) &&
                    checkpoint.context.ambiguous_dependencies.length > 0 ? (
                      <div className="mt-3 rounded-lg border border-border/70 bg-muted/20 p-3">
                        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          Ambiguous dependencies
                        </p>
                        <div className="space-y-3">
                          {checkpoint.context.ambiguous_dependencies.map((dep: any, idx: number) => (
                            <div key={`${checkpoint.id}-${idx}`} className="rounded-md border border-border/60 bg-background/40 p-3">
                              <p className="text-sm font-medium text-foreground">
                                {dep.source_service_name || dep.source_service_id} imports {dep.import_target || dep.normalized_target}
                              </p>
                              {dep.file ? (
                                <p className="mt-1 text-xs text-muted-foreground break-all">
                                  File: {dep.file}
                                </p>
                              ) : null}
                              {dep.explanation ? (
                                <p className="mt-1 text-sm text-muted-foreground">{dep.explanation}</p>
                              ) : null}
                              {Array.isArray(dep.possible_matches) && dep.possible_matches.length > 0 ? (
                                <p className="mt-1 text-xs text-muted-foreground">
                                  Possible matches: {dep.possible_matches.join(', ')}
                                </p>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {checkpoint.options && checkpoint.options.length > 0 && (
                      <div className="mt-3 space-y-2">
                        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          Choose a response
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {checkpoint.options.map((opt: string, idx: number) => (
                            <Button
                              key={idx}
                              type="button"
                              size="sm"
                              variant="success"
                              disabled={resolveMutation.isPending}
                              className="text-xs"
                              onClick={() => {
                                if (
                                  typeof window !== 'undefined' &&
                                  !window.confirm(
                                    `Record “${opt}” as your decision for this checkpoint?\n\nThis saves your answer for this server session (audit).`
                                  )
                                ) {
                                  return
                                }
                                resolveMutation.mutate({
                                  checkpointId: checkpoint.id,
                                  response: opt,
                                })
                              }}
                            >
                              {opt}
                            </Button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No pending checkpoints.</p>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/80">
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-success" />
                  <CardTitle className="text-base">Resolved</CardTitle>
                </div>
                <Badge variant="success">{resolved.length}</Badge>
              </div>
              <CardDescription>Completed review steps.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {resolved.length > 0 ? (
                resolved.map((checkpoint: any) => (
                  <div
                    key={checkpoint.id}
                    className="rounded-xl border border-border/60 bg-muted/20 p-4 opacity-95"
                  >
                    <div className="mb-2 flex items-start justify-between gap-2">
                      <p className="font-semibold text-foreground">{checkpoint.agent}</p>
                      <Badge variant="success" className="shrink-0">
                        Resolved
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{checkpoint.reason}</p>
                    {checkpoint.question ? (
                      <p className="mt-2 text-sm text-foreground">{checkpoint.question}</p>
                    ) : null}
                    {checkpoint.response && (
                      <p className="mt-2 text-sm text-foreground">
                        <span className="font-medium text-muted-foreground">Response: </span>
                        {checkpoint.response}
                      </p>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No resolved checkpoints yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

export default function AgentStatusPage() {
  return (
    <Suspense
      fallback={<div className="py-20 text-center text-sm text-muted-foreground">Loading…</div>}
    >
      <AgentStatusPageContent />
    </Suspense>
  )
}
