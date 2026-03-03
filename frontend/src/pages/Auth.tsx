import type { FC, FormEvent } from 'react'
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

function friendlyAuthError(err: any, mode: 'login' | 'signup') {
  const code = err?.code || err?.error?.code

  if (code === 'auth/invalid-credential') {
    return 'Check your email and password. If you are new, register first.'
  }
  if (code === 'auth/user-not-found') {
    return 'No account found with this email. Please register first.'
  }
  if (code === 'auth/wrong-password') {
    return 'Incorrect password. Please try again.'
  }
  if (code === 'auth/email-already-in-use') {
    return 'This email is already registered. Please login instead.'
  }
  if (code === 'auth/weak-password') {
    return 'Password is too weak. Please use at least 6 characters.'
  }
  if (code === 'auth/invalid-email') {
    return 'Please enter a valid email address.'
  }
  if (code === 'auth/configuration-not-found') {
    return 'Firebase Auth configuration not found. Check your Firebase project setup and authorized domains.'
  }

  // Fallbacks
  if (typeof err?.message === 'string' && err.message.trim()) return err.message
  return mode === 'signup'
    ? 'Registration failed. Please try again.'
    : 'Login failed. Please try again.'
}

const Auth: FC = () => {
  const { user, loading, login, register } = useAuth()
  const navigate = useNavigate()

  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    if (!loading && user) {
      navigate('/dashboard', { replace: true })
    }
  }, [user, loading, navigate])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (submitting) return

    setError(null)
    setSuccess(null)

    if (!email.trim()) {
      setError('Please enter an email address.')
      return
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters long.')
      return
    }

    try {
      setSubmitting(true)
      if (mode === 'login') {
        await login(email.trim(), password)
        setSuccess('Signed in successfully.')
        navigate('/dashboard', { replace: true, state: { toast: 'Welcome back! You are signed in.' } })
      } else {
        await register(email.trim(), password)
        setSuccess('Account created successfully.')
        navigate('/dashboard', { replace: true, state: { toast: 'Account created successfully!' } })
      }
    } catch (err: any) {
      setError(friendlyAuthError(err, mode))
    } finally {
      setSubmitting(false)
    }
  }

  const isLogin = mode === 'login'

  return (
    <div className="min-h-[70vh] flex items-center justify-center bg-slate-50 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl border-2 border-bharat-navy/40 shadow-[0_18px_45px_rgba(0,0,128,0.25)] p-6 sm:p-8">
          <div className="flex justify-center mb-6">
            <div className="inline-flex items-center rounded-full bg-bharat-navy/5 border border-bharat-navy/30 px-3 py-1 text-[11px] font-semibold tracking-wide text-bharat-navy uppercase">
              Secure Access · BharatFinanceAI
            </div>
          </div>

          <div className="flex items-center justify-center gap-2 mb-6 text-sm font-semibold text-bharat-navy">
            <button
              type="button"
              onClick={() => setMode('login')}
              className={`px-4 py-1.5 rounded-full border text-xs sm:text-sm transition-colors ${
                isLogin
                  ? 'bg-bharat-navy text-white border-bharat-navy'
                  : 'bg-white text-bharat-navy border-bharat-navy/40 hover:bg-bharat-navy/5'
              }`}
            >
              Login
            </button>
            <button
              type="button"
              onClick={() => setMode('signup')}
              className={`px-4 py-1.5 rounded-full border text-xs sm:text-sm transition-colors ${
                !isLogin
                  ? 'bg-bharat-navy text-white border-bharat-navy'
                  : 'bg-white text-bharat-navy border-bharat-navy/40 hover:bg-bharat-navy/5'
              }`}
            >
              Register
            </button>
          </div>

          <h1 className="text-xl sm:text-2xl font-semibold text-bharat-navy text-center mb-2">
            {isLogin ? 'Welcome back' : 'Create your BharatFinanceAI account'}
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 text-center mb-4">
            Use your email to {isLogin ? 'sign in to' : 'get started with'} Indian Markets Intelligence.
          </p>

          {error && (
            <div className="mb-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs sm:text-sm text-red-700">
              {error}
            </div>
          )}

          {success && (
            <div className="mb-3 rounded-lg border border-bharat-green/60 bg-bharat-green/10 px-3 py-2 text-xs sm:text-sm text-bharat-green">
              {success}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4 mt-2">
            <div>
              <label className="block text-xs font-medium text-bharat-navy mb-1.5">Email address</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border-2 border-bharat-navy/60 bg-white px-3 py-2 text-sm shadow-sm focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-bharat-navy mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border-2 border-bharat-navy/60 bg-white px-3 py-2 text-sm shadow-sm focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
                placeholder="Minimum 6 characters"
                autoComplete={isLogin ? 'current-password' : 'new-password'}
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full mt-2 inline-flex items-center justify-center rounded-full bg-bharat-saffron px-4 py-2.5 text-sm font-semibold text-bharat-navy shadow-md hover:bg-orange-500 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? 'Please wait…' : isLogin ? 'Sign In' : 'Create Account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

export default Auth

