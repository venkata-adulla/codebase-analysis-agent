import type { GraphLayer } from './model'
import type { RawApiNode } from './model'

/** Map a service to architecture band: API (surface) → core → utils. */
export function assignLayer(node: RawApiNode, displayName: string): GraphLayer {
  const n = displayName.toLowerCase()
  const cls = (node.classification || '').toLowerCase()

  if (cls === 'package_cluster') return 'core'
  if (Number(node.entry_point_count || 0) > 0) return 'api'
  if (cls === 'entrypoint' || cls === 'package_root') return 'api'

  if (
    /\b(__main__|cli|console|entry|_main)\b/.test(n) ||
    n.endsWith('.__init__') ||
    n.includes('__main__')
  ) {
    return 'api'
  }

  if (
    /\b(util|utils|helpers?|compat|_compat|_textwrap|_winconsole|_termui_impl)\b/.test(n) ||
    /^_/.test(displayName.split('.').pop() || '')
  ) {
    return 'utils'
  }

  if (
    /\b(core|parser|engine|shell|format|termui|types|decorators|globals|completion)\b/.test(n) ||
    cls === 'core_library'
  ) {
    return 'core'
  }

  if (cls === 'test' || cls === 'example' || cls === 'documentation') return 'utils'

  return 'core'
}

export function layerPartition(layer: GraphLayer): string {
  switch (layer) {
    case 'api':
      return '0'
    case 'core':
      return '1'
    case 'utils':
      return '2'
    default:
      return '1'
  }
}
