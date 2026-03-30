import { downloadBlob } from '@/lib/export/download'

export function downloadAnalysisJson(
  payload: { analysisType: string; repoId?: string; data: unknown },
  fileBase: string
) {
  const t0 = performance.now()
  const body = JSON.stringify(payload, null, 2)
  const blob = new Blob([body], { type: 'application/json;charset=utf-8' })
  downloadBlob(blob, `${fileBase}.json`)
  console.info('[export]', 'json', fileBase, body.length, 'chars', Math.round(performance.now() - t0), 'ms')
}
