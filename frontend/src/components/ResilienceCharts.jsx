import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  AreaChart,
  Area,
} from 'recharts'

const THEME = {
  navy: '#000080',
  saffron: '#FF9933',
  green: '#128807',
  white: '#FFFFFF',
}

/**
 * Build survival probability curve from API result.
 * Maps months to estimated probability of surviving to that month.
 */
function buildSurvivalData(result) {
  if (!result) return []
  const runway = Number(result.runway_months) || 1
  const prob6 = Number(result.survival_probability_6_months) ?? 60
  const months = [1, 2, 3, 6, 12]
  return months.map((month) => {
    let probability
    if (month <= 1) probability = 95
    else if (month === 2) probability = 90
    else if (month === 3) probability = 82
    else if (month === 6) probability = prob6
    else probability = Math.max(5, Math.round(prob6 - (month - 6) * 5))
    return { month, probability: Math.max(0, Math.min(100, probability)) }
  })
}

/**
 * Build shock scenario comparison from API result.
 */
function buildShockData(result) {
  if (!result) return []
  const runway = Number(result.runway_months) || 1
  const adjusted = result.adjusted_runway_after_market_shock != null
    ? Number(result.adjusted_runway_after_market_shock)
    : runway * 0.75
  const worst = Number(result.worst_case_survival_months) ?? runway * 0.5
  const emergency = runway * 0.4
  return [
    { scenario: 'Normal', months: Math.round(runway * 10) / 10 },
    { scenario: 'Market Crash', months: Math.round(adjusted * 10) / 10 },
    { scenario: 'Job Loss', months: Math.round(worst * 10) / 10 },
    { scenario: 'Emergency', months: Math.round(Math.max(0.5, emergency) * 10) / 10 },
  ]
}

/**
 * Build runway depletion (savings vs months) from savings and monthly expenses.
 */
function buildRunwayData(savings, monthlyExpenses) {
  if (!savings || !monthlyExpenses || monthlyExpenses <= 0) return []
  const s = Number(savings)
  const e = Number(monthlyExpenses)
  const data = []
  let remaining = s
  for (let month = 0; month <= Math.ceil(s / e) + 2 && month <= 24; month++) {
    data.push({ month, savings: Math.max(0, Math.round(remaining)) })
    remaining -= e
  }
  return data
}

export default function ResilienceCharts({ result, inputData = {} }) {
  const survivalData = buildSurvivalData(result)
  const shockData = buildShockData(result)
  const runwayData = buildRunwayData(inputData.savings, inputData.monthlyExpenses)

  const hasAnyData = survivalData.length > 0 || shockData.length > 0 || runwayData.length > 0
  if (!result || !hasAnyData) return null

  return (
    <section className="mt-8 bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
      <h2 className="text-lg font-semibold text-bharat-navy mb-6">
        Financial Shock Simulation Analysis
      </h2>
      <div className="space-y-8">
        {/* Survival Probability Curve */}
        {survivalData.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-slate-700 mb-3">
              Financial Survival Probability
            </h3>
            <div className="h-64 w-full min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={survivalData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month" stroke={THEME.navy} tick={{ fontSize: 12 }} />
                  <YAxis stroke={THEME.navy} tick={{ fontSize: 12 }} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: THEME.white,
                      border: `2px solid ${THEME.navy}`,
                      borderRadius: 8,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="probability"
                    name="Survival %"
                    stroke={THEME.navy}
                    strokeWidth={2}
                    dot={{ fill: THEME.saffron, r: 4 }}
                    activeDot={{ r: 6, fill: THEME.saffron }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Shock Scenario Comparison */}
        {shockData.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-slate-700 mb-3">
              Impact of Financial Shocks
            </h3>
            <div className="h-56 w-full min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shockData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="scenario" stroke={THEME.navy} tick={{ fontSize: 11 }} />
                  <YAxis stroke={THEME.navy} tick={{ fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: THEME.white,
                      border: `2px solid ${THEME.navy}`,
                      borderRadius: 8,
                    }}
                  />
                  <Bar
                    dataKey="months"
                    name="Runway (months)"
                    fill={THEME.saffron}
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Projected Financial Runway */}
        {runwayData.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-slate-700 mb-3">
              Projected Financial Runway
            </h3>
            <div className="h-64 w-full min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={runwayData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month" stroke={THEME.navy} tick={{ fontSize: 12 }} />
                  <YAxis stroke={THEME.navy} tick={{ fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: THEME.white,
                      border: `2px solid ${THEME.navy}`,
                      borderRadius: 8,
                    }}
                    formatter={(v) => [`₹${Number(v).toLocaleString()}`, 'Savings']}
                  />
                  <Area
                    type="monotone"
                    dataKey="savings"
                    stroke={THEME.navy}
                    fill={THEME.navy}
                    fillOpacity={0.3}
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
