import { NextRequest, NextResponse } from 'next/server'

import { getServerBackendBaseUrl } from '@/lib/server-backend-url'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Long-running chat (RAG + LLM). Same rationale as temporal-data: the default Next.js
 * dev rewrite proxy often drops slow responses (ECONNRESET), which surfaces in the
 * browser as "Failed to fetch" — unrelated to OPENAI_API_KEY.
 */
export async function POST(request: NextRequest) {
  const backend = getServerBackendBaseUrl()
  const url = `${backend}/api/chat/`
  const body = await request.text()
  const apiKey =
    request.headers.get('x-api-key') ||
    process.env.NEXT_PUBLIC_API_KEY ||
    'dev-local-key'

  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), 180_000)

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': request.headers.get('content-type') || 'application/json',
        'X-API-Key': apiKey,
      },
      body,
      signal: ctrl.signal,
      cache: 'no-store',
    })

    const text = await res.text()
    return new NextResponse(text, {
      status: res.status,
      headers: {
        'Content-Type': res.headers.get('content-type') || 'application/json',
      },
    })
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ detail: `Chat proxy failed: ${msg}` }, { status: 502 })
  } finally {
    clearTimeout(t)
  }
}
