import { useEffect, useRef, type ReactNode } from 'react'
import {
  Panel,
  PanelGroup,
  PanelResizeHandle,
  type ImperativePanelHandle,
} from 'react-resizable-panels'
import type { LayoutNode, SplitNode, TileId } from './layout'

// Imperative refs per tile, exposed to App.tsx so keyboard shortcuts can
// resize / collapse / expand a tile without going through layout state.
export type TileHandles = Partial<Record<TileId, ImperativePanelHandle>>

type DockProps = {
  layout: LayoutNode
  renderers: Record<TileId, ReactNode>
  onSplitResize: (splitId: string, sizes: number[]) => void
  onTileSwap: (a: TileId, b: TileId) => void
  focused: TileId | null
  collapsed: Set<TileId>
  registerHandle: (tile: TileId, h: ImperativePanelHandle | null) => void
}

export function Dock(props: DockProps) {
  // The root must be a split. If a future layout has a single tile at root
  // we wrap it in a virtual single-child group so the renderer stays uniform.
  const root: SplitNode = props.layout.type === 'split'
    ? props.layout
    : {
        type: 'split',
        id: 'root',
        direction: 'horizontal',
        sizes: [100],
        children: [props.layout],
      }

  return (
    <div className="dock">
      {renderSplit(root, props)}
    </div>
  )
}

function renderSplit(split: SplitNode, ctx: DockProps): ReactNode {
  return (
    <PanelGroup
      direction={split.direction}
      onLayout={(sizes) => ctx.onSplitResize(split.id, sizes)}
      id={split.id}
      className="dock-group"
    >
      {split.children.flatMap((child, idx) => {
        const nodes: ReactNode[] = []
        if (idx > 0) {
          nodes.push(
            <PanelResizeHandle
              key={`h-${split.id}-${idx}`}
              className={`dock-handle ${split.direction === 'horizontal' ? 'h' : 'v'}`}
              hitAreaMargins={{ coarse: 6, fine: 4 }}
            >
              <span className="dock-handle-grip" />
            </PanelResizeHandle>,
          )
        }
        const key = childKey(child, split.id, idx)
        const defaultSize = split.sizes[idx] ?? Math.floor(100 / split.children.length)
        if (child.type === 'tile') {
          nodes.push(
            <TilePanel
              key={key}
              panelId={`${split.id}-${idx}`}
              defaultSize={defaultSize}
              order={idx}
              tile={child.tile}
              content={ctx.renderers[child.tile]}
              focused={ctx.focused === child.tile}
              collapsed={ctx.collapsed.has(child.tile)}
              registerHandle={ctx.registerHandle}
              onTileSwap={ctx.onTileSwap}
            />,
          )
        } else {
          nodes.push(
            <Panel
              key={key}
              id={`${split.id}-${idx}`}
              defaultSize={defaultSize}
              minSize={6}
              order={idx}
              className="dock-subgroup"
            >
              {renderSplit(child, ctx)}
            </Panel>,
          )
        }
        return nodes
      })}
    </PanelGroup>
  )
}

function childKey(child: LayoutNode, parentId: string, idx: number): string {
  if (child.type === 'tile') return `tile-${child.tile}`
  return `split-${parentId}-${idx}-${(child as SplitNode).id}`
}

// ---------------------------------------------------------------
// TilePanel — a real <Panel> + the drag/drop swap surface
// ---------------------------------------------------------------

type TilePanelProps = {
  panelId: string
  defaultSize: number
  order: number
  tile: TileId
  content: ReactNode
  focused: boolean
  collapsed: boolean
  registerHandle: (tile: TileId, h: ImperativePanelHandle | null) => void
  onTileSwap: (a: TileId, b: TileId) => void
}

function TilePanel(p: TilePanelProps) {
  const ref = useRef<ImperativePanelHandle | null>(null)

  // Register with parent so keyboard handlers in App can do resize/collapse.
  useEffect(() => {
    p.registerHandle(p.tile, ref.current)
    return () => p.registerHandle(p.tile, null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.tile])

  // Honour external collapse state via the imperative API.
  useEffect(() => {
    const h = ref.current
    if (!h) return
    const c = h.isCollapsed()
    if (p.collapsed && !c) h.collapse()
    else if (!p.collapsed && c) h.expand()
  }, [p.collapsed])

  return (
    <Panel
      id={p.panelId}
      ref={ref}
      order={p.order}
      defaultSize={p.defaultSize}
      minSize={0}
      collapsible
      collapsedSize={2.4}
      className={`dock-tile ${p.focused ? 'focused' : ''} ${p.collapsed ? 'collapsed' : ''}`}
    >
      <DropZone tile={p.tile} onSwap={p.onTileSwap}>
        {p.content}
      </DropZone>
    </Panel>
  )
}

function DropZone({
  tile, onSwap, children,
}: { tile: TileId; onSwap: (a: TileId, b: TileId) => void; children: ReactNode }) {
  return (
    <div
      className="dock-tile-inner"
      data-tile={tile}
      onDragOver={(e) => {
        const ok = e.dataTransfer.types.includes('application/x-icetea-tile')
        if (ok) {
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
          ;(e.currentTarget as HTMLElement).classList.add('drag-target')
        }
      }}
      onDragLeave={(e) => {
        ;(e.currentTarget as HTMLElement).classList.remove('drag-target')
      }}
      onDrop={(e) => {
        ;(e.currentTarget as HTMLElement).classList.remove('drag-target')
        const src = e.dataTransfer.getData('application/x-icetea-tile') as TileId
        if (src && src !== tile) {
          e.preventDefault()
          onSwap(src, tile)
        }
      }}
    >
      {children}
    </div>
  )
}

// drag handlers a panel header can spread onto its draggable surface
export function tileDragProps(tile: TileId) {
  return {
    draggable: true,
    onDragStart: (e: React.DragEvent) => {
      e.dataTransfer.setData('application/x-icetea-tile', tile)
      e.dataTransfer.effectAllowed = 'move'
    },
  }
}

export function collapsedSet(layout: LayoutNode): Set<TileId> {
  const out = new Set<TileId>()
  const walk = (n: LayoutNode) => {
    if (n.type === 'tile') {
      if (n.collapsed) out.add(n.tile)
      return
    }
    n.children.forEach(walk)
  }
  walk(layout)
  return out
}

