// dock layout — pure data + helpers, zero React.
//
// the tree is a binary-or-nary mix of `split` and `tile` nodes. The shape is
// intentionally tiny so the whole thing serialises into localStorage in a
// few hundred bytes and so the recursive renderer in Dock.tsx stays trivial.

export const TILE_IDS = ['chat', 'portfolio', 'profile', 'trace', 'news', 'reader'] as const
export type TileId = (typeof TILE_IDS)[number]

export const TILE_LABELS: Record<TileId, string> = {
  chat:      'CHAT',
  portfolio: 'PORTFOLIO',
  profile:   'PROFILE',
  trace:     'AGENT TRACE',
  news:      'NEWS',
  reader:    'READER',
}

export type Direction = 'horizontal' | 'vertical'

export type TileNode = {
  type: 'tile'
  tile: TileId
  collapsed?: boolean
}

export type SplitNode = {
  type: 'split'
  id: string                // stable id, used as PanelGroup id
  direction: Direction
  children: LayoutNode[]
  sizes: number[]           // percentages, must sum to 100
}

export type LayoutNode = TileNode | SplitNode

// ---------------------------------------------------------------
// default layout: chat on the left, side-stack on the right
// ---------------------------------------------------------------
export function defaultLayout(): LayoutNode {
  // Three columns.
  // - left: chat
  // - centre: vertical split, news on top / reader on bottom (so clicking
  //   a headline immediately surfaces the article right below it)
  // - right: portfolio / profile / trace stack
  return {
    type: 'split',
    id: 'root',
    direction: 'horizontal',
    sizes: [42, 28, 30],
    children: [
      { type: 'tile', tile: 'chat' },
      {
        type: 'split',
        id: 'middle',
        direction: 'vertical',
        sizes: [52, 48],
        children: [
          { type: 'tile', tile: 'news' },
          { type: 'tile', tile: 'reader' },
        ],
      },
      {
        type: 'split',
        id: 'right',
        direction: 'vertical',
        sizes: [36, 26, 38],
        children: [
          { type: 'tile', tile: 'portfolio' },
          { type: 'tile', tile: 'profile' },
          { type: 'tile', tile: 'trace' },
        ],
      },
    ],
  }
}

// ---------------------------------------------------------------
// tree ops
// ---------------------------------------------------------------

export function findTile(node: LayoutNode, tile: TileId): boolean {
  if (node.type === 'tile') return node.tile === tile
  return node.children.some((c) => findTile(c, tile))
}

export function allTilesIn(node: LayoutNode): TileId[] {
  if (node.type === 'tile') return [node.tile]
  return node.children.flatMap(allTilesIn)
}

// Returns a NEW tree with `a` and `b` swapped in place. If either tile is
// not in the tree the original is returned unchanged.
export function swapTiles(node: LayoutNode, a: TileId, b: TileId): LayoutNode {
  if (a === b) return node
  if (node.type === 'tile') {
    if (node.tile === a) return { ...node, tile: b }
    if (node.tile === b) return { ...node, tile: a }
    return node
  }
  return { ...node, children: node.children.map((c) => swapTiles(c, a, b)) }
}

export function setCollapsed(
  node: LayoutNode,
  tile: TileId,
  collapsed: boolean,
): LayoutNode {
  if (node.type === 'tile') {
    if (node.tile !== tile) return node
    return { ...node, collapsed }
  }
  return { ...node, children: node.children.map((c) => setCollapsed(c, tile, collapsed)) }
}

export function toggleCollapsed(node: LayoutNode, tile: TileId): LayoutNode {
  return setCollapsed(node, tile, !isCollapsed(node, tile))
}

export function isCollapsed(node: LayoutNode, tile: TileId): boolean {
  if (node.type === 'tile') return node.tile === tile && !!node.collapsed
  return node.children.some((c) => isCollapsed(c, tile))
}

// Find the split that directly contains `tile` and return [split, indexInChildren].
export function locateTile(
  node: LayoutNode,
  tile: TileId,
  path: string[] = [],
): { splitId: string; index: number } | null {
  if (node.type === 'tile') return null
  for (let i = 0; i < node.children.length; i++) {
    const c = node.children[i]
    if (c.type === 'tile' && c.tile === tile) return { splitId: node.id, index: i }
    const sub = locateTile(c, tile, [...path, node.id])
    if (sub) return sub
  }
  return null
}

// ---------------------------------------------------------------
// validation — make sure a localStorage-loaded tree is still sane
// (eg. we added a new tile id since the saved layout was written)
// ---------------------------------------------------------------
export function isValidLayout(node: unknown): node is LayoutNode {
  if (!node || typeof node !== 'object') return false
  const n = node as any
  if (n.type === 'tile') {
    return typeof n.tile === 'string' && (TILE_IDS as readonly string[]).includes(n.tile)
  }
  if (n.type !== 'split') return false
  if (n.direction !== 'horizontal' && n.direction !== 'vertical') return false
  if (!Array.isArray(n.children) || n.children.length === 0) return false
  if (!Array.isArray(n.sizes) || n.sizes.length !== n.children.length) return false
  return n.children.every(isValidLayout)
}

export function tilesMatchDefault(node: LayoutNode): boolean {
  const have = new Set(allTilesIn(node))
  if (have.size !== TILE_IDS.length) return false
  return TILE_IDS.every((t) => have.has(t))
}
