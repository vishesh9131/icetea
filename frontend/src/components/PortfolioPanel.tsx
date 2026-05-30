import { useMemo } from 'react'
import { type Profile } from '../profiles'
import type { Position, UserContext } from '../types'

type Props = {
  ctx: UserContext
  setCtx: (ctx: UserContext) => void
  profileId: string
  onProfileChange: (id: string) => void
  profiles: Profile[]
}

export function PortfolioPanel({ ctx, setCtx, profileId, onProfileChange, profiles }: Props) {
  const totalCost = useMemo(
    () => (ctx.positions || []).reduce((s, p) => s + (p.quantity || 0) * (p.avg_cost || 0), 0),
    [ctx.positions],
  )

  const updatePos = (i: number, patch: Partial<Position>) => {
    const next = ctx.positions.map((p, j) => (j === i ? { ...p, ...patch } : p))
    setCtx({ ...ctx, positions: next })
  }
  const addPos = () => {
    setCtx({
      ...ctx,
      positions: [
        ...ctx.positions,
        { ticker: 'NEW', quantity: 0, avg_cost: 0, currency: ctx.base_currency || 'USD' },
      ],
    })
  }
  const delPos = (i: number) => {
    setCtx({ ...ctx, positions: ctx.positions.filter((_, j) => j !== i) })
  }

  return (
    <>
      <div className="portfolio-controls">
        <label>
          PROFILE
          <select
            value={profileId}
            onChange={(e) => onProfileChange(e.target.value)}
          >
            {profiles.map((p: Profile) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </label>
        <label>
          UID
          <input
            value={ctx.user_id}
            onChange={(e) => setCtx({ ...ctx, user_id: e.target.value })}
            style={{ width: 110 }}
          />
        </label>
        <label>
          RISK
          <select
            value={ctx.risk_profile || 'moderate'}
            onChange={(e) => setCtx({ ...ctx, risk_profile: e.target.value })}
          >
            <option value="conservative">CONSERVATIVE</option>
            <option value="moderate">MODERATE</option>
            <option value="aggressive">AGGRESSIVE</option>
          </select>
        </label>
        <label>
          BASE
          <select
            value={ctx.base_currency || 'USD'}
            onChange={(e) => setCtx({ ...ctx, base_currency: e.target.value })}
          >
            {['USD','EUR','GBP','INR','JPY'].map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="panel-body" style={{ padding: 0 }}>
        <table className="portfolio-table">
          <thead>
            <tr>
              <th className="left">TICKER</th>
              <th>QTY</th>
              <th>AVG</th>
              <th>CCY</th>
              <th style={{ width: 30 }}> </th>
            </tr>
          </thead>
          <tbody>
            {ctx.positions.map((p, i) => (
              <tr key={i}>
                <td className="left ticker">
                  <input
                    className="left"
                    value={p.ticker}
                    onChange={(e) => updatePos(i, { ticker: e.target.value.toUpperCase() })}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="0.0001"
                    value={p.quantity}
                    onChange={(e) => updatePos(i, { quantity: parseFloat(e.target.value || '0') })}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    step="0.01"
                    value={p.avg_cost ?? 0}
                    onChange={(e) => updatePos(i, { avg_cost: parseFloat(e.target.value || '0') })}
                  />
                </td>
                <td>
                  <select
                    value={p.currency || 'USD'}
                    onChange={(e) => updatePos(i, { currency: e.target.value })}
                  >
                    {['USD','EUR','GBP','INR','JPY'].map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <button className="del" onClick={() => delPos(i)} title="REMOVE">×</button>
                </td>
              </tr>
            ))}
            {ctx.positions.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--grey)', padding: 12 }}>
                NO POSITIONS — agent will switch to BUILD mode
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="portfolio-footer">
        <span className="summary">
          COST TOTAL <span className="val">{fmtMoney(totalCost)} {ctx.base_currency || 'USD'}</span>
        </span>
        <button onClick={addPos}>+ ADD ROW</button>
      </div>
    </>
  )
}

function fmtMoney(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}
