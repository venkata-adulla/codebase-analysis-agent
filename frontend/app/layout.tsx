import type { Metadata } from 'next'
import { Suspense } from 'react'
import { Plus_Jakarta_Sans } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'
import { AppShell } from '@/components/layout/app-shell'

const sans = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Repository Analysis Agent',
  description: 'Enterprise AI-powered codebase analysis, dependency mapping, and impact assessment.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`${sans.variable} font-sans`}>
        <Providers>
          <Suspense fallback={<div className="min-h-screen bg-background" />}>
            <AppShell>{children}</AppShell>
          </Suspense>
        </Providers>
      </body>
    </html>
  )
}
