import { Link } from 'react-router-dom'

function Login() {
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
            <input
              type="password"
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-bharat-navy focus:ring-1 focus:ring-bharat-navy outline-none"
              placeholder="••••••••"
            />
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

