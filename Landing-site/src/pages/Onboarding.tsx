import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Link, useLocation } from 'react-router-dom'
import { ArrowRight, Loader2 } from 'lucide-react'
import { BackgroundBeams } from '../components/ui/background-beams'

export default function Onboarding() {
  const location = useLocation()
  
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    experience: 'Intermediate',
    objective: 'Long-term Growth'
  })
  
  const [loading, setLoading] = useState(false)

  // Pre-fill email if passed via state from the hero section
  useEffect(() => {
    if (location.state?.email) {
      setFormData(prev => ({ ...prev, email: location.state.email }))
    }
  }, [location.state])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    
    // Simulate provisioning delay then redirect to main app
    const terminalUrl =
      (import.meta.env.VITE_TERMINAL_URL as string | undefined)?.trim() ||
      (import.meta.env.DEV ? 'http://localhost:5173/' : '/app/')
    setTimeout(() => {
      window.location.href = terminalUrl
    }, 2000)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }))
  }

  return (
    <div className="min-h-screen relative flex flex-col bg-black overflow-hidden selection:bg-[#ffb000] selection:text-black pb-12">
      <BackgroundBeams className="z-0" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-[#ffb000]/10 blur-[120px] rounded-full pointer-events-none z-0" />

      {/* Navbar */}
      <nav className="relative z-20 px-8 py-6 w-full max-w-7xl mx-auto flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <img src="/branding/icetea-pixel-wordmark.png" alt="Icetea" className="h-4 mix-blend-screen opacity-90" />
        </Link>
        <div className="flex items-center gap-8 text-sm font-medium text-white/60">
          <Link to="/" className="text-white hover:text-[#ffb000] transition-colors">Return to Home</Link>
        </div>
      </nav>

      {/* Main Content */}
      <div className="relative z-10 flex-1 flex items-center justify-center px-4 py-8">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="w-full max-w-md premium-card p-8 md:p-10"
        >
          <div className="text-center mb-10">
            <h1 className="text-3xl text-white glow-text mb-2">Initialize Profile</h1>
            <p className="text-white/50 text-sm font-light">Configure your AI pipeline before accessing the terminal.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label className="text-xs font-medium text-white/70 uppercase tracking-widest pl-1">Full Name</label>
              <div className="relative group">
                <div className="absolute -inset-0.5 bg-gradient-to-r from-white/20 to-white/0 rounded-xl blur opacity-0 group-focus-within:opacity-100 transition duration-500"></div>
                <input
                  type="text"
                  name="name"
                  required
                  value={formData.name}
                  onChange={handleChange}
                  className="relative w-full bg-black/50 border border-white/10 rounded-xl px-4 py-3 text-white text-sm outline-none focus:border-[#ffb000]/50 transition-colors"
                  placeholder="Jane Doe"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium text-white/70 uppercase tracking-widest pl-1">Email</label>
              <div className="relative group">
                <div className="absolute -inset-0.5 bg-gradient-to-r from-white/20 to-white/0 rounded-xl blur opacity-0 group-focus-within:opacity-100 transition duration-500"></div>
                <input
                  type="email"
                  name="email"
                  required
                  value={formData.email}
                  onChange={handleChange}
                  className="relative w-full bg-black/50 border border-white/10 rounded-xl px-4 py-3 text-white text-sm outline-none focus:border-[#ffb000]/50 transition-colors"
                  placeholder="name@example.com"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium text-white/70 uppercase tracking-widest pl-1">Experience Level</label>
              <div className="relative group">
                <div className="absolute -inset-0.5 bg-gradient-to-r from-white/20 to-white/0 rounded-xl blur opacity-0 group-focus-within:opacity-100 transition duration-500"></div>
                <select
                  name="experience"
                  value={formData.experience}
                  onChange={handleChange}
                  className="relative w-full bg-black/50 border border-white/10 rounded-xl px-4 py-3 text-white text-sm outline-none focus:border-[#ffb000]/50 transition-colors appearance-none cursor-pointer"
                >
                  <option value="Novice">Novice (Just starting out)</option>
                  <option value="Intermediate">Intermediate (Occasional trader)</option>
                  <option value="Advanced">Advanced (Active investor)</option>
                </select>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium text-white/70 uppercase tracking-widest pl-1">Primary Objective</label>
              <div className="relative group">
                <div className="absolute -inset-0.5 bg-gradient-to-r from-white/20 to-white/0 rounded-xl blur opacity-0 group-focus-within:opacity-100 transition duration-500"></div>
                <select
                  name="objective"
                  value={formData.objective}
                  onChange={handleChange}
                  className="relative w-full bg-black/50 border border-white/10 rounded-xl px-4 py-3 text-white text-sm outline-none focus:border-[#ffb000]/50 transition-colors appearance-none cursor-pointer"
                >
                  <option value="Long-term Growth">Long-term Growth</option>
                  <option value="Retirement">Retirement Planning</option>
                  <option value="Day Trading">Day Trading & Alpha</option>
                  <option value="Risk Hedging">Risk Hedging</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-white text-black hover:bg-[#ffb000] transition-colors rounded-xl py-3 text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed mt-6"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  Provisioning Agents...
                </>
              ) : (
                <>
                  Deploy Pipeline <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
        </motion.div>
      </div>
    </div>
  )
}
