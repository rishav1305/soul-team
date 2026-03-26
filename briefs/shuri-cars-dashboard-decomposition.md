# CARS Dashboard — Incremental Build Plan

**Author:** Shuri | **Date:** 2026-03-26
**Builder:** Happy | **QA:** Shuri
**Target:** rishavchatterjee.com/cars | **Deadline:** Mar 27-28

## Source Files (titan-pc ~/soul-bench/dashboard/)

Copy these into portfolio_app BEFORE starting:
- `cars-data.ts` → `~/portfolio_app/src/lib/cars-data.ts`
- `data/dashboard.json` → `~/portfolio_app/public/data/dashboard.json`
- `data/prompts.json` → `~/portfolio_app/public/data/prompts.json`
- `data/metadata.json` → `~/portfolio_app/public/data/metadata.json`

Full spec: `~/soul-bench/dashboard/DASHBOARD_SPEC.md`
Streamlit reference: `~/soul-bench-app/app.py`

## Stack

- Next.js (existing portfolio app, static export)
- Recharts for all charts (already available or easy to add)
- Tailwind CSS dark theme (zinc palette — match existing portfolio)
- TypeScript strict

## Commit 1: Route + Layout Shell + Data Import

**Starting state:** Portfolio site works, /cars doesn't exist
**Goal:** /cars route renders with sidebar nav + empty content area

Files to create:
- `src/app/cars/page.tsx` — Server component, imports dashboard.json
- `src/app/cars/layout.tsx` — Dark shell with sidebar nav (5 view links)
- `src/components/cars/CarsNav.tsx` — Sidebar: logo, 5 nav items, stats (52 models etc), external links
- `src/lib/cars-data.ts` — Copy from soul-bench/dashboard/

Layout: sidebar left (fixed 220px), content right, full dark (zinc-950 bg).
Nav items: Leaderboard (default), Efficiency, Format Tax, Head-to-Head, Insights.
Use client-side state for active view (no sub-routes needed — single page with view switching).

**Test:** Visit /cars → see sidebar with 5 nav items, dark theme, empty content area. Click nav items → active state changes.
**Verify:** `npm run build` passes, no tsc errors.

## Commit 2: Leaderboard Table + Filters

**Starting state:** /cars renders with nav shell
**Goal:** Default view shows sortable table of 52 models with filters

Files to create:
- `src/components/cars/Leaderboard.tsx` — Main leaderboard view
- `src/components/cars/FilterBar.tsx` — Search + provider chips + size slider
- `src/components/cars/SortableTable.tsx` — Column-sortable table

Columns: Rank, Model (with provider color dot from PROVIDER_COLORS), Strict %, Relaxed %, Format Tax (pp), Latency (s), TPS, Size (GB), CARS_Size.
Use `filterModels()` and `sortModels()` from cars-data.ts.
Provider chips: colored pills, click to toggle filter.
Search: text input, filters by model name or provider.

**Test:** See 52 models. Click "Strict %" header → sorts desc/asc. Type in search → filters. Click provider chip → toggles. All data-testid on interactive elements.
**Verify:** `npm run build` clean.

## Commit 3: Efficiency Map + Format Tax

**Starting state:** Leaderboard works with filters
**Goal:** Two new views accessible from nav

### Efficiency Map
Files: `src/components/cars/EfficiencyMap.tsx`
- Recharts ScatterChart: X=latency, Y=accuracy, bubble size=est_size_gb, color=provider
- Pareto frontier dashed line overlay using `paretoFrontier()`
- Top 15 efficiency table below chart
- Toggle: Strict vs Relaxed metric
- Tooltip on hover: model name, CARS score, TPS

### Format Tax
Files: `src/components/cars/FormatTax.tsx`
- Recharts horizontal BarChart: stacked bars (blue=strict, red=gap to relaxed)
- Sort by format_tax_pp descending
- Average callout: "Average across 52 models: {N}pp"
- Model selector dropdown → grouped bar chart showing strict vs relaxed per category

