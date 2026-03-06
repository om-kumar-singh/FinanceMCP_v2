import { useEffect, useState } from 'react'
import { ref, onValue, set, remove } from 'firebase/database'
import { db } from '../lib/firebase'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'

function Watchlist({ onSelectStock, refreshTrigger }) {
  const { user } = useAuth()
  const uid = user?.uid
  const [watchlist, setWatchlist] = useState({})
  const [prices, setPrices] = useState({})
  const [loadingPrices, setLoadingPrices] = useState(false)

  useEffect(() => {
    if (!uid) return
    const wlRef = ref(db, `users/${uid}/watchlist`)
    const unsub = onValue(wlRef, (snapshot) => {
      setWatchlist(snapshot.val() || {})
    })
    return () => unsub()
  }, [uid])

  useEffect(() => {
    const items = Object.values(watchlist)
    const symbols = items.map((item) => item?.symbol).filter(Boolean)
    if (symbols.length === 0) return

    setLoadingPrices(true)
    const promises = symbols.map((sym) =>
      api.get(`/stock/${encodeURIComponent(sym)}`).then((r) => ({ sym, data: r.data })).catch(() => ({ sym, data: null }))
    )
    Promise.all(promises).then((results) => {
      const next = {}
      results.forEach(({ sym, data }) => {
        next[sym] = data ? { price: data.price, change: data.change, change_percent: data.change_percent } : null
      })
      setPrices(next)
      setLoadingPrices(false)
    })
  }, [watchlist, refreshTrigger])

  const entries = Object.entries(watchlist)
  const changeColor = (val) => {
    if (val == null || val === undefined) return 'text-slate-600'
    const n = typeof val === 'number' ? val : parseFloat(val)
    if (Number.isNaN(n)) return 'text-slate-600'
    if (n > 0) return 'text-bharat-green'
    if (n < 0) return 'text-red-600'
    return 'text-slate-600'
  }

  if (!uid) return null

  return (
    <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg overflow-hidden flex flex-col h-full">
      <div className="bg-bharat-navy px-4 py-3 border-b border-bharat-navy/60">
        <h3 className="text-sm font-semibold text-white flex items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <span className="text-bharat-saffron">★</span>
            <span>My Bharat Watchlist</span>
          </span>
          <span className="text-[10px] text-bharat-green/80 uppercase tracking-wide">
            Live 24h moves
          </span>
        </h3>
      </div>

      <div className="flex-1 px-4 py-3 space-y-3 overflow-y-auto max-h-[450px] scrollbar-thin scrollbar-track-transparent scrollbar-thumb-slate-300">
        {entries.length === 0 && (
          <div className="text-center px-2 py-6">
            <p className="text-sm font-medium text-slate-700 mb-1">
              Your watchlist is empty.
            </p>
            <p className="text-xs text-slate-500">
              Search for a stock above to start tracking!
            </p>
          </div>
        )}

        {entries.length > 0 && (
          <ul className="space-y-2">
            {entries.map(([key, meta]) => {
              const symbol = meta?.symbol || key
              const p = prices[symbol]

              const handleRemove = (e) => {
                e.stopPropagation()
                if (!uid || !symbol) return
                const safeKey = symbol.replace(/\./g, '_')
                const wlRef = ref(db, `users/${uid}/watchlist/${safeKey}`)
                remove(wlRef)
              }

              return (
                <li
                  key={key}
                  className="group flex items-center justify-between gap-2 py-2 border-b border-slate-100 last:border-0 cursor-pointer hover:bg-slate-50 rounded-lg px-3 -mx-3 transition-colors bg-white"
                  onClick={() => onSelectStock?.({ symbol, company_name: meta?.name })}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-slate-900 truncate">
                      {meta?.name || symbol.replace('.NS', '')}
                    </div>
                    <div className="text-[10px] text-slate-500">{symbol}</div>
                  </div>
                  <div className="text-right shrink-0 mr-1">
                    {loadingPrices ? (
                      <span className="text-xs text-slate-400">…</span>
                    ) : p ? (
                      <>
                        <div className="text-xs font-semibold text-slate-900">
                          ₹{p.price?.toLocaleString()}
                        </div>
                        <div className={`text-[10px] font-medium ${changeColor(p.change_percent)}`}>
                          {p.change_percent >= 0 ? '+' : ''}
                          {p.change_percent}%
                        </div>
                      </>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleRemove}
                    className="opacity-0 group-hover:opacity-100 p-1.5 rounded-full text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors shrink-0"
                    title="Remove from watchlist"
                  >
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.8}
                        d="M6 7h12M10 11v6m4-6v6M9 7l1-2h4l1 2m-8 0v11a2 2 0 002 2h6a2 2 0 002-2V7"
                      />
                    </svg>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div className="px-4 py-3 border-t border-slate-200 bg-slate-50">
        <p className="text-[11px] text-slate-600 leading-snug">
          <span className="font-semibold text-bharat-navy">ⓘ Watchlist:</span>{' '}
          Your personal space to track your favorite Indian equities. Data is synced across your devices via BharatFinanceAI secure cloud.
        </p>
      </div>
    </div>
  )
}

export function useWatchlist() {
  const { user } = useAuth()
  const uid = user?.uid
  const [watchlist, setWatchlist] = useState({})

  useEffect(() => {
    if (!uid) {
      setWatchlist({})
      return
    }
    const wlRef = ref(db, `users/${uid}/watchlist`)
    const unsub = onValue(wlRef, (snapshot) => {
      setWatchlist(snapshot.val() || {})
    })
    return () => unsub()
  }, [uid])

  const addToWatchlist = (symbol, name) => {
    if (!uid || !symbol) return
    const safeKey = symbol.replace(/\./g, '_')
    const wlRef = ref(db, `users/${uid}/watchlist/${safeKey}`)
    set(wlRef, { symbol, name: name || symbol, addedAt: Date.now() })
  }

  const removeFromWatchlist = (symbol) => {
    if (!uid || !symbol) return
    const safeKey = symbol.replace(/\./g, '_')
    const wlRef = ref(db, `users/${uid}/watchlist/${safeKey}`)
    remove(wlRef)
  }

  const isInWatchlist = (symbol) => {
    if (!symbol) return false
    const safeKey = symbol.replace(/\./g, '_')
    return Boolean(watchlist?.[safeKey])
  }

  return { addToWatchlist, removeFromWatchlist, watchlist, isInWatchlist }
}

export default Watchlist
