import { useEffect, useState } from 'react'
import api from '../services/api'

function formatNumber(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'N/A'
  return n.toFixed(2)
}

// Backend sends pre-formatted IST string; display as-is without JS Date conversion

const SIGNAL_LABELS = {
  bond_yield: 'US 10Y Bond Yield',
  crude_oil: 'Crude Oil (WTI)',
  usd_inr: 'USD/INR',
  gold: 'Gold',
  india_vix: 'India VIX',
}

const SIGNAL_STYLES = {
  bond_yield: 'border-l-2 border-blue-500',
  crude_oil: 'border-l-2 border-orange-500',
  usd_inr: 'border-l-2 border-emerald-500',
  gold: 'border-l-2 border-yellow-400',
  india_vix: 'border-l-2 border-red-500',
}

const SIGNAL_INFO = {
  bond_yield: {
    title: 'US 10Y Bond Yield',
    description:
      'Measures the return on 10-year US government bonds. Rising yields increase borrowing costs globally and reduce valuations of growth stocks like Indian IT companies.',
    threshold: 'Above 4.5% is considered a high pressure zone for emerging markets like India.',
  },
  crude_oil: {
    title: 'Crude Oil (WTI)',
    description:
      'Global benchmark for oil prices. India imports ~85% of its oil needs, so rising crude directly increases inflation, widens the trade deficit, and weakens the INR.',
    threshold: 'Above $90 puts pressure on Indian macro stability.',
  },
  usd_inr: {
    title: 'USD/INR',
    description:
      'Tracks how many Indian Rupees equal 1 US Dollar. A higher value means INR is weakening. Benefits IT and Pharma exporters but hurts oil importers and increases import inflation.',
    threshold: 'Above 84 INR/USD signals significant rupee weakness.',
  },
  gold: {
    title: 'Gold',
    description:
      'Gold is a global safe-haven asset. When gold rises sharply, it signals risk-off sentiment — investors are moving away from equities into safety. Watch for broad market caution.',
    threshold: 'A rise of more than 1.5% in a day signals a strong risk-off move.',
  },
  india_vix: {
    title: 'India VIX',
    description:
      'India Volatility Index measures expected market volatility over the next 30 days. Higher VIX = more fear and uncertainty in the market. Lower VIX = calm and stable conditions.',
    threshold: 'Above 20 signals elevated fear. Above 25 is a high alert zone.',
  },
}

const SEVERITY_STYLES = {
  high: 'bg-red-100 text-red-700 border-red-300',
  medium: 'bg-amber-100 text-amber-800 border-amber-300',
  low: 'bg-sky-100 text-sky-800 border-sky-300',
}

function CrossMarketPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [openSignal, setOpenSignal] = useState(null)

  useEffect(() => {
    let isMounted = true
    let intervalId

    const load = async () => {
      if (!isMounted) return
      setLoading(true)
      setError('')
      try {
        const res = await api.get('/cross-market/analysis')
        if (!isMounted) return
        setData(res.data)
      } catch (err) {
        console.error('[CrossMarketPanel] Failed to fetch cross-market analysis:', err)
        if (isMounted) {
          setError('Unable to load live macro signals right now. Please try again shortly.')
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    load()
    intervalId = setInterval(load, 60_000)

    return () => {
      isMounted = false
      if (intervalId) clearInterval(intervalId)
    }
  }, [])

  const signals = data?.signals || {}
  const causalInsights = Array.isArray(data?.causal_insights) ? data.causal_insights : []
  const lastUpdated = data?.data_timestamp

  return (
    <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg flex flex-col overflow-hidden">
      <div className="bg-bharat-navy px-4 py-3 border-b border-bharat-navy/60 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-5 bg-bharat-saffron rounded-sm" aria-hidden />
          <div>
            <h3 className="text-sm font-semibold text-white">Cross-Market Macro Dashboard</h3>
            <p className="text-[11px] text-bharat-green/80 uppercase tracking-wide">
              Live Global Macro Signals
            </p>
          </div>
        </div>
      </div>

      <div className="px-4 py-3 space-y-4">
        {loading && (
          <div className="flex items-center justify-center py-4">
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <span className="inline-block w-4 h-4 border-2 border-bharat-navy border-t-transparent rounded-full animate-spin" />
              <span>Fetching live cross-market signals…</span>
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        )}

        {/* Live Macro Signals */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-bharat-navy tracking-wide uppercase">
              Live Macro Signals
            </h4>
          </div>

          <div className="space-y-2">
            {Object.entries(SIGNAL_LABELS).map(([key, label]) => {
              const s = signals[key]
              const isAvailable = s && typeof s === 'object'
              const direction = isAvailable ? s.direction : null
              const change = isAvailable ? s.change_pct : null
              const current = isAvailable ? s.current_value : null

              let badgeColor =
                direction === 'up'
                  ? 'bg-bharat-green/10 text-bharat-green border-bharat-green/50'
                  : direction === 'down'
                  ? 'bg-red-50 text-red-700 border-red-300'
                  : 'bg-slate-100 text-slate-600 border-slate-200'

              const arrow = direction === 'up' ? '▲' : direction === 'down' ? '▼' : ''
              const isOpen = openSignal === key
              const info = SIGNAL_INFO[key] || {}
              const leftBorderClass = SIGNAL_STYLES[key] || ''
              const handleToggle = () => {
                setOpenSignal((prev) => (prev === key ? null : key))
              }

              return (
                <div key={key} className="space-y-1">
                  <div
                    className={`w-full flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 text-left hover:bg-slate-100 transition-colors ${leftBorderClass}`}
                    onClick={handleToggle}
                  >
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold text-slate-800">{label}</span>
                      <span className="text-[11px] text-slate-500">
                        {isAvailable ? (
                          <span className="font-semibold text-slate-800">
                            {formatNumber(current)}
                          </span>
                        ) : (
                          <span className="text-slate-400">Unavailable</span>
                        )}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleToggle()
                        }}
                        className={`transition-colors duration-200 ease-out ${
                          isOpen ? 'text-[#FF9933]' : 'text-gray-500'
                        } hover:text-white cursor-pointer`}
                        aria-label="Toggle signal explanation"
                        title="What does this mean?"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="18"
                          height="18"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <circle cx="12" cy="12" r="10" />
                          <line x1="12" y1="16" x2="12" y2="12" />
                          <line x1="12" y1="8" x2="12.01" y2="8" />
                        </svg>
                      </button>
                      {isAvailable && (
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium ${badgeColor}`}
                        >
                          {arrow && <span className="text-[9px]">{arrow}</span>}
                          <span>{formatNumber(change)}%</span>
                        </span>
                      )}
                    </div>
                  </div>

                  <div
                    className={`overflow-hidden transition-all duration-200 ease-out ${
                      isOpen ? 'max-h-40 opacity-100 mt-1' : 'max-h-0 opacity-0'
                    }`}
                  >
                    {isOpen && (
                      <div className="rounded-xl border-l-4 border-bharat-saffron bg-bharat-navy/5 px-3 py-2 text-[11px] text-slate-700">
                        <p className="font-semibold text-bharat-navy mb-1">{info.title}</p>
                        <p className="mb-1">{info.description}</p>
                        <p className="text-[10px] text-slate-600">
                          <span className="font-semibold text-bharat-navy">Key threshold: </span>
                          {info.threshold}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* Causal Insights */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-bharat-navy tracking-wide uppercase">
              Causal Insights
            </h4>
          </div>

          {causalInsights.length === 0 ? (
            <p className="text-[11px] text-slate-500">
              No significant macro signals detected.
            </p>
          ) : (
            <div className="space-y-2">
              {causalInsights.map((insight, idx) => {
                const severity = insight.severity || 'low'
                const sevClass = SEVERITY_STYLES[severity] || SEVERITY_STYLES.low
                const sectors = Array.isArray(insight.affected_sectors)
                  ? insight.affected_sectors
                  : []

                return (
                  <div
                    key={idx}
                    className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-semibold text-slate-900">
                        {insight.impact || 'Macro signal detected'}
                      </p>
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide ${sevClass}`}
                      >
                        {severity} risk
                      </span>
                    </div>
                    {sectors.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {sectors.map((sec) => (
                          <span
                            key={sec}
                            className="inline-flex items-center px-2 py-0.5 rounded-full bg-slate-100 text-[10px] text-slate-700 border border-slate-200"
                          >
                            {sec}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>

      <div className="px-4 py-3 border-t border-slate-200 bg-slate-50 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5">
        <p className="text-[11px] text-slate-600">
          <span className="font-semibold text-bharat-navy">Last updated:</span>{' '}
          {lastUpdated || 'Not available'}
        </p>
        <p className="text-[10px] text-slate-500">Auto-refreshes every 60 seconds</p>
      </div>
    </div>
  )
}

export default CrossMarketPanel

