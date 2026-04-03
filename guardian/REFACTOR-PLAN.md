# Guardian Refactor Decomposition Plan

**Status:** PLANNING (do not implement until approved)
**Source:** `guardian/guardian.py` (2,099 lines, single file)
**Test suite:** `tests/test_guardian.py` (110 tests, 13 test classes)
**Author:** Shuri (Phase 3C, soul-team remediation plan)
**Date:** 2026-03-31

---

## 1. Problem Statement

`soul-guardian.py` is a single 2,099-line file handling 10+ distinct responsibilities:
config loading, agent health checks, auto-restart, idle detection/wake, tmux management,
SQLite logging, TOML parsing, token scanning, message sending, cost tracking, process
monitoring, bridge watchdog, system guard (thermal/memory/CPU), auto-compact, auto-continue,
context budget monitoring, memory enforcement, and the main daemon loop.

This makes it hard to test individual subsystems in isolation, slows down code review,
and creates merge conflict risk when multiple agents touch the file.

---

## 2. Proposed Module Structure

```
guardian/
  __init__.py          # Package marker, VERSION export
  constants.py         # All constants, regex patterns, limits, intervals
  config.py            # TOML loading, model maps, machine config, team config
  state.py             # AgentState class
  logging.py           # log(), warn(), err(), now_iso(), now_date()
  db.py                # SQLite init, _retry_on_busy, all db_* functions
  tmux.py              # capture_pane, send_keys, send_enter, pane_last_line, pane_hash, pane_is_shell_prompt
  health.py            # System health: read_temp_celsius, read_mem_free_mb, read_cpu_pct, find_*_pid, kill_pid
  restart.py           # Restart decision: restart_count_last_hour, maybe_restart_agent, build_launch_cmd
  compact.py           # Auto-compact: maybe_compact_agent, check_context_budget
  idle.py              # Idle detection/wake: is_agent_idle, idle_shutdown_agent, wake_agent, is_hot_period, has_pending_messages
  inbox_watcher.py     # InboxWatcherThread class
  memory.py            # Memory enforcement: inject_memory_reread, run_memory_audit, check_pending_memory_audits
  tokens.py            # Token parsing: parse_tokens_from_pane, _refresh_agent_jsonl_map, _scan_jsonl_*, _compute_cost, scan_tokens_for_agent
  spend.py             # Spend tracking: check_spend
  notify.py            # CEO notification: notify_ceo
  continue_.py         # Auto-continue: maybe_continue_agent (trailing underscore avoids keyword clash)
  bridge.py            # Bridge daemon watchdog: ensure_bridge_running
  guard.py             # system_guard_cycle (thermal/memory/CPU kill)
  check.py             # Dry-run check mode: run_check
  main.py              # Main loop orchestration: build_agent_states, run_daemon, handle_sigterm, main()
  __main__.py          # Entry point: from guardian.main import main; main()
```

**Total: 22 files** (including __init__.py and __main__.py)

---

## 3. Function-to-Module Mapping

### `constants.py` -- All constants, regex patterns, intervals

**Moves here:**
- `VERSION`
- `TEMP_LIMIT_C`, `CPU_WARN_PCT`, `MEM_MIN_MB`
- `MAIN_INTERVAL_S`, `TOKEN_INTERVAL_S`, `SPEND_INTERVAL_S`
- `MAX_RESTARTS_PER_HOUR`, `RESTART_STAGGER_S`, `IDLE_WAKE_STAGGER_S`
- `IDLE_TIMEOUT_S`, `IDLE_PRE_EXIT_WAIT_S`, `IDLE_CHECK_INTERVAL_S`, `IDLE_WAKE_BOOT_WAIT_S`, `IDLE_WAKE_DEDUP_S`, `IDLE_POLL_FALLBACK_S`
- `HOT_PERIOD_FILE`
- `COMPACT_COOLDOWN_S`, `COMPACT_PRE_SAVE_WAIT_S`, `MSG_COUNT_COMPACT_THRESHOLD`
- `CONTEXT_EARLY_COMPACT_PCT`, `CONTEXT_LOG_PCT`
- `SPEND_ALERT_USD`, `SPEND_CAP_USD`
- `COST_RATES`
- `CRITICAL_AGENTS`
- `SHELL_PROMPT_RE`, `BARE_PROMPT_RE`, `COMPACT_TRIGGER_RE`, `SAFE_AUTO_APPROVE_RE`, `NEVER_AUTO_APPROVE_RE`
- `TOKEN_PATTERNS`
- `ACTIVE_INDICATORS`
- `HOME`, `CLAUDE_PROJECTS_DIR`, `DB_PATH`, `LOG_PATH`, `TEAM_NAME`, `TEAMS_CONFIG`, `SOUL_TEAM_TOML`, `BRIDGE_SCRIPT`, `SOUL_MSG`, `MACHINES_JSON`
- `MEMORY_SCANNER_PATH`, `POST_RESTART_AUDIT_DELAY_S`

