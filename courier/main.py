#!/usr/bin/env python3
"""Soul Courier — Reliable message delivery daemon for soul-team."""
import logging
import signal
import sys

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