**Test:** Click Efficiency in nav → scatter appears with bubbles. Click Format Tax → bars appear. Toggle strict/relaxed on Efficiency → chart updates.
**Verify:** `npm run build` clean.

## Commit 4: Leaderboard Row Expand

**Starting state:** Leaderboard table + Efficiency + Format Tax work
**Goal:** Click any table row → expand to show per-prompt results

Files to modify: `SortableTable.tsx` or new `ModelExpander.tsx`
- On row click → expand inline
- Show 3 metric cards: Strict correct (N/30), Relaxed correct (N/30), Format Tax (N prompts affected)
- 30 prompt results as collapsible list with ✅/🟡/❌ icons
- Each prompt: task name, response preview (first 200 chars), latency, score
- Lazy-load prompts.json on first expand: `fetch('/data/prompts.json')`
- Cache in React state after first load

**Test:** Click row → expands with prompt results. Click again → collapses. First expand triggers network fetch (check devtools). Second expand uses cache.
**Verify:** `npm run build` clean. No prompts.json in build output (it's in public/, fetched at runtime).

## Commit 5: Head-to-Head Comparison

**Starting state:** 3 views working
**Goal:** Compare 2-3 models side by side with actual responses

Files: `src/components/cars/HeadToHead.tsx`, `src/components/cars/ModelPicker.tsx`, `src/components/cars/PromptComparison.tsx`
- 2-3 model picker dropdowns with search/autocomplete
- Summary comparison table (side by side stats)
- Recharts RadarChart: 10-category spider chart, one line per model
- 30 collapsible prompt items showing parallel responses
- ⚡ Disagreements expanded by default (models disagree on strict score)
- ✅ Agreements collapsed
- Response text shown (first 300 chars)
- Lazy-load prompts.json (reuse cache from Commit 4 if available)

**Test:** Select 2 models → see comparison table + radar chart + prompt list. Disagreements auto-expanded. Select 3rd model → adds column.
**Verify:** `npm run build` clean.

## Commit 6: Insights + SEO + Methodology

**Starting state:** 4 views working
**Goal:** Final view with 4 tabbed charts + polish

Files: `src/components/cars/Insights.tsx` (with 4 internal tabs)

### Tab 5a: Generation Regression
- Recharts LineChart: 6 model families from MODEL_FAMILIES
- Use `getGenerationRegression()` from cars-data.ts
- Callout annotations: GPT-5 vs GPT-3.5, etc.

### Tab 5b: Reasoning Penalty
- Grouped BarChart: With vs Without reasoning
- Use `getReasoningPenalties()` from cars-data.ts
- Exception callout for O-series

### Tab 5c: Provider Report Card
- Box plot per provider (min/max/median of relaxed accuracy)
- Use `getProviderStats()` from cars-data.ts
- Summary table below

### Tab 5d: Category Heatmap
- Grid: models × categories, RdYlGn color scale
- Slider: Top N (10-52)
- Use `getCategoryHeatmap()` from cars-data.ts

### SEO
- Add meta tags per spec (title, description, og:image)
- Generate OG image (1200x630) or use static placeholder

### Methodology
- Expandable section at bottom of every view
- CARS formula, dual scoring explanation, categories, infrastructure details
- Pull from metadata.json

**Test:** Click Insights → see 4 tabs. Each tab renders its chart. Methodology expands at bottom. Check page source for meta tags.
**Verify:** `npm run build` clean. Full static export works.

## Global Rules

- `data-testid` on EVERY interactive element (buttons, dropdowns, table headers, tabs, chips)
- Dark theme: zinc-950 bg, zinc-900 cards, zinc-100 text
- Provider colors from PROVIDER_COLORS in cars-data.ts
- All charts: dark background, light grid lines, provider-colored data points
- Responsive: works on desktop (primary), degrades gracefully on mobile
- No server-side rendering needed — all data is static/pre-computed
