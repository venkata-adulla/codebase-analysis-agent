'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Boxes } from 'lucide-react'
import api from '@/lib/api'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export default function ServicesPage() {
  const { data: services, isLoading } = useQuery({
    queryKey: ['services'],
    queryFn: async () => {
      const response = await api.get('/api/services/')
      return response.data.services || []
    },
  })

  return (
    <div className="space-y-8">
      <PageHeader
        title="Service inventory"
        description="Services discovered and documented during analysis runs."
        actions={
          <Link href="/analyze" className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}>
            Analyze repository
          </Link>
        }
      />

      {isLoading ? (
        <div className="py-20 text-center text-sm text-muted-foreground">Loading…</div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {services && services.length > 0 ? (
            services.map((service: any) => (
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
                  <CardTitle className="text-lg">{service.name}</CardTitle>
                  <CardDescription>
                    Language: {service.language || 'Unknown'}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {service.description && (
                    <p className="text-sm leading-relaxed text-muted-foreground">
                      {service.description}
                    </p>
                  )}
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
