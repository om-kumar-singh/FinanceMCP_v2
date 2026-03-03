import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import api from '../services/api'
import StockSearch from '../components/StockSearch'
import Chat from '../components/Chat'

function Dashboard() {
  const location = useLocation()
  const navigate = useNavigate()
  const [toast, setToast] = useState(location.state?.toast || null)

  const [selectedSymbol, setSelectedSymbol] = useState('RELIANCE.NS')
  const [selectedName, setSelectedName] = useState('Reliance Industries Limited')
  const [stockData, setStockData] = useState(null)
  const [rsiData, setRsiData] = useState(null)
  const [macdData, setMacdData] = useState(null)

  const [loading, setLoading] = useState(false)
  const [stockError, setStockError] = useState(null)
  const [rsiError, setRsiError] = useState(null)
  const [macdError, setMacdError] = useState(null)

  useEffect(() => {
    const nextToast = location.state?.toast
    if (nextToast) {
      setToast(nextToast)
      // Clear router state so toast won't reappear on refresh/back
      navigate(location.pathname, { replace: true, state: {} })
    }
  }, [location.state, location.pathname, navigate])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 2500)
    return () => clearTimeout(t)
  }, [toast])

  const changeColor = (value) => {
    if (value === null || value === undefined) return 'text-slate-700'
    const num = typeof value === 'number' ? value : parseFloat(value)
    if (Number.isNaN(num)) return 'text-slate-700'
    if (num > 0) return 'text-bharat-green'
    if (num < 0) return 'text-red-600'
    return 'text-slate-700'
  }

  const rsiSignalColor = (signal) => {
    if (!signal) return 'text-slate-700'
    const normalized = signal.toLowerCase()
    if (normalized === 'overbought') return 'text-red-600'
    if (normalized === 'oversold') return 'text-bharat-green'
    if (normalized === 'neutral') return 'text-yellow-600'
    return 'text-slate-700'
  }

  const macdTrendColor = (trend) => {
    if (!trend) return 'text-slate-700'
    const normalized = trend.toLowerCase()
    if (normalized === 'bullish') return 'text-bharat-green'
    if (normalized === 'bearish') return 'text-red-600'
    return 'text-slate-700'
  }

  const fetchStockData = async (symbolToFetch = selectedSymbol) => {
    const symbol = symbolToFetch || selectedSymbol
    if (!symbol) return

    setStockError(null)
    setRsiError(null)
    setMacdError(null)
    setStockData(null)
    setRsiData(null)
    setMacdData(null)
    setLoading(true)

    try {
      const stockPromise = api.get(`/stock/${encodeURIComponent(symbol)}`)
      const rsiPromise = api.get(`/rsi/${encodeURIComponent(symbol)}`)
      const macdPromise = api.get(`/macd/${encodeURIComponent(symbol)}`)

      const [stockRes, rsiRes, macdRes] = await Promise.allSettled([
        stockPromise,
        rsiPromise,
        macdPromise,
      ])

      if (stockRes.status === 'fulfilled') {
        setStockData(stockRes.value.data)
      } else {
        console.error('Stock fetch error:', stockRes.reason)
        const detail = stockRes.reason?.response?.data?.detail || stockRes.reason?.message
        setStockError(detail || 'Failed to fetch stock data')
      }

      if (rsiRes.status === 'fulfilled') {
        setRsiData(rsiRes.value.data)
      } else {
        console.error('RSI fetch error:', rsiRes.reason)
        const detail = rsiRes.reason?.response?.data?.detail || rsiRes.reason?.message
        setRsiError(detail || 'Failed to fetch RSI data')
      }

      if (macdRes.status === 'fulfilled') {
        setMacdData(macdRes.value.data)
      } else {
        console.error('MACD fetch error:', macdRes.reason)
        const detail = macdRes.reason?.response?.data?.detail || macdRes.reason?.message
        setMacdError(detail || 'Failed to fetch MACD data')
      }
    } catch (err) {
      console.error('Unexpected error while fetching market data:', err)
      setStockError('Unexpected error while fetching data')
      setRsiError('Unexpected error while fetching data')
      setMacdError('Unexpected error while fetching data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStockData(selectedSymbol)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleStockSelect = (stock) => {
    if (!stock) return
    setSelectedSymbol(stock.symbol)
    setSelectedName(stock.company_name || stock.display_symbol || stock.symbol)
    fetchStockData(stock.symbol)
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {toast && (
        <div className="rounded-lg border border-bharat-green/60 bg-bharat-green/10 px-4 py-2 text-sm font-semibold text-bharat-green shadow-sm">
          {toast}
        </div>
      )}

      {/* Market Overview */}
      <section className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-5">
          <div>
            <h2 className="text-2xl font-semibold text-bharat-navy">Market Overview</h2>
            <p className="text-sm text-slate-600">
              Real-time price, volume, and daily range for NSE-listed securities.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-3">
            <StockSearch onStockSelect={handleStockSelect} />
            <p className="text-sm text-slate-600">
              Start typing a company name or NSE symbol (e.g. Reliance, TCS, HDFC Bank).
            </p>
          </div>

          <div className="bg-white rounded-xl border-2 border-bharat-navy/30 p-5">
            <h3 className="text-lg font-semibold text-bharat-navy mb-3">Price Data</h3>

            {stockError && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {stockError}
              </div>
            )}

            {loading && !stockData && !stockError && (
              <p className="text-sm text-slate-500">Loading price data...</p>
            )}

            {stockData && (
              <div className="grid grid-cols-1 gap-3 text-sm">
                <div className="pb-2 border-b border-slate-300">
                  <div className="text-base font-semibold text-slate-900">
                    {selectedName || stockData.symbol}
                  </div>
                  <div className="text-xs text-slate-500">NSE: {stockData.symbol?.replace('.NS', '')}</div>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">Price</span>
                  <span className="font-semibold">₹{stockData.price?.toLocaleString()}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">Change</span>
                  <span className={`font-semibold ${changeColor(stockData.change)}`}>
                    {stockData.change >= 0 ? '+' : ''}
                    {stockData.change}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">Change %</span>
                  <span className={`font-semibold ${changeColor(stockData.change_percent)}`}>
                    {stockData.change_percent >= 0 ? '+' : ''}
                    {stockData.change_percent}%
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">Volume</span>
                  <span className="font-semibold">{stockData.volume?.toLocaleString()}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">Day High</span>
                  <span className="font-semibold">₹{stockData.day_high?.toLocaleString()}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-600">Day Low</span>
                  <span className="font-semibold">₹{stockData.day_low?.toLocaleString()}</span>
                </div>
              </div>
            )}

            {!loading && !stockData && !stockError && (
              <p className="text-sm text-slate-500">Pick a stock to see live price data.</p>
            )}
          </div>
        </div>
      </section>

      {/* Technical Lab */}
      <section className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
        <div className="mb-5">
          <h2 className="text-2xl font-semibold text-bharat-navy">Technical Lab</h2>
          <p className="text-sm text-slate-600">
            Signals and momentum tools built for quick decisions.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* RSI */}
          <div className="bg-white rounded-xl border-2 border-bharat-navy/30 p-5">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h3 className="text-lg font-semibold text-bharat-navy">RSI</h3>
              <p className="text-xs text-slate-600 leading-snug max-w-[70%] text-right">
                <span className="font-semibold text-bharat-navy">ⓘ</span>{' '}
                The Relative Strength Index (RSI) measures the speed and change of price movements to identify
                overbought or oversold conditions.
              </p>
            </div>

            {rsiError && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {rsiError}
              </div>
            )}

            {loading && !rsiData && !rsiError && <p className="text-sm text-slate-500">Loading RSI...</p>}

            {rsiData && (
              <div className="space-y-3 text-sm">
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">RSI Value</span>
                  <span className="font-semibold">{rsiData.rsi}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-600">Signal</span>
                  <span className={`font-semibold ${rsiSignalColor(rsiData.signal)}`}>{rsiData.signal}</span>
                </div>
              </div>
            )}

            {!loading && !rsiData && !rsiError && (
              <p className="text-sm text-slate-500">Select a stock to compute RSI.</p>
            )}
          </div>

          {/* MACD */}
          <div className="bg-white rounded-xl border-2 border-bharat-navy/30 p-5">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h3 className="text-lg font-semibold text-bharat-navy">MACD</h3>
              <p className="text-xs text-slate-600 leading-snug max-w-[70%] text-right">
                <span className="font-semibold text-bharat-navy">ⓘ</span>{' '}
                Moving Average Convergence Divergence (MACD) shows the relationship between two moving averages
                of a stock’s price to find momentum.
              </p>
            </div>

            {macdError && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {macdError}
              </div>
            )}

            {loading && !macdData && !macdError && <p className="text-sm text-slate-500">Loading MACD...</p>}

            {macdData && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">MACD</span>
                  <span className="font-semibold">{macdData.macd}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">Signal Line</span>
                  <span className="font-semibold">{macdData.signal}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">Histogram</span>
                  <span className="font-semibold">{macdData.histogram}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-600">Trend</span>
                  <span className={`font-semibold ${macdTrendColor(macdData.trend)}`}>{macdData.trend}</span>
                </div>
              </div>
            )}

            {!loading && !macdData && !macdError && (
              <p className="text-sm text-slate-500">Select a stock to compute MACD.</p>
            )}
          </div>
        </div>
      </section>

      {/* AI Assistant */}
      <section className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
        <div className="mb-4">
          <h2 className="text-2xl font-semibold text-bharat-navy">AI Assistant</h2>
          <p className="text-sm text-slate-600">
            <span className="font-semibold text-bharat-navy">ⓘ</span>{' '}
            Ask BharatFinanceAI for real-time analysis, SIP calculations, or market terminology.
          </p>
        </div>
        <div className="rounded-xl border-2 border-bharat-navy/30 overflow-hidden">
          <Chat embedded heightClassName="h-[560px] md:h-[680px]" />
        </div>
      </section>
    </div>
  )
}

export default Dashboard

