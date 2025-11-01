#!/usr/bin/env python3
"""
Stub memory diagnostic used for demonstrating Road Runner flows.
"""

from __future__ import annotations

import argparse
import random
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory diagnostic stub")
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--pattern", type=str, default="sequential")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    duration = max(args.duration_s, 0.0)
    pattern = args.pattern
    start = time.monotonic()
    iteration = 0
    while time.monotonic() - start < duration:
        iteration += 1
        time.sleep(0.05)
        if iteration % 20 == 0:
            print(f"[mem-test-stub] pattern={pattern} iteration={iteration}", flush=True)

    print("mem-test-stub completed successfully.", flush=True)


if __name__ == "__main__":
    main()
