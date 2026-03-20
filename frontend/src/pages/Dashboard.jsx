import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import api, { getStockHistory } from '../services/api'
import StockSearch from '../components/StockSearch'
import Chat from '../components/Chat'
import Watchlist, { useWatchlist } from '../components/Watchlist'
import RSIGauge from '../components/RSIGauge'
import MACDGauge from '../components/MACDGauge'
import MarketNews from '../components/MarketNews'
import MutualFundSearch from '../components/MutualFundSearch'
import MutualFundSipCalculator from '../components/MutualFundSipCalculator'
import MutualFundWatchlist from '../components/MutualFundWatchlist'
import CrossMarketPanel from "../components/CrossMarketPanel";

const TABS = [
  { id: 'market', label: 'Market View' },
  { id: 'technical', label: 'Technical Analysis' },
  { id: 'mutual', label: 'Mutual Funds' },
  /* TEMPORARILY HIDDEN - Macro Intelligence
  { id: 'macro', label: 'Macro Intelligence' },
  */
  { id: 'ai', label: 'AI Advisor' },
]

function Dashboard() {
  const location = useLocation()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('market')
  const [toast, setToast] = useState(location.state?.toast || null)
  const { addToWatchlist, isInWatchlist } = useWatchlist()

  const [selectedSymbol, setSelectedSymbol] = useState('RELIANCE.NS')
  const [selectedMfFund, setSelectedMfFund] = useState(null)
  const [selectedName, setSelectedName] = useState('Reliance Industries Limited')
  const [stockData, setStockData] = useState(null)
  const [rsiData, setRsiData] = useState(null)
  const [macdData, setMacdData] = useState(null)
  const [maData, setMaData] = useState(null)
  const [historyData, setHistoryData] = useState(null)

  const [loading, setLoading] = useState(false)
  const [stockError, setStockError] = useState(null)
  const [rsiError, setRsiError] = useState(null)
  const [macdError, setMacdError] = useState(null)
  const [watchlistRefresh, setWatchlistRefresh] = useState(0)
  const [optimisticAdded, setOptimisticAdded] = useState(false)

  useEffect(() => {
    const nextToast = location.state?.toast
    if (nextToast) {
      setToast(nextToast)
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
    const n = signal.toLowerCase()
    if (n === 'overbought') return 'text-red-600'
    if (n === 'oversold') return 'text-bharat-green'
    if (n === 'neutral') return 'text-amber-600'
    return 'text-slate-700'
  }

  const macdTrendColor = (trend) => {
    if (!trend) return 'text-slate-700'
    const n = trend.toLowerCase()
    if (n === 'bullish') return 'text-bharat-green'
    if (n === 'bearish') return 'text-red-600'
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
    setMaData(null)
    setHistoryData(null)
    setLoading(true)

    try {
      const [stockRes, rsiRes, macdRes, maRes, histRes] = await Promise.allSettled([
        api.get(`/stock/${encodeURIComponent(symbol)}`),
        api.get(`/rsi/${encodeURIComponent(symbol)}`),
        api.get(`/macd/${encodeURIComponent(symbol)}`),
        api.get(`/moving-averages/${encodeURIComponent(symbol)}`),
        getStockHistory(symbol, '6mo'),
      ])

      if (stockRes.status === 'fulfilled') setStockData(stockRes.value.data)
      else {
        console.error('Stock fetch error:', stockRes.reason)
        setStockError(stockRes.reason?.response?.data?.detail || stockRes.reason?.message || 'Failed to fetch stock data')
      }

      if (rsiRes.status === 'fulfilled') setRsiData(rsiRes.value.data)
      else {
        console.error('RSI fetch error:', rsiRes.reason)
        setRsiError(rsiRes.reason?.response?.data?.detail || rsiRes.reason?.message || 'Failed to fetch RSI data')
      }

      if (macdRes.status === 'fulfilled') setMacdData(macdRes.value.data)
      else {
        console.error('MACD fetch error:', macdRes.reason)
        setMacdError(macdRes.reason?.response?.data?.detail || macdRes.reason?.message || 'Failed to fetch MACD data')
      }

      if (maRes.status === 'fulfilled') setMaData(maRes.value.data)
      if (histRes.status === 'fulfilled' && histRes.value?.dates?.length) {
        const arr = (histRes.value.dates || []).map((d, i) => ({
          date: d,
          close: histRes.value.closes?.[i] ?? 0,
          volume: histRes.value.volumes?.[i] ?? 0,
        }))
        setHistoryData(arr)
      }
    } catch (err) {
      console.error('Unexpected error:', err)
      setStockError('Unexpected error while fetching data')
      setRsiError('Unexpected error while fetching data')
      setMacdError('Unexpected error while fetching data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStockData(selectedSymbol)
    setOptimisticAdded(false)
  }, [selectedSymbol])

  const handleStockSelect = (stock) => {
    if (!stock) return
    setSelectedSymbol(stock.symbol)
    setSelectedName(stock.company_name || stock.display_symbol || stock.symbol)
    fetchStockData(stock.symbol)
  }

  const handleAddToWatchlist = () => {
    if (!selectedSymbol) return
    const already = Boolean(isInWatchlist?.(selectedSymbol))
    if (already || optimisticAdded) return
    addToWatchlist(selectedSymbol, selectedName)
    setOptimisticAdded(true)
    setWatchlistRefresh((v) => v + 1)
  }

  const isAddedToWatchlist = optimisticAdded || Boolean(isInWatchlist?.(selectedSymbol))

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {toast && (
        <div className="rounded-lg border border-bharat-green/60 bg-bharat-green/10 px-4 py-2 text-sm font-semibold text-bharat-green shadow-sm mb-4">
          {toast}
        </div>
      )}

      {/* Tab bar */}
      <div className="flex border-b-2 border-slate-200 mb-6">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`relative flex items-center gap-2 px-5 py-3 text-sm font-semibold transition-colors ${
              activeTab === tab.id
                ? 'text-bharat-navy'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <span>{tab.label}</span>
            {activeTab === tab.id && (
              <span
                className="w-1.5 h-1.5 rounded-full bg-bharat-saffron shrink-0"
                aria-hidden
              />
            )}
            {activeTab === tab.id && (
              <span
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-bharat-navy"
                aria-hidden
              />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'market' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
              <h2 className="text-xl font-semibold text-bharat-navy mb-4">Market Overview</h2>
              <p className="text-sm text-slate-600 mb-4">
                Real-time price, volume, and daily range for NSE-listed securities.
              </p>
              <StockSearch onStockSelect={handleStockSelect} />
              <p className="text-xs text-slate-500 mt-2">
                Start typing a company name or NSE symbol (e.g. Reliance, TCS, HDFC Bank).
              </p>
            </div>

            <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-bharat-navy">Stock Data</h3>
                <button
                  type="button"
                  onClick={handleAddToWatchlist}
                  disabled={isAddedToWatchlist}
                  className={`p-2 rounded-full transition-colors ${
                    isAddedToWatchlist
                      ? 'text-bharat-green bg-bharat-green/10 cursor-not-allowed'
                      : 'text-bharat-saffron hover:bg-bharat-saffron/10'
                  }`}
                  title={isAddedToWatchlist ? 'Added to watchlist' : 'Add to watchlist'}
                >
                  {isAddedToWatchlist ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.286 3.967a1 1 0 00.95.69h4.174c.969 0 1.371 1.24.588 1.81l-3.378 2.455a1 1 0 00-.364 1.118l1.287 3.966c.3.922-.755 1.688-1.54 1.118l-3.378-2.454a1 1 0 00-1.175 0l-3.378 2.454c-.784.57-1.838-.196-1.539-1.118l1.287-3.966a1 1 0 00-.364-1.118L2.952 9.394c-.783-.57-.38-1.81.588-1.81h4.174a1 1 0 00.95-.69l1.286-3.967z"
                      />
                    </svg>
                  )}
                </button>
              </div>

              {stockError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                  {stockError}
                </div>
              )}

              {loading && !stockData && !stockError && (
                <p className="text-sm text-slate-500">Fetching Bharat Markets Data...</p>
              )}

              {stockData && (
                <div className="grid grid-cols-1 gap-3 text-sm">
                  <div className="pb-2 border-b border-slate-300">
                    <div className="flex items-center gap-2">
                      <span className="text-base font-semibold text-slate-900">
                        {selectedName || stockData.symbol}
                      </span>
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
                      {stockData.change >= 0 ? '+' : ''}{stockData.change}
                    </span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-200">
                    <span className="text-slate-600">Change %</span>
                    <span className={`font-semibold ${changeColor(stockData.change_percent)}`}>
                      {stockData.change_percent >= 0 ? '+' : ''}{stockData.change_percent}%
                    </span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-200">
                    <span className="text-slate-600">Volume</span>
                    <span className="font-semibold">{stockData.volume?.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-slate-600">Day High / Low</span>
                    <span className="font-semibold">
                      ₹{stockData.day_high?.toLocaleString()} / ₹{stockData.day_low?.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}

              {!loading && !stockData && !stockError && (
                <p className="text-sm text-slate-500">Pick a stock to see live price data.</p>
              )}
            </div>

            {/* Price History & Volume charts */}
            {historyData && historyData.length > 0 && (
              <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
                <h3 className="text-lg font-semibold text-bharat-navy mb-4">Price History (6M)</h3>
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={historyData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#0f172a" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="#0f172a" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => (v || '').slice(5)} />
                    <YAxis tick={{ fontSize: 10 }} domain={['auto', 'auto']} tickFormatter={(v) => `₹${v}`} />
                    <Tooltip formatter={(v) => [`₹${v}`, 'Close']} labelFormatter={(l) => l} />
                    <Area type="monotone" dataKey="close" stroke="#0f172a" fill="url(#priceGrad)" strokeWidth={2} name="Price" />
                  </AreaChart>
                </ResponsiveContainer>
                <h3 className="text-lg font-semibold text-bharat-navy mt-6 mb-2">Volume</h3>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={historyData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => (v || '').slice(5)} />
                    <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v)} />
                    <Tooltip formatter={(v) => [v?.toLocaleString(), 'Volume']} labelFormatter={(l) => l} />
                    <Bar dataKey="volume" fill="#ea580c" radius={[2, 2, 0, 0]} name="Volume" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-4 max-h-[calc(100vh-220px)] overflow-y-auto">
            <MarketNews symbol={selectedSymbol} />
            <Watchlist onSelectStock={handleStockSelect} refreshTrigger={watchlistRefresh} />
          </div>
        </div>
      )}

      {activeTab === 'technical' && (
        <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
          <h2 className="text-xl font-semibold text-bharat-navy mb-2">Technical Analysis</h2>
          <p className="text-sm text-slate-600 mb-6">
            Signals and momentum tools built for quick decisions.
          </p>

          {maData && (
            <div className="mb-6 p-4 rounded-xl bg-slate-50 border border-slate-200">
              <h3 className="text-sm font-semibold text-bharat-navy mb-2">Moving Averages</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                <div><span className="text-slate-600">Price</span><br /><span className="font-semibold">₹{maData.price}</span></div>
                <div><span className="text-slate-600">50 Day MA</span><br /><span className="font-semibold">₹{maData.sma50}</span> <span className={maData.signal_sma50 === 'above' ? 'text-bharat-green' : 'text-red-600'}>({maData.signal_sma50})</span></div>
                <div><span className="text-slate-600">200 Day MA</span><br /><span className="font-semibold">₹{maData.sma200}</span> <span className={maData.signal_sma200 === 'above' ? 'text-bharat-green' : 'text-red-600'}>({maData.signal_sma200})</span></div>
                <div><span className="text-slate-600">SMA20</span><br /><span className="font-semibold">₹{maData.sma20}</span></div>
              </div>
              <p className="text-xs text-slate-500 mt-2">
                {maData.signal_sma200 === 'above' ? 'Price above 200-day MA suggests bullish long-term trend.' : 'Price below 200-day MA; watch for support levels.'}
              </p>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl border-2 border-bharat-navy/30 p-5">
              <h3 className="text-lg font-semibold text-bharat-navy mb-2">RSI</h3>
              <p className="text-xs text-slate-600 mb-4">
                <span className="font-semibold text-bharat-navy">ⓘ</span> The Relative Strength Index (RSI) measures the speed and change of price movements to identify overbought or oversold conditions.
              </p>
              {rsiError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                  {rsiError}
                </div>
              )}
              {loading && !rsiData && !rsiError && (
                <p className="text-sm text-slate-500">Fetching Bharat Markets Data...</p>
              )}
              {rsiData && <RSIGauge value={rsiData.rsi} signal={rsiData.signal} />}
              {!loading && !rsiData && !rsiError && (
                <p className="text-sm text-slate-500">Select a stock in Market View to compute RSI.</p>
              )}
            </div>

            <div className="bg-white rounded-xl border-2 border-bharat-navy/30 p-5">
              <h3 className="text-lg font-semibold text-bharat-navy mb-2">MACD</h3>
              <p className="text-xs text-slate-600 mb-4">
                <span className="font-semibold text-bharat-navy">ⓘ</span> Moving Average Convergence Divergence (MACD) shows the relationship between two moving averages of a stock's price to find momentum.
              </p>
              {macdError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                  {macdError}
                </div>
              )}
              {loading && !macdData && !macdError && (
                <p className="text-sm text-slate-500">Fetching Bharat Markets Data...</p>
              )}
              {macdData && (
                <div className="space-y-4">
                  <MACDGauge histogram={macdData.histogram} trend={macdData.trend} />
                  <div className="grid grid-cols-2 gap-2 text-sm pt-2 border-t border-slate-200">
                    <div className="flex justify-between">
                      <span className="text-slate-600">MACD</span>
                      <span className="font-semibold">{macdData.macd}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-600">Signal</span>
                      <span className="font-semibold">{macdData.signal}</span>
                    </div>
                  </div>
                </div>
              )}
              {!loading && !macdData && !macdError && (
                <p className="text-sm text-slate-500">Select a stock in Market View to compute MACD.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'ai' && (
        <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
          <h2 className="text-xl font-semibold text-bharat-navy mb-2">AI Advisor</h2>
          <p className="text-sm text-slate-600 mb-4">
            <span className="font-semibold text-bharat-navy">ⓘ</span> Ask BharatFinanceAI for real-time analysis, SIP calculations, or market terminology.
          </p>
          <div className="rounded-xl border-2 border-bharat-navy/30 overflow-hidden">
            <Chat embedded heightClassName="h-[560px] md:h-[680px]" />
          </div>
        </div>
      )}

      {/* TEMPORARILY HIDDEN - Macro Intelligence Panel
      {activeTab === 'macro' && <CrossMarketPanel />}
      */}

      {activeTab === 'mutual' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6">
              <h2 className="text-xl font-semibold text-bharat-navy mb-2">Mutual Funds</h2>
              <p className="text-sm text-slate-600 mb-4">
                Discover Indian mutual funds, track NAVs, and plan disciplined SIP investments.
              </p>
              <MutualFundSearch onSelectFund={setSelectedMfFund} />
            </div>
          </div>
          <div className="flex flex-col gap-4">
            <MutualFundSipCalculator selectedFund={selectedMfFund} />
            <MutualFundWatchlist onSelectScheme={(s) => setSelectedMfFund(s)} />
          </div>
        </div>
      )}
    </div>
  )
}

export default Dashboard
