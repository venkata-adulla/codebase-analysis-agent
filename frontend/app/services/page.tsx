'use client'

import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import Link from 'next/link'

export default function ServicesPage() {
  const { data: services, isLoading } = useQuery({
    queryKey: ['services'],
    queryFn: async () => {
      const response = await api.get('/api/services/')
      return response.data.services || []
    },
  })

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Service Inventory</h1>
        
        {isLoading ? (
          <div className="text-center py-12">Loading...</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {services && services.length > 0 ? (
              services.map((service: any) => (
                <div
                  key={service.id}
                  className="p-6 border rounded-lg hover:shadow-lg transition-shadow"
                >
                  <h2 className="text-xl font-semibold mb-2">{service.name}</h2>
                  <p className="text-sm text-gray-500 mb-2">Language: {service.language || 'Unknown'}</p>
                  {service.description && (
                    <p className="text-gray-700 mb-4">{service.description}</p>
                  )}
                  <Link
                    href={`/services/${service.id}`}
                    className="text-blue-600 hover:underline"
                  >
                    View Details →
                  </Link>
                </div>
              ))
            ) : (
              <div className="col-span-full text-center py-12 text-gray-500">
                No services found. Start by analyzing a repository.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
