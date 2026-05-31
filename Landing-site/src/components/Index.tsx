import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { BackgroundBeams } from './ui/background-beams'

export default function Index() {
  const [asciiTitle, setAsciiTitle] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    fetch('/branding/icetea-title.txt')
      .then((res) => res.text())
      .then(setAsciiTitle)
      .catch(console.error)
  }, [])

  return (
    <section className="min-h-[85vh] relative flex flex-col bg-black overflow-hidden selection:bg-[#ffb000] selection:text-black">
      <BackgroundBeams className="z-0" />
      {/* Subtle ambient background glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-[#ffb000]/10 blur-[120px] rounded-full pointer-events-none z-0" />

      {/* Modern minimalist navbar */}
      <nav className="relative z-20 px-8 py-6 w-full max-w-7xl mx-auto flex items-center justify-between">
        <motion.div 
          className="flex items-center gap-2"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <img
            src="/branding/icetea-pixel-wordmark.png"
            alt="Icetea"
            className="h-4 mix-blend-screen opacity-90"
          />
        </motion.div>
        
        <motion.div 
          className="flex items-center gap-8 text-sm font-medium text-white/60"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <a href="#terminal" className="hover:text-white transition-colors">Terminal</a>
          <a href="#agents" className="hover:text-white transition-colors">Agents</a>
          <Link to="/onboarding" className="text-black bg-white hover:bg-[#ffb000] px-4 py-2 rounded-full transition-colors font-semibold">Access Terminal</Link>
        </motion.div>
      </nav>

      {/* Hero content */}
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-4 py-12 text-center">
        
        {/* Rendered ASCII Art, beautifully centered and scaled */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="w-full flex justify-center mb-8"
        >
          <pre className="text-[2px] sm:text-[3px] md:text-[3.5px] lg:text-[4.5px] xl:text-[5px] leading-[1.05] text-white/80 font-mono whitespace-pre text-center overflow-hidden mix-blend-screen drop-shadow-lg">
            {asciiTitle}
          </pre>
        </motion.div>

        {/* Hero Copy */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3, ease: "easeOut" }}
          className="max-w-2xl mx-auto"
        >
          <h1 className="text-4xl md:text-5xl lg:text-6xl text-white mb-6 tracking-tight glow-text leading-tight">
            Trade like you have a 100-person team. <br className="hidden md:block" />
            <span className="text-white/50 italic font-serif">Without the team.</span>
          </h1>
          
          <p className="text-white/60 text-lg mb-10 font-light">
            Just you, a sleek terminal, and a pipeline of 11 specialist AI agents doing the heavy lifting.
          </p>

          {/* Email input - modern style */}
          <form 
            className="max-w-md mx-auto relative group"
            onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.currentTarget);
              const email = formData.get('email');
              navigate('/onboarding', { state: { email } });
            }}
          >
            <div className="absolute -inset-0.5 bg-gradient-to-r from-white/20 to-white/0 rounded-full blur opacity-50 group-hover:opacity-100 transition duration-500"></div>
            <div className="relative bg-black border border-white/10 rounded-full pl-6 pr-2 py-2 flex items-center gap-3">
              <input
                type="email"
                name="email"
                placeholder="Enter email for early access"
                className="flex-1 bg-transparent outline-none text-white placeholder:text-white/40 text-sm"
              />
              <button type="submit" className="bg-white rounded-full p-2.5 text-black hover:bg-[#ffb000] transition-colors flex-shrink-0 cursor-pointer">
                <ArrowRight size={18} />
              </button>
            </div>
          </form>
        </motion.div>
      </div>
    </section>
  )
}