**Dependencies:** None (leaf module, everything else imports from here)

**Shared state:** `CRITICAL_AGENTS` set (read from env at import time; read-only after that)

### `config.py` -- TOML loading, model maps, machine config

**Moves here:**
- `load_machines_config()` (lines 185-194)
- `_load_toml_agents()` (lines 366-373)
- `load_agent_models()` (lines 376-382)
- `load_team_config()` (lines 385-391)
- `build_agent_pane_map()` (lines 394-426)

**Module-level mutable state:** `_machines_config: dict[str, dict]` (currently a module global in guardian)

**Dependencies:**
- `constants` (for `SOUL_TEAM_TOML`, `TEAMS_CONFIG`, `MACHINES_JSON`, `TEAM_NAME`)
- `logging` (for `log()` -- only `build_agent_pane_map` doesn't use it, but it's nearby)
- stdlib: `json`, `tomllib`, `subprocess`

**Shared state that must be passed:** `_machines_config` dict -- used by `build_launch_cmd` in restart.py and `_refresh_agent_jsonl_map` in tokens.py. Options:
1. Keep as module-level global in config.py; other modules import it directly
2. Return from `load_machines_config()` and pass into callers (preferred for testability)

**Recommendation:** Keep as module global in `config.py`, export via `get_machines_config()` accessor. Restart and token modules import `config.get_machines_config()`.

### `state.py` -- AgentState class

**Moves here:**
- `class AgentState` (lines 431-453)

**Dependencies:** None (uses only stdlib `time`)

**Shared state:** AgentState instances are passed around as `dict[str, AgentState]`. No change needed.

### `logging.py` -- Logging utilities

**Moves here:**
- `now_iso()` (lines 199-200)
- `now_date()` (lines 203-205)
- `log()` (lines 208-218)
- `warn()` (lines 221-222)
- `err()` (lines 225-226)

**Dependencies:**
- `constants` (for `LOG_PATH`)

**Shared state:** None (writes to file, no mutable globals)

**Note:** Name `logging.py` shadows stdlib `logging`. Consider naming it `logger.py` instead to avoid import confusion. Alternatively, since we never import stdlib logging, the shadow is benign within the package -- but `logger.py` is safer.

### `db.py` -- SQLite operations

**Moves here:**
- `_db_lock` (line 231)
- `_retry_on_busy()` decorator (lines 234-250)
- `db_connect()` (lines 253-258)
- `db_init()` (lines 261-305)
- `db_log_heal()` (lines 309-316)
- `db_log_memory_audit()` (lines 320-329)
- `db_upsert_token_usage()` (lines 333-352)
- `db_today_total_spend()` (lines 355-361)

**Dependencies:**
- `constants` (for `DB_PATH`)
- `logger` (for `now_iso`, `now_date`)

**Shared state:** `_db_lock` threading.Lock -- stays as module-level global in db.py. The `conn` object itself is created once in `main.py` and passed as argument to all functions, which is already the pattern.

### `tmux.py` -- tmux pane interaction

**Moves here:**
- `capture_pane()` (lines 458-467)
- `send_keys()` (lines 470-479)
- `send_enter()` (lines 482-490)
- `pane_last_line()` (lines 493-496)
- `pane_hash()` (lines 499-500)
- `pane_is_shell_prompt()` (lines 503-509)

**Dependencies:**
- `constants` (for `SHELL_PROMPT_RE`, `BARE_PROMPT_RE`)

