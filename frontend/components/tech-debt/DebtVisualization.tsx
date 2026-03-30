'use client'

import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from 'recharts'

function formatCategoryLabel(raw: string) {
  return raw
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (l) => l.toUpperCase())
}

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

  const assessmentCoverage = metrics?.assessment_coverage || report?.assessment_coverage || {}
  const coverageFallbackScore = (rawName: string): number => {
    const cov = assessmentCoverage?.[rawName]
    if (!cov || cov.supported === false) return 0
    const confidence = String(cov.confidence || '').toLowerCase()
    if (confidence === 'high') return 6
    if (confidence === 'medium') return 4
    if (confidence === 'low') return 2
    return 0
  }

  // Category distribution
  const categoryData = metrics?.items_by_category
    ? Object.entries(metrics.items_by_category).map(([name, value]) => ({
        name: formatCategoryLabel(name),
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
        name: formatCategoryLabel(name),
        rawName: name,
        rawScore: Number(value),
        score: Number(value) > 0 ? Number(value) : coverageFallbackScore(name),
      }))
    : []
  const scoreExplanation = metrics?.score_explanation || report?.score_explanation || {}
  const overallWeights = scoreExplanation?.overall_weights || {}
  const severityWeights = scoreExplanation?.severity_weights || {}

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
          <p className="mt-3 text-xs text-muted-foreground">
            Higher score means more accumulated technical debt and remediation effort.
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-border/80 bg-card/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-foreground">How the score is calculated</h3>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>
            <span className="font-medium text-foreground">Overall formula:</span>{' '}
            {String(scoreExplanation.overall_formula || 'Weighted average of category scores')}
          </p>
          <p>
            <span className="font-medium text-foreground">Category formula:</span>{' '}
            {String(
              scoreExplanation.category_formula ||
                'Sum of severity-weighted issue impacts, normalized to a 0-100 scale'
            )}
          </p>
          {Object.keys(overallWeights).length > 0 ? (
            <div>
              <p className="font-medium text-foreground">Category weights</p>
              <div className="mt-1 flex flex-wrap gap-2">
                {Object.entries(overallWeights).map(([name, value]) => (
                  <span key={name} className="rounded-full border border-border/70 px-2 py-1 text-xs">
                    {formatCategoryLabel(name)}: {(Number(value) * 100).toFixed(0)}%
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          {Object.keys(severityWeights).length > 0 ? (
            <div>
              <p className="font-medium text-foreground">Severity weights</p>
              <div className="mt-1 flex flex-wrap gap-2">
                {Object.entries(severityWeights).map(([name, value]) => (
                  <span key={name} className="rounded-full border border-border/70 px-2 py-1 text-xs">
                    {formatCategoryLabel(name)}: {Number(value).toFixed(1)}x
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          {Array.isArray(scoreExplanation.notes) && scoreExplanation.notes.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5">
              {scoreExplanation.notes.map((note: string) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>

      {/* Category Distribution */}
      <div className="rounded-xl border border-border/80 bg-card/50 p-6">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Debt by category</h3>
        {categoryData.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
              <Pie
                data={categoryData}
                cx="38%"
                cy="50%"
                labelLine={false}
                label={({ percent }) => `${(percent * 100).toFixed(0)}%`}
                outerRadius={72}
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
              <Legend
                layout="vertical"
                align="right"
                verticalAlign="middle"
                wrapperStyle={{ paddingLeft: 12, fontSize: 12, color: 'hsl(210 40% 96%)' }}
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
        <p className="mb-4 text-sm text-muted-foreground">
          Scores can reflect either detected issues or the current level of analysis coverage. A `0.0` does not always
          mean the repository is risk-free.
        </p>
        {categoryScores.length > 0 ? (
          <div className="space-y-3">
            {categoryScores.map((item) => (
              <div key={item.name}>
                <div className="mb-1 flex justify-between">
                  <div>
                    <span className="text-sm text-foreground">{item.name}</span>
                    {assessmentCoverage[item.rawName] ? (
                      <span className="ml-2 text-xs text-muted-foreground">
                        {assessmentCoverage[item.rawName].supported === false
                          ? 'not fully supported'
                          : assessmentCoverage[item.rawName].confidence === 'low'
                            ? 'limited coverage'
                            : assessmentCoverage[item.rawName].confidence === 'medium'
                              ? 'basic coverage'
                              : 'good coverage'}
                      </span>
                    ) : null}
                  </div>
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
                {assessmentCoverage[item.rawName]?.note ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {String(assessmentCoverage[item.rawName].note)}
                  </p>
                ) : null}
                {item.rawScore === 0 && item.score > 0 ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Showing provisional score from analysis coverage; rerun analysis for issue-based scoring.
                  </p>
                ) : null}
                {item.score === 0 && assessmentCoverage[item.rawName]?.supported !== false ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    No issues were detected for this category in the current analysis window.
                  </p>
                ) : null}
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
