import ast
import json
import sys

import numpy as np
import pytest

from src.autonomous_brand_agent import AutonomousBrandEngine, BrandEntity
from src.run_autopoietic_factory import run_brand_autopoiesis_factory


def test_brand_initialization_is_deterministic_without_global_rng_mutation():
    np.random.seed(123)
    before = np.random.get_state()

    first = BrandEntity("brand-id", "Brand", "Mission")
    second = BrandEntity("brand-id", "Brand", "Mission")
    after = np.random.get_state()

    assert np.array_equal(first.vector_h4, second.vector_h4)
    assert np.array_equal(before[1], after[1])
    assert before[2:] == after[2:]


def test_iteration_updates_brand_and_generates_safe_reviewable_script():
    engine = AutonomousBrandEngine(brand_name="Brand 'X'", brand_id="brand-1")

    result = engine.run_successive_iteration(
        {"market_demand": "sustainable_compute", "target_audience": "Researchers"}
    )

    assert result["accepted_by_ctm"] is True
    assert result["brand_summary"]["generation"] == 1
    assert result["brand_summary"]["products_count"] == 1
    assert result["worker_results"]["evaluator"]["simulated_net_worth"] > 10
    script = next(iter(engine.brand.code_artifacts.values()))
    parsed_script = ast.parse(script)
    brand_name_assignment = next(
        statement
        for statement in parsed_script.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "BRAND_NAME"
            for target in statement.targets
        )
    )
    assert ast.literal_eval(brand_name_assignment.value) == "Brand 'X'"


def test_iteration_rejects_invalid_energy_factor():
    engine = AutonomousBrandEngine()

    with pytest.raises(ValueError, match="pef_t"):
        engine.run_successive_iteration({}, pef_t=0)


def test_ctm_rejection_rolls_back_brand_state():
    engine = AutonomousBrandEngine()
    before = json.loads(json.dumps(engine.brand.to_dict()))
    history_size = len(engine.memory.history)
    engine.ctm_anchor.apply_quine_anchor = lambda *args, **kwargs: (args[0], False)

    result = engine.run_successive_iteration({"market_demand": "sustainable_compute"})

    assert result["accepted_by_ctm"] is False
    assert engine.brand.to_dict() == before
    assert len(engine.memory.history) == history_size


def test_factory_writes_checkpoints_products_scripts_and_csv(tmp_path):
    result = run_brand_autopoiesis_factory(generations=2, output_dir=tmp_path)

    assert result["generations_completed"] == 2
    assert (tmp_path / "brand_checkpoint_gen_01.json").exists()
    assert (tmp_path / "brand_checkpoint_gen_02.json").exists()
    assert (tmp_path / "products" / "PROD-001.json").exists()
    assert (tmp_path / "products" / "PROD-002.json").exists()
    scripts = list((tmp_path / "autopoietic_scripts").glob("*.py"))
    assert len(scripts) == 2
    assert (tmp_path / "evolution_metrics.csv").read_text(
        encoding="utf-8"
    ).count("\n") == 3
    assert json.loads((tmp_path / "brand_checkpoint_gen_02.json").read_text())[
        "products_count"
    ] == 2
    assert json.loads((tmp_path / "brand_checkpoint_gen_02.json").read_text())[
        "simulated_net_worth"
    ] > 10


def test_factory_requires_positive_generation_count(tmp_path):
    with pytest.raises(ValueError, match="generations"):
        run_brand_autopoiesis_factory(generations=0, output_dir=tmp_path)
