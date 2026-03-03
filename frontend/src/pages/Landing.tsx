import type { FC } from 'react'
import { Link } from 'react-router-dom'

const Landing: FC = () => {
  return (
    <div className="bg-slate-50 min-h-screen">
      {/* Hero Section */}
      <section className="bg-gradient-to-b from-bharat-navy via-bharat-navy to-slate-900 text-bharat-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-20 lg:py-24 grid gap-10 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] items-center">
          <div>
            <p className="inline-flex items-center rounded-full bg-bharat-white/10 px-3 py-1 text-xs font-semibold tracking-wide text-bharat-white/80 mb-4">
              Made for Indian traders &amp; investors
            </p>
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight">
              Indian Markets Intelligence
            </h1>
            <p className="mt-4 text-sm sm:text-base text-bharat-white/80 max-w-xl">
              BharatFinanceAI combines live NSE data, technical indicators, and an AI
              assistant so you can move from raw charts to clear trading decisions
              in seconds.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                to="/login"
                className="inline-flex items-center justify-center rounded-full bg-bharat-saffron px-6 py-2.5 text-sm font-semibold text-bharat-navy shadow-md hover:bg-orange-500 transition-colors"
              >
                Get Started
              </Link>
              <a
                href="/#features"
                className="inline-flex items-center justify-center rounded-full border border-bharat-white/40 bg-bharat-white/5 px-6 py-2.5 text-sm font-semibold text-bharat-white hover:bg-bharat-white/10 transition-colors"
              >
                Explore Features
              </a>
            </div>

            <div className="mt-8 grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs sm:text-sm text-bharat-white/80">
              <div className="border-l-2 border-bharat-saffron pl-3">
                <p className="font-semibold text-bharat-white">NSE Focused</p>
                <p>Built around Indian equities, indices, and sectors.</p>
              </div>
              <div className="border-l-2 border-emerald-400 pl-3">
                <p className="font-semibold text-bharat-white">Signal Driven</p>
                <p>RSI/MACD, Bollinger Bands, and trend detection.</p>
              </div>
              <div className="border-l-2 border-sky-400 pl-3 sm:block hidden">
                <p className="font-semibold text-bharat-white">AI Assistance</p>
                <p>Ask natural language questions about any stock.</p>
              </div>
            </div>
          </div>

          <div className="bg-bharat-white rounded-2xl shadow-2xl border-2 border-bharat-navy/40 p-5 sm:p-6 space-y-4">
            <p className="text-xs font-semibold tracking-wide text-bharat-navy/70 uppercase">
              Snapshot
            </p>
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-bharat-navy/80">Market Mood</span>
                <span className="inline-flex items-center rounded-full bg-bharat-green/10 px-3 py-1 text-xs font-semibold text-bharat-green border border-bharat-green/30">
                  Mildly Bullish
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-bharat-navy/80">Signals Tracked</span>
                <span className="font-semibold text-bharat-navy">RSI · MACD · BB</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-bharat-navy/80">Coverage</span>
                <span className="font-semibold text-bharat-navy">Full NSE universe</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section
        id="features"
        className="bg-bharat-white py-14 sm:py-16 border-b-2 border-slate-300"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="text-2xl sm:text-3xl font-semibold text-bharat-navy mb-6">
            Built for serious market participants
          </h2>
          <div className="grid gap-6 md:grid-cols-3">
            <div className="bg-white rounded-xl border-2 border-slate-400 shadow-sm hover:shadow-md transition-shadow p-5">
              <h3 className="text-lg font-semibold text-bharat-navy mb-2">
                Technical Indicators (RSI/MACD)
              </h3>
              <p className="text-sm text-slate-700">
                BharatFinanceAI computes RSI and MACD for your symbols so you can quickly
                spot overbought, oversold, and momentum shifts without juggling multiple
                charting tools. This helps you time entries and exits with more
                confidence instead of trading purely on gut feeling.
              </p>
            </div>
            <div className="bg-white rounded-xl border-2 border-slate-400 shadow-sm hover:shadow-md transition-shadow p-5">
              <h3 className="text-lg font-semibold text-bharat-navy mb-2">
                Real-time NSE Data
              </h3>
              <p className="text-sm text-slate-700">
                Live price and volume data from the NSE keeps every analysis grounded in
                the current market, not yesterday&apos;s close. Intraday traders can
                react faster to breakouts, reversals, and sector rotations as they
                happen.
              </p>
            </div>
            <div className="bg-white rounded-xl border-2 border-slate-400 shadow-sm hover:shadow-md transition-shadow p-5">
              <h3 className="text-lg font-semibold text-bharat-navy mb-2">
                AI Financial Assistant
              </h3>
              <p className="text-sm text-slate-700">
                Ask questions like &quot;What&apos;s the RSI of TCS?&quot; or
                &quot;Summarise my portfolio risk&quot; and get structured answers in
                plain English. This reduces research time and lets you run deeper checks
                on your ideas before putting capital at risk.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* About Section */}
      <section id="about" className="bg-slate-50 py-12 sm:py-16">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-2xl sm:text-3xl font-semibold text-bharat-navy mb-4">
            About BharatFinanceAI
          </h2>
          <p className="text-sm sm:text-base text-slate-700 leading-relaxed">
            BharatFinanceAI is built with one goal: to give Indian traders and investors
            institutional-grade tools without institutional complexity. By combining
            real-time NSE data, battle-tested technical indicators, and an AI assistant
            that understands your questions, we aim to make disciplined, data-backed
            decision making accessible to everyone from first-time investors to seasoned
            market professionals.
          </p>
        </div>
      </section>
    </div>
  )
}

export default Landing

