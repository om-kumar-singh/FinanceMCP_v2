import axios from 'axios'

// In dev, use Vite proxy (/api → localhost:8000) to avoid CORS/network errors.
const baseURL = import.meta.env.DEV ? '/api' : (import.meta.env.VITE_API_URL || 'http://localhost:8000')

const api = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 60000, // Resilience predictor can take 30+ seconds (ML, Monte Carlo, yfinance)
})

export const searchStocks = async (query, limit = 8, signal) => {
  const response = await api.get('/stock/search', {
    params: { q: query, limit },
    signal,
  })
  return response.data
}

export const getPopularStocks = async () => {
  const response = await api.get('/stock/popular')
  return response.data
}

export const resolveSymbol = async (query) => {
  const response = await api.get('/stock/resolve', {
    params: { q: query },
  })
  return response.data
}

export const getMarketNews = async (symbol) => {
  const safeSymbol = symbol || 'NSE'
  const response = await api.get(`/news/${encodeURIComponent(safeSymbol)}`)
  return response.data
}

export const searchMutualFunds = async (query) => {
  const response = await api.get('/mutual-fund/search', {
    params: { query },
  })
  return response.data
}

export const getMutualFundNav = async (schemeCode) => {
  if (!schemeCode) throw new Error('schemeCode is required')
  const response = await api.get(`/mutual-fund/${encodeURIComponent(schemeCode)}`)
  return response.data
}

export const calculateSip = async (monthlyInvestment, years, annualReturn) => {
  const response = await api.get('/sip', {
    params: {
      monthly_investment: monthlyInvestment,
      years,
      annual_return: annualReturn,
    },
  })
  return response.data
}

export const predictResilience = async (payload) => {
  const response = await api.post('/predict-resilience', payload)
  return response.data
}

export default api
