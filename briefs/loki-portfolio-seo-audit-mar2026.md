---
author: loki
date: 2026-03-21
type: seo-audit
status: complete
---

# Portfolio SEO Audit — March 21, 2026

## Executive Summary

**SEO Health: RED — Stale Index, Wrong Positioning**

Google has indexed rishavchatterjee.com but shows the OLD positioning. The current live site may have updated copy, but Google hasn't re-crawled. Only 1 page is indexed.

## Google Index State

```
site:rishavchatterjee.com
```

**Result:** 1 page indexed.

| Field | What Google Shows | What It Should Show |
|-------|-------------------|---------------------|
| **Title** | "Rishav Chatterjee \| Technology Leader & Freelance Data Consultant" | "Rishav Chatterjee — AI Systems Engineer \| Enterprise AI Consulting" |
| **Description** | "Project Lead, Full Stack Developer, and Data Specialist providing enterprise-grade freelance solutions" | "I build production AI systems for enterprise — RAG pipelines, agentic platforms, LLM evaluation. 5,000+ users served." |
| **Positioning** | Data Engineering / Freelance Data Consultant | AI Systems Engineer / Enterprise AI |

**Verdict:** Google is actively showing the wrong person to anyone searching. Every day this stays, it's attracting the wrong audience and repelling the right one.

## Root Cause

GSC verification token is a placeholder (`"google-site-verification-code"` at layout.tsx:103). Without GSC verification:
- Cannot request re-indexing
- Cannot submit sitemap
- Cannot see search queries or impressions
- Cannot debug crawl issues
- Cannot use URL inspection tool

**Fix required:** Real GSC verification token. This is the #1 blocker.

## On-Page SEO Audit (Live Site)

### Strengths
1. **Title tag** (in code): Good — "AI Systems Engineer | Enterprise AI Consulting"
2. **Meta description** (in code): Good — mentions RAG, LLM, production AI
3. **H1/H2 structure**: Clean hierarchy
4. **Schema markup**: JSON-LD for Person + ProfessionalService present (but services are wrong — see structured data issue)
5. **Social proof**: Brand logos (IBM, TWC, Gartner), testimonial, quantified achievements
6. **CTAs**: Multiple — "Schedule a Call," "View My Work," "Get In Touch"
7. **Mobile responsive**: Tailwind CSS, responsive design
8. **Vercel hosting**: Fast CDN, good Core Web Vitals baseline

### Issues Found

| Issue | Impact | Priority | Fix |
|-------|--------|----------|-----|
| GSC not verified | CRITICAL — can't request re-index | P0 | Get real verification code |
| Structured data lists wrong services | HIGH — tells Google wrong specialization | P0 | Shuri has spec (sent today) |
| Google index shows old positioning | HIGH — wrong brand appearing in search | P0 | Depends on GSC fix |
| Project images missing alt text | MEDIUM — lost keyword opportunities | P1 | Add descriptive alt text with keywords |
| "Enterprise AI" underrepresented in body copy | LOW — keyword gap | P2 | Weave into services descriptions |
| No breadcrumb navigation | LOW — UX for deep pages | P3 | Add Next.js breadcrumbs |
| Limited internal contextual linking | LOW — reduced crawlability | P3 | Link projects to related services |
| Only 1 page indexed | INFO — thin index | — | Will improve after GSC fix + content |

## Recommendations Priority

1. **TODAY:** Shuri fixes GSC verification + structured data (brief already sent)
2. **This week:** After GSC is live, submit sitemap + request re-indexing of homepage
3. **Next week:** Add alt text to project images with target keywords
4. **Ongoing:** Publish blog content (anchor article) → new indexed pages
5. **Month 1:** Monitor Search Console for keyword impressions, adjust copy

## Competitive SEO Comparison

| Factor | Rishav | Fmind | Nikhil Paleti |
|--------|--------|-------|---------------|
| Indexed pages | 1 (stale) | Multiple (active blog) | Multiple (GitHub Pages) |
| Schema markup | Yes (but wrong services) | Yes (correct) | Yes (correct) |
| Content assets | 0 published | 8+ articles | 6+ publications |
| GSC verified | NO | Likely yes | N/A (GH Pages) |
| Title tag quality | Good (if re-indexed) | Good | Good |

**Gap:** Content and indexing are the two critical gaps. Both are being addressed this week.
