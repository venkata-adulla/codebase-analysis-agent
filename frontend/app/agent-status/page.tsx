'use client'

import { useQuery } from '@tanstack/react-query'
import { Bot, CheckCircle2, Clock } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

export default function AgentStatusPage() {
  const { data: checkpoints, isLoading } = useQuery({
    queryKey: ['human-review-checkpoints'],
    queryFn: async () => {
      try {
        const response = await api.get('/api/human-review/checkpoints')
        return response.data.checkpoints || []
      } catch {
        return []
      }
    },
    refetchInterval: 5000,
  })

  const pending = checkpoints?.filter((c: any) => c.status === 'pending') || []
  const resolved = checkpoints?.filter((c: any) => c.status === 'resolved') || []

  return (
    <div className="space-y-8">
      <PageHeader
        title="Agents & human review"
        description="Checkpoints where the workflow pauses for clarification or approval."
      />

      {isLoading ? (
        <div className="py-20 text-center text-sm text-muted-foreground">Loading…</div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="border-border/80">
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Clock className="h-5 w-5 text-amber-400" />
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
                    {checkpoint.options && checkpoint.options.length > 0 && (
                      <div className="mt-3">
                        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          Options
                        </p>
                        <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                          {checkpoint.options.map((opt: string, idx: number) => (
                            <li key={idx}>{opt}</li>
                          ))}
                        </ul>
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
                  <CheckCircle2 className="h-5 w-5 text-emerald-400" />
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
