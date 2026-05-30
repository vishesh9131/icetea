import asciiTitle from './icetea-title.txt?raw'

// Big, off-centred, intentionally clipped render of the same ascii cube
// we use on the splash. Sits behind the onboarding cards as a textured
// backdrop - the operator never sees the whole cube, just a slice of it
// bleeding in from one edge. The CSS scales it 4-5x larger than the
// splash version + offsets it negatively so a slab of the cube is cut
// off by the viewport on purpose ("artistic crop").

type Crop = 'right' | 'left' | 'top' | 'bottom-right'

export function AsciiBackdrop({ crop = 'right' }: { crop?: Crop }) {
  // belt-and-braces fallback - same logic as the splash so a stale raw
  // import never leaves the backdrop empty
  const art = (asciiTitle && asciiTitle.trim().length > 0)
    ? asciiTitle
    : ''
  if (!art) return null
  return (
    <div className={`onb-ascii-bg onb-ascii-bg--${crop}`} aria-hidden="true">
      <pre className="onb-ascii-bg-art">{art}</pre>
    </div>
  )
}
