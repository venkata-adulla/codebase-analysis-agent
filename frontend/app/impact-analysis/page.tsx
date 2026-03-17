'use client'

import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'

export default function ImpactAnalysisPage() {
  const [changeDescription, setChangeDescription] = useState('')
  const [repositoryId, setRepositoryId] = useState('')

  const { data: analysis, mutate: runAnalysis, isPending } = useMutation({
    mutationFn: async (data: { repository_id: string; change_description: string }) => {
      const response = await api.post('/api/impact-analysis/analyze', data)
      return response.data
    },
  })

  const handleAnalyze = () => {
    if (repositoryId && changeDescription) {
      runAnalysis({
        repository_id: repositoryId,
        change_description: changeDescription,
      })
    }
  }

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Impact Analysis</h1>
        
        <div className="space-y-6">
          <div className="p-6 border rounded-lg">
            <h2 className="text-xl font-semibold mb-4">Run Impact Analysis</h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Repository ID
                </label>
                <input
                  type="text"
                  value={repositoryId}
                  onChange={(e) => setRepositoryId(e.target.value)}
                  className="w-full p-2 border rounded"
                  placeholder="Enter repository ID"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">
                  Change Description
                </label>
                <textarea
                  value={changeDescription}
                  onChange={(e) => setChangeDescription(e.target.value)}
                  className="w-full p-2 border rounded"
                  rows={4}
                  placeholder="Describe the change you want to analyze..."
                />
              </div>
              
              <Button onClick={handleAnalyze} disabled={isPending}>
                {isPending ? 'Analyzing...' : 'Analyze Impact'}
              </Button>
            </div>
          </div>
          
          {analysis && (
            <div className="p-6 border rounded-lg">
              <h2 className="text-xl font-semibold mb-4">Analysis Results</h2>
              
              <div className="mb-4">
                <span className={`px-3 py-1 rounded text-sm font-semibold ${
                  analysis.risk_level === 'critical' ? 'bg-red-100 text-red-800' :
                  analysis.risk_level === 'high' ? 'bg-orange-100 text-orange-800' :
                  analysis.risk_level === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                  'bg-green-100 text-green-800'
                }`}>
                  Risk Level: {analysis.risk_level?.toUpperCase()}
                </span>
              </div>
              
              <div className="mb-4">
                <h3 className="font-semibold mb-2">
                  Impacted Services ({analysis.total_impacted || 0})
                </h3>
                <ul className="space-y-2">
                  {analysis.impacted_services?.map((service: any, index: number) => (
                    <li key={index} className="p-3 border rounded">
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="font-medium">{service.service_name}</p>
                          <p className="text-sm text-gray-600">{service.reason}</p>
                        </div>
                        <span className="text-sm font-semibold">
                          Impact: {(service.impact_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
              
              {analysis.recommendations && analysis.recommendations.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-2">Recommendations</h3>
                  <ul className="list-disc list-inside space-y-1">
                    {analysis.recommendations.map((rec: string, index: number) => (
                      <li key={index}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
