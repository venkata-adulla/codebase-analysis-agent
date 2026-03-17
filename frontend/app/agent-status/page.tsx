'use client'

import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'

export default function AgentStatusPage() {
  const { data: checkpoints, isLoading } = useQuery({
    queryKey: ['human-review-checkpoints'],
    queryFn: async () => {
      try {
        const response = await api.get('/api/human-review/checkpoints')
        return response.data.checkpoints || []
      } catch (error) {
        return []
      }
    },
    refetchInterval: 5000, // Poll every 5 seconds
  })

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Agent Status & Human Review</h1>
        
        {isLoading ? (
          <div className="text-center py-12">Loading...</div>
        ) : (
          <div className="space-y-6">
            <div className="p-6 border rounded-lg">
              <h2 className="text-xl font-semibold mb-4">
                Pending Checkpoints ({checkpoints?.filter((c: any) => c.status === 'pending').length || 0})
              </h2>
              
              {checkpoints && checkpoints.length > 0 ? (
                <div className="space-y-4">
                  {checkpoints
                    .filter((c: any) => c.status === 'pending')
                    .map((checkpoint: any) => (
                      <div key={checkpoint.id} className="p-4 border rounded-lg">
                        <div className="flex justify-between items-start mb-2">
                          <div>
                            <p className="font-semibold">{checkpoint.agent}</p>
                            <p className="text-sm text-gray-600">{checkpoint.reason}</p>
                          </div>
                          <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-sm">
                            Pending
                          </span>
                        </div>
                        
                        <p className="mb-2">{checkpoint.question}</p>
                        
                        {checkpoint.options && checkpoint.options.length > 0 && (
                          <div className="mt-2">
                            <p className="text-sm font-medium mb-1">Options:</p>
                            <ul className="list-disc list-inside text-sm">
                              {checkpoint.options.map((opt: string, idx: number) => (
                                <li key={idx}>{opt}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    ))}
                </div>
              ) : (
                <p className="text-gray-500">No pending checkpoints</p>
              )}
            </div>
            
            <div className="p-6 border rounded-lg">
              <h2 className="text-xl font-semibold mb-4">Resolved Checkpoints</h2>
              
              {checkpoints && checkpoints.length > 0 ? (
                <div className="space-y-4">
                  {checkpoints
                    .filter((c: any) => c.status === 'resolved')
                    .map((checkpoint: any) => (
                      <div key={checkpoint.id} className="p-4 border rounded-lg opacity-75">
                        <div className="flex justify-between items-start mb-2">
                          <div>
                            <p className="font-semibold">{checkpoint.agent}</p>
                            <p className="text-sm text-gray-600">{checkpoint.reason}</p>
                          </div>
                          <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-sm">
                            Resolved
                          </span>
                        </div>
                        
                        {checkpoint.response && (
                          <p className="text-sm mt-2">
                            <span className="font-medium">Response:</span> {checkpoint.response}
                          </p>
                        )}
                      </div>
                    ))}
                </div>
              ) : (
                <p className="text-gray-500">No resolved checkpoints</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