**Shared state:** None (pure functions + subprocess calls)

### `health.py` -- System health monitoring

**Moves here:**
- `read_temp_celsius()` (lines 514-520)
- `read_mem_free_mb()` (lines 523-532)
- `read_cpu_pct()` (lines 535-553)
- `find_heaviest_claude_pid()` (lines 556-572)
- `find_newest_claude_pid()` (lines 575-598)
- `kill_pid()` (lines 601-605)

**Dependencies:** None (only stdlib: `os`, `re`, `subprocess`, `signal`, `time`, `pathlib`)

**Shared state:** None (pure functions)

### `restart.py` -- Restart decision logic and launch command building

**Moves here:**
- `build_launch_cmd()` (lines 626-679)
- `restart_count_last_hour()` (lines 684-687)
- `_last_restart_ts` global (line 691)
- `maybe_restart_agent()` (lines 694-775)

**Dependencies:**
- `constants` (for `MAX_RESTARTS_PER_HOUR`, `RESTART_STAGGER_S`, `HOME`, `TEAM_NAME`)
- `config` (for `get_machines_config()`, `_load_toml_agents()` -- only for model_map in build_launch_cmd)
- `tmux` (for `capture_pane`, `send_keys`, `send_enter`, `pane_last_line`, `pane_is_shell_prompt`)
- `db` (for `db_log_heal`)
- `logger` (for `log`, `warn`, `err`)
- `notify` (for `notify_ceo`)
- `state` (for `AgentState`)

**Shared state:**
- `_last_restart_ts: float` -- module-level global, written by both `maybe_restart_agent` and `wake_agent`. **Solution:** Export as `get_last_restart_ts()` / `set_last_restart_ts()` from `restart.py`. `idle.py::wake_agent` imports these.
- `_pending_memory_audits: dict` -- currently updated by restart, compact, idle, and memory modules. **Solution:** Move to `memory.py` and export `schedule_memory_audit()` function. Other modules call `memory.schedule_memory_audit(agent, delay)`.

### `compact.py` -- Auto-compact and context budget monitor

**Moves here:**
- `maybe_compact_agent()` (lines 895-948)
- `check_context_budget()` (lines 956-1035)
- `_context_alerts_sent: dict` (line 953)

**Dependencies:**
- `constants` (for `COMPACT_TRIGGER_RE`, `MSG_COUNT_COMPACT_THRESHOLD`, `COMPACT_PRE_SAVE_WAIT_S`, `CONTEXT_EARLY_COMPACT_PCT`, `CONTEXT_LOG_PCT`, `TOKEN_PATTERNS`, `POST_RESTART_AUDIT_DELAY_S`)
- `tmux` (for `capture_pane`, `send_keys`, `send_enter`)
- `db` (for `db_log_heal`)
- `logger` (for `log`)
- `notify` (for `notify_ceo`)
- `memory` (for `schedule_memory_audit`)
- `state` (for `AgentState`)

**Shared state:** `_context_alerts_sent` stays as module-level dict in compact.py.

### `idle.py` -- Idle detection, shutdown, and wake

**Moves here:**
- `ACTIVE_INDICATORS` list -- actually move to `constants.py`, reference from here
- `_last_wake_ts: dict` (line 1048)
- `_INBOX_DIR` and `_COURIER_QUEUE_DIR` paths (lines 1051-1052) -- move to `constants.py`
- `is_hot_period()` (lines 1055-1068)
- `has_pending_messages()` (lines 1071-1090)
- `is_agent_idle()` (lines 1093-1118)
- `idle_shutdown_agent()` (lines 1121-1175)
- `wake_agent()` (lines 1178-1250)

**Dependencies:**
- `constants` (for `HOT_PERIOD_FILE`, `IDLE_TIMEOUT_S`, `IDLE_PRE_EXIT_WAIT_S`, `IDLE_WAKE_DEDUP_S`, `IDLE_WAKE_STAGGER_S`, `IDLE_WAKE_BOOT_WAIT_S`, `ACTIVE_INDICATORS`, `CRITICAL_AGENTS`, `POST_RESTART_AUDIT_DELAY_S`, `_INBOX_DIR`, `_COURIER_QUEUE_DIR`)
- `tmux` (for `capture_pane`, `send_keys`, `send_enter`, `pane_last_line`, `pane_hash`, `pane_is_shell_prompt`)
- `restart` (for `get_last_restart_ts`, `set_last_restart_ts`, `build_launch_cmd`)
- `db` (for `db_log_heal`)
- `logger` (for `log`, `err`)
- `memory` (for `schedule_memory_audit`)
- `state` (for `AgentState`)

