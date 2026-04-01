'use client'

import { useQuery, useMutation } from '@tanstack/react-query'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'

interface RemediationPlanProps {
  repositoryId: string
}

export default function RemediationPlan({ repositoryId }: RemediationPlanProps) {
  const { data: plan, isLoading, refetch } = useQuery({
    queryKey: ['remediation-plan', repositoryId],
    queryFn: async () => {
      const response = await api.post('/tech-debt/remediation-plan', {
        repository_id: repositoryId,
      })
      return response.data
    },
    enabled: !!repositoryId,
  })

  const { mutate: generatePlan, isPending } = useMutation({
    mutationFn: async () => {
      const response = await api.post('/tech-debt/remediation-plan', {
        repository_id: repositoryId,
      })
      return response.data
    },
    onSuccess: () => {
      refetch()
    },
  })

  if (isLoading) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>
    )
  }

  if (!plan) {
    return (
      <div className="rounded-xl border border-dashed border-border/80 bg-muted/20 py-12 text-center">
        <p className="mb-4 text-sm text-muted-foreground">No remediation plan found.</p>
        <Button onClick={() => generatePlan()} disabled={isPending}>
          {isPending ? 'Generating…' : 'Generate remediation plan'}
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Plan Overview */}
      <div className="rounded-xl border border-border/80 bg-card/50 p-6">
        <h2 className="mb-2 text-xl font-semibold text-foreground">
          {plan.plan_name || 'Remediation plan'}
        </h2>
        <p className="mb-6 text-sm leading-relaxed text-muted-foreground">
          The three numbers below count <span className="font-medium text-foreground">debt items</span> for this
          repository after the analyzer assigns each item a priority band from impact and estimated effort.
          They match the <span className="font-medium text-foreground">Priority 1 / 2 / 3</span> labels on the
          Debt items tab. Items classified as “avoid” (priority 4) are not included here.
        </p>

        {plan.priority_breakdown && (
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-4">
              <p className="text-sm font-medium text-foreground">Quick wins</p>
              <p className="mt-1 text-2xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
                {plan.priority_breakdown.quick_wins || 0}
              </p>
              <p className="mt-2 text-xs leading-snug text-muted-foreground">
                Priority 1 — high impact with low effort (typically hours). Best to schedule first.
              </p>
            </div>
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4">
              <p className="text-sm font-medium text-foreground">Strategic</p>
              <p className="mt-1 text-2xl font-bold tabular-nums text-amber-600 dark:text-amber-400">
                {plan.priority_breakdown.strategic || 0}
              </p>
              <p className="mt-2 text-xs leading-snug text-muted-foreground">
                Priority 2 — high impact but larger effort (days or more). Plan as focused initiatives.
              </p>
            </div>
            <div className="rounded-lg border border-border bg-muted/40 p-4">
              <p className="text-sm font-medium text-foreground">Fill-ins</p>
              <p className="mt-1 text-2xl font-bold tabular-nums text-foreground">
                {plan.priority_breakdown.fill_ins || 0}
              </p>
              <p className="mt-2 text-xs leading-snug text-muted-foreground">
                Priority 3 — lower impact or smaller slices of work. Good for slack time or batch cleanup.
              </p>
            </div>
          </div>
        )}

        {plan.total_estimated_effort && (
          <div className="mb-4">
            <p className="text-sm text-muted-foreground">Total estimated effort</p>
            <p className="text-lg font-semibold text-foreground">{plan.total_estimated_effort}</p>
          </div>
        )}
      </div>

      {/* Sprint Allocation */}
      {plan.sprint_allocation && (
        <div className="rounded-xl border border-border/80 bg-card/50 p-6">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Sprint allocation</h3>
          <div className="space-y-4">
            {Object.entries(plan.sprint_allocation).map(([sprint, allocation]: [string, any]) => (
              <div key={sprint} className="rounded-lg border border-border/60 bg-muted/30 p-4">
                <h4 className="mb-2 font-semibold text-foreground">
                  {sprint.replace('_', ' ').toUpperCase()}
                </h4>
                <p className="mb-2 text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">Focus: </span>
                  {allocation.focus}
                </p>
                <p className="mb-2 text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">Estimated effort: </span>
                  {allocation.estimated_effort}
                </p>
                {allocation.items && allocation.items.length > 0 && (
                  <div className="mt-3">
                    <p className="mb-2 text-sm font-medium text-foreground">
                      Items ({allocation.items.length})
                    </p>
                    <ul className="list-inside list-disc space-y-1">
                      {allocation.items.slice(0, 5).map((item: any, idx: number) => (
                        <li key={idx} className="text-sm text-muted-foreground">
                          {item.title || item.id}
                        </li>
                      ))}
                      {allocation.items.length > 5 && (
                        <li className="text-sm text-muted-foreground">
                          … and {allocation.items.length - 5} more
                        </li>
                      )}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {plan.recommendations && plan.recommendations.length > 0 && (
        <div className="rounded-xl border border-border/80 bg-card/50 p-6">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Top recommendations</h3>
          <ul className="space-y-2">
            {plan.recommendations.map((rec: string, idx: number) => (
              <li key={idx} className="flex items-start gap-2 text-sm text-foreground">
                <span className="text-primary">•</span>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ROI Analysis */}
      {plan.roi_analysis && (
        <div className="rounded-xl border border-border/80 bg-card/50 p-6">
          <h3 className="mb-4 text-lg font-semibold text-foreground">ROI analysis</h3>
          <div className="space-y-2">
            {Object.entries(plan.roi_analysis).map(([key, value]: [string, any]) => (
              <div key={key} className="flex justify-between gap-4 text-sm">
                <span className="text-muted-foreground">
                  {key.replace('_', ' ').replace(/\b\w/g, (l) => l.toUpperCase())}:
                </span>
                <span className="font-medium text-foreground">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <Button onClick={() => generatePlan()} disabled={isPending}>
          {isPending ? 'Regenerating...' : 'Regenerate Plan'}
        </Button>
      </div>
    </div>
  )
}
