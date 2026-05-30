import { useEffect, useState } from 'react'

/**
 * Animated dense-ASCII thumbnails for the onboarding capability tour.
 *
 * Each component renders a multi-line `<pre>` representing the feature
 * (chat panel, candlestick chart, newswire, agent forge, dock layout) and
 * tweaks a few characters per frame so the thumb feels alive instead of
 * being a static logo. All components share the same wall-clock tick rate
 * via the `useFrame` hook so the whole tour runs in lockstep - cheaper and
 * also visually nicer because the cursors all pulse together.
 */

// Centralised frame ticker. 250ms = 4hz, a nice "terminal" cadence.
function useFrame(hz = 4): number {
  const [f, setF] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setF((x) => (x + 1) % 1_000_000), Math.floor(1000 / hz))
    return () => clearInterval(id)
  }, [hz])
  return f
}

// ----------------------------------------------------------------------
// 1. CHAT  ·  team of agents + operator
// ----------------------------------------------------------------------
// Four faces in a row (STRAT, RISK, DEBATE, PLAN) connected to an
// OPERATOR box below. Each frame, one random face blinks (eyes change
// from `o o` to `- -`) and the cursor on the operator line toggles.

export function ChatThumb() {
  const f = useFrame()
  // pick which face blinks this frame. Stays still for 2 frames then jumps.
  const blink = Math.floor(f / 2) % 8
  const eyes = (idx: number) => (blink === idx ? '- -' : 'o o')
  const cursor = f % 2 === 0 ? '_' : ' '

  // The talking agent each frame - shows a `>` next to one of the
  // four labels so you can see "the team is discussing".
  const speaker = Math.floor(f / 4) % 4
  const arrow = (idx: number) => (speaker === idx ? '>' : ' ')

  return (
    <pre className="onb-thumb">
{`    .-----.    .-----.    .-----.    .-----.
   /::::::|\\  /::::::|\\  /::::::|\\  /::::::|\\
  |::${eyes(0)}::| ||::${eyes(1)}::| ||::${eyes(2)}::| ||::${eyes(3)}::| |
  |:: ___ ::|/ |:: ___ ::|/ |:: ___ ::|/ |:: ___ ::|/
   \\:::::::/    \\:::::::/    \\:::::::/    \\:::::::/
    ${arrow(0)}STRAT      ${arrow(1)}RISK      ${arrow(2)}DEBATE     ${arrow(3)}PLAN
       \\          \\          /          /
        \`==========+====+====+==========\`
                        |
                  .-----v-----.
                  |  OPERATOR ${cursor} |
                  \`-----------\``}
    </pre>
  )
}

// ----------------------------------------------------------------------
// 2. PORTFOLIO + RISK  ·  candlestick chart with sweeping price line
// ----------------------------------------------------------------------
// Six candles drawn with density chars (`#` body, `|` wick). A `<-` cursor
// moves across the chart each frame to simulate a live price marker. Stats
// line beneath rotates between three risk metrics.

export function ChartThumb() {
  const f = useFrame()
  const cursorCol = f % 6                         // 0..5
  const metricIdx = Math.floor(f / 6) % 3
  const metrics = [
    'NVDA +35.4% | beta 1.82 | concentration 71%',
    'AAPL +18.0% | beta 1.14 | sharpe 1.43      ',
    'VTI  +12.7% | beta 1.00 | drawdown -8.2%   ',
  ]

  // pre-baked candle bodies. Six columns, each with a (top, bottom).
  // Top is wick top (single `|`), middle is body (`#` block), bottom is
  // wick bottom. We build the chart row-by-row.
  const candles: Array<[number, number]> = [
    [2, 5], [4, 6], [3, 7], [1, 5], [5, 8], [3, 6],
  ]

  const rows: string[] = []
  for (let r = 0; r < 9; r++) {
    let line = '  '
    for (let c = 0; c < 6; c++) {
      const [top, bot] = candles[c]
      const pad = '       '
      let cell = pad
      if (r === top) cell = '   .#.  '
      else if (r > top && r < bot) cell = '   |#|  '
      else if (r === bot) cell = '   `#`  '
      // overlay the moving price cursor as a single-char marker
      if (c === cursorCol && r === Math.min(bot, top + 1)) {
        cell = '  <##]> '
      }
      line += cell
    }
    rows.push('   $ |' + line)
  }
  // axis + x-labels
  rows.push('   $ |' + '_'.repeat(48))
  rows.push('       MON   TUE   WED   THU   FRI   MON')
  rows.push('')
  rows.push('   ' + metrics[metricIdx])

  return <pre className="onb-thumb">{rows.join('\n')}</pre>
}

