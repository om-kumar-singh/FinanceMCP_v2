import { useState } from 'react'
import api from '../services/api'

function Stock() {
  const [symbol, setSymbol] = useState('RELIANCE.NS')
  const [stockData, setStockData] = useState(null)
  const [rsiData, setRsiData] = useState(null)
  const [macdData, setMacdData] = useState(null)

  const [loading, setLoading] = useState(false)
  const [stockError, setStockError] = useState(null)
  const [rsiError, setRsiError] = useState(null)
  const [macdError, setMacdError] = useState(null)

  const fetchStockData = async () => {
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
        const detail = stockRes.reason?.response?.data?.detail
        setStockError(detail || 'Failed to fetch stock data')
      }

      if (rsiRes.status === 'fulfilled') {
        setRsiData(rsiRes.value.data)
      } else {
        const detail = rsiRes.reason?.response?.data?.detail
        setRsiError(detail || 'Failed to fetch RSI data')
      }

      if (macdRes.status === 'fulfilled') {
        setMacdData(macdRes.value.data)
      } else {
        const detail = macdRes.reason?.response?.data?.detail
        setMacdError(detail || 'Failed to fetch MACD data')
      }
    } catch {
      setStockError('Unexpected error while fetching data')
      setRsiError('Unexpected error while fetching data')
      setMacdError('Unexpected error while fetching data')
    } finally {
      setLoading(false)
    }
  }

  const changeColor = (value) => {
    if (value === null || value === undefined) return 'text-gray-700'
    const num = typeof value === 'number' ? value : parseFloat(value)
    if (Number.isNaN(num)) return 'text-gray-700'
    if (num > 0) return 'text-green-600'
    if (num < 0) return 'text-red-600'
    return 'text-gray-700'
  }

  const rsiSignalColor = (signal) => {
    if (!signal) return 'text-gray-700'
    const normalized = signal.toLowerCase()
    if (normalized === 'overbought') return 'text-red-600'
    if (normalized === 'oversold') return 'text-green-600'
    if (normalized === 'neutral') return 'text-yellow-600'
    return 'text-gray-700'
  }

  const macdTrendColor = (trend) => {
    if (!trend) return 'text-gray-700'
    const normalized = trend.toLowerCase()
    if (normalized === 'bullish') return 'text-green-600'
    if (normalized === 'bearish') return 'text-red-600'
    return 'text-gray-700'
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Input and action card */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">Stock Dashboard</h2>

        <div className="flex flex-col sm:flex-row gap-3 mb-2">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="Enter stock symbol (e.g. RELIANCE.NS)"
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
          />
          <button
            onClick={fetchStockData}
            disabled={loading}
            className="px-6 py-2 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Loading...' : 'Get Stock Data'}
          </button>
        </div>
        <p className="text-sm text-gray-500">
          Example symbols: RELIANCE.NS, TCS.NS, INFY.NS
        </p>
      </div>

      {/* Data cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Stock Data Card */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Stock Data</h3>

          {stockError && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
              {stockError}
            </div>
          )}

          {loading && !stockData && !stockError && (
            <p className="text-sm text-gray-500">Loading stock data...</p>
          )}

          {stockData && (
            <div className="grid grid-cols-1 gap-3">
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">Symbol</span>
                <span className="font-medium">{stockData.symbol}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">Price</span>
                <span className="font-medium">₹{stockData.price?.toLocaleString()}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">Change</span>
                <span className={`font-medium ${changeColor(stockData.change)}`}>
                  {stockData.change >= 0 ? '+' : ''}
                  {stockData.change}
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">Change %</span>
                <span className={`font-medium ${changeColor(stockData.change_percent)}`}>
                  {stockData.change_percent >= 0 ? '+' : ''}
                  {stockData.change_percent}%
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">Volume</span>
                <span className="font-medium">
                  {stockData.volume?.toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">Day High</span>
                <span className="font-medium">
                  ₹{stockData.day_high?.toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-gray-600">Day Low</span>
                <span className="font-medium">
                  ₹{stockData.day_low?.toLocaleString()}
                </span>
              </div>
            </div>
          )}

          {!loading && !stockData && !stockError && (
            <p className="text-sm text-gray-500">
              Enter a symbol and click &quot;Get Stock Data&quot; to view details.
            </p>
          )}
        </div>

        {/* RSI Card */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">RSI</h3>

          {rsiError && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
              {rsiError}
            </div>
          )}

          {loading && !rsiData && !rsiError && (
            <p className="text-sm text-gray-500">Loading RSI data...</p>
          )}

          {rsiData && (
            <div className="space-y-3">
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">RSI Value</span>
                <span className="font-medium">{rsiData.rsi}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-gray-600">Signal</span>
                <span className={`font-medium ${rsiSignalColor(rsiData.signal)}`}>
                  {rsiData.signal}
                </span>
              </div>
            </div>
          )}

          {!loading && !rsiData && !rsiError && (
            <p className="text-sm text-gray-500">
              RSI will appear here after you fetch stock data.
            </p>
          )}
        </div>

        {/* MACD Card */}
        <div className="bg-white rounded-lg shadow-md p-6 md:col-span-2">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">MACD</h3>

          {macdError && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
              {macdError}
            </div>
          )}

          {loading && !macdData && !macdError && (
            <p className="text-sm text-gray-500">Loading MACD data...</p>
          )}

          {macdData && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">MACD</span>
                <span className="font-medium">{macdData.macd}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">Signal Line</span>
                <span className="font-medium">{macdData.signal}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-gray-100">
                <span className="text-gray-600">Histogram</span>
                <span className="font-medium">{macdData.histogram}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-gray-600">Trend</span>
                <span className={`font-medium ${macdTrendColor(macdData.trend)}`}>
                  {macdData.trend}
                </span>
              </div>
            </div>
          )}

          {!loading && !macdData && !macdError && (
            <p className="text-sm text-gray-500">
              MACD will appear here after you fetch stock data.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export default Stock
