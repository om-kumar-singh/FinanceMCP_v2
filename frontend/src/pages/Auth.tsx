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
  const [showPassword, setShowPassword] = useState(false)
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
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-lg border-2 border-bharat-navy/60 bg-white px-3 py-2 pr-10 text-sm shadow-sm focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
                  placeholder="Minimum 6 characters"
                  autoComplete={isLogin ? 'current-password' : 'new-password'}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute inset-y-0 right-0 px-3 text-slate-500 hover:text-bharat-navy"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M3 3l18 18"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M10.58 10.58A2 2 0 0012 14a2 2 0 001.42-.58"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9.88 5.09A10.94 10.94 0 0112 5c5 0 9.27 3.11 11 7-1.03 2.33-2.74 4.27-4.85 5.5M6.11 6.11C4.04 7.35 2.4 9.27 1 12c1.73 3.89 6 7 11 7 1.02 0 2-.13 2.93-.38"
                      />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 15a3 3 0 100-6 3 3 0 000 6z"
                      />
                    </svg>
                  )}
                </button>
              </div>
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

