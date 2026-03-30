import { ServiceDetailClient } from './service-detail-client'

type PageProps = {
  params: Promise<{ id: string }> | { id: string }
}

/**
 * Server entry for the dynamic segment so Next.js registers `/services/[id]` correctly
 * (client-only dynamic pages can fail to match in App Router + Turbopack).
 */
export default async function ServiceDetailPage({ params }: PageProps) {
  const resolved = await Promise.resolve(params)
  const raw = resolved?.id ?? ''
  const id = decodeURIComponent(raw)
  return <ServiceDetailClient serviceId={id} />
}