// ----------------------------------------------------------------------
// 3. NEWS  ·  newswire with blinking LIVE indicator + scrolling source
// ----------------------------------------------------------------------
// A masthead with a blinking `LIVE *` indicator, then 4 headline rows.
// The "source · time" line on each row stays put; the body cycles each
// few frames so it looks like new headlines are dropping in.

export function NewsThumb() {
  const f = useFrame()
  const livePulse = f % 4 < 2 ? 'LIVE *' : 'LIVE  '
  const rotate = Math.floor(f / 6) % 3

  const sets: Array<Array<[string, string]>> = [
    [
      ['NVDA hits new all-time high on AI demand   ', 'Reuters       2m ago'],
      ['FED holds rates steady at 5.25%-5.50%      ', 'Bloomberg    14m ago'],
      ['AAPL beats Q3 EPS by 8 cents               ', 'Yahoo Fin     1h ago'],
      ['OPEC+ extends 2.2M b/d output cuts         ', 'FT            2h ago'],
    ],
    [
      ['ASML books record orders amid chip rebound ', 'Reuters       1m ago'],
      ['MSFT-OpenAI extend exclusivity to 2030     ', 'The Verge     9m ago'],
      ['Treasury 10Y yields slip below 4.20%       ', 'WSJ          25m ago'],
      ['BTC reclaims $72k as ETF flows resume      ', 'CoinDesk      1h ago'],
    ],
    [
      ['TSLA delays Cybercab launch to Q3 \'26      ', 'Electrek      4m ago'],
      ['ECB signals June cut as inflation eases    ', 'FT           18m ago'],
      ['GOOGL Gemini 3 tops MMLU at 92.4%          ', 'TechCrunch   46m ago'],
      ['Oil dips on weak China import data         ', 'Reuters       3h ago'],
    ],
  ]
  const items = sets[rotate]

  return (
    <pre className="onb-thumb">
{`   .===========================================.
   |  ICETEA NEWSWIRE                  ${livePulse}  |
   |===========================================|
   |  > ${items[0][0]} |
   |      ${items[0][1]}             |
   |  > ${items[1][0]} |
   |      ${items[1][1]}             |
   |  > ${items[2][0]} |
   |      ${items[2][1]}             |
   |  > ${items[3][0]} |
   |      ${items[3][1]}             |
   '==========================================='`}
    </pre>
  )
}

// ----------------------------------------------------------------------
// 4. AGENT BUILDER  ·  forge form with cursor and animated checkboxes
// ----------------------------------------------------------------------
// A workbench-styled form with id/role/model fields. The id field has a
// blinking cursor at the typing position. The tools checklist fills in
// progressively each frame (`[ ]` -> `[.]` -> `[x]`) like the agent is
// being assembled in real time.

