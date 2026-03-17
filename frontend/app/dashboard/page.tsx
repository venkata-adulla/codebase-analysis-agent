'use client'

import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function DashboardPage() {
  const { data: repositories, isLoading } = useQuery({
    queryKey: ['repositories'],
    queryFn: async () => {
      const response = await axios.get(`${API_URL}/api/repositories/`, {
        headers: { 'X-API-Key': 'dev-local-key' }
      })
      return response.data.repositories || []
    },
  })

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Dashboard</h1>
        
        {isLoading ? (
          <div className="text-center py-12">Loading...</div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="p-6 border rounded-lg">
                <h3 className="text-lg font-semibold mb-2">Repositories</h3>
                <p className="text-3xl font-bold">{repositories?.length || 0}</p>
              </div>
              
              <div className="p-6 border rounded-lg">
                <h3 className="text-lg font-semibold mb-2">Services</h3>
                <p className="text-3xl font-bold">-</p>
              </div>
              
              <div className="p-6 border rounded-lg">
                <h3 className="text-lg font-semibold mb-2">Analyses</h3>
                <p className="text-3xl font-bold">-</p>
              </div>
            </div>
            
            <div className="border rounded-lg p-6">
              <h2 className="text-xl font-semibold mb-4">Recent Repositories</h2>
              {repositories && repositories.length > 0 ? (
                <ul className="space-y-2">
                  {repositories.map((repo: any) => (
                    <li key={repo.id} className="p-3 border rounded">
                      {repo.name || repo.id}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-gray-500">No repositories analyzed yet</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
