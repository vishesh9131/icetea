import { motion } from 'framer-motion'

export default function FeaturedVideoSection() {
  return (
    <section id="terminal" className="bg-black py-16 px-4 md:px-8 relative z-20 -mt-10">
      <div className="max-w-5xl mx-auto">
        <motion.div 
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="premium-card p-2 md:p-3"
        >
          {/* Subtle OS-style header for the video wrapper */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
            <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
            <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
            <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
            <span className="ml-4 text-xs font-mono text-white/30">icetea-pipeline-stream.exe</span>
          </div>

          <div className="relative aspect-video rounded-b-xl overflow-hidden bg-[#050505]">
            <video
              src="/branding/icetea-showcase.mp4"
              muted
              autoPlay
              loop
              playsInline
              className="w-full h-full object-cover opacity-90"
            />
          </div>
        </motion.div>

        {/* Caption below video */}
        <motion.div 
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="mt-8 text-center"
        >
          <p className="text-white/40 text-sm max-w-2xl mx-auto font-light leading-relaxed">
            Every query flows through a safety guard, an LLM intent classifier, and a roster of 11 specialist agents — then streams back in real time via SSE.
          </p>
        </motion.div>
      </div>
    </section>
  )
}
