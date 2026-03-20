import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import api from '../services/api'
import { onValue, push, ref, remove, serverTimestamp, set, update } from 'firebase/database'
import { db } from '../lib/firebase'
import { useAuth } from '../context/AuthContext'

function formatBotResponse(response) {
  if (!response) return 'Sorry, I did not get a response.'

  // Prefer pre-formatted message (standard macro/portfolio/stock analysis blocks)
  if (response.message && (!response.result || response.message.startsWith('**'))) {
    return response.message
  }

  const { source, result, query } = response
  if (!result) {
    return typeof response === 'string' ? response : JSON.stringify(response, null, 2)
  }

  // AI Advisor: compare_stocks (with markdown table)
  if (source === 'compare_stocks' && result.name1) {
    let text = `**${result.name1} vs ${result.name2}**\n\n`
    text += `| Metric | ${result.name1} | ${result.name2} |\n|--------|--------|--------|\n`
    text += `| Price | ₹${result.price1} | ₹${result.price2} |\n`
    text += `| PE Ratio | ${result.pe1 ?? 'N/A'} | ${result.pe2 ?? 'N/A'} |\n`
    text += `| Dividend Yield | ${result.dividendYield1}% | ${result.dividendYield2}% |\n\n`
    if (result.interpretation?.length) {
      text += `**Interpretation:**\n${result.interpretation.join(' ')}`
    }
    return text
  }

  // AI Advisor: buy_recommendation
  if (source === 'buy_recommendation' && result.symbol) {
    let text = `**Analysis: ${result.symbol.replace('.NS', '')}**\n\n`
    text += `Price: ₹${result.price}\nPE Ratio: ${result.pe ?? 'N/A'}\nSector: ${result.sector}\nSector Avg PE: ~${result.sector_avg_pe}\n\n`
    if (result.interpretation) text += `**Interpretation:**\n${result.interpretation}\n\n`
    if (result.risk_factors) text += `**Risk Factors:**\n${result.risk_factors}\n\n`
    if (result.conclusion) text += `**Conclusion:**\n${result.conclusion}`
    return text
  }

  // AI Advisor: market_news (with optional summary)
  if (source === 'market_news' && result.news) {
    const summary = result.summary ? `**${result.summary}**\n\n` : ''
    const lines = (result.news || []).slice(0, 5).map((n) => `- ${n.title || n.headline}${n.source ? ` (${n.source})` : ''}`)
    return `${summary}**Headlines (${result.market || 'NSE'}):**\n\n${lines.join('\n')}`
  }

  // AI Advisor: stock_analysis (with risk factors)
  if (source === 'stock_analysis' && result.symbol) {
    let text = `**${result.title || 'Stock Analysis'}**\n\n`
    text += `**Price:** ₹${result.price}\n**PE Ratio:** ${result.pe ?? 'N/A'}\n**Sector Avg PE:** ~${result.sector_avg_pe ?? 'N/A'}\n**Dividend Yield:** ${result.dividendYield ?? 0}%\n**Market Cap:** ${result.marketCap ?? 'N/A'}\n**Sector:** ${result.sector}\n\n`
    if (result.interpretation) text += `**Interpretation:**\n${result.interpretation}\n\n`
    if (result.risk_factors) text += `**Risk Factors:**\n${result.risk_factors}`
    return text
  }

  // AI Advisor: technical_analysis
  if (source === 'technical_analysis' && result.symbol) {
    let text = `**${result.title || 'Technical Analysis'}**\n\n`
    if (result.rsi) {
      const r = result.rsi
      text += `**RSI:** ${r.rsi} (${r.signal})\n`
    }
    if (result.moving_averages) {
      const m = result.moving_averages
      text += `**50 Day MA:** ₹${m.sma50}\n**200 Day MA:** ₹${m.sma200}\n**Price vs 200 MA:** ${m.signal_sma200}\n\n`
    }
    if (result.macd) {
      const mac = result.macd
      text += `**MACD:** ${mac.macd} | Signal: ${mac.signal} | Trend: ${mac.trend}\n\n`
    }
    if (result.interpretation?.length) {
      text += `**Interpretation:**\n${result.interpretation.join(' ')}`
    }
    return text
  }

  // AI Advisor: portfolio_analysis
  if (source === 'portfolio_analysis' && result.stocks) {
    let text = `**Portfolio Analysis**\n\n`
    text += `| Stock | Price | PE | Sector |\n|-------|-------|-----|--------|\n`
    for (const s of result.stocks) {
      text += `| ${(s.symbol || '').replace('.NS', '')} | ₹${s.price} | ${s.pe ?? 'N/A'} | ${s.sector ?? 'N/A'} |\n`
    }
    text += `\n**Sector breakdown:** ${JSON.stringify(result.sector_breakdown || {})}\n\n`
    if (result.diversification) text += `**Diversification:** ${result.diversification}\n\n`
    if (result.suggestions) text += `**Suggestions:** ${result.suggestions}`
    return text
  }

  // AI Advisor: market_trend (gainers/losers)
  if (source === 'market_trend' && result.gainers) {
    const g = (result.gainers || []).slice(0, 5).map((s) => `${s.symbol?.replace('.NS', '')}: +${s.change_percent}%`)
    const l = (result.losers || []).slice(0, 5).map((s) => `${s.symbol?.replace('.NS', '')}: ${s.change_percent}%`)
    return `**Market Trend (NIFTY 50)**\n\n**Top Gainers:**\n${g.join('\n')}\n\n**Top Losers:**\n${l.join('\n')}`
  }

  // AI Advisor: pe_ratio
  if (source === 'pe_ratio' && result.symbol) {
    return `PE ratio of ${result.symbol.replace('.NS', '')} is **${result.pe}** (price ₹${result.price}).`
  }

  // AI Advisor: dividend_yield
  if (source === 'dividend_yield' && result.symbol) {
    return `Dividend yield of ${result.symbol.replace('.NS', '')} is **${result.dividendYield}%** (price ₹${result.price}).`
  }

  // Handle known sources – stock_api (advisor format may include pe, sector)
  if (source === 'stock_api' && result.symbol) {
    let msg = `Current price of ${result.symbol.replace('.NS', '')} is **₹${result.price}**`
    if (result.change != null && result.change_percent != null) {
      msg += ` (change ${result.change} / ${result.change_percent}%)`
    }
    if (result.pe != null) msg += `. PE: ${result.pe}`
    if (result.sector && result.sector !== 'N/A') msg += `. Sector: ${result.sector}`
    msg += '.'
    return msg
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
    // New cross-market macro shape: result.signals + causal_insights
    if (result && result.signals) {
      const { signals, causal_insights, data_timestamp } = result

      const describe = (label, key) => {
        const s = signals?.[key]
        if (!s || typeof s !== 'object') {
          return `${label} data is currently unavailable.`
        }
        const current = Number.isFinite(Number(s.current_value)) ? Number(s.current_value) : null
        const pct = Number.isFinite(Number(s.change_pct)) ? Number(s.change_pct) : null
        const dir = s.direction || (pct != null && pct !== 0 ? (pct > 0 ? 'up' : 'down') : 'flat')
        if (current == null || pct == null) {
          return `${label} data is currently unavailable.`
        }
        const pctAbs = Math.abs(pct).toFixed(2)
        return `${label} is currently at ${current.toFixed(2)}, ${dir} ${pctAbs}% today.`
      }

      const lines = []
      lines.push('Here is the current cross-market macro backdrop:')
      lines.push(describe('US 10Y bond yield', 'us_10y_yield'))
      lines.push(describe('Crude oil (WTI)', 'wti_crude'))
      lines.push(describe('USD/INR', 'usd_inr'))
      lines.push(describe('Gold', 'gold'))
      lines.push(describe('India VIX', 'india_vix'))

      if (Array.isArray(causal_insights) && causal_insights.length > 0) {
        lines.push('')
        lines.push('How this typically affects Indian equities:')
        causal_insights.forEach((ins) => {
          const impact = ins.impact || 'Macro signal detected.'
          const severity = ins.severity || 'low'
          const sectors = Array.isArray(ins.affected_sectors) ? ins.affected_sectors.join(', ') : 'various sectors'
          lines.push(`- ${impact} (severity: ${severity}, sectors most affected: ${sectors}).`)
        })
      }

      if (data_timestamp) {
        try {
          const local = new Date(data_timestamp).toLocaleString()
          lines.push('')
          lines.push(`Data snapshot time: ${local}`)
        } catch {
          // ignore formatting errors
        }
      }

      return lines.join('\n')
    }

    // Legacy macro shapes (inflation / GDP / repo)
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

  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [editingMessageId, setEditingMessageId] = useState(null)
  const [editingText, setEditingText] = useState('')
  const [renamingSessionId, setRenamingSessionId] = useState(null)
  const [renamingTitle, setRenamingTitle] = useState('')

  const messagesEndRef = useRef(null)

  // Load chat sessions list
  useEffect(() => {
    if (!uid) return

    const chatsRef = ref(db, `users/${uid}/chats`)
    const unsubscribe = onValue(chatsRef, (snapshot) => {
      const val = snapshot.val() || {}
      const items = Object.entries(val).map(([id, data]) => ({
        id,
        title: data.title || 'New Chat',
        createdAt: typeof data.createdAt === 'number' ? data.createdAt : 0,
        updatedAt: typeof data.updatedAt === 'number' ? data.updatedAt : data.createdAt || 0,
      }))
      items.sort((a, b) => b.updatedAt - a.updatedAt)
      setSessions(items)

      if (!activeSessionId && items.length > 0) {
        setActiveSessionId(items[0].id)
      }
    })

    return () => unsubscribe()
  }, [uid, activeSessionId])

  // Load messages for active session
  useEffect(() => {
    if (!uid || !activeSessionId) {
      setMessages([
        {
          id: 'welcome',
          sender: 'bot',
          text: 'Hi, I am BharatFinanceAI. I know your saved stocks, Indian markets, and macro data. Ask concise, focused questions for best results.',
        },
      ])
      return
    }

    const msgsRef = ref(db, `users/${uid}/chats/${activeSessionId}/messages`)
    const unsubscribe = onValue(msgsRef, (snapshot) => {
      const val = snapshot.val() || {}
      const list = Object.entries(val).map(([id, data]) => ({
        id,
        ...data,
      }))
      list.sort((a, b) => {
        const ta = typeof a.createdAt === 'number' ? a.createdAt : 0
        const tb = typeof b.createdAt === 'number' ? b.createdAt : 0
        return ta - tb
      })
      if (list.length === 0) {
        setMessages([
          {
            id: 'welcome',
            sender: 'bot',
            text: 'Hi, I am BharatFinanceAI. I know your saved stocks, Indian markets, and macro data. Ask concise, focused questions for best results.',
          },
        ])
      } else {
        setMessages(list)
      }
    })

    return () => unsubscribe()
  }, [uid, activeSessionId])

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, loading])

  const ensureSession = async () => {
    if (!uid) throw new Error('Not signed in')
    if (activeSessionId) return activeSessionId

    const chatsRef = ref(db, `users/${uid}/chats`)
    const newRef = push(chatsRef)
    await set(newRef, {
      title: 'New Chat',
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp(),
    })
    setActiveSessionId(newRef.key)
    return newRef.key
  }

  const handleNewChat = async () => {
    if (!uid) return
    const chatsRef = ref(db, `users/${uid}/chats`)
    const newRef = push(chatsRef)
    await set(newRef, {
      title: 'New Chat',
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp(),
    })
    setActiveSessionId(newRef.key)
    setMessages([
      {
        id: 'welcome',
        sender: 'bot',
        text: 'New chat started. Ask anything about Indian markets, your watchlist, or macro data.',
      },
    ])
    setInput('')
  }

  const handleSend = async () => {
    const trimmed = input.trim()
    if (!trimmed || loading) return

    // UX: if user types "one more" after news/trend, infer the intent
    const t = trimmed.toLowerCase()
    const lastBot = [...messages].filter((m) => m.sender === 'bot').slice(-1)[0]
    const lastText = (lastBot?.text || '').toLowerCase()
    const inferred =
      (t === 'one more' || t === 'more' || t === 'again' || t === 'another') && lastText.includes('headlines')
        ? 'Show NSE news'
        : (t === 'one more' || t === 'more' || t === 'again' || t === 'another') && lastText.includes('market trend')
          ? 'Market trend'
          : trimmed

    setInput('')
    setLoading(true)

    try {
      if (!uid) {
        throw new Error('Not signed in')
      }

      const sessionId = await ensureSession()
      const basePath = `users/${uid}/chats/${sessionId}`
      const msgsRef = ref(db, `${basePath}/messages`)

      const userMsgRef = push(msgsRef)
      await set(userMsgRef, {
        sender: 'user',
        text: inferred,
        createdAt: serverTimestamp(),
      })

      // For future MCP/LLM: pass watchlist context (optional, currently ignored by backend)
      const response = await api.post('/chat', { query: inferred })
      const botText = formatBotResponse(response.data)

      const botMsgRef = push(msgsRef)
      await set(botMsgRef, {
        sender: 'bot',
        text: botText,
        createdAt: serverTimestamp(),
      })

      await update(ref(db, basePath), {
        updatedAt: serverTimestamp(),
        // Simple heuristic: title from first few words of user question
        title: inferred.length > 40 ? `${inferred.slice(0, 40)}…` : inferred,
      })
    } catch (error) {
      console.error('Chat /chat error:', error)
      const isTimeout =
        error?.code === 'ECONNABORTED' ||
        String(error?.message || '').toLowerCase().includes('timeout')
      const detail = isTimeout
        ? 'Market data is taking longer than usual to load. Please try your question again.'
        : error.response?.data?.detail || error.message || 'Sorry, something went wrong while contacting the server.'
      if (uid && activeSessionId) {
        const msgsRef = ref(db, `users/${uid}/chats/${activeSessionId}/messages`)
        const errRef = push(msgsRef)
        await set(errRef, {
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
      if (editingMessageId) {
        handleSaveEdit()
      } else {
        handleSend()
      }
    }
  }

  const handleDeleteMessage = async (messageId) => {
    if (!uid || !activeSessionId || !messageId) return
    const msgRef = ref(db, `users/${uid}/chats/${activeSessionId}/messages/${messageId}`)
    await remove(msgRef)
  }

  const handleStartEdit = (msg) => {
    setEditingMessageId(msg.id)
    setEditingText(msg.text)
  }

  const handleSaveEdit = async () => {
    if (!uid || !activeSessionId || !editingMessageId) return
    const trimmed = editingText.trim()
    if (!trimmed) {
      setEditingMessageId(null)
      return
    }
    const msgRef = ref(db, `users/${uid}/chats/${activeSessionId}/messages/${editingMessageId}`)
    await update(msgRef, { text: trimmed })
    setEditingMessageId(null)

    try {
      setLoading(true)
      const response = await api.post('/chat', { query: trimmed })
      const botText = formatBotResponse(response.data)

      const lastBot = [...messages].filter((m) => m.sender === 'bot').slice(-1)[0]
      if (lastBot?.id) {
        const botRef = ref(db, `users/${uid}/chats/${activeSessionId}/messages/${lastBot.id}`)
        await update(botRef, { text: botText })
      }
    } finally {
      setLoading(false)
    }
  }

  const handleRenameSession = async (sessionId, title) => {
    if (!uid || !sessionId) return
    const trimmed = (title || '').trim()
    if (!trimmed) {
      setRenamingSessionId(null)
      return
    }
    const sRef = ref(db, `users/${uid}/chats/${sessionId}`)
    await update(sRef, { title: trimmed, updatedAt: serverTimestamp() })
    setRenamingSessionId(null)
  }

  const handleDeleteSession = async (sessionId) => {
    if (!uid || !sessionId) return
    const sRef = ref(db, `users/${uid}/chats/${sessionId}`)
    await remove(sRef)
    if (activeSessionId === sessionId) {
      setActiveSessionId(null)
      setMessages([
        {
          id: 'welcome',
          sender: 'bot',
          text: 'Hi, I am BharatFinanceAI. Start a new chat to ask about your watchlist, Indian stocks, or macro data.',
        },
      ])
    }
  }

  const latestBotMessage = [...messages].filter((m) => m.sender === 'bot').slice(-1)[0]
  const latestUserMessage = [...messages].filter((m) => m.sender === 'user').slice(-1)[0]

  const handleCopyLatest = async () => {
    if (!latestBotMessage?.text) return
    try {
      await navigator.clipboard.writeText(latestBotMessage.text)
    } catch {
      // ignore
    }
  }

  const handleRegenerate = async () => {
    if (!uid || !activeSessionId || !latestUserMessage) return
    try {
      setLoading(true)
      const response = await api.post('/chat', { query: latestUserMessage.text })
      const botText = formatBotResponse(response.data)
      if (latestBotMessage?.id) {
        const botRef = ref(db, `users/${uid}/chats/${activeSessionId}/messages/${latestBotMessage.id}`)
        await update(botRef, { text: botText })
      } else {
        const msgsRef = ref(db, `users/${uid}/chats/${activeSessionId}/messages`)
        const botRef = push(msgsRef)
        await set(botRef, {
          sender: 'bot',
          text: botText,
          createdAt: serverTimestamp(),
        })
      }
    } finally {
      setLoading(false)
    }
  }

  const outerClassName = embedded ? 'w-full' : 'max-w-5xl mx-auto'
  const cardClassName = embedded
    ? `bg-white text-slate-900 flex flex-col ${heightClassName}`
    : `bg-white text-slate-900 rounded-xl border-2 border-slate-400 shadow-lg flex flex-col ${heightClassName} overflow-hidden`

  return (
    <div className={outerClassName}>
      <div className={cardClassName}>
        <div className="flex h-full">
          {/* Sidebar - Recent Chats */}
          <aside className="w-60 border-r border-slate-200 bg-slate-50 flex flex-col">
            <div className="px-3 py-3 border-b border-slate-200">
              <h2 className="text-xs font-semibold text-bharat-navy uppercase tracking-wide mb-2">
                Recent Chats
              </h2>
              <button
                type="button"
                onClick={handleNewChat}
                className="w-full px-3 py-1.5 rounded-lg bg-bharat-saffron text-bharat-navy text-xs font-semibold hover:bg-orange-500 transition-colors"
              >
                + New Chat
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setActiveSessionId(s.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setActiveSessionId(s.id)
                    }
                  }}
                  className={`w-full text-left px-2 py-2 rounded-lg border text-xs flex items-center justify-between gap-2 cursor-pointer ${
                    activeSessionId === s.id
                      ? 'border-bharat-navy bg-white text-bharat-navy'
                      : 'border-transparent bg-transparent text-slate-700 hover:bg-white hover:border-slate-200'
                  }`}
                >
                  <span className="flex-1 min-w-0">
                    {renamingSessionId === s.id ? (
                      <input
                        autoFocus
                        value={renamingTitle}
                        onChange={(e) => setRenamingTitle(e.target.value)}
                        onBlur={() => handleRenameSession(s.id, renamingTitle)}
                        onKeyDown={(e) => {
                          e.stopPropagation()
                          if (e.key === 'Enter') {
                            e.preventDefault()
                            handleRenameSession(s.id, renamingTitle)
                          }
                        }}
                        className="w-full bg-white border border-bharat-navy/40 rounded px-1 py-0.5 text-[11px] outline-none"
                      />
                    ) : (
                      <span className="block truncate">{s.title}</span>
                    )}
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setRenamingSessionId(s.id)
                        setRenamingTitle(s.title || '')
                      }}
                      className="text-slate-400 hover:text-bharat-navy"
                      title="Rename chat"
                    >
                      ✎
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDeleteSession(s.id)
                      }}
                      className="text-slate-400 hover:text-red-600"
                      title="Delete chat"
                    >
                      🗑
                    </button>
                  </span>
                </div>
              ))}
              {sessions.length === 0 && (
                <p className="text-[11px] text-slate-500 px-1">
                  No chats yet. Start a new conversation to see it here.
                </p>
              )}
            </div>
          </aside>

          {/* Main chat area */}
          <div className="flex-1 flex flex-col">
            <div
              className={`px-4 py-3 border-b-2 border-slate-400 flex items-center justify-between bg-gradient-to-r from-orange-50 to-white ${
                embedded ? '' : 'rounded-t-xl'
              }`}
            >
              <div>
                <h2 className="text-lg font-semibold text-slate-900">BharatFinanceAI – AI Advisor</h2>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  You are BharatFinanceAI. You have access to the user&apos;s saved stocks and live NSE/BSE data via MCP tools. Be concise, professional, and use Indian financial terminology.
                </p>
              </div>
              {loading && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-bharat-navy">Analyzing macro signals and market data...</span>
                  <span className="flex gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-bharat-navy animate-bounce [animation-delay:-0.2s]" />
                    <span className="w-1.5 h-1.5 rounded-full bg-bharat-navy animate-bounce [animation-delay:-0.1s]" />
                    <span className="w-1.5 h-1.5 rounded-full bg-bharat-navy animate-bounce" />
                  </span>
                </div>
              )}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
              {messages.map((msg, index) => {
                const isUser = msg.sender === 'user'
                const isEditing = editingMessageId === msg.id
                const canEdit = isUser && latestUserMessage && latestUserMessage.id === msg.id
                return (
                  <div
                    key={msg.id || index}
                    className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className="max-w-[80%] flex flex-col gap-1">
                      <div
                        className={`rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words border-2 ${
                          isUser
                            ? 'bg-bharat-saffron text-white border-bharat-saffron rounded-br-sm self-end'
                            : 'bg-white text-bharat-navy border-bharat-navy rounded-bl-sm self-start'
                        }`}
                      >
                        {isEditing ? (
                          <textarea
                            value={editingText}
                            onChange={(e) => setEditingText(e.target.value)}
                            onKeyDown={handleKeyDown}
                            className="w-full bg-transparent border border-white/40 rounded px-2 py-1 text-sm outline-none"
                            rows={2}
                          />
                        ) : isUser ? (
                          msg.text
                        ) : (
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              p: ({ node, ...props }) => (
                                <p className="mb-1 last:mb-0" {...props} />
                              ),
                              strong: ({ node, ...props }) => (
                                <strong className="font-semibold" {...props} />
                              ),
                              ul: ({ node, ...props }) => (
                                <ul className="list-disc pl-5 mb-1 last:mb-0" {...props} />
                              ),
                              ol: ({ node, ...props }) => (
                                <ol className="list-decimal pl-5 mb-1 last:mb-0" {...props} />
                              ),
                              table: ({ node, ...props }) => (
                                <div className="overflow-x-auto my-4">
                                  <table
                                    className="w-full border-collapse text-sm border border-gray-700 [&_tbody_tr:nth-child(even)]:bg-[rgba(255,255,255,0.03)] [&_tbody_tr:hover]:bg-[rgba(255,153,51,0.08)]"
                                    {...props}
                                  />
                                </div>
                              ),
                              th: ({ node, ...props }) => (
                                <th
                                  className="bg-[#0D1B3E] text-[#FF9933] px-4 py-2 text-left border border-gray-700 text-xs font-semibold"
                                  {...props}
                                />
                              ),
                              td: ({ node, ...props }) => (
                                <td
                                  className="px-4 py-2 border border-gray-700 text-slate-900 text-xs bg-white"
                                  {...props}
                                />
                              ),
                            }}
                          >
                            {msg.text}
                          </ReactMarkdown>
                        )}
                      </div>
                      <div
                        className={`flex items-center gap-2 ${
                          isUser ? 'justify-end text-[10px]' : 'justify-start text-[10px]'
                        } text-slate-400`}
                      >
                        {isUser && (
                          <>
                            {canEdit && (
                              <button
                                type="button"
                                onClick={() => handleStartEdit(msg)}
                                className="hover:text-bharat-navy"
                              >
                                Edit
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => handleDeleteMessage(msg.id)}
                              className="hover:text-red-600"
                            >
                              Delete
                            </button>
                          </>
                        )}
                        {!isUser && (
                          <button
                            type="button"
                            onClick={() => handleDeleteMessage(msg.id)}
                            className="hover:text-red-600"
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-white text-bharat-navy border-2 border-bharat-navy rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm flex items-center gap-2">
                    <span>Analyzing macro signals and market data...</span>
                    <span className="flex gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-bharat-navy animate-bounce [animation-delay:-0.2s]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-bharat-navy animate-bounce [animation-delay:-0.1s]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-bharat-navy animate-bounce" />
                    </span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Latest AI tools */}
            {latestBotMessage && (
              <div className="px-4 pb-2 flex justify-end gap-2 text-[11px]">
                <button
                  type="button"
                  onClick={handleCopyLatest}
                  className="px-2 py-1 rounded-full border border-slate-300 text-slate-700 hover:border-bharat-navy hover:text-bharat-navy transition-colors"
                >
                  Copy
                </button>
                <button
                  type="button"
                  onClick={handleRegenerate}
                  disabled={loading}
                  className="px-2 py-1 rounded-full border border-bharat-navy text-bharat-navy hover:bg-bharat-navy hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Regenerate
                </button>
              </div>
            )}

            {/* Input */}
            <div
              className={`border-t-2 border-slate-400 px-3 py-3 bg-slate-50 ${
                embedded ? '' : 'rounded-b-xl'
              }`}
            >
              <div className="flex items-end gap-2">
                <textarea
                  rows={1}
                  value={editingMessageId ? editingText : input}
                  onChange={(e) =>
                    editingMessageId ? setEditingText(e.target.value) : setInput(e.target.value)
                  }
                  onKeyDown={handleKeyDown}
                  placeholder='Ask a question, e.g. "What is the RSI of Reliance?"'
                  className="flex-1 resize-none rounded-lg bg-white text-slate-900 border-2 border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400 placeholder:text-slate-400"
                />
                <button
                  type="button"
                  onClick={editingMessageId ? handleSaveEdit : handleSend}
                  disabled={loading || !((editingMessageId ? editingText : input).trim())}
                  className="px-4 py-2 rounded-lg bg-bharat-saffron hover:bg-orange-500 text-bharat-navy text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {editingMessageId ? 'Save' : loading ? 'Sending...' : 'Send'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Chat

