import { useCallback, useEffect, useState } from 'react'

// Themes are wired purely through `[data-theme="..."]` on the <html>
// element; the CSS variables live in styles/terminal.css. The selected
// theme persists in localStorage so a reload doesnt yank the operator
// back to the default.

export const THEMES = ['amber', 'teal', 'crt', 'ice', 'paper'] as const
export type ThemeId = (typeof THEMES)[number]

export const THEME_LABELS: Record<ThemeId, string> = {
  amber: 'BLOOMBERG AMBER',
  teal:  'ICETEA TEAL',
  crt:   'CRT GREEN',
  ice:   'ICE BLUE',
  paper: 'PAPERWHITE',
}

const STORAGE_KEY = 'icetea.theme'
const DEFAULT_THEME: ThemeId = 'amber'

function isTheme(x: string | null): x is ThemeId {
  return !!x && (THEMES as readonly string[]).includes(x)
}

function readInitial(): ThemeId {
  if (typeof window === 'undefined') return DEFAULT_THEME
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return isTheme(stored) ? stored : DEFAULT_THEME
}

export function useTheme(): [ThemeId, (t: ThemeId) => void, () => void] {
  const [theme, setThemeState] = useState<ThemeId>(readInitial)

  useEffect(() => {
    if (typeof document === 'undefined') return
    document.documentElement.setAttribute('data-theme', theme)
    try {
      window.localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // localStorage might be blocked (private mode); no big deal
    }
  }, [theme])

  const setTheme = useCallback((t: ThemeId) => {
    if (!isTheme(t)) return
    setThemeState(t)
  }, [])

  const cycleTheme = useCallback(() => {
    setThemeState((prev) => {
      const idx = THEMES.indexOf(prev)
      return THEMES[(idx + 1) % THEMES.length]
    })
  }, [])

  return [theme, setTheme, cycleTheme]
}
