import { create } from 'zustand'

/** Intensity 0–1 from temporal heatmap; shown on dependency graph nodes when active. */
interface TemporalHeatmapState {
  repoId: string | null
  /** service id -> intensity 0–1 */
  byServiceId: Record<string, number>
  active: boolean
  setOverlay: (repoId: string, modules: { service_id: string; intensity: number }[]) => void
  clear: () => void
}

export const useTemporalHeatmapStore = create<TemporalHeatmapState>((set) => ({
  repoId: null,
  byServiceId: {},
  active: false,
  setOverlay: (repoId, modules) => {
    const m: Record<string, number> = {}
    for (const row of modules) {
      if (row.service_id) m[row.service_id] = Math.min(1, Math.max(0, row.intensity))
    }
    set({ repoId, byServiceId: m, active: Object.keys(m).length > 0 })
  },
  clear: () => set({ repoId: null, byServiceId: {}, active: false }),
}))