export function BuilderThumb() {
  const f = useFrame()
  const cursor = f % 2 === 0 ? '_' : ' '

  // 6 tools, each fills in over 12 frames sequentially.
  const tools = ['web_search   ', 'yfinance     ', 'reader       ', 'memory       ', 'code_exec    ', 'python_env   ']
  const stage = (i: number): string => {
    const start = i * 4
    const local = (f - start) % 24
    if (local < 0 || local < 4) return ' '
    if (local < 8) return '.'
    return 'x'
  }

  return (
    <pre className="onb-thumb">
{`   .=========================================.
   ||         ICETEA  ::  AGENT FORGE        ||
   '=========================================='
   |  id     [ research_v2${cursor}              ]    |
   |  role   [ ANALYST                       ]    |
   |  model  [ vllm/qwen3-30b              v ]    |
   |  temp   [ 0.20 ]   max_tokens [ 2048 ]      |
   |                                              |
   |  tools                                       |
   |    [${stage(0)}] ${tools[0]}    [${stage(3)}] ${tools[3]}     |
   |    [${stage(1)}] ${tools[1]}    [${stage(4)}] ${tools[4]}     |
   |    [${stage(2)}] ${tools[2]}    [${stage(5)}] ${tools[5]}     |
   |                                              |
   |                                  [ FORGE ]   |
   '=============================================='`}
    </pre>
  )
}

// ----------------------------------------------------------------------
// 5. DOCK + KEYBOARD  ·  4-panel grid with focus rotating
// ----------------------------------------------------------------------
// Mini dock with CHAT (left), PORT/PROF (middle stack), NEWS/READER
// (right stack). The "focused" tile each frame is highlighted with a
// dense `#` fill, the others use a dim `.` fill. Below the dock, a
// key-hint line rotates between the actual shortcuts the operator can
// use after launch.

export function DockThumb() {
  const f = useFrame()
  const focused = Math.floor(f / 3) % 5

  const hints = [
    '^1..6 focus tile      ^Shift+arrows resize ',
    '^M collapse/expand    ^Shift R reset       ',
    '^B agent builder      ^Shift O re-onboard  ',
    'F12 cycle themes      drag header to swap  ',
  ]
  const hint = hints[Math.floor(f / 4) % hints.length]

  // The geometry is fixed: 18-wide left column (CHAT), 12-wide middle
  // (PORT/PROF), 16-wide right (NEWS/READER). Inner widths are 16, 10,
  // 14 once the `|` separators are deducted. Pre-compute the fill for
  // each tile so the rows below are pure string-builders.
  const lit = '################'      // 16
  const dim = '. . . . . . . . '      // 16

  const cell = (idx: number, width: number, label?: string): string => {
    const ch = focused === idx ? lit : dim
    const body = ch.slice(0, width)
    if (!label) return body
    // centre the label inside the body, replacing the middle chars.
    const start = Math.floor((width - label.length) / 2)
    return body.slice(0, start) + label + body.slice(start + label.length)
  }

  // CHAT is two rows tall in the left column, PORT/PROF stacked in the
  // middle, NEWS/READER stacked on the right. Six rows total.
  const r1 = `   |${cell(0, 16, ' CHAT ')}|${cell(1, 10, ' PORT ')}|${cell(2, 14, ' NEWS ')}|`
  const r2 = `   |${cell(0, 16)}|${cell(1, 10)}|${cell(2, 14)}|`
  const r3 = `   |${cell(0, 16)}|${cell(1, 10)}+--------------+`
  const r4 = `   |${cell(0, 16)}+----------+${cell(4, 14, ' READER ')}|`
  const r5 = `   |${cell(0, 16)}|${cell(3, 10, ' PROF ')}|${cell(4, 14)}|`
  const r6 = `   |${cell(0, 16)}|${cell(3, 10)}|${cell(4, 14)}|`

  return (
    <pre className="onb-thumb">
{`   +----------------+----------+--------------+
${r1}
${r2}
${r3}
${r4}
${r5}
${r6}
   +----------------+----------+--------------+

   ${hint}`}
    </pre>
  )
}

// ----------------------------------------------------------------------
// Public list. The OnboardingFlow references these by index in the same
// order the capability cards declare their text.
// ----------------------------------------------------------------------

export const THUMBS = [ChatThumb, ChartThumb, NewsThumb, BuilderThumb, DockThumb]