**Shared state:** `_last_wake_ts` stays as module-level dict in idle.py. Uses `restart._last_restart_ts` via accessor.

### `inbox_watcher.py` -- InboxWatcherThread

**Moves here:**
- `class InboxWatcherThread` (lines 1255-1304)

**Dependencies:**
- `idle` (for `has_pending_messages`)
- `logger` (for `log`, `warn`)
- `constants` (for `IDLE_POLL_FALLBACK_S`)
- `state` (for `AgentState`)

**Shared state:** Thread-safe wake queue (already uses internal lock). Reads `agent_states` dict.

### `memory.py` -- Memory enforcement

**Moves here:**
- `_pending_memory_audits: dict` (line 780)
- `inject_memory_reread()` (lines 783-812)
- `run_memory_audit()` (lines 815-869)
- `check_pending_memory_audits()` (lines 872-890)
- `schedule_memory_audit()` -- **NEW** convenience function wrapping `_pending_memory_audits[agent] = time + delay`

**Dependencies:**
- `constants` (for `MEMORY_SCANNER_PATH`, `POST_RESTART_AUDIT_DELAY_S`)
- `tmux` (for `send_keys`, `send_enter`)
- `db` (for `db_log_heal`, `db_log_memory_audit`)
- `logger` (for `log`, `warn`, `err`)
- `notify` (for `notify_ceo`)
- `state` (for `AgentState`)

**Shared state:** `_pending_memory_audits` dict -- module-level in memory.py, exported via `schedule_memory_audit()`.

### `tokens.py` -- Token tracking and JSONL scanning

**Moves here:**
- `_jsonl_offsets: dict` (line 141)
- `_agent_jsonl_map: dict` (line 142)
- `_jsonl_map_refresh_ts: float` (line 143)
- `JSONL_MAP_REFRESH_S` constant -- move to `constants.py`
- `parse_tokens_from_pane()` (lines 1361-1395)
- `_refresh_agent_jsonl_map()` (lines 1398-1478)
- `_scan_jsonl_incremental()` (lines 1481-1547)
- `_scan_jsonl_remote()` (lines 1550-1600)
- `_compute_cost()` (lines 1603-1626)
- `scan_tokens_for_agent()` (lines 1629-1669)

**Dependencies:**
- `constants` (for `CLAUDE_PROJECTS_DIR`, `COST_RATES`, `TOKEN_PATTERNS`, `JSONL_MAP_REFRESH_S`)
- `config` (for `get_machines_config`)
- `tmux` (for `capture_pane`)
- `db` (for `db_upsert_token_usage`)
- `logger` (for `log`, `warn`)
- `state` (for `AgentState`)

**Shared state:** `_jsonl_offsets`, `_agent_jsonl_map`, `_jsonl_map_refresh_ts` -- all module-level in tokens.py.

### `spend.py` -- Spend tracking

**Moves here:**
- `_spend_alert_sent_date: str` (line 1674)
- `check_spend()` (lines 1677-1699)

**Dependencies:**
- `constants` (for `SPEND_ALERT_USD`, `SPEND_CAP_USD`)
- `db` (for `db_today_total_spend`)
- `logger` (for `log`, `now_date`)
- `notify` (for `notify_ceo`)
- `state` (for `AgentState`)

**Shared state:** `_spend_alert_sent_date` stays as module-level string in spend.py.

### `notify.py` -- CEO notifications

**Moves here:**
- `notify_ceo()` (lines 610-621)

**Dependencies:**
- `constants` (for `SOUL_MSG`)

**Shared state:** None

### `continue_.py` -- Auto-continue logic

**Moves here:**
- `_pane_last_seen: dict` (line 1310)
- `maybe_continue_agent()` (lines 1313-1356)

