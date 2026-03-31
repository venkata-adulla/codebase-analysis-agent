'use client'

import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

/**
 * Block code is rendered as <pre><code>…</code></pre> by react-markdown.
 * The `code` node must not wrap another <pre> (invalid inside <p>).
 */
const mdComponents = {
  h1: ({ children }: { children?: ReactNode }) => (
    <h1 className="mb-2 mt-4 text-lg font-semibold text-foreground first:mt-0">{children}</h1>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2 className="mb-2 mt-4 text-base font-semibold text-foreground">{children}</h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3 className="mb-1.5 mt-3 text-sm font-semibold text-foreground">{children}</h3>
  ),
  h4: ({ children }: { children?: ReactNode }) => (
    <h4 className="mb-1.5 mt-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground first:mt-0">
      {children}
    </h4>
  ),
  p: ({ children }: { children?: ReactNode }) => (
    <p className="mb-3 last:mb-0 text-muted-foreground">{children}</p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="mb-3 list-inside list-disc space-y-1 text-muted-foreground">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="mb-3 list-inside list-decimal space-y-1 text-muted-foreground">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold text-foreground">{children}</strong>
  ),
  a: ({ href, children }: { href?: string; children?: ReactNode }) => (
    <a
      href={href}
      className="text-primary underline underline-offset-2 hover:text-primary/90"
      target="_blank"
      rel="noreferrer"
    >
      {children}
    </a>
  ),
  code: (props: { inline?: boolean; className?: string; children?: ReactNode }) => {
    const { inline, className, children } = props
    if (inline) {
      return (
        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">{children}</code>
      )
    }
    return <code className={className}>{children}</code>
  },
  pre: ({ children }: { children?: ReactNode }) => (
    <pre className="mb-3 overflow-x-auto rounded-lg bg-muted/80 p-3 font-mono text-xs leading-relaxed text-foreground">
      {children}
    </pre>
  ),
  hr: () => <hr className="my-4 border-border" />,
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="border-l-2 border-primary/40 pl-3 text-muted-foreground">{children}</blockquote>
  ),
}

export function MarkdownBody({
  children,
  className,
  compact,
}: {
  children?: ReactNode
  className?: string
  compact?: boolean
}) {
  const content =
    typeof children === 'string'
      ? children
      : Array.isArray(children)
        ? children
            .map((child) => (typeof child === 'string' ? child : child == null ? '' : String(child)))
            .join('')
        : children == null
          ? ''
          : String(children)

  if (!content.trim()) return null
  return (
    <div
      className={cn(
        compact ? 'max-h-64 overflow-y-auto pr-1' : '',
        'markdown-body',
        className
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
