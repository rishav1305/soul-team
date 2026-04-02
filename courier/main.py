#!/usr/bin/env python3
"""Soul Courier — Reliable message delivery daemon for soul-team."""
import os
import logging
import signal
import sys

# Fix sys.path: Python adds the script's directory (courier/) to sys.path[0].
# courier/queue.py shadows stdlib queue — remove the courier dir and ensure
# the repo root is present instead so that soul_courier.* imports work.
_script_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_script_dir)
if _script_dir in sys.path:
    sys.path.remove(_script_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from soul_courier.daemon import CourierDaemon


def main():
    daemon = CourierDaemon()

    def handle_signal(signum, frame):
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    daemon.start()


if __name__ == "__main__":
    main()
