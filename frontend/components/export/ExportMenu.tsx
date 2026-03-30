'use client'

import { useCallback, useState } from 'react'
import { Download, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { exportFileBase } from '@/lib/export/download'
import { downloadAnalysisJson } from '@/lib/export/json-export'
import { downloadCsv, type CsvSection } from '@/lib/export/csv-export'
import { downloadElementAsPng } from '@/lib/export/image-export'
import { downloadAnalysisPdf, type PdfSection } from '@/lib/export/pdf-export'

export type ExportMenuProps = {
  analysisType: string
  pageTitle: string
  /** Filename slug e.g. services, dependency-graph */
  pageSlug: string
  repoId?: string
  repoName?: string
  /** Current view payload — not recomputed on server */
  getJsonData: () => Record<string, unknown>
  getCsvSections?: () => CsvSection[]
  captureRef?: React.RefObject<HTMLElement | null>
  /** Default true when captureRef is set */
  enableImageExport?: boolean
  getPdfSections?: () => PdfSection[]
}

export function ExportMenu({
  analysisType,
  pageTitle,
  pageSlug,
  repoId,
  repoName,
  getJsonData,
  getCsvSections,
  captureRef,
  enableImageExport,
  getPdfSections,
}: ExportMenuProps) {
  const [busy, setBusy] = useState(false)
  const showPng = Boolean(captureRef) && enableImageExport !== false

  const base = useCallback(() => exportFileBase(pageSlug, repoId), [pageSlug, repoId])

  const runJson = useCallback(() => {
    const fileBase = base()
    downloadAnalysisJson(
      {
        analysisType,
        repoId: repoId || '',
        data: getJsonData(),
      },
      fileBase
    )
  }, [analysisType, repoId, getJsonData, base])

  const runCsv = useCallback(() => {
    const sections = getCsvSections?.()
    if (!sections?.length) return
    downloadCsv(sections, base())
  }, [getCsvSections, base])

  const runPng = useCallback(async () => {
    if (!captureRef?.current) return
    setBusy(true)
    try {
      await downloadElementAsPng(captureRef.current, base())
    } finally {
      setBusy(false)
    }
  }, [captureRef, base])

  const runPdf = useCallback(async () => {
    setBusy(true)
    try {
      const sections =
        getPdfSections?.() ??
        ([
          {
            heading: 'Exported data (truncated)',
            body: JSON.stringify(getJsonData(), null, 2).slice(0, 14000),
          },
        ] as PdfSection[])
      await downloadAnalysisPdf({
        title: pageTitle,
        repoLabel: repoName || repoId || '—',
        repoId,
        sections,
        imageElement: showPng && captureRef?.current ? captureRef.current : undefined,
        fileBase: base(),
      })
    } finally {
      setBusy(false)
    }
  }, [getPdfSections, getJsonData, pageTitle, repoName, repoId, captureRef, base, showPng])

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="outline" size="sm" disabled={busy}>
          {busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Download className="mr-1 h-4 w-4" />}
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          Current view & filters
        </DropdownMenuLabel>
        <DropdownMenuItem
          onSelect={(e) => {
            e.preventDefault()
            runJson()
          }}
        >
          JSON
        </DropdownMenuItem>
        {getCsvSections ? (
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault()
              runCsv()
            }}
          >
            CSV
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={(e) => {
            e.preventDefault()
            void runPdf()
          }}
        >
          PDF report
        </DropdownMenuItem>
        {showPng ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault()
                void runPng()
              }}
            >
              PNG (visual)
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
