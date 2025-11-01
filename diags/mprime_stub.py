#!/usr/bin/env python3
"""
Stub implementation of an mprime-style diagnostic.

This keeps the repository self-contained while mimicking the CLI surface of a real binary.
"""

from __future__ import annotations

import argparse
import random
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="mprime diagnostic stub")
    parser.add_argument("--duration-s", type=float, default=5.0, help="Run duration in seconds")
    parser.add_argument("--worker-count", type=int, default=1, help="Number of threads to simulate")
    parser.add_argument("--seed", type=int, help="Random seed for deterministic stress patterns")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    duration = max(args.duration_s, 0.0)
    workers = max(args.worker_count, 1)
    start = time.monotonic()
    iteration = 0
    while time.monotonic() - start < duration:
        iteration += 1
        # Simulate work by sleeping for a fraction of the duration
        time.sleep(min(0.05, duration / max(iteration * workers, 1)))
        if iteration % 10 == 0:
            print(f"[mprime-stub] Iteration {iteration} workers={workers}", flush=True)

    print("mprime-stub completed successfully.", flush=True)


if __name__ == "__main__":
    main()
