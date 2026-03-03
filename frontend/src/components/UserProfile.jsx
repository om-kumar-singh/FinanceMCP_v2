import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

function UserProfile() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)

  const email = user?.email || 'Signed in'
  const initial = useMemo(() => {
    const source = (user?.email || user?.displayName || 'U').trim()
    return (source[0] || 'U').toUpperCase()
  }, [user])

  useEffect(() => {
    const onDocClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const handleLogout = async () => {
    try {
      await logout()
    } finally {
      setOpen(false)
      navigate('/', { replace: true })
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="h-10 w-10 rounded-full bg-bharat-navy border-2 border-bharat-white/30 text-white font-bold flex items-center justify-center hover:bg-bharat-navy/90 transition-colors"
        aria-label="User menu"
      >
        {initial}
      </button>

      {open && (
        <div className="absolute right-0 mt-3 w-72 rounded-xl bg-white border-2 border-slate-400 shadow-xl overflow-hidden z-50">
          <div className="px-4 py-3 border-b border-slate-300 bg-slate-50">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Signed in as
            </div>
            <div className="text-sm font-semibold text-bharat-navy truncate">{email}</div>
          </div>

          <div className="p-2">
            <button
              type="button"
              onClick={handleLogout}
              className="w-full text-left flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold text-red-600 hover:bg-red-50 transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default UserProfile

