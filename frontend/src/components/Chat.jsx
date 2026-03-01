import { useEffect, useRef, useState } from 'react'
import api from '../services/api'

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

function Chat() {
  const [messages, setMessages] = useState([
    {
      sender: 'bot',
      text: 'Hi, I am BharatFinanceAI assistant. Ask me about stocks, RSI, MACD, SIP, mutual funds, IPOs, or macro data (repo rate, inflation, GDP).',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  const handleSend = async () => {
    const trimmed = input.trim()
    if (!trimmed || loading) return

    const userMessage = { sender: 'user', text: trimmed }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const response = await api.post('/ask', { query: trimmed })
      const botText = formatBotResponse(response.data)
      const botMessage = { sender: 'bot', text: botText }
      setMessages((prev) => [...prev, botMessage])
    } catch (error) {
      const detail =
        error.response?.data?.detail || 'Sorry, something went wrong while contacting the server.'
      setMessages((prev) => [
        ...prev,
        { sender: 'bot', text: detail },
      ])
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

  return (
    <div className="max-w-5xl mx-auto">
      <div className="bg-slate-900 text-slate-100 rounded-xl shadow-lg flex flex-col h-[480px] md:h-[560px]">
        <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold">AI Chat</h2>
          {loading && <span className="text-xs text-slate-400">BharatFinanceAI is thinking...</span>}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
          {messages.map((msg, index) => (
            <div
              key={index}
              className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap break-words ${
                  msg.sender === 'user'
                    ? 'bg-indigo-500 text-white rounded-br-sm'
                    : 'bg-slate-800 text-slate-100 rounded-bl-sm'
                }`}
              >
                {msg.text}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-slate-700 px-3 py-3">
          <div className="flex items-end gap-2">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder='Ask a question, e.g. "What is the RSI of Reliance?"'
              className="flex-1 resize-none rounded-lg bg-slate-800 text-slate-100 border border-slate-600 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder:text-slate-400"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="px-4 py-2 rounded-lg bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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

