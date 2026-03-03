import type { FC } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import UserProfile from './UserProfile'

const Navbar: FC = () => {
  const { user, loading } = useAuth()

  return (
    <nav className="bg-bharat-navy text-bharat-white border-b-2 border-bharat-white/20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-bharat-white/10 border border-bharat-white/30 flex items-center justify-center">
              <span className="text-bharat-saffron font-bold text-lg">₹</span>
            </div>
            <div>
              <Link to="/" className="flex flex-col">
                <span className="text-lg font-semibold tracking-tight">BharatFinanceAI</span>
                <span className="text-[11px] uppercase tracking-[0.18em] text-bharat-white/70">
                  Indian Markets Intelligence
                </span>
              </Link>
            </div>
          </div>

          {/* Nav links */}
          <div className="hidden md:flex items-center gap-6 text-sm font-medium">
            <a
              href="/#features"
              className="px-3 py-1.5 rounded-full hover:bg-bharat-white/10 hover:text-bharat-saffron hover:underline underline-offset-4 transition-colors"
            >
              Features
            </a>
            <a
              href="/#about"
              className="px-3 py-1.5 rounded-full hover:bg-bharat-white/10 hover:text-bharat-saffron hover:underline underline-offset-4 transition-colors"
            >
              About
            </a>

            {!loading && !user && (
              <Link
                to="/login"
                className="inline-flex items-center rounded-full bg-bharat-saffron px-4 py-1.5 text-sm font-semibold text-bharat-navy shadow-sm hover:bg-orange-500 transition-colors"
              >
                Login
              </Link>
            )}

            {!loading && user && <UserProfile />}
          </div>
        </div>
      </div>
    </nav>
  )
}

export default Navbar

