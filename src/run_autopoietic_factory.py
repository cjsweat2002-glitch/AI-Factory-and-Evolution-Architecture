import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.autonomous_brand_agent import AutonomousBrandEngine


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "memory" / "brand_factory"
MARKET_SIGNALS = [
    {
        "market_demand": "clean_energy_compute_acceleration",
        "target_audience": "Hyperscale Infrastructure Engineers",
    },
    {
        "market_demand": "autopoietic_neurosymbolic_self_improvement",
        "target_audience": "Autonomous Agent Developers",
    },
    {
        "market_demand": "hyperbolic_sheaf_diffusion_graphs",
        "target_audience": "Topological ML Researchers",
    },
    {
        "market_demand": "autonomous_bio_med_drug_synthesis",
        "target_audience": "Computational Pharmacologists",
    },
    {
        "market_demand": "zero_copy_webgpu_wasm_runtimes",
        "target_audience": "Real-time Graphics Engine Architects",
    },
]


def run_brand_autopoiesis_factory(
    generations: int = 20,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    brand_name: str = "Plantable-AI-Generative",
    brand_id: str = "PLANTABLE-REPO-001",
) -> Dict[str, Any]:
    if generations < 1:
        raise ValueError("generations must be positive")

    output_dir = Path(output_dir)
    products_dir = output_dir / "products"
    scripts_dir = output_dir / "autopoietic_scripts"
    products_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)
    engine = AutonomousBrandEngine(brand_name=brand_name, brand_id=brand_id)
    records: List[Dict[str, Any]] = []

    for generation in range(1, generations + 1):
        pef = 1.1 + 0.4 * math.cos(generation * 0.3)
        result = engine.run_successive_iteration(
            MARKET_SIGNALS[(generation - 1) % len(MARKET_SIGNALS)], pef_t=pef
        )
        if not result["accepted_by_ctm"]:
            continue
        brand_data = result["brand_summary"]
        (output_dir / f"brand_checkpoint_gen_{generation:02d}.json").write_text(
            json.dumps(brand_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        for product in brand_data["products"]:
            product_path = products_dir / f"{product['product_id']}.json"
            product_path.write_text(
                json.dumps(product, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        for script_key, content in engine.brand.code_artifacts.items():
            (scripts_dir / script_key).write_text(content, encoding="utf-8")

        records.append(
            {
                "generation": generation,
                "quality_score": brand_data["quality_score"],
                "sheaf_obstruction": brand_data["sheaf_obstruction"],
                "simulated_net_worth": brand_data["simulated_net_worth"],
                "learning_rate_eta": result["eta_t"],
                "product_count": brand_data["products_count"],
                "h4_embedding_norm": sum(
                    value**2 for value in brand_data["vector_h4"]
                )
                ** 0.5,
            }
        )

    dataset_path = output_dir / "evolution_metrics.csv"
    fieldnames = [
        "generation",
        "quality_score",
        "sheaf_obstruction",
        "simulated_net_worth",
        "learning_rate_eta",
        "product_count",
        "h4_embedding_norm",
    ]
    with dataset_path.open("w", newline="", encoding="utf-8") as dataset_file:
        writer = csv.DictWriter(dataset_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    return {
        "status": "success",
        "generations_requested": generations,
        "generations_completed": len(records),
        "final_brand": engine.brand.to_dict(),
        "output_dir": str(output_dir.resolve()),
        "dataset_path": str(dataset_path.resolve()),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate reviewable brand-factory checkpoints and metrics."
    )
    parser.add_argument("--generations", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--brand-name", default="Plantable-AI-Generative")
    parser.add_argument("--brand-id", default="PLANTABLE-REPO-001")
    args = parser.parse_args(argv)
    result = run_brand_autopoiesis_factory(
        generations=args.generations,
        output_dir=args.output_dir,
        brand_name=args.brand_name,
        brand_id=args.brand_id,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
