import type { UserContext } from '../types'

type Props = { ctx: UserContext }

export function ProfileSummary({ ctx }: Props) {
  return (
    <div className="panel-body" style={{ fontSize: 11.5 }}>
      <Row k="NAME"     v={ctx.name || '—'} />
      <Row k="AGE"      v={ctx.age != null ? String(ctx.age) : '—'} />
      <Row k="COUNTRY"  v={ctx.country || '—'} />
      <Row k="BASE CCY" v={ctx.base_currency || 'USD'} />
      <Row k="RISK"     v={(ctx.risk_profile || '—').toUpperCase()} />
      <Row k="POSITIONS" v={String(ctx.positions?.length ?? 0)} />
      {ctx.preferences && Object.keys(ctx.preferences).length > 0 && (
        <Row
          k="PREFS"
          v={Object.entries(ctx.preferences)
            .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
            .join('  ·  ')}
        />
      )}
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: 6, padding: '1px 0' }}>
      <span className="fg-amber" style={{ fontSize: 10.5, letterSpacing: '0.1em' }}>{k}</span>
      <span className="fg-white">{v}</span>
    </div>
  )
}
