"""Run a day-long microgrid scenario and print or save results."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .simulation import day_profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the microgrid controller simulation")
    parser.add_argument("--steps", type=int, default=96)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    rows = day_profile(args.steps)
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    summary = {
        "steps": len(rows),
        "final_soc": rows[-1]["next_soc"],
        "peak_grid_import_kw": max(float(row["grid_import_kw"]) for row in rows),
        "unserved_energy_kwh": round(
            sum(float(row["unserved_load_kw"]) * float(row["interval_hours"]) for row in rows),
            3,
        ),
        "modes": sorted({str(row["mode"]) for row in rows}),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

