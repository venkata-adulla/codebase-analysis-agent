'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MessageCircle, X, Loader2, Trash2, ExternalLink, Sparkles, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ExportMenu } from '@/components/export/ExportMenu'
import { MetricExplainer } from '@/components/layout/metric-explainer'
import type { CsvSection } from '@/lib/export/csv-export'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import {
  useCodebaseChatStore,
  type ChatMessage,
  type RelatedNode,
} from '@/stores/codebase-chat-store'

const LS_REPO = 'codebase-chat-repo-id'

const SUGGESTED = [
  'What does the main application service do?',
  'Which services depend on the API layer?',
  'Where is authentication or security-sensitive logic described?',
  'What might break if I change a highly connected module?',
  'Which parts of the graph look tightly coupled?',
]

function buildHistory(messages: ChatMessage[]): { role: string; content: string }[] {
  const out: { role: string; content: string }[] = []
  for (const m of messages) {
    if (m.pending) continue
    if (m.role === 'user') {
      out.push({ role: 'user', content: m.content })
    } else if (m.role === 'assistant' && m.content.trim()) {
      out.push({ role: 'assistant', content: m.content })
    }
  }
  return out.slice(-16)
}

async function postChatJson(body: {
  query: string
  repoId: string
  history: { role: string; content: string }[]
}) {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'
  const res = await fetch('/api/chat/', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify({
      query: body.query,
      repoId: body.repoId,
      history: body.history,
      use_cache: true,
    }),
  })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || res.statusText)
  }
  return res.json() as Promise<{
    answer: string
    summary: string
    detailed: string
    impact?: string | null
    relatedNodes: RelatedNode[]
    confidence: number
  }>
}

async function streamChat(
  body: {
    query: string
    repoId: string
    history: { role: string; content: string }[]
  },
  onMeta: (related: { id: string; name: string }[]) => void,
  onToken: (chunk: string) => void
): Promise<void> {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY || 'dev-local-key'
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify({
      query: body.query,
      repoId: body.repoId,
      history: body.history,
      use_cache: true,
    }),
  })
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => '')
    throw new Error(t || res.statusText)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const block of parts) {
      const line = block.trim()
      if (!line.startsWith('data: ')) continue
      let data: Record<string, unknown>
      try {
        data = JSON.parse(line.slice(6)) as Record<string, unknown>
      } catch {
        continue
      }
      if (data.type === 'meta' && Array.isArray(data.relatedNodes)) {
        onMeta(data.relatedNodes as { id: string; name: string }[])
      } else if (data.type === 'token' && typeof data.chunk === 'string') {
        onToken(data.chunk)
      } else if (data.type === 'error') {
        throw new Error(String(data.message || 'Stream error'))
      }
    }
  }
}