**Dependencies:**
- `constants` (for `SAFE_AUTO_APPROVE_RE`, `NEVER_AUTO_APPROVE_RE`)
- `tmux` (for `capture_pane`, `send_keys`, `send_enter`, `pane_last_line`, `pane_hash`)
- `db` (for `db_log_heal`)
- `logger` (for `log`)
- `state` (for `AgentState`)

**Shared state:** `_pane_last_seen` stays as module-level dict in continue_.py.

### `bridge.py` -- Bridge daemon watchdog

**Moves here:**
- `_bridge_pid: int` (line 1704)
- `ensure_bridge_running()` (lines 1707-1756)

**Dependencies:**
- `constants` (for `BRIDGE_SCRIPT`)
- `db` (for `db_log_heal`)
- `logger` (for `log`, `err`)

**Shared state:** `_bridge_pid` stays as module-level int in bridge.py.

### `guard.py` -- System guard cycle

**Moves here:**
- `system_guard_cycle()` (lines 1761-1819)

**Dependencies:**
- `constants` (for `TEMP_LIMIT_C`, `CPU_WARN_PCT`, `MEM_MIN_MB`)
- `health` (for `read_temp_celsius`, `read_mem_free_mb`, `read_cpu_pct`, `find_newest_claude_pid`, `find_heaviest_claude_pid`, `kill_pid`)
- `db` (for `db_log_heal`)
- `logger` (for `log`, `warn`)

**Shared state:** None

### `check.py` -- Dry-run check mode

**Moves here:**
- `run_check()` (lines 1824-1894)

**Dependencies:**
- `constants` (for `VERSION`, `TEAM_NAME`, `DB_PATH`, `TEMP_LIMIT_C`, `MEM_MIN_MB`, `CPU_WARN_PCT`, `BRIDGE_SCRIPT`, `COMPACT_TRIGGER_RE`, `SAFE_AUTO_APPROVE_RE`, `NEVER_AUTO_APPROVE_RE`)
- `health` (for `read_temp_celsius`, `read_mem_free_mb`, `read_cpu_pct`)
- `tmux` (for `capture_pane`, `pane_last_line`, `pane_is_shell_prompt`)
- `db` (for `db_connect`, `db_init`, `db_today_total_spend`)
- `logger` (for `now_iso`)
- `state` (for `AgentState`)

**Shared state:** None

### `main.py` -- Main loop orchestration

**Moves here:**
- `_running: bool` (line 1899)
- `handle_sigterm()` (lines 1902-1904)
- `build_agent_states()` (lines 1908-1928)
- `run_daemon()` (lines 1931-2070)
- `main()` (lines 2075-2105)

**Dependencies:** All modules (orchestrator). Specifically:
- `constants` (for `VERSION`, `MAIN_INTERVAL_S`, `TOKEN_INTERVAL_S`, `SPEND_INTERVAL_S`, `IDLE_CHECK_INTERVAL_S`)
- `config` (for `load_machines_config`, `load_agent_models`, `build_agent_pane_map`, `_load_toml_agents`)
- `state` (for `AgentState`)
- `db` (for `db_connect`, `db_init`)
- `logger` (for `log`, `warn`, `err`)
- `guard` (for `system_guard_cycle`)
- `bridge` (for `ensure_bridge_running`)
- `restart` (for `maybe_restart_agent`)
- `compact` (for `maybe_compact_agent`, `check_context_budget`)
- `continue_` (for `maybe_continue_agent`)
- `idle` (for `is_agent_idle`, `idle_shutdown_agent`, `wake_agent`, `is_hot_period`)
- `inbox_watcher` (for `InboxWatcherThread`)
- `memory` (for `check_pending_memory_audits`)
- `tokens` (for `scan_tokens_for_agent`, `_refresh_agent_jsonl_map`)
- `spend` (for `check_spend`)
- `check` (for `run_check`)

**Shared state:** `_running` bool stays as module-level in main.py.

---

## 4. Dependency Graph (import direction)

