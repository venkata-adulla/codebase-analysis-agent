'use client'

import { Suspense, useEffect } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { EnterpriseDependencyGraph } from '@/components/dependency-graph/EnterpriseDependencyGraph'
import { useGraphExplorerStore } from '@/stores/graph-explorer-store'

function DependencyGraphPageInner() {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const repositoryId = searchParams.get('repo') || ''
  const resetExplorer = useGraphExplorerStore((s) => s.reset)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const search = window.location.search
    if (search.startsWith('?=') && search.length > 2) {
      const id = decodeURIComponent(search.slice(2).split('&')[0])
      if (id) router.replace(`${pathname}?repo=${encodeURIComponent(id)}`)
    }
  }, [pathname, router])

  useEffect(() => {
    resetExplorer()
  }, [repositoryId, resetExplorer])

  return <EnterpriseDependencyGraph />
}

export default function DependencyGraphPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading dependency graph…</div>}>
      <DependencyGraphPageInner />
    </Suspense>
  )
}
