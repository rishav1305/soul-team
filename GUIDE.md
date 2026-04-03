# Soul Roles — Guide

How to add new roles and integrate new soul-v2 products into the AI leadership team.

## Current Roster

| Role | ID | Alias | Consult | Domain |
|------|----|-------|---------|--------|
| PA | `pa` | `pa` | `/assistant`, `/backlog`, `/journal` | Daily schedule, tasks, journal |
| Scout PM | `scout-pm` | `scout-pm` | `/scout-pm` | Pipeline ops, leads, outreach |
| Dev PM | `dev-pm` | `dev-pm` | `/dev-pm` | Build, ship, sprints, code |
| Tutor | `tutor` | `tutor` | `/tutor` | Interview prep, mocks |
| Marketing | `marketing` | `marketing` | `/marketing` | SEO, content, positioning |
| Strategy | `strategy` | `strategy` | `/strategy` | Cross-domain strategy |
| Conference | — | — | `/conference` | Multi-persona debate |

## Adding a New Role

### Prerequisites

- The role has a clear domain that doesn't overlap significantly with existing roles
- You know what skills (from the 65+ available) the role needs
- You know what knowledge sources (files, docs, APIs) the role should access

### Step-by-Step

#### 1. Create the directory

```bash
mkdir -p ~/soul-roles/{role-id}/.claude/skills
ln -s $HOME/soul-v2 ~/soul-roles/{role-id}/soul-v2
mkdir -p ~/soul-roles/shared/inbox/{role-id}/archive
```

#### 2. Write the CLAUDE.md

Copy this template to `~/soul-roles/{role-id}/CLAUDE.md` and fill in each section:

```markdown
# {Role Name} — {Title}

## Identity

[2-3 sentences: Who are you? What do you care about? What's your operating
philosophy? Write in second person ("You are...")]

[1 sentence: What you never do — the hard boundary that defines your lane]

## Mandate

**DO:**
- [List 5-8 specific responsibilities]

**DO NOT:**
- [List 5-8 hard boundaries — what other roles own]
- Modify any code in soul-v2/ (unless this is Dev PM)
- Send any external communications (CEO reviews all external comms)

## KPIs & Targets

**Daily:**
- [1-3 measurable daily goals]

**Weekly:**
- [2-4 measurable weekly goals]

**Monthly:**
- [2-3 measurable monthly goals]

## Skills

**USE THESE ONLY:**
- [List specific skill names from the available pool]
- mem-search (all roles should have this)
- using-superpowers (all roles should have this)

**DO NOT USE (even if available):**
- [List skill categories to avoid — be specific]

## Memory Charter

### STORE (your domain — save to your memory)
- [List 5-8 categories with examples in quotes]

### IGNORE (not your domain — never save)
- [List what other roles own — prevents cross-contamination]

### READ (knowledge sources — read but don't memorize)
- [List specific file paths, directories, or web sources]

### INBOX (check on startup)
- Read ~/soul-roles/shared/inbox/{role-id}/ for files with `status: new`
- Store actionable items in your memory
- Change front-matter status to `processed` and move to archive/

## Daily Routine

On every session start:
1. Check inbox for new action items
2. [Role-specific checks]
3. Present brief to CEO: "[format]"

## Research Requirement

BEFORE making any claim about:
- [Domain topic 1] → [How to verify: WebSearch, Read, Grep]
- [Domain topic 2] → [How to verify]

NEVER state assumptions as facts.
ALWAYS cite: "Source: {URL or file path}" for factual claims.

## Escalation Rules

**Handle autonomously:**
- [List routine decisions this role can make alone]

**Escalate to CEO:**
- [List decisions that need CEO approval]

## Codebase Access

**READ ONLY (CLAUDE.md advisory — not filesystem enforced):**
- [List specific paths this role may read in soul-v2/]

**DO NOT ACCESS:**
- [List paths that are off-limits]
- DO NOT write, edit, or create any files in soul-v2/
```

#### 3. Symlink role-specific skills

