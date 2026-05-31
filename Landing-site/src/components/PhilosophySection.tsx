import { motion } from 'framer-motion'

export default function PhilosophySection() {
  return (
    <section className="bg-black py-24 px-4 md:px-8 relative">
      <div className="max-w-6xl mx-auto">
        <div className="mb-16 text-center md:text-left">
          <h2 className="text-3xl md:text-5xl text-white mb-4">Architecture</h2>
          <p className="text-white/50 text-lg max-w-2xl font-light">
            A synchronous safety filter and an LLM intent classifier, working together to route your queries instantly.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Bento Box 1: Safety Guard */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="premium-card p-8 flex flex-col justify-between overflow-hidden group min-h-[400px]"
          >
            <div className="relative z-10">
              <h3 className="text-xl md:text-2xl text-white mb-3">Synchronous Safety Guard</h3>
              <p className="text-white/60 text-sm leading-relaxed max-w-md">
                Blocks insider trading, market manipulation, guaranteed-return claims, and reckless advice in &lt;10ms. No network call, no LLM. Safety is non-negotiable.
              </p>
            </div>
            
            {/* Abstract visual */}
            <div className="absolute right-0 bottom-0 translate-x-1/4 translate-y-1/4 opacity-10 group-hover:opacity-30 transition-opacity duration-700">
              <img src="/branding/icetea-skull-badge.png" alt="Safety" className="w-[300px] h-[300px] object-contain mix-blend-screen" />
            </div>
          </motion.div>

          {/* Bento Box 2: Intent Classifier */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="premium-card p-8 flex flex-col justify-between overflow-hidden group min-h-[400px]"
          >
            <div className="relative z-10">
              <h3 className="text-xl md:text-2xl text-white mb-3">LLM Intent Classifier</h3>
              <p className="text-white/60 text-sm leading-relaxed max-w-md">
                A single LLM call extracts intent, ticker entities, target agent, and confidence — then routes to the right specialist. Handles multi-turn pronoun resolution with ease.
              </p>
            </div>

            {/* Abstract visual */}
            <div className="absolute right-0 bottom-0 translate-x-1/4 translate-y-1/4 opacity-10 group-hover:opacity-30 transition-opacity duration-700">
              <img src="/branding/icetea-pipes-logo.png" alt="Routing" className="w-[400px] h-[400px] object-contain mix-blend-screen" />
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
