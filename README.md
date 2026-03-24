# soul-team

**Run a team of Claude AI agents across multiple machines.**

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![License MIT](https://img.shields.io/badge/License-MIT-green)
![tmux 3.2+](https://img.shields.io/badge/tmux-3.2%2B-orange)

soul-team is an open-source framework for running distributed teams of Claude AI agents using tmux. Each agent lives in its own pane, communicates with teammates via a structured message bus, and is managed by daemons that handle delivery, health monitoring, and resource enforcement — all configured from a single YAML file.

---

## Architecture

```
┌─────────────────── primary machine ──────────────────────┐
│  tmux session "soul-team"                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │CEO pane │  │agent-1  │  │agent-2  │  │agent-3  │    │
│  │(you)    │  │(Claude) │  │(Claude) │  │(Claude) │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │
│                                                           │
│  courier.py  ─── watches panes, routes messages           │
│  guardian.py ─── monitors health, restarts agents         │
│  mcp-server/ ─── MCP tools for agent coordination        │
└──────────────────────────────────────────────────────────┘
         │ SSH
┌─────────────────── worker machine ───────────────────────┐
│  ┌─────────┐  ┌─────────┐                                │
│  │agent-4  │  │agent-5  │  (Claude agents via SSH)       │
│  │(Claude) │  │(Claude) │                                │
│  └─────────┘  └─────────┘                                │
└──────────────────────────────────────────────────────────┘
```

The primary machine runs the tmux session, courier, guardian, and MCP server. Worker machines host additional agent panes over SSH. All coordination (messages, tasks, health events) flows through the ClawTeam message bus.

---

## Features

- **Distributed execution** across multiple machines via SSH — scale agents beyond a single host
- **Dynamic tmux layout** — auto-calculates columns and rows from agent count; resizes gracefully
- **ClawTeam message bus** — inbox, broadcast, discussions, and task management between agents
- **Courier daemon** — watches Claude panes, delivers messages, handles P1 interrupts, sends reminder pings
- **Guardian daemon** — monitors CPU/temperature/RAM, revives dead agents, enforces resource limits
- **MCP server** — gives each agent structured team tools: send message, read inbox, manage tasks
- **Single config file** — `cluster.yaml` defines machines, agents, models, roles, and cgroup limits
- **cgroup support** — CPU and memory limits per agent on Linux systems
- **Graceful continue mode** — `--continue` flag reconnects to an existing session without restarting agents

---

## Quick Start

### Single Machine

```bash
# 1. Clone and install
git clone https://github.com/your-org/soul-team.git
cd soul-team
bash setup.sh

# 2. Configure
cp cluster.yaml.example ~/.config/soul-team/cluster.yaml
# Edit cluster.yaml: set mode: local, define your agents
nano ~/.config/soul-team/cluster.yaml

# 3. Launch
soul-team
```

### Distributed (Primary + Worker)

```bash
# On the PRIMARY machine
git clone https://github.com/your-org/soul-team.git && cd soul-team && bash setup.sh
cp cluster.yaml.example ~/.config/soul-team/cluster.yaml
# Edit cluster.yaml: add worker section with SSH host/user/agents
nano ~/.config/soul-team/cluster.yaml

# On each WORKER machine (SSH in first)
git clone https://github.com/your-org/soul-team.git && cd soul-team && bash setup.sh

# Back on primary — launch everything
soul-team
```

The primary machine will SSH into workers, launch agent panes there, and integrate them into the shared session automatically.

---

## cluster.yaml Reference

| Field | Description | Example |
|---|---|---|
| `mode` | `local` or `distributed` | `distributed` |
| `session` | tmux session name | `soul-team` |
| `primary.host` | Primary machine hostname or IP | `primary.local` |
| `primary.agents[]` | List of agents on the primary | see below |
| `workers[]` | List of worker machine definitions | see below |
| `agent.name` | Agent identifier (used for messaging) | `researcher` |
| `agent.role` | Path to assistant.md role file | `agents/researcher.md` |
| `agent.model` | Claude model to use | `claude-opus-4-5` |
| `agent.cpu_quota` | CPU limit (Linux cgroups, %) | `50` |
| `agent.memory_limit` | RAM limit (Linux cgroups) | `2G` |
| `courier.interval` | Message poll interval in seconds | `5` |
| `guardian.restart_on_exit` | Auto-revive dead agents | `true` |
| `guardian.temp_limit_c` | Kill threshold in °C | `85` |
| `guardian.ram_limit_pct` | Kill threshold % of total RAM | `90` |

**Minimal cluster.yaml (local mode):**

```yaml
mode: local
session: soul-team

primary:
  agents:
    - name: developer
      role: agents/developer.md
      model: claude-opus-4-5
    - name: researcher
      role: agents/researcher.md
      model: claude-opus-4-5

courier:
  interval: 5

guardian:
  restart_on_exit: true
  temp_limit_c: 85
  ram_limit_pct: 90
```

---

## Agent Roles

Each agent is given a system prompt that defines its role. Templates live in `agents/`:

| File | Role description |
|---|---|
| `agents/assistant.md` | General-purpose assistant; coordinates with other agents |
| `agents/developer.md` | Software development; reads/writes code, runs tests |
| `agents/researcher.md` | Research and summarization; uses web search and documents |

You can add custom role files — point `agent.role` to any `.md` file. The file is passed to `claude` as `--system-prompt`.

Role files can include team-awareness instructions (who the other agents are, how to reach them) and MCP tool references (`send_message`, `read_inbox`, `create_task`).

---

## Commands

### `soul-team`

```
soul-team [OPTIONS]

Options:
  --config PATH       Path to cluster.yaml  [default: ~/.config/soul-team/cluster.yaml]
  --continue          Reconnect to an existing session without restarting agents
  --dry-run           Print what would be launched without executing
  --no-guardian       Skip starting the guardian daemon
  --no-courier        Skip starting the courier daemon
  --session NAME      Override the tmux session name
  -h, --help          Show this help message
```

### `soul-msg`

```
soul-msg <agent> <message>        Send a message to a named agent's inbox
soul-msg --broadcast <message>    Send to all agents
soul-msg --list                   List known agents and their last-seen time
soul-msg --tasks                  Show open tasks
```

Examples:

```bash
# Ask the researcher to summarize a paper
soul-msg researcher "Please summarize arxiv:2401.00001 and post findings to broadcast"

# Broadcast a priority interrupt to all agents
soul-msg --broadcast "STOP current work. Switch to hotfix branch immediately."

# List active agents
soul-msg --list
```

---

## Project Structure

```
soul-team/
├── setup.sh                  # Installer script
├── cluster.yaml.example      # Example configuration
├── bin/
│   ├── soul-team             # Main launcher script
│   └── soul-msg              # Message CLI
├── courier/
│   ├── courier.py            # Message delivery daemon
│   └── interrupt.py          # P1 interrupt handler
├── guardian/
│   └── guardian.py           # Health monitor and agent revival daemon
├── mcp-server/
│   ├── server.py             # MCP server entry point
│   └── tools/                # MCP tool definitions
│       ├── messaging.py
│       └── tasks.py
├── agents/
│   ├── assistant.md          # Role template: general assistant
│   ├── developer.md          # Role template: software developer
│   └── researcher.md         # Role template: researcher
└── systemd/
    ├── soul-courier.service  # systemd user unit for courier
    └── soul-guardian.service # systemd user unit for guardian
```

---

## Requirements

| Dependency | Version | Required | Notes |
|---|---|---|---|
| tmux | ≥ 3.2 | Yes | Session and pane management |
| Python | ≥ 3.11 | Yes | Courier, guardian, MCP server |
| Claude Code CLI (`claude`) | latest | Yes | Runs each agent |
| clawteam | latest | Yes | Message bus (inbox/broadcast/tasks) |
| PyYAML | any | Yes | Config parsing (`pip install PyYAML`) |
| psutil | any | Yes | Process/resource monitoring (`pip install psutil`) |
| jq | any | No | Optional panes.json manipulation |
| systemd | any | No | Optional service management |

Install Python dependencies:

```bash
pip install --user PyYAML psutil
```

---

## License

MIT — see [LICENSE](LICENSE).

Contributions welcome. Open an issue or pull request on GitHub.
