import csv
import math
from pathlib import Path

import numpy as np
import pytest

from src.run_sheaf_multiverse import run_multiverse
from src.sheaf_neurosymbolic_multiverse_engine import (
    CaputoFractionalMemory,
    CellularSheafNetwork,
    HJPOptimalControlGate,
    NeurosymbolicCTMAnchor,
    PoincareHyperbolicSpace,
    SheafNeurosymbolicMultiverseEngine,
)


def test_poincare_exp_and_log_maps_round_trip():
    space = PoincareHyperbolicSpace(dim=2)
    base = np.array([0.1, -0.05])
    tangent = np.array([0.02, 0.03])

    point = space.exp_map(base, tangent)

    assert np.linalg.norm(point) < 1
    assert space.log_map(base, point) == pytest.approx(tangent, abs=1e-8)
    lambda_base = 2 / (1 - np.dot(base, base))
    assert space.hyperbolic_distance(base, point) == pytest.approx(
        lambda_base * np.linalg.norm(tangent), abs=1e-8
    )


def test_sheaf_laplacian_is_symmetric_positive_semidefinite():
    network = CellularSheafNetwork(num_nodes=5, node_dim=4)
    laplacian = network.compute_sheaf_laplacian()

    assert laplacian == pytest.approx(laplacian.T)
    assert np.linalg.eigvalsh(laplacian).min() >= -1e-10


def test_sheaf_obstruction_rejects_bad_state_shape():
    network = CellularSheafNetwork(num_nodes=3, node_dim=2)

    with pytest.raises(ValueError, match="global_state"):
        network.sheaf_obstruction_index(np.zeros((3, 3)))


def test_caputo_fractional_derivative_has_correct_single_interval_scaling():
    derivative = CaputoFractionalMemory(gamma=0.5, dt=0.25).compute_fractional_derivative(
        [np.array([0.0]), np.array([1.0])]
    )

    assert derivative[0] == pytest.approx(
        1 / (0.25**0.5 * math.gamma(1.5))
    )


def test_hjb_gate_uses_positive_time_varying_energy_factor():
    gate = HJPOptimalControlGate()

    rate, pef = gate.compute_optimal_learning_rate(grad_norm=0.1, costate_lambda=1, hour=6)

    assert 0.001 <= rate <= 0.5
    assert pef > 0
    assert HJPOptimalControlGate.primary_energy_factor(6) != pytest.approx(
        HJPOptimalControlGate.primary_energy_factor(18)
    )


def test_ctm_anchor_returns_finite_complexity_and_anchored_state():
    anchor = NeurosymbolicCTMAnchor()
    state, loss, complexity = anchor.apply_symbolic_potential_barrier(
        np.array([0.13, -0.22, 0.31, 0.07]), loss=2.0
    )

    assert state.shape == (4,)
    assert loss > 2
    assert math.isfinite(complexity)


def test_simulation_reduces_obstruction_and_preserves_poincare_ball():
    records = SheafNeurosymbolicMultiverseEngine(total_steps=100).run_simulation()

    assert len(records) == 100
    assert records[-1]["Sheaf_Obstruction"] < records[0]["Sheaf_Obstruction"]
    assert records[-1]["Neurosymbolic_Quality"] > records[0]["Neurosymbolic_Quality"]
    assert max(record["Poincare_Norm"] for record in records) < 1


def test_runner_writes_csv_metrics(tmp_path):
    output_path = tmp_path / "nested" / "metrics.csv"

    summary = run_multiverse(total_steps=3, output_path=output_path)

    assert summary["steps_completed"] == 3
    with output_path.open(newline="", encoding="utf-8") as csv_file:
        records = list(csv.DictReader(csv_file))
    assert len(records) == 3
    assert "Raw_HJB_Learning_Rate" in records[0]
    assert "Simulated_Value_Index" in records[0]


def test_supplied_reference_dataset_exposes_reported_instability():
    dataset_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "sam_h5_reference_dataset.csv"
    )
    with dataset_path.open(newline="", encoding="utf-8-sig") as dataset_file:
        rows = list(csv.DictReader(dataset_file))

    obstruction = [float(row["Sheaf_Obstruction"]) for row in rows]
    rates = [float(row["HJB_Learning_Rate"]) for row in rows]
    norms = [float(row["Poincare_Norm"]) for row in rows]
    qualities = [float(row["Neurosymbolic_Quality"]) for row in rows]

    assert len(rows) == 100
    assert obstruction[-1] > obstruction[0]
    assert set(rates) == {0.5}
    assert max(norms) > 1
    assert set(qualities) == {0.85}
