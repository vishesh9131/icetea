// Quick-pick prompt templates surfaced through the right-side menu
// in the command bar. Categories roughly mirror the agent ids the
// classifier routes to, so an operator can browse by intent and pick
// a known-good seed query instead of guessing wording.

export type PromptTemplate = {
  id: string
  category: string
  title: string
  prompt: string
  // optional: bypass the classifier and route straight to this agent
  agent_override?: string
}

export const PROMPT_TEMPLATES: PromptTemplate[] = [
  // ---- Portfolio Health ----------------------------------------------------
  { id: 'ph-quarter', category: 'PORTFOLIO', title: 'Quarter health check',
    prompt: 'how is my portfolio doing this quarter? give me a 5-bullet summary' },
  { id: 'ph-alloc', category: 'PORTFOLIO', title: 'Allocation balance',
    prompt: 'is my sleeve allocation balanced or am i over-concentrated anywhere?' },
  { id: 'ph-rebal', category: 'PORTFOLIO', title: 'Rebalance suggestions',
    prompt: 'suggest a few rebalancing trades to bring me closer to a 60/30/10 split' },
  { id: 'ph-cash', category: 'PORTFOLIO', title: 'Cash position',
    prompt: 'am i holding too much cash given current conditions? where could it go to work?' },

  // ---- Risk ----------------------------------------------------------------
  { id: 'rk-stress', category: 'RISK', title: 'Stress test -30%',
    prompt: 'stress test my portfolio if the market drops 30% next quarter — show worst positions' },
  { id: 'rk-rates', category: 'RISK', title: 'Rates +100bps',
    prompt: 'what if the fed lifts rates 100bps over the next 12 months — how does my book respond?' },
  { id: 'rk-concentration', category: 'RISK', title: 'Concentration flags',
    prompt: 'flag any concentration risks above 25% in a single name or sector' },
  { id: 'rk-tail', category: 'RISK', title: 'Tail risk',
    prompt: 'what is my biggest tail risk right now and how would i hedge it?' },

  // ---- Market Research -----------------------------------------------------
  { id: 'mr-nvda', category: 'MARKET RESEARCH', title: 'NVDA this week',
    prompt: 'how is nvda doing this week? earnings, news, analyst takes' },
  { id: 'mr-fed', category: 'MARKET RESEARCH', title: 'Fed watch',
    prompt: 'what is the fed up to this week? rate path, balance sheet, dot plot' },
  { id: 'mr-sector', category: 'MARKET RESEARCH', title: 'Sector rotation',
    prompt: 'which sectors are leading and lagging this month? what is the rotation thesis?' },
  { id: 'mr-macro', category: 'MARKET RESEARCH', title: 'Macro snapshot',
    prompt: 'give me a macro snapshot — cpi, jobs, gdp, dollar, oil — and what it means for stocks' },

  // ---- Strategy ------------------------------------------------------------
  { id: 'st-trim', category: 'STRATEGY', title: 'Trim winner',
    prompt: 'should i sell half of nvda? walk me through the trim vs hold case' },
  { id: 'st-add', category: 'STRATEGY', title: 'Add to position',
    prompt: 'i have dry powder — which existing position deserves a top-up here?' },
  { id: 'st-new', category: 'STRATEGY', title: 'New idea screen',
    prompt: 'give me 3 new ideas i do not currently own that fit my risk profile' },
  { id: 'st-tax', category: 'STRATEGY', title: 'Tax-loss harvest',
    prompt: 'any tax-loss harvesting opportunities in my book before year-end?' },

  // ---- Debate --------------------------------------------------------------
  { id: 'db-msft', category: 'DEBATE', title: 'MSFT 3yr bull/bear',
    prompt: 'give me the bull case AND bear case on microsoft for the next 3 years' },
  { id: 'db-ai', category: 'DEBATE', title: 'AI capex bubble?',
    prompt: 'is the AI capex spend a bubble or a structural shift? steel-man both sides' },
  { id: 'db-china', category: 'DEBATE', title: 'China exposure',
    prompt: 'bull case AND bear case for adding china exposure to my portfolio right now' },

  // ---- Planning ------------------------------------------------------------
  { id: 'pl-ret', category: 'PLANNING', title: 'Retirement at 60',
    prompt: 'how do i plan retirement at 60 if i save 2000 a month — show me the math' },
  { id: 'pl-house', category: 'PLANNING', title: 'House down-payment',
    prompt: 'i want a 100k down-payment in 4 years — what is the safest path that still beats inflation?' },
  { id: 'pl-college', category: 'PLANNING', title: 'College fund',
    prompt: 'design a college fund plan for a kid born this year — 18-year horizon' },

  // ---- News / Web ----------------------------------------------------------
  { id: 'nw-breaking', category: 'NEWS', title: 'Breaking news scan',
    prompt: 'scan breaking news today that touches anything in my portfolio' },
  { id: 'nw-earnings', category: 'NEWS', title: 'Earnings this week',
    prompt: 'which of my holdings report earnings this week and what should i watch for?' },
  { id: 'nw-web', category: 'NEWS', title: 'Web research (web_research)',
    prompt: 'pull the latest credible web sources on the semiconductor cycle',
    agent_override: 'web_research' },
]

export const CATEGORIES = Array.from(
  new Set(PROMPT_TEMPLATES.map((t) => t.category)),
)