```
constants  <-- LEAF (no intra-package imports)
     ^
     |
  logger  <-- imports constants
     ^
     |
  state   <-- LEAF (no intra-package imports)
     ^
     |
  +------+------+------+
  |      |      |      |
 tmux   db   notify  health    <-- Layer 2 (import constants, logger)
  ^      ^      ^      ^
  |      |      |      |
  +--+---+--+---+--+---+
     |      |      |
  config  restart  guard       <-- Layer 3 (import Layer 2)
     ^      ^      ^
     |      |      |
  compact  idle  memory        <-- Layer 4 (import Layer 3)
     ^      ^      ^
     |      |      |
  tokens  continue_ spend     <-- Layer 4 (peers)
     ^      ^      ^
     |      |      |
  inbox_watcher  bridge        <-- Layer 4 (peers)
     ^      ^      ^
     |      |      |
     +------+------+
            |
         check                 <-- Layer 5 (diagnostic)
            ^
            |
          main                 <-- Layer 6 (orchestrator, imports everything)
```

No circular dependencies. Every module imports only from lower layers.

---

## 5. Migration Strategy

### Phase 1: Extract pure-function modules (no shared state)

**Scope:** 4 modules, minimal risk. All are leaf nodes or near-leaf.

1. **`constants.py`** -- Move all constants, regex patterns, path definitions. Every other module's `from soul_guardian import CONST` becomes `from guardian.constants import CONST`. This is the foundation -- do it first.

2. **`logger.py`** -- Move `now_iso`, `now_date`, `log`, `warn`, `err`. Pure functions with file I/O only.

3. **`state.py`** -- Move `AgentState` class. Zero dependencies on other guardian code.

4. **`health.py`** -- Move system monitoring functions. Pure functions reading /proc and /sys.

**Verification gate:** All 110 tests pass after Phase 1. Run `python3 -m pytest tests/test_guardian.py -v --timeout=10`.

**How to keep tests passing during Phase 1:**
- After extracting modules, the monolith `soul-guardian.py` must re-export all extracted names. Add `from guardian.constants import *` etc. at the top. Tests import `soul-guardian` and expect those names to exist.
- This re-export layer is temporary scaffolding, removed in Phase 3.

### Phase 2: Extract stateful modules with dependency injection

**Scope:** 11 modules. Each has mutable module-level state or depends on other extracted modules.

**Order matters.** Extract in dependency order (lower layers first):

1. **`notify.py`** -- Trivial, single function, no shared state.
2. **`tmux.py`** -- Pure functions + subprocess calls. No shared state.
3. **`db.py`** -- Has `_db_lock`. Lock stays in db.py. `conn` already passed as argument everywhere.
4. **`config.py`** -- Has `_machines_config`. Export via accessor function.
5. **`restart.py`** -- Has `_last_restart_ts`. Export via accessor functions.
6. **`memory.py`** -- Has `_pending_memory_audits`. Export via `schedule_memory_audit()`.
7. **`compact.py`** -- Has `_context_alerts_sent`. Local to module.
8. **`idle.py`** -- Has `_last_wake_ts`. Uses restart accessors for stagger coordination.
9. **`tokens.py`** -- Has `_jsonl_offsets`, `_agent_jsonl_map`, `_jsonl_map_refresh_ts`.
10. **`continue_.py`** -- Has `_pane_last_seen`.
11. **`spend.py`, `bridge.py`, `guard.py`, `inbox_watcher.py`** -- Each has one piece of local state.

**Verification gate:** All 110 tests pass after each sub-step. Run full suite after each module extraction.

### Phase 3: Slim down main.py to orchestration only

1. **`check.py`** -- Extract `run_check()`.
2. **`main.py`** -- Extract `build_agent_states`, `run_daemon`, `handle_sigterm`, `main`.
3. **`__main__.py`** -- Create entry point: `from guardian.main import main; main()`.
4. **Remove re-export scaffolding** from the original `soul-guardian.py`. Replace it with a thin wrapper:
   ```python
   # soul-guardian.py -- DEPRECATED, use `python3 -m guardian` instead
   from guardian.main import main
   if __name__ == "__main__":
       main()
   ```
5. **Migrate tests** to import from `guardian.*` modules instead of `soul-guardian`.

**Verification gate:** All 110 tests pass. `python3 -m guardian --check` works identically to `python3 soul-guardian.py --check`.

---

## 6. Test Mapping

### Existing test classes -> proposed modules