function RelatedNodeLinks({ nodes, repoId }: { nodes: RelatedNode[]; repoId: string }) {
  if (!nodes.length) return null
  return (
    <section className="mt-3 border-t border-border/60 pt-3">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Related modules / services
      </h4>
      <ul className="mt-1 space-y-2">
        {nodes.map((n) => (
          <li
            key={n.id}
            className="rounded-md border border-border/60 bg-muted/20 px-2 py-1.5 text-xs"
          >
            <span className="font-medium text-foreground">{n.name}</span>
            {n.reason ? <span className="text-muted-foreground"> — {n.reason}</span> : null}
            {repoId ? (
              <div className="mt-1">
                <Link
                  href={`/dependency-graph?repo=${encodeURIComponent(repoId)}&focus=${encodeURIComponent(n.id)}`}
                  className="inline-flex items-center gap-1 text-primary hover:underline"
                >
                  <ExternalLink className="h-3 w-3" />
                  View in graph
                </Link>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}

function StructuredAssistant({
  msg,
  repoId,
}: {
  msg: ChatMessage
  repoId: string
}) {
  const s = msg.structured
  if (!s) {
    return (
      <div>
        <div className="prose prose-invert prose-sm max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
        </div>
        {msg.relatedNodes?.length ? <RelatedNodeLinks nodes={msg.relatedNodes} repoId={repoId} /> : null}
      </div>
    )
  }
  return (
    <div className="space-y-3 text-sm">
      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-primary">Summary</h4>
        <p className="mt-1 text-foreground/95">{s.summary || '—'}</p>
      </section>
      {s.detailed ? (
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Details</h4>
          <div className="prose prose-invert prose-sm mt-1 max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.detailed}</ReactMarkdown>
          </div>
        </section>
      ) : null}
      {s.impact ? (
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-amber-500/90">Impact</h4>
          <div className="prose prose-invert prose-sm mt-1 max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.impact}</ReactMarkdown>
          </div>
        </section>
      ) : null}
      {s.relatedNodes?.length ? (
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Related modules / services
          </h4>
          <ul className="mt-1 space-y-2">
            {s.relatedNodes.map((n) => (
              <li
                key={n.id}
                className="rounded-md border border-border/60 bg-muted/20 px-2 py-1.5 text-xs"
              >
                <span className="font-medium text-foreground">{n.name}</span>
                {n.reason ? (
                  <span className="text-muted-foreground"> — {n.reason}</span>
                ) : null}
                {repoId ? (
                  <div className="mt-1">
                    <Link
                      href={`/dependency-graph?repo=${encodeURIComponent(repoId)}&focus=${encodeURIComponent(n.id)}`}
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      <ExternalLink className="h-3 w-3" />
                      View in graph
                    </Link>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <p className="text-[11px] text-muted-foreground">
        Confidence: {Math.round((s.confidence ?? 0) * 100)}% (grounded in retrieved analysis data)
      </p>
    </div>
  )
}

export function CodebaseChatPanel() {
  const searchParams = useSearchParams()
  const repoFromUrl = searchParams.get('repo') || ''

  const open = useCodebaseChatStore((s) => s.open)
  const toggleOpen = useCodebaseChatStore((s) => s.toggleOpen)
  const repoId = useCodebaseChatStore((s) => s.repoId)
  const setRepoIdStore = useCodebaseChatStore((s) => s.setRepoId)
  const messages = useCodebaseChatStore((s) => s.messages)
  const pushUser = useCodebaseChatStore((s) => s.pushUser)
  const pushAssistantPlaceholder = useCodebaseChatStore((s) => s.pushAssistantPlaceholder)
  const patchMessage = useCodebaseChatStore((s) => s.patchMessage)
  const clear = useCodebaseChatStore((s) => s.clear)

  const [input, setInput] = useState('')
  const [repoInput, setRepoInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [preferStream] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const chatPanelExportRef = useRef<HTMLDivElement>(null)

  const setRepoId = useCallback(
    (id: string) => {
      setRepoIdStore(id)
      if (typeof window !== 'undefined' && id) {
        try {
          localStorage.setItem(LS_REPO, id)
        } catch {
          /* ignore */
        }
      }
    },
    [setRepoIdStore]
  )

  useEffect(() => {
    if (repoFromUrl) {
      setRepoId(repoFromUrl)
      setRepoInput(repoFromUrl)
      return
    }
    try {
      const saved = localStorage.getItem(LS_REPO)
      if (saved) {
        setRepoId(saved)
        setRepoInput(saved)
      }
    } catch {
      /* ignore */
    }
  }, [repoFromUrl, setRepoId])

  useEffect(() => {
    if (!open) return
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, open])

  const effectiveRepo = repoInput.trim() || repoId

  const send = useCallback(async () => {
    const q = input.trim()
    if (!q || !effectiveRepo || loading) return
    setInput('')
    pushUser(q)
    const assistantId = pushAssistantPlaceholder()
    setLoading(true)

    const history = buildHistory(
      useCodebaseChatStore.getState().messages.filter((m) => m.id !== assistantId)
    )

    try {
      if (preferStream) {
        let text = ''
        let metaNodes: { id: string; name: string }[] = []
        await streamChat(
          { query: q, repoId: effectiveRepo, history },
          (related) => {
            metaNodes = related
          },
          (chunk) => {
            text += chunk
            patchMessage(assistantId, { content: text })
          }
        )
        patchMessage(assistantId, {
          pending: false,
          content: text,
          relatedNodes: metaNodes.map((n) => ({
            id: n.id,
            name: n.name || n.id,
            reason: 'Retrieved as relevant context for this question.',
          })),
        })
      } else {
        const data = await postChatJson({ query: q, repoId: effectiveRepo, history })
        patchMessage(assistantId, {
          pending: false,
          content: data.answer,
          structured: {
            summary: data.summary,
            detailed: data.detailed,
            impact: data.impact ?? null,
            relatedNodes: data.relatedNodes || [],
            confidence: data.confidence,
          },
        })
      }
    } catch (e) {
      const err = e instanceof Error ? e.message : 'Request failed'
      try {
        const data = await postChatJson({ query: q, repoId: effectiveRepo, history })
        patchMessage(assistantId, {
          pending: false,
          content: data.answer,
          structured: {
            summary: data.summary,
            detailed: data.detailed,
            impact: data.impact ?? null,
            relatedNodes: data.relatedNodes || [],
            confidence: data.confidence,
          },
        })
      } catch {
        patchMessage(assistantId, {
          pending: false,
          content: `**Error**\n\n${err}`,
        })
      }
    } finally {
      setLoading(false)
    }
  }, [
    input,
    effectiveRepo,
    loading,
    preferStream,
    pushUser,
    pushAssistantPlaceholder,
    patchMessage,
  ])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  const suggestedVisible = useMemo(() => open && messages.length === 0, [open, messages.length])

  return (
    <>
      <button
        type="button"
        onClick={() => toggleOpen()}
        className={cn(
          'fixed bottom-6 right-6 z-[100] flex h-14 w-14 items-center justify-center rounded-full',
          'bg-primary text-primary-foreground shadow-lg ring-2 ring-primary/30 transition hover:bg-primary/90',
          open && 'ring-primary'
        )}
        aria-label={open ? 'Close codebase assistant' : 'Open codebase assistant'}
      >
        {open ? <X className="h-6 w-6" /> : <MessageCircle className="h-6 w-6" />}
      </button>

      {open ? (
        <div
          ref={chatPanelExportRef}
          className={cn(
            'fixed bottom-24 right-6 z-[100] flex w-[min(100vw-2rem,420px)] flex-col overflow-hidden rounded-2xl',
            'border border-border bg-card shadow-2xl ring-1 ring-border/80'
          )}
          style={{ maxHeight: 'min(78vh, 720px)' }}
        >
          <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-4 py-3">
            <Sparkles className="h-5 w-5 shrink-0 text-primary" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold leading-tight">Codebase assistant</p>
              <p className="text-[11px] text-muted-foreground">
                RAG over services, docs, and dependency edges — answers are grounded in your analysis data.
              </p>
            </div>
            <ExportMenu
              analysisType="chat"
              pageTitle="Codebase assistant"
              pageSlug="chat"
              repoId={effectiveRepo || undefined}
              captureRef={chatPanelExportRef}
              getJsonData={() => ({
                repositoryId: effectiveRepo || null,
                messages: messages.map((m) => ({
                  id: m.id,
                  role: m.role,
                  content: m.content,
                  pending: m.pending,
                  structured: m.structured,
                })),
              })}
              getCsvSections={() => {
                const sections: CsvSection[] = [
                  {
                    name: 'Messages',
                    headers: ['role', 'content'],
                    rows: messages
                      .filter((m) => !m.pending)
                      .map((m) => [m.role, m.content.replace(/\r?\n/g, ' ').slice(0, 8000)]),
                  },
                ]
                return sections
              }}
              getPdfSections={() => [
                {
                  heading: 'Transcript',
                  body: messages
                    .filter((m) => !m.pending && m.content.trim())
                    .map((m) => `${m.role.toUpperCase()}: ${m.content}`)
                    .join('\n\n')
                    .slice(0, 12000),
                },
              ]}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0"
              onClick={() => clear()}
              title="Clear chat"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>

          <div className="space-y-2 border-b border-border/80 px-4 py-2">
            <label className="text-[11px] font-medium text-muted-foreground" htmlFor="chat-repo-id">
              Repository ID
            </label>
            <Input
              id="chat-repo-id"
              placeholder="Paste repository UUID (from Analyze or URL ?repo=…)"
              value={repoInput}
              onChange={(e) => {
                setRepoInput(e.target.value)
                setRepoId(e.target.value.trim())
              }}
              className="h-9 text-xs"
            />
          </div>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
            <MetricExplainer
              title="How to read chat confidence"
              points={[
                'Confidence % indicates how strongly retrieved repository context supports the answer.',
                'Higher confidence does not guarantee correctness; verify critical decisions against source code.',
              ]}
            />
            {suggestedVisible ? (
              <div className="space-y-2">
                <p className="text-[11px] font-medium text-muted-foreground">Suggested</p>
                <div className="flex flex-col gap-1.5">
                  {SUGGESTED.map((s) => (
                    <button
                      key={s}
                      type="button"
                      className="rounded-lg border border-border/60 bg-muted/15 px-2.5 py-2 text-left text-xs text-foreground/90 hover:bg-muted/40"
                      onClick={() => setInput(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {messages.map((m) => (
              <div
                key={m.id}
                className={cn(
                  'rounded-xl px-3 py-2.5 text-sm',
                  m.role === 'user'
                    ? 'ml-6 bg-primary/15 text-foreground'
                    : 'mr-2 border border-border/50 bg-background/80'
                )}
              >
                {m.role === 'user' ? (
                  <p className="whitespace-pre-wrap">{m.content}</p>
                ) : m.pending && !m.content ? (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Retrieving context and generating…
                  </div>
                ) : (
                  <StructuredAssistant msg={m} repoId={effectiveRepo} />
                )}
              </div>
            ))}
          </div>

          <div className="border-t border-border p-3">
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={
                  effectiveRepo
                    ? 'Ask about architecture, dependencies, impact…'
                    : 'Set repository ID above first'
                }
                disabled={!effectiveRepo || loading}
                rows={2}
                className={cn(
                  'min-h-[44px] flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm',
                  'ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
                )}
              />
              <Button
                type="button"
                size="icon"
                className="shrink-0 self-end"
                disabled={!effectiveRepo || loading || !input.trim()}
                onClick={() => void send()}
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
