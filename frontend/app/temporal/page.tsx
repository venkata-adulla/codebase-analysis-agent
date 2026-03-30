import { Suspense } from 'react'
import { TemporalClient } from './temporal-client'

function Fallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-sm text-muted-foreground">
      Loading temporal view…
    </div>
  )
}

export default function TemporalPage() {
  return (
    <Suspense fallback={<Fallback />}>
      <TemporalClient />
    </Suspense>
  )
}
