import { Suspense } from 'react'
import { ArchitectureClient } from './architecture-client'

function Fallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-sm text-muted-foreground">
      Loading architecture…
    </div>
  )
}

export default function ArchitecturePage() {
  return (
    <Suspense fallback={<Fallback />}>
      <ArchitectureClient />
    </Suspense>
  )
}
