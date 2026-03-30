'use client'

import { Suspense } from 'react'
import { CodebaseChatPanel } from '@/components/chat/CodebaseChatPanel'

export function CodebaseChatRoot() {
  return (
    <Suspense fallback={null}>
      <CodebaseChatPanel />
    </Suspense>
  )
}
