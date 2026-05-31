import { motion } from 'framer-motion'
import { CheckCircle2 } from 'lucide-react'

const AGENTS = [
  "Portfolio Health Monitor",
  "Risk Assessor",
  "Investment Strategy Planner",
  "Retirement Advisor",
  "Market Trend Analyzer",
  "Tax Optimization Agent",
  "Sector Specialist",
  "Bull vs Bear Debater",
  "ETF Matchmaker",
  "Macroeconomic Analyst",
  "Trading Psychology Coach"
]

export default function ServicesSection() {
  return (
    <section id="agents" className="bg-black py-24 px-4 md:px-8 pb-40">
      <div className="max-w-6xl mx-auto">
        
        <div className="flex flex-col md:flex-row items-start md:items-end justify-between mb-16 gap-8">
          <div>
            <h2 className="text-3xl md:text-5xl text-white mb-4">11 Specialist Agents</h2>
            <p className="text-white/50 text-lg max-w-2xl font-light">
              Why rely on a single generalized model? Icetea dynamically routes your queries to a team of highly specialized financial experts.
            </p>
          </div>
          <button className="text-sm font-medium text-black bg-white hover:bg-[#ffb000] transition-colors px-6 py-3 rounded-full flex-shrink-0 cursor-pointer">
            Explore All Capabilities
          </button>
        </div>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="premium-card p-8 md:p-12 relative overflow-hidden"
        >
          {/* Subtle background glow for this specific card */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full bg-[#ffb000]/5 blur-[100px] pointer-events-none" />
          
          <div className="relative z-10 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-y-6 gap-x-8">
            {AGENTS.map((agent, i) => (
              <motion.div 
                key={i}
                initial={{ opacity: 0, x: -10 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.05 }}
                className="flex items-center gap-3 group cursor-default"
              >
                <CheckCircle2 size={16} className="text-[#ffb000]/60 group-hover:text-[#ffb000] transition-colors" />
                <span className="text-white/70 text-sm font-medium group-hover:text-white transition-colors">{agent}</span>
              </motion.div>
            ))}
          </div>

          <div className="mt-16 pt-8 border-t border-white/10 flex flex-col items-center justify-center text-center">
            <img src="/branding/icetea-welcome.png" alt="Rose Graphic" className="h-32 object-contain mix-blend-screen opacity-40 mb-6" />
            <h3 className="text-2xl text-white mb-2 font-serif italic">Your personal advisory board.</h3>
            <p className="text-white/40 text-sm">Working in parallel, presenting a unified conclusion.</p>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
