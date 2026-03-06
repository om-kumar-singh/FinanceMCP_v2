import { useEffect, useState } from 'react'
import { ref, set } from 'firebase/database'
import { db } from '../lib/firebase'
import { useAuth } from '../context/AuthContext'
import { getMarketNews } from '../services/api'

const NEWSAPI_KEY = import.meta.env.VITE_NEWSAPI_KEY
const FINNHUB_KEY = import.meta.env.VITE_FINNHUB_KEY
const CORS_PROXY = import.meta.env.VITE_CORS_PROXY || 'https://cors-anywhere.herokuapp.com/'

// const MOCK_NEWS = [
//   {
//     title: 'Sensex hits all-time high as banking and IT stocks rally',
//     publisher: 'Bharat Markets Desk',
//     url: '#',
//     publishedAt: '2026-03-03T09:15:00Z',
//     urlToImage: '',
//   },
//   {
//     title: 'RBI maintains repo rate; stance remains focused on withdrawal of accommodation',
//     publisher: 'RBI Policy Watch',
//     url: '#',
//     publishedAt: '2026-03-03T08:30:00Z',
//     urlToImage: '',
//   },
//   {
//     title: 'FPIs turn net buyers in Indian equities for third straight month',
//     publisher: 'Global Flows India',
//     url: '#',
//     publishedAt: '2026-03-02T16:00:00Z',
//     urlToImage: '',
//   },
//   {
//     title: 'SIP inflows hit record high as retail investors stay the course',
//     publisher: 'Mutual Fund Insights',
//     url: '#',
//     publishedAt: '2026-03-02T10:45:00Z',
//     urlToImage: '',
//   },
//   {
//     title: "Crude cools off; relief for India's inflation outlook and CAD",
//     publisher: 'Macro Watch India',
//     url: '#',
//     publishedAt: '2026-03-01T18:20:00Z',
//     urlToImage: '',
//   },
// ]

function timeAgo(iso) {
  try {
    const date = new Date(iso)
    const now = new Date()
    const diffMs = now - date
    const diffMins = Math.floor(diffMs / 60000)
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins} min ago`
    const diffHrs = Math.floor(diffMins / 60)
    if (diffHrs < 24) return `${diffHrs} hr${diffHrs > 1 ? 's' : ''} ago`
    const diffDays = Math.floor(diffHrs / 24)
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
  } catch {
    return ''
  }
}

async function fetchNewsFromNewsApi() {
  if (!NEWSAPI_KEY) return null
  const url = `https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey=${NEWSAPI_KEY}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`NewsAPI status ${res.status}`)
  const data = await res.json()
  if (!Array.isArray(data.articles)) return null
  return data.articles.map((a) => ({
    title: a.title,
    publisher: a.source?.name || 'NewsAPI',
    url: a.url,
    publishedAt: a.publishedAt,
    urlToImage: a.urlToImage || '',
  }))
}

async function fetchNewsFromFinnhub() {
  if (!FINNHUB_KEY) return null
  const url = `https://finnhub.io/api/v1/news?category=general&token=${FINNHUB_KEY}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Finnhub status ${res.status}`)
  const data = await res.json()
  if (!Array.isArray(data)) return null
  return data.map((a) => ({
    title: a.headline,
    publisher: a.source || 'Finnhub',
    url: a.url,
    publishedAt: a.datetime ? new Date(a.datetime * 1000).toISOString() : '',
    urlToImage: a.image || '',
  }))
}

async function fetchWithProxy(url) {
  const res = await fetch(`${CORS_PROXY}${url}`)
  if (!res.ok) throw new Error(`Proxy status ${res.status}`)
  return res
}

