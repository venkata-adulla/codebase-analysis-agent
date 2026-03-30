import { downloadBlob } from '@/lib/export/download'

export async function downloadElementAsPng(el: HTMLElement | null, fileBase: string): Promise<void> {
  if (!el) {
    console.warn('[export] png: no element')
    return
  }
  const t0 = performance.now()
  const { toPng } = await import('html-to-image')
  const dataUrl = await toPng(el, {
    pixelRatio: 2,
    cacheBust: true,
    backgroundColor: '#0b1220',
  })
  const res = await fetch(dataUrl)
  const blob = await res.blob()
  downloadBlob(blob, `${fileBase}.png`)
  console.info('[export]', 'png', fileBase, blob.size, 'bytes', Math.round(performance.now() - t0), 'ms')
}