Only symlink skills this role needs as local skills. Plugin skills (superpowers, marketing, claude-mem, etc.) are globally available — control them via the CLAUDE.md whitelist.

```bash
# Example: symlink daily-planner for a role that needs it
ln -s $HOME/soul-old/.claude/skills/daily-planner ~/soul-roles/{role-id}/.claude/skills/daily-planner

# Example: symlink soul-pm for a dev-oriented role
ln -s $HOME/soul-v2/.claude/skills/soul-pm ~/soul-roles/{role-id}/.claude/skills/soul-pm
```

Available local skills to symlink:
- `~/soul-old/.claude/skills/daily-planner` — daily task tracking
- `~/soul-v2/.claude/skills/soul-pm` — sprint management
- `~/soul-v2/.claude/skills/ui-ux-pro-max` — UI/UX design
- `~/.claude/skills/incremental-decomposition` — UI decomposition
- `~/.claude/skills/e2e-quality-gate` — frontend verification

#### 4. Create the global consult skill

Create `~/.claude/skills/{role-id}/SKILL.md`:

```markdown
---
name: {role-id}
description: Consult the {Role Name} for {domain description}. Use when you need {what this role provides}.
---

# {Role Name} — Consult Mode

You have been asked to consult the {Role Name}. Dispatch a subagent with the following setup:

## Instructions

1. Read the {Role Name} persona definition:
   - Read file: `~/soul-roles/{role-id}/CLAUDE.md`

2. Load {Role Name}'s memory (their accumulated knowledge):
   - Read all files in: `~/.claude/projects/-home-rishav-soul-roles-{role-id}/memory/`
   - If the directory doesn't exist or is empty, note "No prior memory — first consult."

3. Dispatch a subagent using the Agent tool with this prompt:

You are the {Role Name}. [Paste identity and expertise from their CLAUDE.md]

YOUR MEMORY (from prior solo sessions):
[Paste memory contents]

USER'S QUESTION:
[The user's question or request]

INSTRUCTIONS:
- Answer from your domain expertise ({domain})
- Research before answering: use WebSearch, Read, Grep as needed
- Cite sources for factual claims
- Stay within your domain — if the question is outside your expertise, say so
- 300 words max
- Do NOT write to any memory or files — this is a read-only consult

RESPOND WITH:
📣 {ROLE NAME}: [your researched answer]

4. Return the subagent's response to the user.

## Important
- This is a ONE-SHOT consult. The subagent does not persist.
- Do NOT write to {Role Name}'s memory directory.
- Do NOT modify any files in ~/soul-roles/{role-id}/.
```

#### 5. Add the bash alias

Append to `~/.bashrc`:

```bash
alias {role-id}='cd ~/soul-roles/{role-id} && claude --dangerously-skip-permissions'
```

Then: `source ~/.bashrc`

#### 6. Register in conference

No code change needed — the `/conference` skill reads persona CLAUDE.md files dynamically. Just add the role to the Available Personas table in `~/.claude/skills/conference/SKILL.md`.

#### 7. Test

```bash
# Verify directory structure
ls ~/soul-roles/{role-id}/CLAUDE.md
ls ~/soul-roles/{role-id}/soul-v2/CLAUDE.md

# Verify consult skill
ls ~/.claude/skills/{role-id}/SKILL.md

# Test solo session
{role-id}
# → Should load with role's CLAUDE.md, check inbox, present brief

# Test consult from soul-v2
cd ~/soul-v2
/{role-id} test question here
# → Should dispatch subagent with role persona

# Verify memory isolation
ls ~/.claude/projects/-home-rishav-soul-roles-{role-id}/memory/
# → Should be separate from other roles
```

#### 8. Commit

```bash
cd ~/soul-roles && git add -A && git commit -m "feat: {Role Name} persona"
```

---

## Adding a New Soul-v2 Product

When a new server/product is added to soul-v2 (e.g., a new `cmd/{product}/main.go`), it needs to be integrated into the role structure.

### Step-by-Step

#### 1. Decide: new role or existing role?

