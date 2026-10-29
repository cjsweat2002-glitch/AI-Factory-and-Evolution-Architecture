import argparse
import csv
import json
from pathlib import Path
from typing import List, Optional

from src.sheaf_neurosymbolic_multiverse_engine import (
    SheafNeurosymbolicMultiverseEngine,
)


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "memory"
    / "multiverse"
    / "sheaf-neurosymbolic-multiverse-results.csv"
)


def run_multiverse(
    total_steps: int = 100, output_path: Path = DEFAULT_OUTPUT, seed: int = 42
) -> dict:
    engine = SheafNeurosymbolicMultiverseEngine(total_steps=total_steps, seed=seed)
    records = engine.run_simulation()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(records[0])
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    return {
        "status": "success",
        "steps_completed": len(records),
        "initial_obstruction": records[0]["Sheaf_Obstruction"],
        "final_obstruction": records[-1]["Sheaf_Obstruction"],
        "max_poincare_norm": max(record["Poincare_Norm"] for record in records),
        "output_path": str(output_path.resolve()),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the SAM-H5 sheaf-neurosymbolic simulation."
    )
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    print(json.dumps(run_multiverse(args.steps, args.output, args.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
