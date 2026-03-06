import { Link } from 'react-router-dom'
import { useState } from 'react'

function Login() {
  const [showPassword, setShowPassword] = useState(false)

  return (
    <div className="min-h-[60vh] flex items-center justify-center bg-slate-50 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-md bg-bharat-white rounded-2xl border-2 border-bharat-navy/40 shadow-lg p-6 sm:p-8">
        <h1 className="text-2xl font-semibold text-bharat-navy mb-2">Login</h1>
        <p className="text-sm text-slate-600 mb-6">
          Sign in to access your personalised dashboards, watchlists, and AI trading
          assistant.
        </p>

        <form className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Email or Mobile
            </label>
            <input
              type="text"
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 pr-10 text-sm shadow-sm focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
                placeholder="••••••••"
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
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3l18 18" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.58 10.58A2 2 0 0012 14a2 2 0 001.42-.58" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.88 5.09A10.94 10.94 0 0112 5c5 0 9.27 3.11 11 7-1.03 2.33-2.74 4.27-4.85 5.5M6.11 6.11C4.04 7.35 2.4 9.27 1 12c1.73 3.89 6 7 11 7 1.02 0 2-.13 2.93-.38" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="w-full mt-2 inline-flex items-center justify-center rounded-full bg-bharat-saffron px-4 py-2.5 text-sm font-semibold text-bharat-navy shadow-md hover:bg-orange-500 transition-colors"
          >
            Login
          </button>
        </form>

        <div className="mt-4 flex flex-col gap-2 text-xs text-slate-600">
          <p className="text-center">
            Or{' '}
            <Link to="/dashboard" className="font-semibold text-bharat-navy underline-offset-2 hover:underline">
              go to dashboard
            </Link>{' '}
            to explore the platform.
          </p>
        </div>
      </div>
    </div>
  )
}

export default Login

