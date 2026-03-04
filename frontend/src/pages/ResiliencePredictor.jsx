import { useState } from 'react'
import { predictResilience } from '../services/api'
import ResilienceCharts from '../components/ResilienceCharts'

function getRiskLevelColor(riskLevel) {
  if (!riskLevel) return 'text-slate-700'
  const level = String(riskLevel).toLowerCase()
  if (level.includes('strong')) return 'text-green-600 bg-green-50 border-green-200'
  if (level.includes('moderate')) return 'text-amber-700 bg-amber-50 border-amber-200'
  if (level.includes('vulnerable')) return 'text-orange-600 bg-orange-50 border-orange-200'
  if (level.includes('high')) return 'text-red-600 bg-red-50 border-red-200'
  return 'text-slate-700 bg-slate-50 border-slate-200'
}

function ResiliencePredictor() {
  const [income, setIncome] = useState('')
  const [monthlyExpenses, setMonthlyExpenses] = useState('')
  const [savings, setSavings] = useState('')
  const [emi, setEmi] = useState('')
  const [stockPortfolioValue, setStockPortfolioValue] = useState('')
  const [mutualFundValue, setMutualFundValue] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [lastInputs, setLastInputs] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setResult(null)

    const inc = parseFloat(income)
    const exp = parseFloat(monthlyExpenses)
    const sav = parseFloat(savings)
    const emiVal = parseFloat(emi)
    if (!income || !monthlyExpenses || !savings || emi === '' || isNaN(inc) || isNaN(exp) || isNaN(sav) || isNaN(emiVal)) {
      setError('Please fill in Income, Monthly Expenses, Savings, and EMI.')
      return
    }
    if (inc <= 0 || exp <= 0 || sav < 0 || emiVal < 0) {
      setError('Income and expenses must be positive. Savings and EMI must be non-negative.')
      return
    }

    setLoading(true)
    try {
      const payload = {
        income: inc,
        monthly_expenses: exp,
        savings: sav,
        emi: emiVal,
        stock_portfolio_value: stockPortfolioValue ? parseFloat(stockPortfolioValue) || 0 : 0,
        mutual_fund_value: mutualFundValue ? parseFloat(mutualFundValue) || 0 : 0,
      }
      const data = await predictResilience(payload)
      setResult(data)
      setLastInputs({ savings: sav, monthlyExpenses: exp })
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to predict resilience.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-2xl sm:text-3xl font-bold text-bharat-navy mb-6">
        AI Financial Shock Resilience Predictor
      </h1>

      {/* Section 1: Financial Inputs Form */}
      <section className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6 mb-8">
        <h2 className="text-lg font-semibold text-bharat-navy mb-4">Financial Inputs</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="income" className="block text-sm font-medium text-slate-700 mb-1">
              Monthly Income (₹)
            </label>
            <input
              id="income"
              type="number"
              min="0"
              step="1000"
              value={income}
              onChange={(e) => setIncome(e.target.value)}
              placeholder="e.g. 80000"
              className="w-full rounded-lg border-2 border-slate-300 px-3 py-2 text-slate-900 focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
            />
          </div>
          <div>
            <label htmlFor="monthlyExpenses" className="block text-sm font-medium text-slate-700 mb-1">
              Monthly Expenses (₹)
            </label>
            <input
              id="monthlyExpenses"
              type="number"
              min="0"
              step="1000"
              value={monthlyExpenses}
              onChange={(e) => setMonthlyExpenses(e.target.value)}
              placeholder="e.g. 40000"
              className="w-full rounded-lg border-2 border-slate-300 px-3 py-2 text-slate-900 focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
            />
          </div>
          <div>
            <label htmlFor="savings" className="block text-sm font-medium text-slate-700 mb-1">
              Savings (₹)
            </label>
            <input
              id="savings"
              type="number"
              min="0"
              step="1000"
              value={savings}
              onChange={(e) => setSavings(e.target.value)}
              placeholder="e.g. 240000"
              className="w-full rounded-lg border-2 border-slate-300 px-3 py-2 text-slate-900 focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
            />
          </div>
          <div>
            <label htmlFor="emi" className="block text-sm font-medium text-slate-700 mb-1">
              EMI (₹)
            </label>
            <input
              id="emi"
              type="number"
              min="0"
              step="500"
              value={emi}
              onChange={(e) => setEmi(e.target.value)}
              placeholder="e.g. 10000"
              className="w-full rounded-lg border-2 border-slate-300 px-3 py-2 text-slate-900 focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
            />
          </div>
          <div>
            <label htmlFor="stockPortfolioValue" className="block text-sm font-medium text-slate-700 mb-1">
              Stock Portfolio Value (₹) <span className="text-slate-500">optional</span>
            </label>
            <input
              id="stockPortfolioValue"
              type="number"
              min="0"
              step="1000"
              value={stockPortfolioValue}
              onChange={(e) => setStockPortfolioValue(e.target.value)}
              placeholder="e.g. 500000"
              className="w-full rounded-lg border-2 border-slate-300 px-3 py-2 text-slate-900 focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
            />
          </div>
          <div>
            <label htmlFor="mutualFundValue" className="block text-sm font-medium text-slate-700 mb-1">
              Mutual Fund Value (₹) <span className="text-slate-500">optional</span>
            </label>
            <input
              id="mutualFundValue"
              type="number"
              min="0"
              step="1000"
              value={mutualFundValue}
              onChange={(e) => setMutualFundValue(e.target.value)}
              placeholder="e.g. 300000"
              className="w-full rounded-lg border-2 border-slate-300 px-3 py-2 text-slate-900 focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
            />
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full sm:w-auto inline-flex items-center justify-center rounded-full bg-bharat-saffron px-6 py-2.5 text-sm font-semibold text-bharat-navy shadow-md hover:bg-orange-500 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Predicting…' : 'Predict Resilience'}
          </button>
        </form>
      </section>

      {/* Section 2: Prediction Results Card */}
      {result && (
        <section className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
          <h2 className="text-lg font-semibold text-bharat-navy mb-4">Prediction Results</h2>
          {result.insight && (
            <p className="text-sm text-slate-600 mb-4 pb-4 border-b border-slate-200">
              {result.insight}
            </p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <ResultRow label="Resilience Score" value={result.resilience_score} />
            <ResultRow
              label="Risk Level"
              value={result.risk_level}
              highlight
              colorClass={getRiskLevelColor(result.risk_level)}
            />
            <ResultRow label="Runway Months" value={result.runway_months} />
            {result.adjusted_runway_after_market_shock != null && (
              <ResultRow label="Adjusted Runway After Market Shock" value={result.adjusted_runway_after_market_shock} />
            )}
            {result.portfolio_volatility != null && (
              <ResultRow label="Portfolio Volatility" value={result.portfolio_volatility} />
            )}
            {result.macro_sentiment_risk != null && (
              <ResultRow label="Macro Sentiment Risk" value={result.macro_sentiment_risk} />
            )}
            {result.survival_probability_6_months != null && (
              <ResultRow label="Survival Probability (6 months) %" value={result.survival_probability_6_months} />
            )}
            {result.ml_resilience_score != null && (
              <ResultRow label="ML Resilience Score" value={result.ml_resilience_score} />
            )}
            {result.combined_resilience_score != null && (
              <ResultRow label="Combined Resilience Score" value={result.combined_resilience_score} />
            )}
          </div>
          {result.news_based_adjustment && (
            <p className="mt-4 text-xs text-slate-500">{result.news_based_adjustment}</p>
          )}
        </section>
      )}
      {result && (
        <ResilienceCharts result={result} inputData={lastInputs || {}} />
      )}
    </div>
  )
}

function ResultRow({ label, value, highlight, colorClass }) {
  if (value == null && value !== 0) return null
  const val =
    typeof value === 'number'
      ? Number.isInteger(value)
        ? value
        : Number(value.toFixed(2))
      : value
  return (
    <div
      className={`flex justify-between items-center py-2 border-b border-slate-100 ${highlight ? 'rounded-lg px-3 -mx-3 border' : ''} ${colorClass || ''}`}
    >
      <span className="text-sm text-slate-600">{label}</span>
      <span className="text-sm font-semibold">{val}</span>
    </div>
  )
}

export default ResiliencePredictor
