import { create } from 'zustand'
import type { ViewLevel } from '@/lib/graph/model'

export interface GraphExplorerState {
  selectedNodeId: string | null
  focusMode: boolean
  simplifiedView: boolean
  /** Package keys with expanded cluster (show member services). */
  expandedPackageKeys: string[]
  viewLevel: ViewLevel
  /** Service drilled for "module" exploration (same package + neighbors). */
  drillServiceId: string | null
  hoveredNodeId: string | null
  setSelected: (id: string | null) => void
  setFocusMode: (v: boolean) => void
  setSimplifiedView: (v: boolean) => void
  togglePackageExpanded: (key: string) => void
  setViewLevel: (v: ViewLevel) => void
  setDrillServiceId: (id: string | null) => void
  setHoveredNodeId: (id: string | null) => void
  reset: () => void
}

const initial = {
  selectedNodeId: null as string | null,
  focusMode: false,
  simplifiedView: true,
  expandedPackageKeys: [] as string[],
  viewLevel: 'service' as ViewLevel,
  drillServiceId: null as string | null,
  hoveredNodeId: null as string | null,
}

export const useGraphExplorerStore = create<GraphExplorerState>((set) => ({
  ...initial,
  setSelected: (id) => set({ selectedNodeId: id }),
  setFocusMode: (v) => set({ focusMode: v }),
  setSimplifiedView: (v) => set({ simplifiedView: v }),
  togglePackageExpanded: (key) =>
    set((s) => ({
      expandedPackageKeys: s.expandedPackageKeys.includes(key)
        ? s.expandedPackageKeys.filter((k) => k !== key)
        : [...s.expandedPackageKeys, key],
    })),
  setViewLevel: (v) => set({ viewLevel: v }),
  setDrillServiceId: (id) => set({ drillServiceId: id }),
  setHoveredNodeId: (id) => set({ hoveredNodeId: id }),
  reset: () => set({ ...initial }),
}))
