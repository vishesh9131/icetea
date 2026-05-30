import type { ReactNode } from 'react'

/**
 * Onboarding thumbnails built as small product screenshots.
 *
 * These deliberately reuse terminal UI language from the app instead of
 * abstract illustration: panel headers, tables, traces, news rows, and command
 * strips. Animation is handled in CSS so movement is continuous instead of a
 * stepped JavaScript timer.
 */

function Meter({ value, tone = 'primary', delay = 0 }: { value: number; tone?: 'primary' | 'cyan' | 'red' | 'green'; delay?: number }) {
  return (
    <span className="mini-meter">
      <span
        className={`mini-meter-fill ${tone}`}
        style={{
          width: `${Math.max(4, Math.min(100, value))}%`,
          animationDelay: `${delay}s`,
        }}
      />
    </span>
  )
}

function Shell({ children }: { children: ReactNode }) {
  return <div className="onb-product-thumb">{children}</div>
}

function Header({ title, right }: { title: string; right?: string }) {
  return (
    <div className="mini-head">
      <span>{title}</span>
      {right && <span className="mini-head-right">{right}</span>}
    </div>
  )
}

export function ChatThumb() {
  return (
    <Shell>
      <div className="mini-grid chat-shot">
        <section className="mini-panel chat-main drift-a">
          <Header title="CHAT" right="STREAMING" />
          <div className="mini-chat-row user">should i reduce nvda before earnings?</div>
          <div className="mini-chat-row bot">
            <span className="mini-agent">MULTIAGENT</span>
            The book has concentration risk, but recent tape is still constructive. Split the decision into sizing, tax, and thesis triggers.
          </div>
          <div className="mini-token-line">
            <span>chair synthesis</span>
            <Meter value={76} tone="cyan" />
          </div>
        </section>
        <section className="mini-panel team-stack drift-b">
          <Header title="AGENTS" right="LIVE ROUTING" />
          {['PORTFOLIO', 'MARKET', 'RISK', 'PLANNER'].map((name, i) => (
            <div key={name} className="mini-agent-row" style={{ animationDelay: `${i * 0.45}s` }}>
              <span>{name}</span>
              <Meter value={[72, 48, 84, 63][i]} tone={i === 2 ? 'red' : i === 1 ? 'cyan' : 'primary'} delay={i * 0.2} />
            </div>
          ))}
        </section>
        <section className="mini-panel trace-strip drift-c">
          <Header title="TRACE" right="SSE" />
          <div>guard ok</div>
          <div>classified investment_strategy</div>
          <div>round stream rotating specialists</div>
        </section>
      </div>
    </Shell>
  )
}

export function ChartThumb() {
  const rows = [
    ['NVDA', '42.8%', '1.31', 'HIGH'],
    ['QQQ', '24.1%', '1.08', 'MED'],
    ['AAPL', '16.4%', '0.96', 'OK'],
    ['BND', '10.2%', '0.15', 'LOW'],
  ]
  return (
    <Shell>
      <div className="mini-grid risk-shot">
        <section className="mini-panel risk-chart drift-a">
          <Header title="PORTFOLIO RISK" right="-30% SCENARIO" />
          <div className="chart-canvas">
            <div className="chart-gridline g1" />
            <div className="chart-gridline g2" />
            <div className="chart-gridline g3" />
            <div className="chart-area" />
            <div className="chart-line" />
            <div className="chart-marker" />
          </div>
          <div className="risk-stats">
            <span>book beta 1.31</span>
            <span>est hit -39.3%</span>
            <span>overlap 4 factors</span>
          </div>
        </section>
        <section className="mini-panel risk-table drift-b">
          <Header title="HOLDINGS" right="LIVE" />
          <table>
            <thead><tr><th>SYM</th><th>WT</th><th>BETA</th><th>FLAG</th></tr></thead>
            <tbody>
              {rows.map((r, i) => <tr key={r[0]} style={{ animationDelay: `${i * 0.18}s` }}><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>)}
            </tbody>
          </table>
        </section>
      </div>
    </Shell>
  )
}

