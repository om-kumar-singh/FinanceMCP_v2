import { useCallback, useEffect, useRef, useState } from 'react'
import { getPopularStocks, searchStocks } from '../services/api'

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debouncedValue
}

function StockSearch({ onStockSelect }) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [defaultSuggestions, setDefaultSuggestions] = useState([])
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)

  const containerRef = useRef(null)
  const searchCache = useRef({})
  const abortRef = useRef(null)

  const debouncedQuery = useDebounce(query, 300)

  // Load popular stocks on mount
  useEffect(() => {
    let cancelled = false

    const loadPopular = async () => {
      try {
        const data = await getPopularStocks()
        if (!cancelled && Array.isArray(data)) {
          setDefaultSuggestions(data)
        }
      } catch {
        // Ignore popular load failures; search will still work
      }
    }

    loadPopular()
    return () => {
      cancelled = true
    }
  }, [])

  // Handle outside click to close dropdown
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false)
        setHighlightedIndex(-1)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  // Perform search when debounced query changes
  useEffect(() => {
    const q = debouncedQuery.trim()

    if (!q) {
      setSuggestions(defaultSuggestions)
      return
    }

    const cached = searchCache.current[q]
    if (cached) {
      setSuggestions(cached)
      return
    }

    const doSearch = async () => {
      if (abortRef.current) {
        abortRef.current.abort()
      }
      const controller = new AbortController()
      abortRef.current = controller
      setIsLoading(true)
      try {
        const data = await searchStocks(q, 8, controller.signal)
        if (Array.isArray(data)) {
          searchCache.current[q] = data
          setSuggestions(data)
        }
      } catch {
        // Swallow errors for autocomplete
      } finally {
        setIsLoading(false)
      }
    }

    doSearch()
  }, [debouncedQuery, defaultSuggestions])

  const handleQueryChange = useCallback((event) => {
    setQuery(event.target.value)
    setIsOpen(true)
    setHighlightedIndex(-1)
  }, [])

  const handleFocus = useCallback(() => {
    setIsOpen(true)
    setSuggestions((prev) => (prev.length ? prev : defaultSuggestions))
  }, [defaultSuggestions])

  const clearSearch = useCallback(() => {
    setQuery('')
    setSuggestions(defaultSuggestions)
    setHighlightedIndex(-1)
  }, [defaultSuggestions])

  const selectStock = useCallback(
    (stock) => {
      if (!stock) return
      setQuery(stock.company_name || stock.display_symbol || '')
      setIsOpen(false)
      setHighlightedIndex(-1)
      if (onStockSelect) {
        onStockSelect(stock)
      }
    },
    [onStockSelect],
  )

  const handleKeyDown = useCallback(
    (event) => {
      if (!isOpen && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
        setIsOpen(true)
        return
      }

      if (!isOpen) return

      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setHighlightedIndex((prev) => {
          const next = prev + 1
          return next >= suggestions.length ? 0 : next
        })
      } else if (event.key === 'ArrowUp') {
        event.preventDefault()
        setHighlightedIndex((prev) => {
          const next = prev - 1
          return next < 0 ? suggestions.length - 1 : next
        })
      } else if (event.key === 'Enter') {
        if (highlightedIndex >= 0 && highlightedIndex < suggestions.length) {
          event.preventDefault()
          selectStock(suggestions[highlightedIndex])
        }
      } else if (event.key === 'Escape') {
        setIsOpen(false)
        setHighlightedIndex(-1)
      }
    },
    [isOpen, suggestions, highlightedIndex, selectStock],
  )

  return (
    <div ref={containerRef} className="relative">
      {/* Search input wrapper */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-2 border-slate-400 rounded-xl shadow-md hover:shadow-lg focus-within:border-orange-500 focus-within:shadow-lg transition-all">
        {/* Search icon */}
        <span className="text-gray-400">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M8.5 3a5.5 5.5 0 013.983 9.304l3.606 3.607a1 1 0 01-1.415 1.414l-3.607-3.606A5.5 5.5 0 118.5 3zm0 2a3.5 3.5 0 100 7 3.5 3.5 0 000-7z"
              clipRule="evenodd"
            />
          </svg>
        </span>

        <input
          type="text"
          value={query}
          onChange={handleQueryChange}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          placeholder="Search stocks... (e.g. Reliance, TCS, HDFC Bank)"
          className="flex-1 bg-transparent outline-none text-gray-800 placeholder:text-gray-400 text-base font-medium"
        />

        {isLoading && (
          <div className="h-4 w-4 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
        )}

        {query && !isLoading && (
          <button
            type="button"
            onClick={clearSearch}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            ✕
          </button>
        )}
      </div>

      {/* Suggestions dropdown */}
      {isOpen && (suggestions?.length ?? 0) > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 z-50 bg-white rounded-xl shadow-xl border-2 border-slate-400 max-h-80 overflow-y-auto">
          <div className="px-4 py-2 text-xs font-semibold text-gray-600 border-b border-slate-300">
            {query.trim() ? `Results for "${query.trim()}"` : 'Popular Stocks'}
          </div>

          {suggestions.map((stock, index) => (
            <div
              key={stock.symbol}
              className={`flex items-center gap-3 px-4 py-3 border-b border-slate-200 last:border-0 cursor-pointer transition-colors ${
                index === highlightedIndex ? 'bg-orange-50' : 'hover:bg-orange-50'
              }`}
              onClick={() => selectStock(stock)}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              <div className="w-10 h-10 rounded-full bg-green-100 text-green-700 flex items-center justify-center font-bold text-sm">
                {(stock.display_symbol || stock.symbol || '?')[0]}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-gray-900 truncate">
                    {stock.display_symbol || stock.symbol}
                  </span>
                  <span className="text-[10px] px-2 py-1 rounded-full bg-gray-100 text-gray-600 font-medium">
                    {stock.exchange || 'NSE'}
                  </span>
                </div>
                <div className="text-xs text-gray-500 truncate">
                  {stock.company_name || ''}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {isOpen && !isLoading && suggestions.length === 0 && query.trim() && (
        <div className="absolute top-full left-0 right-0 mt-2 z-50 bg-white rounded-xl shadow-xl border-2 border-slate-400 p-4 text-sm text-gray-700">
          No stocks found for &quot;{query.trim()}&quot;
          <br />
          <span className="text-xs text-gray-400">
            Try searching by company name or NSE symbol.
          </span>
        </div>
      )}
    </div>
  )
}

export default StockSearch

