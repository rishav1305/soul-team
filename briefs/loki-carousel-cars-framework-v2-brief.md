# Carousel Brief: "The CARS Framework" (v2 — Updated with 52-Model Benchmark Data)

**Purpose:** Production-ready slide content for Puppeteer HTML-to-PDF carousel generation.
**Platform:** LinkedIn carousel (PDF upload)
**Dimensions:** 1080 x 1350 px (4:5 portrait)
**Design:** Dark charcoal background, gold accent (#e8a849), Inter font (same as "Why 9 Agents" carousel)
**Calendar date:** Mar 28 Fri
**Supersedes:** loki-linkedin-carousel-slides-v1.md (which used hypothetical data)
**Key upgrade:** All examples now use REAL data from Banner's 52-model benchmark run

---

## Design Specs

Same as Why-9-Agents carousel brief:
- Background: Dark charcoal gradient (#1a1a2e → #16213e)
- Primary text: White (#f0f0f0)
- Accent/highlights: Gold (#e8a849)
- Secondary: Light gray (#a0a0b0)
- Font: Inter (Bold/700 headings, Regular/400 body, Medium/500 accent)
- Heading: 48-56px, Body: 28-32px, Footer: 20-24px
- Padding: 80px horizontal, 100px vertical
- One insight per slide

---

## SLIDE 1 — TITLE

**[Gold text, large]**
The CARS Framework

**[White text, medium]**
How I Actually Evaluate LLMs for Enterprise Production

**[Small gold text]**
52 models. 7 providers. 30 tasks. Real data.

**[Footer]**
Rishav Chatterjee | Senior AI Architect

---

## SLIDE 2 — THE PROBLEM

**[Gold heading]**
Benchmarks Measure the Wrong Thing

**[White text]**
MMLU, HumanEval, HellaSwag answer:
"What can this model DO?"

They DON'T answer:
"What can this model do ON MY BUDGET?"

**[Gold callout box]**
Frontier models now score 88%+ on MMLU.
The benchmark can't differentiate them anymore.

**[Footer]**
You need a metric that includes cost, latency, and format compliance.

---

## SLIDE 3 — THE FORMULA

**[Gold heading, very large]**
CARS

**[White subhead]**
Cost-Adjusted Relative Score

**[Formula, centered, large gold text]**
Accuracy / (Resource Cost x Latency)

**[White text below]**
One number that captures what benchmarks ignore:
how efficient a model is in the real world.

---

## SLIDE 4 — THE FORMAT TAX (NEW — original concept)

**[Gold heading]**
The Format Tax

**[White text]**
I measure two scores:
**Strict** = exact format match
**Relaxed** = right answer, any format

The gap reveals a hidden cost:

**[Gold stats, large]**
o3: 0pp tax (perfect compliance)
Claude Opus 4.5: 27pp tax (knows answer, wraps in markdown)

**[Gold callout]**
Average across 52 models: 14 percentage points lost to formatting.

Most benchmarks don't even measure this.

---

## SLIDE 5 — THE REGRESSION PROBLEM (REAL DATA)

**[Gold heading]**
Newer Models Are Getting Worse

**[Data pairs, gold number + white text]**

GPT-5: 56.7% → GPT-3.5 Turbo: 75.7%
**19pp regression**

Gemini 2.5 Pro: 33.9% → Gemini 2.0 Flash: 66.3%
**32pp regression**

Claude 3.7 Sonnet: 33.9% → Claude 3.5 Sonnet: 71.2%
**37pp regression**

**[Footer, gold]**
At structured output tasks. Not because they're dumber — because they think too much.

---

## SLIDE 6 — THE EFFICIENCY SURPRISE (REAL DATA)

**[Gold heading]**
The "Worst" Model Wins

**[Two column comparison]**

**[Left — dimmed]** GPT-4o
High accuracy. High cost. High latency.
Industry default.

**[Right — gold highlighted]** Amazon Nova Micro
3B parameters. 1.42s latency. 79% accuracy.
**3.5x more efficient** than the next best model.

**[Footer]**
A 20B open-source model on AWS Bedrock also beat GPT-4o on accuracy at a fraction of the price.

---

## SLIDE 7 — FIVE PRODUCTION RULES (REAL DATA)

**[Gold heading]**
5 Rules From 52 Models

**[Numbered list, gold numbers]**

1. **Pin your model versions.** Upgrades can break pipelines.

2. **Turn off reasoning for structured tasks.** Gemini scores 2x worse with reasoning on.

3. **Test strict AND relaxed.** 65% strict / 92% relaxed = needs a parser, not a new model.

4. **Small models dominate efficiency.** Nova Micro at 3B outperforms 100x-larger models per dollar.

5. **Don't trust the marketing.** Test against YOUR tasks with YOUR scoring.

---

## SLIDE 8 — THE BENCHMARK

**[Gold heading]**
52 Models, 7 Providers, 30 Tasks

**[Visual: grid showing provider logos/names]**
OpenAI | Anthropic | Google | AWS Bedrock | Groq | Mistral | Fireworks

**[Stats row]**
10 evaluation categories
Strict + Relaxed scoring
Cost + Latency + Size factored

**[Footer]**
The most comprehensive public LLM efficiency benchmark.

---

## SLIDE 9 — SOUL BENCH

**[Gold heading]**
I Built a Tool for This

**[Terminal-style code block]**
Soul Bench automates the evaluation pipeline:

- 30 benchmark prompts
- 10 evaluation categories
- 7 scoring methods
- CARS metrics computed automatically
- 52 models benchmarked and scored

**[Footer]**
Methodology article coming soon. Follow for the full deep-dive with all 8 charts.

---

## SLIDE 10 — CTA

**[Large gold text, centered]**
Stop Picking Models by Vibes.

**[White text]**
The teams that win in 2026 treat LLM selection
like engineering, not shopping.

**[Gold divider]**

**[CTA]** Follow for the full 52-model benchmark results.

**[Footer]**
Rishav Chatterjee | Senior AI Architect
rishavchatterjee.com

---

## NOTES FOR PRODUCTION

- Slides 4-6 are the original/unique content (Format Tax, Regression, Efficiency Surprise) — most saveable, most polish needed
- Chart 4 (Format Tax heatmap) from Banner at 300 DPI could replace text on Slide 4 if available
- Chart 7 (Generation Regression) from Banner at 300 DPI could supplement Slide 5 if available
- All numbers are from Banner's verified 52-model benchmark run
- "Format Tax" is an ORIGINAL concept — first time anyone has named this gap publicly. This is the most saveable slide.
- Companion post text in loki-linkedin-carousel-slides-v1.md (update to reference 52 models)