| Test Class | Count | Target Module(s) |
|---|---|---|
| `TestConfigLoading` | 9 | `config.py` |
| `TestHealthCheckLogic` | 9 | `tmux.py` (pane_last_line, pane_hash, pane_is_shell_prompt) |
| `TestRestartLogic` | 8 | `restart.py` |
| `TestSQLiteOperations` | 10 | `db.py` |
| `TestBuildLaunchCmd` | 9 | `restart.py` (build_launch_cmd) |
| `TestTokenParsing` | 9 | `tokens.py` |
| `TestUtilityFunctions` | 12 | `state.py`, `logger.py`, `constants.py` (split across 3 modules) |
| `TestTokenPatterns` | 5 | `constants.py` (patterns) + `tokens.py` (parsing) |
| `TestSpendCheck` | 2 | `spend.py` |
| `TestAutoContinue` | 3 | `continue_.py` |
| `TestIdleDetection` | 9 | `idle.py` |
| `TestWakeAgent` | 5 | `idle.py` (wake_agent) |
| `TestIntegration` | 3 | Cross-module (keep as integration) |
| *Parametrized expand* | 17 | (pane_is_shell_prompt parametrized = 16 extra + 1 base) |
| **TOTAL** | **110** | |

### Post-refactor test file structure

```
tests/
  __init__.py
  conftest.py              # Shared fixtures (in_memory_db, sample_toml, agent_state, reset_globals)
  test_constants.py        # Constants sanity, regex patterns (from TestUtilityFunctions + TestTokenPatterns)
  test_config.py           # TestConfigLoading (9 tests)
  test_state.py            # AgentState init/repr (from TestUtilityFunctions)
  test_logger.py           # now_iso, now_date format (from TestUtilityFunctions)
  test_db.py               # TestSQLiteOperations (10 tests)
  test_tmux.py             # TestHealthCheckLogic (9 tests -- pane functions)
  test_health.py           # NEW: mock /proc /sys reads
  test_restart.py          # TestRestartLogic + TestBuildLaunchCmd (17 tests)
  test_compact.py          # NEW: maybe_compact_agent, check_context_budget
  test_idle.py             # TestIdleDetection + TestWakeAgent (14 tests)
  test_memory.py           # NEW: inject_memory_reread, run_memory_audit
  test_tokens.py           # TestTokenParsing (9 tests)
  test_spend.py            # TestSpendCheck (2 tests)
  test_continue.py         # TestAutoContinue (3 tests)
  test_notify.py           # NEW: notify_ceo mock tests
  test_bridge.py           # NEW: ensure_bridge_running mock tests
  test_guard.py            # NEW: system_guard_cycle integration
  test_inbox_watcher.py    # NEW: InboxWatcherThread lifecycle
  test_integration.py      # TestIntegration (3 tests) -- cross-module
  test_guardian_compat.py  # Backward compat: verify soul-guardian.py still works
```

### New tests needed post-refactor

These functions currently have ZERO direct test coverage:

| Function | Module | Priority | Complexity |
|---|---|---|---|
| `inject_memory_reread()` | memory.py | P1 | Low (mock send_keys) |
| `run_memory_audit()` | memory.py | P1 | Medium (mock subprocess) |
| `check_pending_memory_audits()` | memory.py | P1 | Medium (time-based scheduling) |
| `maybe_compact_agent()` | compact.py | P1 | Medium (mock capture_pane + time) |
| `check_context_budget()` | compact.py | P2 | Medium (multi-path) |
| `idle_shutdown_agent()` | idle.py | P1 | Medium (multi-step with sleeps) |
| `system_guard_cycle()` | guard.py | P2 | Low (mock health reads) |
| `ensure_bridge_running()` | bridge.py | P2 | Medium (PID lifecycle) |
| `InboxWatcherThread` | inbox_watcher.py | P2 | High (threading) |
| `scan_tokens_for_agent()` | tokens.py | P2 | Medium (JSONL + pane) |
| `_refresh_agent_jsonl_map()` | tokens.py | P3 | High (filesystem + SSH) |
| `_scan_jsonl_remote()` | tokens.py | P3 | High (SSH subprocess) |
| `build_agent_states()` | main.py | P2 | Low (mock config) |
| `run_daemon()` | main.py | P3 | High (full loop) |
| `run_check()` | check.py | P2 | Medium (end-to-end output) |
| `notify_ceo()` | notify.py | P2 | Low (mock subprocess) |

