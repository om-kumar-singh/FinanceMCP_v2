function Footer() {
  return (
    <footer className="bg-bharat-navy text-bharat-white/80 border-t border-bharat-navy/70 mt-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs sm:text-sm">
        <p className="tracking-wide">
          © {new Date().getFullYear()} BharatFinanceAI. Built for Indian markets.
        </p>
        <p className="text-bharat-white/60">
          Powered by NSE data, technical indicators, and AI insights.
        </p>
      </div>
    </footer>
  )
}

export default Footer

