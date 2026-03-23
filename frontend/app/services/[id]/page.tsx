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

export default function ServiceDetailPage() {
  const params = useParams()
  const id = params.id as string

  const { data, isLoading, error } = useQuery({
    queryKey: ['service', id],
    queryFn: async () => {
      const res = await api.get(`/api/services/${id}`)
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
        description={`ID: ${id}`}
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
                <CardTitle>{data?.name || 'Service'}</CardTitle>
                <CardDescription>{data?.language}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            {data?.description && <p>{data.description}</p>}
            <pre className="mt-4 overflow-x-auto rounded-lg bg-muted/50 p-4 text-xs text-foreground">
              {JSON.stringify(data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
