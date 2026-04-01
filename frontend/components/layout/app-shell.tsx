'use client'

import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { cn } from '@/lib/utils'
import { CodebaseChatRoot } from '@/components/chat/CodebaseChatRoot'

/** Brand bar background — #2e2d78 */
const BRAND = '#2e2d78'

const nav = [
  { href: '/analyze', label: 'Analyze' },
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/dependency-graph', label: 'Dependencies' },
  { href: '/architecture', label: 'Architecture' },
  { href: '/temporal', label: 'Temporal' },
  { href: '/compare', label: 'Compare' },
  { href: '/services', label: 'Services' },
  { href: '/impact-analysis', label: 'Impact' },
  { href: '/tech-debt', label: 'Tech Debt' },
  { href: '/agent-status', label: 'Human Review' },
]

const LAST_REPO_KEY = 'caa:lastRepositoryId'
const repoScopedRoutes = new Set([
  '/dependency-graph',
  '/architecture',
  '/temporal',
  '/services',
  '/impact-analysis',
  '/tech-debt',
  '/agent-status',
])

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [lastRepoId, setLastRepoId] = useState('')

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      setLastRepoId(localStorage.getItem(LAST_REPO_KEY) || '')
    } catch {
      /* ignore */
    }
  }, [pathname])

  const currentRepoId = searchParams.get('repo') || lastRepoId

  const navItems = useMemo(
    () =>
      nav.map((item) => {
        if (!currentRepoId || !repoScopedRoutes.has(item.href)) {
          return item
        }
        return {
          ...item,
          href: `${item.href}?repo=${encodeURIComponent(currentRepoId)}`,
        }
      }),
    [currentRepoId]
  )

  return (
    <div className="flex min-h-screen flex-col bg-page">
      {/* Top bar — reference: brand strip, title left, nav links with yellow underline on active */}
      <header
        className="sticky top-0 z-50 border-b border-black/10 shadow-sm"
        style={{ backgroundColor: BRAND }}
      >
        <div className="mx-auto flex h-14 max-w-[1600px] items-stretch gap-4 px-4 sm:px-6 lg:px-8">
          <Link
            href="/"
            className="flex shrink-0 items-center text-base font-bold tracking-tight text-white sm:text-lg"
          >
            Repository Analysis
          </Link>
          <nav
            className="scrollbar-thin flex min-h-0 min-w-0 flex-1 items-stretch justify-end gap-0 overflow-x-auto sm:justify-center sm:gap-1 lg:gap-2"
            aria-label="Main"
          >
            {navItems.map((item) => {
              const itemPath = item.href.split('?')[0]
              const active =
                pathname === itemPath || pathname.startsWith(`${itemPath}/`)
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'flex shrink-0 items-center whitespace-nowrap border-b-4 px-2.5 text-sm font-medium transition-colors sm:px-3',
                    active
                      ? 'border-[#ffd700] text-white'
                      : 'border-transparent text-white/90 hover:border-white/25 hover:text-white'
                  )}
                >
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </div>
      </header>

      <main className="flex-1 px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
      <CodebaseChatRoot />
    </div>
  )
}