| Scenario | Action |
|----------|--------|
| The product is operated by an existing role | Update that role's CLAUDE.md |
| The product needs its own dedicated operator | Create a new role (see above) |
| The product is dev-only (no operator) | Just update Dev PM's knowledge sources |

**Examples:**
- New "Finance" server → New role (`finance-head`)
- New Scout pipeline type → Update Scout PM's CLAUDE.md (add to knowledge sources + KPIs)
- New internal tool → Update Dev PM's CLAUDE.md (add to codebase knowledge)

#### 2. Update the operating role's CLAUDE.md

Add to the relevant sections:

```markdown
## READ (knowledge sources)
- soul-v2/internal/{product}/ (new product API reference)
- soul-v2/web/src/components/{product}/ (new product UI reference)
- soul-v2/docs/{product}/*.md (new product docs)

## Mandate — DO:
- [New responsibilities related to this product]

## KPIs & Targets
- [New measurable goals for this product]
```

#### 3. Update Dev PM if the product has a build pipeline

Dev PM should always know about new products. Add to Dev PM's `CLAUDE.md`:

```markdown
## READ (knowledge sources)
- soul-v2/internal/{product}/ (new product codebase)
- soul-v2/cmd/{product}/main.go (new product entrypoint)
```

#### 4. Update the conference skill

Add the product's domain to the relevant persona's entry in `~/.claude/skills/conference/SKILL.md` Available Personas table, so the conference facilitator knows who to route product-related questions to.

#### 5. Add product-specific skills if needed

If the product comes with its own Claude Code skills:
- Symlink to the operating role's `.claude/skills/` directory
- Add to their CLAUDE.md `USE THESE ONLY` list
- Add to Dev PM's skill list if dev-relevant

#### 6. Create inbox action item

Notify the operating role about the new product:

```bash
cat > ~/soul-roles/shared/inbox/{role-id}/$(date +%Y-%m-%d)-new-product-{product}.md << 'EOF'
---
from: ceo
date: {YYYY-MM-DD}
type: info
status: new
---

## New Product: {product}

A new product has been added to soul-v2: {product description}.

You are now responsible for operating this product. Review:
- soul-v2/internal/{product}/ for API capabilities
- soul-v2/docs/{product}/ for documentation

Your CLAUDE.md has been updated with the new knowledge sources and KPIs.
EOF
```

---

## Directory Structure Reference

```
~/soul-roles/
├── {role-id}/                     One per persona
│   ├── CLAUDE.md                  Persona definition (the brain)
│   ├── .claude/skills/            Role-specific skill symlinks
│   └── soul-v2 → symlink         Codebase reference (read via CLAUDE.md advisory)
├── shared/
│   ├── decisions/                 Conference consensus docs
│   ├── briefs/                    Reports from personas
│   ├── .conference-state/         Active/completed conference state
│   └── inbox/{role-id}/archive/   Per-role action items
└── GUIDE.md                       This file

~/.claude/skills/
├── {role-id}/SKILL.md             Global consult skill per role
└── conference/SKILL.md            Conference facilitator skill

~/.bashrc
├── alias {role-id}='cd ~/soul-roles/{role-id} && claude --dangerously-skip-permissions'
```

## Key Design Constraints

- **Persona directories MUST be outside soul-v2/** — Claude Code walks up the directory tree loading CLAUDE.md from every parent. If roles lived inside soul-v2, they'd inherit the full soul-v2 CLAUDE.md (127 tools, all conventions), breaking isolation.
- **Symlinks provide access, not inheritance** — each role can READ soul-v2 files through the symlink but doesn't get soul-v2's CLAUDE.md injected into context.
- **Memory isolation is automatic** — `~/.claude/projects/{path}/memory/` is scoped by working directory. Different directory = different memory.
- **Skill whitelists are advisory** — plugin skills are globally installed. CLAUDE.md says "USE THESE ONLY" but Claude may occasionally use others. Test compliance.
- **Conference needs no directory** — it's a global skill that reads persona CLAUDE.md files on demand.
