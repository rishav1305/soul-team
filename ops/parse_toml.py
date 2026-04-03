#!/usr/bin/env python3
"""
parse_toml.py -- Single TOML parser for soul-team.sh.

Replaces all inline Python regex TOML parsers with a clean tomllib-based
solution. Outputs structured JSON to stdout for consumption by jq.

Usage:
    parse_toml.py <path-to-toml>

Output JSON structure:
{
    "boot_prompt": "...",
    "stagger_seconds": 10,
    "agents": [
        {"name": "pepper", "model": "sonnet", "machine": "local"},
        ...
    ],
    "agent_machines": {"pepper": "local", "shuri": "worker", ...}
}
"""

import json
import sys
import tomllib


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: parse_toml.py <path-to-toml>", file=sys.stderr)
        sys.exit(1)

    toml_path = sys.argv[1]

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        print(f"Error: {toml_path} not found", file=sys.stderr)
        sys.exit(1)
    except tomllib.TOMLDecodeError as e:
        print(f"Error: invalid TOML: {e}", file=sys.stderr)
        sys.exit(1)

    team = data.get("team", {})
    agents = data.get("agents", [])

    result = {
        "boot_prompt": team.get("boot_prompt", ""),
        "stagger_seconds": team.get("stagger_seconds", 10),
        "agents": [
            {
                "name": a.get("name", ""),
                "model": a.get("model", "sonnet"),
                "machine": a.get("machine", "local"),
            }
            for a in agents
            if a.get("name")
        ],
        "agent_machines": {
            a["name"]: a.get("machine", "local")
            for a in agents
            if a.get("name")
        },
    }

    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