function MarketNews() {
  const { user } = useAuth()
  const uid = user?.uid

  const [news, setNews] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let isMounted = true
    const load = async () => {
      setLoading(true)
      try {
        // 1) Primary: Backend (yfinance real-time, no CORS, no API keys)
        try {
          const raw = await getMarketNews('NSE')
          const list = Array.isArray(raw) ? raw : (raw?.news || [])
          if (list.length > 0 && isMounted) {
            const items = list.map((a) => ({
              title: a.title,
              publisher: a.publisher || a.source || 'Market Desk',
              url: a.link || a.url || '#',
              publishedAt: a.publishedAt || '',
              urlToImage: a.urlToImage || '',
            }))
            setNews(items)
            return
          }
        } catch (err) {
          console.error('[MarketNews] Backend news fetch failed:', err?.message || err)
        }

        // 2) Fallback: NewsAPI (direct or via proxy if CORS blocks)
        try {
          const items = await fetchNewsFromNewsApi()
          if (items && items.length > 0 && isMounted) {
            setNews(items)
            return
          }
        } catch (err) {
          console.error('[MarketNews] NewsAPI direct error:', err?.message || err)
          if (NEWSAPI_KEY) {
            try {
              const proxied = await fetchWithProxy(
                `https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey=${NEWSAPI_KEY}`,
              )
              const data = await proxied.json()
              if (Array.isArray(data?.articles) && data.articles.length > 0 && isMounted) {
                const items = data.articles.map((a) => ({
                  title: a.title,
                  publisher: a.source?.name || 'NewsAPI',
                  url: a.url,
                  publishedAt: a.publishedAt,
                  urlToImage: a.urlToImage || '',
                }))
                setNews(items)
                return
              }
            } catch (proxyErr) {
              console.error('[MarketNews] NewsAPI proxy error:', proxyErr?.message || proxyErr)
            }
          }
        }

        // 3) Fallback: Finnhub
        try {
          const items = await fetchNewsFromFinnhub()
          if (items && items.length > 0 && isMounted) {
            setNews(items)
            return
          }
        } catch (err) {
          console.error('[MarketNews] Finnhub error:', err?.message || err)
        }

        // 4) Last resort: mock news (disabled to ensure only API-fetched data is shown)
        // if (isMounted) {
        //   console.warn('[MarketNews] Using mock news fallback')
        //   setNews(MOCK_NEWS)
        // }
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    load()
    return () => {
      isMounted = false
    }
  }, [])

  const handleClickArticle = (item) => {
    if (uid && item?.title) {
      const activityRef = ref(db, `users/${uid}/activity/last_read_article`)
      set(activityRef, {
        title: item.title,
        publisher: item.publisher,
        link: item.url,
        symbol: 'MARKET',
        clickedAt: Date.now(),
      }).catch(() => {})
    }
  }

  return (
    <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg overflow-hidden flex flex-col">
      <div className="bg-bharat-navy px-4 py-3 border-b border-bharat-navy/60">
        <h3 className="text-sm font-semibold text-white flex items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <span className="w-1.5 h-4 bg-bharat-saffron rounded-sm" aria-hidden />
            <span>Latest from Finance</span>
          </span>
          <span className="text-[10px] text-bharat-green/80 uppercase tracking-wide">
            Live Headlines
          </span>
        </h3>
      </div>

      <div className="px-4 py-3 space-y-3 max-h-[380px] overflow-y-auto">
        {loading && (
          <p className="text-sm text-slate-500">Fetching the latest headlines…</p>
        )}

        {!loading &&
          news.map((item, idx) => {
            const rawUrl = item.url || ''
            const safeUrl =
              rawUrl && /^https?:\/\//i.test(rawUrl)
                ? rawUrl
                : rawUrl
                ? `https://${rawUrl.replace(/^\/+/, '')}`
                : ''

            const hasRealLink = Boolean(safeUrl && safeUrl !== '#')

            return (
              <article
                key={`${item.url || item.title || idx}`}
                className="flex items-center gap-3 bg-white border border-slate-200 rounded-lg p-3 hover:border-bharat-navy/50 hover:shadow-md transition-all"
              >
                {item.urlToImage ? (
                  <div className="w-10 h-10 rounded-md overflow-hidden bg-slate-100 shrink-0">
                    <img
                      src={item.urlToImage}
                      alt={item.title}
                      className="w-full h-full object-cover"
                    />
                  </div>
                ) : (
                  <div className="w-10 h-10 rounded-md bg-bharat-navy/5 flex items-center justify-center shrink-0">
                    <span className="text-[10px] text-bharat-navy font-semibold">BF</span>
                  </div>
                )}
                <a
                  href={hasRealLink ? safeUrl : undefined}
                  target={hasRealLink ? '_blank' : undefined}
                  rel={hasRealLink ? 'noopener noreferrer' : undefined}
                  onClick={(e) => {
                    if (!hasRealLink) {
                      e.preventDefault()
                    }
                    handleClickArticle(item)
                  }}
                  className="flex-1 min-w-0"
                >
                  <h4 className="text-xs font-semibold text-slate-900 leading-snug line-clamp-3">
                    {item.title}
                  </h4>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-bharat-green/10 text-[10px] font-semibold text-bharat-green border border-bharat-green/40">
                      {item.publisher || 'Market Desk'}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {item.publishedAt ? timeAgo(item.publishedAt) : ''}
                    </span>
                  </div>
                </a>
              </article>
            )
          })}
      </div>

      <div className="px-4 py-3 border-t border-slate-200 bg-slate-50">
        <p className="text-[11px] text-slate-600 leading-snug">
          <span className="font-semibold text-bharat-navy">ⓘ Market News:</span>{' '}
          Real-time headlines aggregated from major Indian financial outlets to help you stay ahead of market-moving events.
        </p>
      </div>
    </div>
  )
}

export default MarketNews

