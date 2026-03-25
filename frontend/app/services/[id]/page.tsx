'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Boxes } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { MarkdownBody } from '@/components/markdown-body'
import { repositoryDisplayName } from '@/lib/repository-display'
import { serviceDisplayName } from '@/lib/service-display'

export default function ServiceDetailPage() {
  const params = useParams()
  const id = params.id as string

  const { data, isLoading, error } = useQuery({
    queryKey: ['service', id],
    queryFn: async () => {
      const res = await api.get(`/services/${id}`)
      return res.data
    },
    retry: false,
  })

  return (
    <div className="space-y-8">
      <Link
        href="/services"
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
            <CardTitle className="text-base">Not available yet</CardTitle>
            <CardDescription>
              The API returns no service record for this ID until service persistence is wired up.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {(error as Error).message}
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
            {data?.description && <MarkdownBody>{data.description}</MarkdownBody>}
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
