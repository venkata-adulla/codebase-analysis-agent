'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import axios from 'axios'
import { ArrowLeft, Boxes } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { MarkdownBody } from '@/components/markdown-body'
import { repositoryDisplayName } from '@/lib/repository-display'
import { serviceDisplayName } from '@/lib/service-display'

function formatApiError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const d = err.response?.data
    if (typeof d?.detail === 'string') return d.detail
    if (typeof d === 'string') return d
    if (d && typeof d === 'object' && 'detail' in d && typeof (d as { detail: unknown }).detail === 'string') {
      return (d as { detail: string }).detail
    }
    return err.message || err.response?.statusText || 'Request failed'
  }
  if (err instanceof Error) return err.message
  return 'Request failed'
}

export function ServiceDetailClient({ serviceId }: { serviceId: string }) {
  const searchParams = useSearchParams()
  const repoFromQuery = searchParams.get('repo') || ''
  const backHref = repoFromQuery ? `/services?repo=${encodeURIComponent(repoFromQuery)}` : '/services'

  const { data, isLoading, error } = useQuery({
    queryKey: ['service', serviceId],
    queryFn: async () => {
      const res = await api.get(`/services/${encodeURIComponent(serviceId)}`)
      return res.data
    },
    retry: false,
    enabled: !!serviceId,
  })

  const summaryText = typeof data?.summary === 'string' ? data.summary.trim() : ''
  const descriptionText = typeof data?.description === 'string' ? data.description.trim() : ''
  useEffect(() => {
    if (process.env.NODE_ENV !== 'development' || !data) return
    if (summaryText) {
      console.debug('[ServiceDetail] summary', data.id, summaryText.slice(0, 160))
    } else if (descriptionText) {
      console.debug('[ServiceDetail] summary missing; has description', data.id)
    } else {
      console.debug('[ServiceDetail] no summary', data.id, data.name)
    }
  }, [data, summaryText, descriptionText])

  return (
    <div className="space-y-8">
      <Link
        href={backHref}
        className={cn(
          buttonVariants({ variant: 'ghost', size: 'sm' }),
          '-ml-2 gap-1 text-muted-foreground hover:text-foreground'
        )}
      >
        <ArrowLeft className="h-4 w-4" />
        Back to inventory
      </Link>

      <PageHeader
        title="Service detail"
        description={
          data
            ? `Viewing ${serviceDisplayName(data)} in ${repositoryDisplayName(data.repository_name, data.repository_id)}.`
            : `Viewing service details.`
        }
      />

      {isLoading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>
      ) : error ? (
        <Card className="border-dashed border-border/80 bg-muted/20">
          <CardHeader>
            <CardTitle className="text-base">Could not load service</CardTitle>
            <CardDescription>
              The backend returned an error for this service id. Check that analysis has persisted services and the id
              is correct.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {formatApiError(error)}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Boxes className="h-6 w-6" />
              </div>
              <div>
                <CardTitle>{data ? serviceDisplayName(data) : 'Service'}</CardTitle>
                <CardDescription>
                  Repository {repositoryDisplayName(data?.repository_name, data?.repository_id)} · Language:{' '}
                  {data?.language || 'unknown'}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {data?.meta_data?.classification || Number(data?.meta_data?.entry_point_count || 0) > 0 ? (
              <div className="rounded-lg border border-border/60 bg-muted/20 p-3 text-sm text-muted-foreground">
                {data?.meta_data?.classification ? (
                  <p>
                    Module classification:{' '}
                    <span className="font-medium text-foreground">
                      {String(data.meta_data.classification).replace(/_/g, ' ')}
                    </span>
                  </p>
                ) : null}
                {Number(data?.meta_data?.entry_point_count || 0) > 0 ? (
                  <p className="mt-1">
                    Entry points detected:{' '}
                    <span className="font-medium text-foreground">{data.meta_data.entry_point_count}</span>
                  </p>
                ) : null}
              </div>
            ) : null}
            <div className="rounded-lg border border-border/60 bg-muted/10 p-4">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                AI summary
              </p>
              {summaryText ? (
                <MarkdownBody className="text-sm leading-relaxed">{summaryText}</MarkdownBody>
              ) : descriptionText ? (
                <p className="text-sm text-muted-foreground">
                  No short AI summary stored. See the full documentation markdown below.
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">No summary available</p>
              )}
            </div>
            {data?.description ? (
              <div className="rounded-lg border border-border/60 bg-muted/10 p-4">
                <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Documentation (markdown)
                </p>
                <MarkdownBody className="text-sm leading-relaxed">{data.description}</MarkdownBody>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No documentation body stored for this service yet.</p>
            )}
            <details className="rounded-lg border border-border/60 bg-muted/20 p-3 text-xs">
              <summary className="cursor-pointer font-medium text-muted-foreground">Raw JSON</summary>
              <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-all text-[11px] leading-relaxed text-foreground">
                {JSON.stringify(data, null, 2)}
              </pre>
            </details>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
