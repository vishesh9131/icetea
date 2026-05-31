import type { UserContext } from './types'

// Demo investor profiles fetched at runtime from public/profiles.json.
// Operators can edit that file (or replace it with a real backend response)
// without a rebuild. We deliberately do not ship hardcoded fallback data
// here past a single empty placeholder - we want a missing/broken profiles
// file to be visible immediately rather than masquerading as live data.

export type Profile = {
  id: string
  label: string
  ctx: UserContext
}

type ProfilesDoc = {
  default?: string
  profiles: Profile[]
}

// Single safe placeholder used until the JSON loads (or if it 404s). The
// label intentionally calls out that we are not yet wired up.
const LOADING_PROFILE: Profile = {
  id: 'loading',
  label: 'LOADING — fetching profiles.json...',
  ctx: {
    user_id: 'usr_loading',
    country: 'US',
    base_currency: 'USD',
    risk_profile: 'moderate',
    positions: [],
  },
}

let _profiles: Profile[] = [LOADING_PROFILE]
let _defaultId: string = LOADING_PROFILE.id
let _loaded: Promise<Profile[]> | null = null

export function getProfiles(): Profile[] {
  return _profiles
}

export function defaultProfile(): Profile {
  const hit = _profiles.find((p) => p.id === _defaultId)
  return hit || _profiles[0]
}

// Lazy load + memoize. Call from a top-level effect on mount.
export function loadProfiles(): Promise<Profile[]> {
  if (_loaded) return _loaded
  _loaded = (async () => {
    try {
      const url = `${import.meta.env.BASE_URL}profiles.json`
      const r = await fetch(url, { cache: 'no-cache' })
      if (!r.ok) throw new Error(`profiles.json ${r.status}`)
      const doc = (await r.json()) as ProfilesDoc
      if (!Array.isArray(doc.profiles) || doc.profiles.length === 0) {
        throw new Error('profiles.json: no profiles array')
      }
      _profiles = doc.profiles
      _defaultId = doc.default || doc.profiles[0].id
      return _profiles
    } catch (err) {
      // leave the loading placeholder so the UI shows we couldn't reach the
      // file - silent fallback to fake data is the thing we are explicitly
      // avoiding here.
      console.warn('profiles.json load failed:', err)
      _profiles = [
        {
          id: 'missing',
          label: `MISSING — could not load ${import.meta.env.BASE_URL}profiles.json`,
          ctx: {
            user_id: 'usr_missing',
            country: 'US',
            base_currency: 'USD',
            risk_profile: 'moderate',
            positions: [],
          },
        },
      ]
      _defaultId = _profiles[0].id
      return _profiles
    }
  })()
  return _loaded
}

// Back-compat re-export for files that already imported PROFILES synchronously.
// After loadProfiles() resolves, this array reference is replaced - consumers
// should call getProfiles() to get the current snapshot.
export const PROFILES: Profile[] = _profiles
