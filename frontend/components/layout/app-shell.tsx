'use client'

import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  Bot,
  Building2,
  GitBranch,
  GitCompare,
  History,
  Home,
  Layers,
  LayoutDashboard,
  Shield,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { CodebaseChatRoot } from '@/components/chat/CodebaseChatRoot'

const nav = [
  { href: '/', label: 'Overview', icon: Home },
  { href: '/analyze', label: 'Analyze', icon: GitBranch },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/dependency-graph', label: 'Dependencies', icon: Layers },
  { href: '/architecture', label: 'Architecture', icon: Building2 },
  { href: '/temporal', label: 'Temporal', icon: History },
  { href: '/compare', label: 'Compare', icon: GitCompare },
  { href: '/services', label: 'Services', icon: BarChart3 },
  { href: '/impact-analysis', label: 'Impact', icon: Shield },
  { href: '/tech-debt', label: 'Tech debt', icon: Activity },
  { href: '/agent-status', label: 'Human Review', icon: Bot },
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
    <div className="flex min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-border bg-sidebar lg:flex">
        <div className="flex h-16 items-center gap-3 border-b border-border px-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 ring-1 ring-primary/25">
            <GitBranch className="h-5 w-5 text-primary" aria-hidden />
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold tracking-tight text-foreground">
              Codebase Analysis
            </span>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-3">
          {navItems.map((item) => {
            const itemPath = item.href.split('?')[0]
            const active =
              itemPath === '/'
                ? pathname === '/'
                : pathname === itemPath || pathname.startsWith(`${itemPath}/`)
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  active
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-sm'
                    : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground'
                )}
              >
                <Icon
                  className={cn(
                    'h-[18px] w-[18px] shrink-0',
                    active ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground'
                  )}
                  aria-hidden
                />
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="border-t border-border p-4">
          <div className="inline-flex items-center rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-400">
            Workspace ready
          </div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="flex min-h-screen flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-background/80 px-4 backdrop-blur-md lg:hidden">
          <div className="flex items-center gap-2">
            <GitBranch className="h-5 w-5 text-primary" />
            <span className="font-semibold">Codebase Analysis</span>
          </div>
          <nav className="flex gap-1 overflow-x-auto">
            {navItems.slice(0, 4).map((item) => {
              const itemPath = item.href.split('?')[0]
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium',
                    pathname === itemPath ? 'bg-muted text-foreground' : 'text-muted-foreground'
                  )}
                >
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
        <CodebaseChatRoot />
      </div>
    </div>
  )
}
