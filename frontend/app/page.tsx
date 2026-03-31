import Link from 'next/link'
import {
  Activity,
  ArrowRight,
  BarChart3,
  Building2,
  Bot,
  GitBranch,
  GitCompare,
  History,
  Layers,
  LayoutDashboard,
  Shield,
  Sparkles,
} from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const modules = [
  {
    href: '/analyze',
    title: 'Analyze repository',
    description: 'Paste a Git URL, GitHub coordinates, or local path to run the full pipeline.',
    icon: GitBranch,
    highlight: true,
  },
  {
    href: '/dashboard',
    title: 'Dashboard',
    description: 'Live overview of queued and completed analyses.',
    icon: LayoutDashboard,
  },
  {
    href: '/dependency-graph',
    title: 'Dependency graph',
    description: 'Interactive dependency and service topology.',
    icon: Layers,
  },
  {
    href: '/architecture',
    title: 'Architecture',
    description: 'System-level view of components, stack signals, and risks.',
    icon: Building2,
  },
  {
    href: '/temporal',
    title: 'Temporal',
    description: 'Timeline and trend insights from repository evolution.',
    icon: History,
  },
  {
    href: '/compare',
    title: 'Compare',
    description: 'Compare analyses or repositories side-by-side.',
    icon: GitCompare,
  },
  {
    href: '/services',
    title: 'Service inventory',
    description: 'Catalog of discovered services and documentation.',
    icon: BarChart3,
  },
  {
    href: '/impact-analysis',
    title: 'Impact analysis',
    description: 'Change impact, risk scoring, and recommendations.',
    icon: Shield,
  },
  {
    href: '/agent-status',
    title: 'Agents & review',
    description: 'Human-in-the-loop checkpoints and agent activity.',
    icon: Bot,
  },
  {
    href: '/tech-debt',
    title: 'Technical debt',
    description: 'Debt metrics, remediation plans, and trends.',
    icon: Activity,
  },
]

export default function Home() {
  return (
    <div className="space-y-12">
      <section className="relative overflow-hidden rounded-2xl border border-border/80 bg-gradient-to-br from-primary/10 via-card to-card p-8 shadow-glow md:p-10">
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary/20 blur-3xl" />
        <div className="relative flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              <Sparkles className="h-3.5 w-3.5" />
              Multi-agent codebase intelligence
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
              Codebase Analysis Agent
            </h1>
            <p className="text-base text-muted-foreground md:text-lg">
              Map dependencies, detect technical debt, document services, and assess change impact
              across polyglot repositories with a production-oriented orchestration stack.
            </p>
          </div>
          <Link
            href="/analyze"
            className={cn(
              buttonVariants({ size: 'lg' }),
              'gap-2 self-start shadow-glow md:self-end'
            )}
          >
            Start with a Git URL
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <div>
        <PageHeader
          title="Operations"
          description="Jump into the workspace area you need. Analysis always begins from the Analyze page or the API."
          className="border-0 pb-4"
        />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {modules.map((m) => {
            const Icon = m.icon
            return (
              <Link key={m.href} href={m.href} className="group block">
                <Card
                  className={cn(
                    'h-full border-border/80 transition-all duration-200',
                    'hover:border-primary/35 hover:bg-card/80 hover:shadow-glow',
                    m.highlight && 'ring-1 ring-primary/20'
                  )}
                >
                  <CardHeader className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/20">
                        <Icon className="h-5 w-5" />
                      </div>
                      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                    </div>
                    <CardTitle className="text-base">{m.title}</CardTitle>
                    <CardDescription className="text-sm leading-relaxed">
                      {m.description}
                    </CardDescription>
                  </CardHeader>
                </Card>
              </Link>
            )
          })}
        </div>
      </div>
    </div>
  )
}
