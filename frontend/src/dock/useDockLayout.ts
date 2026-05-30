import { useCallback, useEffect, useState } from 'react'
import {
  defaultLayout,
  isValidLayout,
  isCollapsed,
  setCollapsed as setCollapsedT,
  swapTiles as swapTilesT,
  tilesMatchDefault,
  toggleCollapsed as toggleCollapsedT,
  type LayoutNode,
  type TileId,
} from './layout'

// v3 = added the READER tile (middle column splits news/reader vertically).
// We bump the key so any old saved layout is dropped back to the new default
// tree which actually contains the new tile.
const STORAGE_KEY = 'icetea.layout.v3'

function readInitial(): LayoutNode {
  if (typeof window === 'undefined') return defaultLayout()
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultLayout()
    const parsed = JSON.parse(raw)
    if (!isValidLayout(parsed)) return defaultLayout()
    if (!tilesMatchDefault(parsed)) return defaultLayout()
    return parsed
  } catch {
    return defaultLayout()
  }
}

export function useDockLayout() {
  const [layout, setLayout] = useState<LayoutNode>(readInitial)

  // Persist on every change. The tree is tiny so we just stringify each time
  // rather than wire up a debounce.
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(layout))
    } catch {
      // localStorage may be blocked; not fatal
    }
  }, [layout])

  const reset = useCallback(() => setLayout(defaultLayout()), [])

  const swap = useCallback((a: TileId, b: TileId) => {
    setLayout((prev) => swapTilesT(prev, a, b))
  }, [])

  const setCollapsed = useCallback((tile: TileId, collapsed: boolean) => {
    setLayout((prev) => setCollapsedT(prev, tile, collapsed))
  }, [])

  const toggleCollapsed = useCallback((tile: TileId) => {
    setLayout((prev) => toggleCollapsedT(prev, tile))
  }, [])

  const tileIsCollapsed = useCallback(
    (tile: TileId) => isCollapsed(layout, tile),
    [layout],
  )

  // Updating sizes after a user drag of a splitter.
  const setSplitSizes = useCallback((splitId: string, sizes: number[]) => {
    setLayout((prev) => updateSplitSizes(prev, splitId, sizes))
  }, [])

  return {
    layout,
    setLayout,
    reset,
    swap,
    setCollapsed,
    toggleCollapsed,
    tileIsCollapsed,
    setSplitSizes,
  }
}

function updateSplitSizes(
  node: LayoutNode,
  splitId: string,
  sizes: number[],
): LayoutNode {
  if (node.type === 'tile') return node
  if (node.id === splitId) {
    // Only accept if length matches; otherwise the saved layout is stale and
    // we ignore the resize callback rather than crash.
    if (sizes.length !== node.sizes.length) return node
    return { ...node, sizes }
  }
  return { ...node, children: node.children.map((c) => updateSplitSizes(c, splitId, sizes)) }
}
