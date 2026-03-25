/**
 * API requests use baseURL `/api` in the browser; Next rewrites forward to the real FastAPI server.
 *
 * If you see: "Failed to proxy ... ECONNREFUSED 127.0.0.1:8000"
 *   1. Start the backend: `cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000`
 *   2. If `next dev` runs inside WSL but uvicorn runs on Windows, set API_PROXY_TARGET to your
 *      Windows host IP (from WSL: `grep nameserver /etc/resolv.conf`) or set WSL_USE_WINDOWS_HOST=1
 */
const fs = require('fs')

function readWslWindowsHostIp() {
  try {
    const text = fs.readFileSync('/etc/resolv.conf', 'utf8')
    const m = text.match(/^nameserver\s+(\d{1,3}(?:\.\d{1,3}){3})\s*$/m)
    return m ? m[1] : null
  } catch {
    return null
  }
}

function resolveBackendBaseUrl() {
  const explicit = process.env.API_PROXY_TARGET?.trim()
  if (explicit) return explicit.replace(/\/$/, '')

  const publicUrl = process.env.NEXT_PUBLIC_API_URL?.trim()
  if (publicUrl) return publicUrl.replace(/\/$/, '')

  const useWin =
    process.env.WSL_USE_WINDOWS_HOST === '1' ||
    process.env.WSL_USE_WINDOWS_HOST === 'true'
  if (useWin) {
    const ip = readWslWindowsHostIp()
    if (ip) return `http://${ip}:8000`
  }

  return 'http://127.0.0.1:8000'
}

const backendBaseUrl = resolveBackendBaseUrl()

if (process.env.NODE_ENV === 'development') {
  // eslint-disable-next-line no-console
  console.info(`[next.config] Rewriting /api/* → ${backendBaseUrl}/api/*`)
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendBaseUrl}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