export function NewsThumb() {
  const headlines = [
    ['NVDA', 'AI capex estimates revised higher', '02m'],
    ['SPX', 'Fed minutes split rate path', '14m'],
    ['AAPL', 'Services margin expands', '31m'],
  ]
  return (
    <Shell>
      <div className="mini-grid news-shot">
        <section className="mini-panel news-list-shot drift-a">
          <Header title="NEWS" right="PORTFOLIO" />
          {headlines.map((h, i) => (
            <div key={h[0]} className="mini-news-row" style={{ animationDelay: `${i * 0.65}s` }}>
              <span className="ticker">{h[0]}</span>
              <span className="headline">{h[1]}</span>
              <span className="time">{h[2]}</span>
            </div>
          ))}
        </section>
        <section className="mini-panel reader-shot drift-b">
          <Header title="READER" right="IN-APP" />
          <div className="reader-title-line">Nvidia demand lifts sector outlook</div>
          <div className="reader-line w1" style={{ animationDelay: '0s' }} />
          <div className="reader-line w2" style={{ animationDelay: '0.2s' }} />
          <div className="reader-line w3" style={{ animationDelay: '0.4s' }} />
          <div className="reader-line w4" style={{ animationDelay: '0.6s' }} />
          <div className="reader-fetch">
            <span>server fetch</span>
            <Meter value={72} tone="cyan" />
          </div>
        </section>
      </div>
    </Shell>
  )
}

export function BuilderThumb() {
  const tools = ['web_search', 'fetch_url', 'mcp_market', 'risk_tax', 'session']
  return (
    <Shell>
      <div className="mini-grid builder-shot">
        <section className="mini-panel builder-form drift-a">
          <Header title="AGENT BUILDER" right="CUSTOM" />
          <label style={{ animationDelay: '0s' }}>ID <span>macro_research_desk</span></label>
          <label style={{ animationDelay: '0.16s' }}>ROLE <span>market analyst</span></label>
          <label style={{ animationDelay: '0.32s' }}>MODEL <span>vllm/qwen3-30b</span></label>
          <label style={{ animationDelay: '0.48s' }}>PROMPT <span>cite sources, no invented facts</span></label>
        </section>
        <section className="mini-panel tool-list-shot drift-b">
          <Header title="TOOLS" right={`${tools.length} SELECTED`} />
          {tools.map((t, i) => (
            <div key={t} className="mini-tool" style={{ animationDelay: `${i * 0.22}s` }}>
              <span className="box" />
              <span>{t}</span>
            </div>
          ))}
          <button className="mini-run">RUN AGENT</button>
        </section>
      </div>
    </Shell>
  )
}

export function DockThumb() {
  const cls = (name: string) => `dock-mini-tile ${name}`
  return (
    <Shell>
      <div className="dock-mini">
        <div className={cls('chat')} style={{ animationDelay: '0s' }}><Header title="CHAT" /><span>stream + payload</span></div>
        <div className={cls('port')} style={{ animationDelay: '0.22s' }}><Header title="PORT" /><span>editable book</span></div>
        <div className={cls('prof')} style={{ animationDelay: '0.44s' }}><Header title="PROFILE" /><span>risk / ccy</span></div>
        <div className={cls('news')} style={{ animationDelay: '0.66s' }}><Header title="NEWS" /><span>headlines</span></div>
        <div className={cls('trace')} style={{ animationDelay: '0.88s' }}><Header title="TRACE" /><span>events</span></div>
        <div className={cls('reader')} style={{ animationDelay: '1.1s' }}><Header title="READER" /><span>article body</span></div>
        <div className="dock-mini-cmd">ICE&gt; / focus command · F12 theme · Ctrl+Shift+arrows resize</div>
      </div>
    </Shell>
  )
}

export const THUMBS = [ChatThumb, ChartThumb, NewsThumb, BuilderThumb, DockThumb]
