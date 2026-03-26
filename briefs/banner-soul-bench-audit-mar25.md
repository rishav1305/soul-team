# soul-bench Repository Audit — Pre-Publish Review

**Author:** Banner | **Date:** March 25, 2026
**Per:** CEO directive (Mar 25) + Pepper review ("verify no API keys before Mar 28")
**Repo:** github.com/rishav1305/soul-bench (PUBLIC, MIT)

---

## Key Finding: GitHub Repo is EMPTY

The GitHub repo `rishav1305/soul-bench` exists but has **zero commits**. The actual content (19 commits) lives in `~/soul-old/soul-bench/` with origin at Gitea (`ssh://git@git.titan.local:222/admin/soul.git`).

**Action needed:** Push content from `soul-old/soul-bench` to GitHub. Need to either:
- (a) Add GitHub as a remote and push the soul-bench subtree, OR
- (b) Copy files into a fresh clone and push (cleaner — avoids leaking monorepo git history that references other soul components)

---

## Secrets Audit: CLEAN

| Check | Result | Details |
|-------|--------|---------|
| API keys / tokens | **CLEAN** | All "token" matches are `tokens_per_second` benchmark metrics |
| .env / credentials | **CLEAN** | No .env files, no credentials files |
| Private keys (.pem, .key) | **CLEAN** | None found |
| Bearer / sk- / ghp_ | **CLEAN** | Only a phishing example in classification prompt (expected) |
| Internal IPs | **1 hit** | `192.168.0.113` in CARS baseline report SSH config example |
| Personal data | **LOW** | Username `rishav` in SSH config example (same report) |

---

## Content Inventory (26 files)

```
soul-bench/
├── README.md                          # Project overview + results
├── SPEC.md                            # Benchmark specification
├── notebooks/
│   └── cars_benchmark.ipynb           # CARS analysis notebook
├── prompts/                           # 10 categories + smoke test
│   ├── 01-system-health.json
│   ├── 02-code-generation.json
│   ├── 03-email-drafting.json
│   ├── 04-contact-research.json
│   ├── 05-knowledge-qa.json
│   ├── 06-task-planning.json
│   ├── 07-classification.json
│   ├── 08-campaign-planning.json
│   ├── 09-reply-classification.json
│   ├── 10-infra-management.json
│   └── smoke-test.json
├── results/                           # 2 model results + reports
│   ├── 2026-02-22-Phi-3.5-mini-instruct-Q4_K_M.json
│   ├── 2026-02-22-qwen2.5-3b-instruct-q4_k_m.json
│   ├── 2026-02-22-cars-baseline-report.md
│   ├── 2026-02-23-soul-bench-full-suite-report.md
│   ├── 2026-02-24-gpu-Phi-3.5-mini-instruct-Q4_K_M.json
│   ├── 2026-02-24-gpu-qwen2.5-3b-instruct-q4_k_m.json
│   └── BASELINE.md
├── scripts/
│   ├── benchmark.py                   # Main benchmark runner
│   ├── scoring.py                     # 7 scoring methods
│   ├── colab_setup.py                 # Google Colab GPU setup
│   └── setup-titan.sh                 # Local setup script
└── tests/
    ├── __init__.py
    ├── test_benchmark.py
    └── test_scoring.py
```

---

## Pre-Publish Checklist

| Item | Status | Action |
|------|--------|--------|
| No API keys | ✅ CLEAN | — |
| No credentials | ✅ CLEAN | — |
| No .env files | ✅ CLEAN | — |
| No private keys | ✅ CLEAN | — |
| Internal IP scrub | ⚠️ 1 hit | Remove `192.168.0.113` from CARS baseline report line 153 |
| .gitignore | ❌ MISSING | Create with: `*.pyc`, `__pycache__/`, `.env`, `*.db`, `venv/`, `.ipynb_checkpoints/` |
| License file | ❌ MISSING | Add MIT LICENSE file (repo is designated MIT) |
| GitHub push | ❌ NOT DONE | Content exists in soul-old/soul-bench, not on GitHub |

---

## Recommendation

**Safe to publish after 3 minor fixes** (~15 min total):
1. Scrub the SSH config example from `results/2026-02-22-cars-baseline-report.md` line 148-157
2. Add `.gitignore`
3. Add `LICENSE` (MIT)

Then push to GitHub via fresh clone (don't push monorepo history).

---

*Audit by Banner | March 25, 2026 | Pre-Mar 28 verification*
