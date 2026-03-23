import { Suspense } from 'react'
import { ImpactClient } from './impact-client'

function Fallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-sm text-muted-foreground">
      Loading…
    </div>
  )
}

export default function ImpactAnalysisPage() {
  return (
    <Suspense fallback={<Fallback />}>
      <ImpactClient />
    </Suspense>
  )
}
