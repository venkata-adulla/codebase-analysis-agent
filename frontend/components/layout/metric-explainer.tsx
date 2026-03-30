'use client'

import { Info } from 'lucide-react'

export function MetricExplainer({
  title = 'How to read these metrics',
  points,
  className = '',
}: {
  title?: string
  points: string[]
  className?: string
}) {
  if (!points?.length) return null
  return (
    <details className={`rounded-lg border border-border/60 bg-background/40 p-3 text-xs text-muted-foreground ${className}`}>
      <summary className="flex cursor-pointer list-none items-center gap-1.5 font-medium text-foreground">
        <Info className="h-3.5 w-3.5 text-primary" />
        {title}
      </summary>
      <ul className="mt-2 list-disc space-y-1 pl-4">
        {points.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    </details>
  )
}
