'use client'

import Link from 'next/link'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'
import { ArrowRight, Boxes } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { MarkdownBody } from '@/components/markdown-body'
import { repositoryDisplayName } from '@/lib/repository-display'
import { serviceDisplayName } from '@/lib/service-display'

const LS_KEY = 'caa:lastRepositoryId'

export default function ServicesPage() {
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const router = useRouter()
  const repositoryId = searchParams.get('repo') || ''
  const showAll = searchParams.get('all') === '1'

  useEffect(() => {
    if (repositoryId || showAll || typeof window === 'undefined') return
    const remembered = localStorage.getItem(LS_KEY)
    if (remembered) {
      router.replace(`${pathname}?repo=${encodeURIComponent(remembered)}`)
    }
  }, [pathname, repositoryId, router, showAll])

  const { data: services, isLoading } = useQuery({
    queryKey: ['services', repositoryId],
    queryFn: async () => {
      const response = await api.get('/services/', {
        params: repositoryId ? { repository_id: repositoryId } : undefined,
      })
      return response.data.services || []
    },
  })

  const visibleServices = useMemo(() => {
      const rows = Array.isArray(services) ? services : []
    const seen = new Set<string>()
    return rows.filter((service: any) => {
        const key = `${service.repository_id || ''}|${service.name || ''}|${service.path || ''}`.toLowerCase()
        if (!key.trim() || seen.has(key)) return false
        seen.add(key)
        return true
      })
  }, [services])

  return (
    <div className="space-y-8">
      <PageHeader
        title="Service inventory"
        description={
          repositoryId
            ? `Showing services for the selected repository. You can also use a service id or a clone-folder segment in ?repo=.`
            : showAll
              ? 'Showing services from all analyzed repositories. Repeated service names across different analyses are expected.'
              : 'Loading the latest analyzed repository by default. Add ?all=1 to browse services from every analysis.'
        }
        actions={
          <div className="flex flex-wrap gap-2">
            <Link href="/analyze" className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}>
              Analyze repository
            </Link>
            {showAll ? (
              <Link href="/services" className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}>
                Latest repo
              </Link>
            ) : (
              <Link href="/services?all=1" className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}>
                Show all repos
              </Link>
            )}
            {repositoryId ? (
              <Link
                href={`/dependency-graph?repo=${encodeURIComponent(repositoryId)}`}
                className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}
              >
                Open graph
              </Link>
            ) : null}
          </div>
        }
      />

      {isLoading ? (
        <div className="py-20 text-center text-sm text-muted-foreground">Loading…</div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visibleServices.length > 0 ? (
            visibleServices.map((service: any) => (
              <Card
                key={service.id}
                className="group border-border/80 bg-card/50 transition-all hover:border-primary/30 hover:shadow-glow"
              >
                <CardHeader>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Boxes className="h-5 w-5" />
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                  </div>
                  <CardTitle className="text-lg leading-snug">{serviceDisplayName(service)}</CardTitle>
                  <CardDescription className="flex flex-col gap-1">
                    <span className="text-xs text-muted-foreground/90">
                      Repo {repositoryDisplayName(service.repository_name, service.repository_id)}
                    </span>
                    <span>
                      Language: {service.language || 'Unknown'}
                    </span>
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="min-h-24">
                    {service.description ? (
                      <MarkdownBody compact className="max-h-28 overflow-hidden text-sm">
                        {service.description}
                      </MarkdownBody>
                    ) : (
                      <p className="text-sm text-muted-foreground">No documentation summary available yet.</p>
                    )}
                  </div>
                  <Link
                    href={`/services/${service.id}`}
                    className={cn(
                      buttonVariants({ variant: 'ghost', size: 'sm' }),
                      'h-auto p-0 text-primary hover:text-primary'
                    )}
                  >
                    View details →
                  </Link>
                </CardContent>
              </Card>
            ))
          ) : (
            <div className="col-span-full">
              <Card className="border-dashed border-border/80 bg-muted/20">
                <CardContent className="py-16 text-center">
                  <p className="text-sm text-muted-foreground">
                    No services found. Run a repository analysis first.
                  </p>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
