import { Suspense } from 'react'
import { TechDebtClient } from './tech-debt-client'

function TechDebtFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-sm text-muted-foreground">
      Loading workspace…
    </div>
  )
}

export default function TechDebtPage() {
  return (
    <Suspense fallback={<TechDebtFallback />}>
      <TechDebtClient />
    </Suspense>
  )
}
