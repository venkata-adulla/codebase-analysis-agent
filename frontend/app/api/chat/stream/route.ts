import { NextRequest, NextResponse } from 'next/server'

import { getServerBackendBaseUrl } from '@/lib/server-backend-url'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/** SSE chat stream — proxy without short dev rewrite timeouts. */
export async function POST(request: NextRequest) {
  const backend = getServerBackendBaseUrl()
  const url = `${backend}/api/chat/stream`
  const body = await request.text()
  const apiKey =
    request.headers.get('x-api-key') ||
    process.env.NEXT_PUBLIC_API_KEY ||
    'dev-local-key'

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': request.headers.get('content-type') || 'application/json',
        'X-API-Key': apiKey,
      },
      body,
      cache: 'no-store',
    })

    if (!res.ok || !res.body) {
      const text = await res.text()
      return new NextResponse(text, {
        status: res.status,
        headers: {
          'Content-Type': res.headers.get('content-type') || 'application/json',
        },
      })
    }

    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    })
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ detail: `Chat stream proxy failed: ${msg}` }, { status: 502 })
  }
}
