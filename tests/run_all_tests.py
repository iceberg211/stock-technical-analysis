#!/usr/bin/env python3
"""Run all tests across all skills in the suite."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"


def main():
    test_commands = [
        (
            "stock-technical-analysis contract tests",
            [
                sys.executable,
                str(
                    SKILLS
                    / "stock-technical-analysis"
                    / "tests"
                    / "test_architecture_contract.py"
                ),
            ],
        ),
        (
            "price-action-decision contract tests",
            [
                sys.executable,
                str(
                    SKILLS
                    / "price-action-decision"
                    / "tests"
                    / "test_skill_contract.py"
                ),
            ],
        ),
        (
            "market-data unit tests",
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(SKILLS / "market-data" / "tests"),
            ],
        ),
    ]

    failed = False
    for name, cmd in test_commands:
        print(f"\n=== Running {name} ===")
        res = subprocess.run(cmd, cwd=str(ROOT))
        if res.returncode != 0:
            print(f"[FAIL] {name} exited with code {res.returncode}")
            failed = True
        else:
            print(f"[PASS] {name}")

    if failed:
        sys.exit(1)
    print("\nAll skill tests passed successfully!")


if __name__ == "__main__":
    main()
