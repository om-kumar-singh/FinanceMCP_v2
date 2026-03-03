import { useEffect, useRef, useState } from 'react'
import api from '../services/api'
import { onValue, push, query, ref, serverTimestamp } from 'firebase/database'
import { db } from '../lib/firebase'
import { useAuth } from '../context/AuthContext'

function formatBotResponse(response) {
  if (!response) return 'Sorry, I did not get a response.'

  if (response.message && !response.result) {
    return response.message
  }

  const { source, result, query } = response
  if (!result) {
    return typeof response === 'string' ? response : JSON.stringify(response, null, 2)
  }

  // Handle known sources
  if (source === 'stock_api' && result.symbol) {
    return `Current price of ${result.symbol} is ₹${result.price} (change ${result.change} / ${result.change_percent}% ).`
  }

  if (source === 'rsi' && result.symbol) {
    return `RSI for ${result.symbol} is ${result.rsi} (${result.signal}).`
  }

  if (source === 'macd' && result.symbol) {
    return `MACD for ${result.symbol}: MACD ${result.macd}, signal ${result.signal}, histogram ${result.histogram} (trend ${result.trend}).`
  }

  if (source === 'gainers_losers' && result.gainers) {
    const g = result.gainers.slice(0, 3).map((s) => `${s.symbol}: +${s.change_percent}%`)
    const l = result.losers.slice(0, 3).map((s) => `${s.symbol}: ${s.change_percent}%`)
    return `Top gainers:\n${g.join('\n')}\n\nTop losers:\n${l.join('\n')}`
  }

  if (source === 'moving_averages' && result.symbol) {
    return `${result.symbol}: Price ₹${result.price}, SMA20 ${result.sma20} (${result.signal_sma20}), SMA50 ${result.sma50} (${result.signal_sma50}), SMA200 ${result.sma200} (${result.signal_sma200}).`
  }

  if (source === 'bollinger' && result.symbol) {
    return `Bollinger Bands for ${result.symbol}: upper ${result.upper}, middle ${result.middle}, lower ${result.lower} (signal: ${result.signal}).`
  }

  if (source === 'sip' && result.future_value !== undefined) {
    return `If you invest ₹${result.monthly_investment} per month for ${result.years} years at ${result.annual_return}% annual return, your future value could be around ₹${result.future_value}.`
  }

  if (source === 'mutual_fund' && result.scheme_name) {
    return `Latest NAV for scheme ${result.scheme_name} (code ${result.scheme_code}) is ${result.nav} as of ${result.date}.`
  }

  if (source === 'ipo' && Array.isArray(result)) {
    const first = result[0]
    if (!first) {
      return 'No upcoming IPOs found.'
    }
    const lines = result.slice(0, 3).map((ipo) => {
      return `${ipo.name}: opens ${ipo.open_date}, closes ${ipo.close_date}, price band ${ipo.price_band}.`
    })
    return `Here are some upcoming IPOs:\n- ${lines.join('\n- ')}`
  }

  if (source === 'macro') {
    if (Array.isArray(result) && result[0]?.inflation !== undefined) {
      const lines = result
        .slice(0, 3)
        .map((r) => `${r.year}: ${r.inflation}%`)
      return `Recent CPI inflation for India:\n${lines.join('\n')}`
    }
    if (Array.isArray(result) && result[0]?.gdp_growth !== undefined) {
      const lines = result
        .slice(0, 3)
        .map((r) => `${r.year}: ${r.gdp_growth}%`)
      return `Recent GDP growth for India:\n${lines.join('\n')}`
    }
    if (result.repo_rate !== undefined) {
      return `Current RBI repo rate is ${result.repo_rate}% (last updated ${result.last_updated}).`
    }
  }

  // Generic fallback
  return `Here is what I found for "${query || ''}":\n${JSON.stringify(result, null, 2)}`
}

function Chat({ embedded = false, heightClassName = 'h-[480px] md:h-[560px]' }) {
  const { user } = useAuth()
  const uid = user?.uid
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    if (!uid) return

    const chatsRef = ref(db, `users/${uid}/chats`)
    const chatsQuery = query(chatsRef)

    const unsubscribe = onValue(chatsQuery, (snapshot) => {
      const val = snapshot.val()
      if (!val) {
        setMessages([
          {
            id: 'welcome',
            sender: 'bot',
            text: 'Hi, I am BharatFinanceAI assistant. Ask me about stocks, RSI, MACD, SIP, mutual funds, IPOs, or macro data (repo rate, inflation, GDP).',
          },
        ])
        return
      }

      const next = Object.entries(val).map(([id, msg]) => ({
        id,
        ...msg,
      }))

      next.sort((a, b) => {
        const ta = typeof a.createdAt === 'number' ? a.createdAt : 0
        const tb = typeof b.createdAt === 'number' ? b.createdAt : 0
        return ta - tb
      })

      setMessages(next)
    })

    return () => unsubscribe()
  }, [uid])

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  const handleSend = async () => {
    const trimmed = input.trim()
    if (!trimmed || loading) return

    setInput('')
    setLoading(true)

    try {
      if (!uid) {
        throw new Error('Not signed in')
      }

      const chatsRef = ref(db, `users/${uid}/chats`)
      await push(chatsRef, {
        sender: 'user',
        text: trimmed,
        createdAt: serverTimestamp(),
      })

      const response = await api.post('/ask', { query: trimmed })
      const botText = formatBotResponse(response.data)
      await push(chatsRef, {
        sender: 'bot',
        text: botText,
        createdAt: serverTimestamp(),
      })
    } catch (error) {
      console.error('Chat /ask error:', error)
      const detail =
        error.response?.data?.detail || error.message || 'Sorry, something went wrong while contacting the server.'
      if (uid) {
        const chatsRef = ref(db, `users/${uid}/chats`)
        await push(chatsRef, {
          sender: 'bot',
          text: detail,
          createdAt: serverTimestamp(),
        })
      }
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  const outerClassName = embedded ? 'w-full' : 'max-w-5xl mx-auto'
  const cardClassName = embedded
    ? `bg-white text-slate-900 flex flex-col ${heightClassName}`
    : `bg-white text-slate-900 rounded-xl border-2 border-slate-400 shadow-lg flex flex-col ${heightClassName} overflow-hidden`

  return (
    <div className={outerClassName}>
      <div className={cardClassName}>
        <div
          className={`px-4 py-3 border-b-2 border-slate-400 flex items-center justify-between bg-gradient-to-r from-orange-50 to-white ${
            embedded ? '' : 'rounded-t-xl'
          }`}
        >
          <h2 className="text-lg font-semibold text-slate-900">AI Chat</h2>
          {loading && <span className="text-xs text-orange-500">BharatFinanceAI is thinking...</span>}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
          {messages.map((msg, index) => (
            <div
              key={msg.id || index}
              className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap break-words border ${
                  msg.sender === 'user'
                    ? 'bg-orange-500 text-white border-orange-500 rounded-br-sm'
                    : 'bg-slate-50 text-slate-900 border-slate-300 rounded-bl-sm'
                }`}
              >
                {msg.text}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className={`border-t-2 border-slate-400 px-3 py-3 bg-slate-50 ${embedded ? '' : 'rounded-b-xl'}`}>
          <div className="flex items-end gap-2">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder='Ask a question, e.g. "What is the RSI of Reliance?"'
              className="flex-1 resize-none rounded-lg bg-white text-slate-900 border-2 border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400 placeholder:text-slate-400"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="px-4 py-2 rounded-lg bg-green-500 hover:bg-green-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Sending...' : 'Send'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Chat

