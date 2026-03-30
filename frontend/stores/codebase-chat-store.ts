import { create } from 'zustand'

export interface RelatedNode {
  id: string
  name: string
  reason?: string | null
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  structured?: {
    summary: string
    detailed: string
    impact?: string | null
    relatedNodes: RelatedNode[]
    confidence: number
  }
  /** Used when streaming or non-JSON path; links to graph. */
  relatedNodes?: RelatedNode[]
  pending?: boolean
}

function mkId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `m-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`
}

interface CodebaseChatState {
  open: boolean
  repoId: string
  messages: ChatMessage[]
  toggleOpen: () => void
  setOpen: (open: boolean) => void
  setRepoId: (repoId: string) => void
  pushUser: (text: string) => void
  pushAssistantPlaceholder: () => string
  patchMessage: (id: string, patch: Partial<ChatMessage>) => void
  clear: () => void
}

export const useCodebaseChatStore = create<CodebaseChatState>((set) => ({
  open: false,
  repoId: '',
  messages: [],
  toggleOpen: () => set((s) => ({ open: !s.open })),
  setOpen: (open) => set({ open }),
  setRepoId: (repoId) => set({ repoId }),
  pushUser: (text) =>
    set((s) => ({
      messages: [...s.messages, { id: mkId(), role: 'user', content: text }],
    })),
  pushAssistantPlaceholder: () => {
    const id = mkId()
    set((s) => ({
      messages: [...s.messages, { id, role: 'assistant', content: '', pending: true }],
    }))
    return id
  },
  patchMessage: (id, patch) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    })),
  clear: () => set({ messages: [] }),
}))