**Estimated new tests: 25-35** to bring coverage up to solid levels.

**Post-refactor total: ~135-145 tests.**

---

## 7. Risk Assessment

### What could break

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Import path changes break tests | HIGH | LOW | Re-export scaffolding in Phase 1 keeps tests green while migrating |
| Module-level state initialization order changes | MEDIUM | MEDIUM | Constants module has no side effects. Config loading happens explicitly in main. |
| Circular imports between restart/idle (shared `_last_restart_ts`) | MEDIUM | HIGH | Use accessor functions, not direct attribute access. Verified by dependency graph (no cycles). |
| `_pending_memory_audits` accessed from 4 modules simultaneously | MEDIUM | MEDIUM | Centralize in memory.py with `schedule_memory_audit()` function |
| Race conditions in `_db_lock` across module boundaries | LOW | HIGH | Lock stays in db.py. All DB calls already go through db.py functions. No change. |
| `systemd` service breakage (`python3 soul-guardian.py` -> `python3 -m guardian`) | MEDIUM | HIGH | Keep `soul-guardian.py` as a thin wrapper forwarding to `guardian.main`. Update systemd unit after verification. |
| Regex patterns behave differently when compiled in a different module | NEGLIGIBLE | LOW | Patterns are compiled at import time regardless of module location. |
| `autouse` fixture `reset_guardian_globals` misses new module globals | HIGH | MEDIUM | Each new test file gets its own reset fixture. Integration conftest handles cross-module resets. |
| Performance regression from added import overhead | LOW | LOW | Python caches imports. ~20 modules adds <50ms to startup. Guardian runs as a long-lived daemon. |

### Rollback strategy

1. **Git branch isolation:** All work on `refactor/guardian-modularize` branch.
2. **`soul-guardian.py` thin wrapper** remains functional at all times. If anything breaks in prod, revert to the single-file version by restoring `soul-guardian.py` from the commit before the refactor.
3. **Phase gates:** Each phase has a test verification checkpoint. If tests break and can't be fixed within the phase, revert that phase only.
4. **Systemd unit unchanged** until Phase 3 is verified. The service continues running `python3 ~/.claude/scripts/soul-guardian.py` throughout the refactor.

---

## 8. Prerequisites (Non-Negotiable)

1. **Test coverage must stay at 110+ tests passing throughout every phase.**
2. **No functional changes** -- behavior must be identical. Zero new features, zero bug fixes during refactor.
3. **The `soul-guardian.py` entry point must remain functional** until the systemd unit is updated.
4. **`python3 -m pytest tests/test_guardian.py -v --timeout=10`** must pass before and after each phase.
5. **`python3 soul-guardian.py --check`** output must be byte-identical before and after (modulo timestamps).
6. **Guardian systemd service** (`soul-guardian.service`) must not be touched until Phase 3 is complete and verified.

---

## 9. Effort Estimate

| Phase | Modules | Estimated Time | Risk |
|---|---|---|---|
| Phase 1: Pure functions | 4 modules | 45-60 min | Low |
| Phase 2: Stateful modules | 11 modules | 2-3 hours | Medium |
| Phase 3: Main + test migration | 3 modules + test split | 1-2 hours | Medium |
| New test coverage | ~30 tests | 1-2 hours | Low |
| **TOTAL** | 22 files | **5-7 hours** | |

Best executed as a single focused sprint with verification gates between phases.

---

## 10. Open Questions for CEO Approval

1. **Module naming:** `logger.py` vs `logging.py` -- recommend `logger.py` to avoid stdlib shadow. Confirm?
2. **Entry point migration timeline:** When to update `soul-guardian.service` ExecStart from `soul-guardian.py` to `python3 -m guardian`? Recommend: 48h after Phase 3 passes in production.
3. **Test file split:** Split into per-module test files (as proposed) or keep single test file with updated imports? Recommend: split for maintainability, but the single-file approach is lower risk.
4. **Backward compat wrapper:** Keep `soul-guardian.py` as thin wrapper permanently, or delete after systemd migration? Recommend: keep for 2 weeks, then archive.
