'use client'

import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend } from 'recharts'

interface DebtVisualizationProps {
  metrics: any
  report: any
}

const COLORS = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#f59e0b',
  low: '#84cc16',
}

export default function DebtVisualization({ metrics, report }: DebtVisualizationProps) {
  // Debt score gauge data
  const debtScore = metrics?.total_debt_score || 0
  const scoreColor = debtScore > 75 ? COLORS.critical : debtScore > 50 ? COLORS.high : debtScore > 25 ? COLORS.medium : COLORS.low

  // Category distribution
  const categoryData = metrics?.items_by_category
    ? Object.entries(metrics.items_by_category).map(([name, value]) => ({
        name: name.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()),
        value,
      }))
    : []

  // Severity distribution
  const severityData = metrics?.items_by_severity
    ? Object.entries(metrics.items_by_severity).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value,
        fill: COLORS[name as keyof typeof COLORS] || COLORS.low,
      }))
    : []

  // Category scores
  const categoryScores = metrics?.category_scores
    ? Object.entries(metrics.category_scores).map(([name, value]) => ({
        name: name.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()),
        score: value,
      }))
    : []

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      {/* Debt Score Gauge */}
      <div className="rounded-xl border border-border/80 bg-card/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Overall debt score</h3>
        <div className="text-center">
          <div className="relative inline-block">
            <div
              className="text-6xl font-bold"
              style={{ color: scoreColor }}
            >
              {debtScore.toFixed(1)}
            </div>
            <div className="mt-2 text-sm text-muted-foreground">out of 100</div>
          </div>
          <div className="mt-4">
            <div className="h-4 w-full rounded-full bg-muted">
              <div
                className="h-4 rounded-full transition-all"
                style={{
                  width: `${debtScore}%`,
                  backgroundColor: scoreColor,
                }}
              />
            </div>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {debtScore > 75
              ? 'Critical debt level - Immediate action required'
              : debtScore > 50
              ? 'High debt level - Plan remediation'
              : debtScore > 25
              ? 'Moderate debt level - Monitor closely'
              : 'Low debt level - Good health'}
          </p>
        </div>
      </div>

      {/* Category Distribution */}
      <div className="rounded-xl border border-border/80 bg-card/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Debt by category</h3>
        {categoryData.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={categoryData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {categoryData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={Object.values(COLORS)[index % 4]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(222 47% 8%)',
                  border: '1px solid hsl(217 33% 20%)',
                  borderRadius: 8,
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <div className="py-8 text-center text-muted-foreground">No data available</div>
        )}
      </div>

      {/* Severity Distribution */}
      <div className="rounded-xl border border-border/80 bg-card/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Debt by severity</h3>
        {severityData.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={severityData}>
              <XAxis dataKey="name" stroke="#64748b" tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <YAxis stroke="#64748b" tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(222 47% 8%)',
                  border: '1px solid hsl(217 33% 20%)',
                  borderRadius: 8,
                }}
              />
              <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="py-8 text-center text-muted-foreground">No data available</div>
        )}
      </div>

      {/* Category Scores */}
      <div className="rounded-xl border border-border/80 bg-card/50 p-6 md:col-span-2">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Category scores</h3>
        {categoryScores.length > 0 ? (
          <div className="space-y-3">
            {categoryScores.map((item) => (
              <div key={item.name}>
                <div className="mb-1 flex justify-between">
                  <span className="text-sm text-foreground">{item.name}</span>
                  <span className="text-sm font-semibold text-foreground">{item.score.toFixed(1)}</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted">
                  <div
                    className="h-2 rounded-full"
                    style={{
                      width: `${item.score}%`,
                      backgroundColor:
                        item.score > 75
                          ? COLORS.critical
                          : item.score > 50
                          ? COLORS.high
                          : item.score > 25
                          ? COLORS.medium
                          : COLORS.low,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-8 text-center text-muted-foreground">No data available</div>
        )}
      </div>
    </div>
  )
}
