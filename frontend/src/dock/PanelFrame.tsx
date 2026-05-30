import type { ReactNode } from 'react'
import { tileDragProps } from './Dock'
import { TILE_LABELS, type TileId } from './layout'

// PanelFrame is the consistent chrome around every tile body: the .panel-header
// at the top (with the tile label, the optional right-side bits supplied by
// the caller, and the dock controls), and the scrollable content below.
//
// The whole header is also the drag-source for swapping tiles, so we attach
// the HTML5 drag handlers here. A small focus indicator is rendered on the
// left of the label when the tile is keyboard-focused.

type PanelFrameProps = {
  tile: TileId
  label?: string                // override default TILE_LABELS[tile]
  focused: boolean
  collapsed: boolean
  hint?: ReactNode              // tiny right-aligned hint (e.g. "<F1>")
  rightExtra?: ReactNode        // extra controls before the dock buttons
  onToggleCollapse: () => void
  onFocus: () => void
  children: ReactNode
}

export function PanelFrame(p: PanelFrameProps) {
  const label = p.label ?? TILE_LABELS[p.tile]
  return (
    <section
      className={`panel ${p.focused ? 'panel-focused' : ''} ${p.collapsed ? 'panel-collapsed' : ''}`}
      onMouseDown={p.onFocus}
    >
      <header
        className="panel-header dock-header"
        {...tileDragProps(p.tile)}
        title="Drag to swap with another panel — double-click to collapse"
        onDoubleClick={p.onToggleCollapse}
      >
        <span className="dock-grip" aria-hidden>{'\u22EE\u22EE'}</span>
        <span className="ph-title">{label}</span>
        {p.hint && <span className="ph-hint">{p.hint}</span>}
        <span className="ph-spacer" />
        {p.rightExtra}
        <button
          className="dock-btn"
          title={p.collapsed ? 'Expand (Cmd+M)' : 'Collapse (Cmd+M)'}
          onClick={(e) => { e.stopPropagation(); p.onToggleCollapse() }}
        >
          {p.collapsed ? '+' : '\u2014'}
        </button>
      </header>
      {!p.collapsed && p.children}
    </section>
  )
}
