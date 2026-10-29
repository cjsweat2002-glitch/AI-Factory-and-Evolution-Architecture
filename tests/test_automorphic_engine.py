import math

import numpy as np
import pytest

from src.automorphic_engine_core import (
    CTMProgramAnchor,
    CaputoFractionalMemory,
    HJBPmpResourceScheduler,
    HyperbolicSheafLaplacian,
    PoincareHyperbolicSpace,
)


def test_poincare_distance_matches_geodesic_and_is_symmetric():
    space = PoincareHyperbolicSpace(dim=2)
    origin = np.zeros(2)
    point = np.array([0.5, 0.0])

    assert space.poincare_distance(origin, point) == pytest.approx(2 * math.atanh(0.5))
    assert space.poincare_distance(origin, origin) == 0
    assert space.poincare_distance(origin, point) == pytest.approx(
        space.poincare_distance(point, origin)
    )


def test_poincare_space_rejects_invalid_curvature_and_out_of_ball_points():
    with pytest.raises(ValueError, match="c must"):
        PoincareHyperbolicSpace(c=0)

    with pytest.raises(ValueError, match="inside"):
        PoincareHyperbolicSpace(dim=2).poincare_distance(
            np.array([1.0, 0.0]), np.zeros(2)
        )


def test_caputo_derivative_uses_current_state_and_dt():
    memory = CaputoFractionalMemory(gamma=0.5)
    memory.push(np.array([0.0]))

    result = memory.compute_fractional_derivative(np.array([1.0]), dt=0.25)

    assert result[0] == pytest.approx(1 / (0.25**0.5 * math.gamma(1.5)))


def test_sheaf_initialization_does_not_mutate_global_random_state():
    np.random.seed(123)
    before = np.random.get_state()

    HyperbolicSheafLaplacian(num_nodes=2, feature_dim=2)

    after = np.random.get_state()
    assert before[0] == after[0]
    assert np.array_equal(before[1], after[1])
    assert before[2:] == after[2:]


def test_sheaf_requires_one_state_per_node():
    sheaf = HyperbolicSheafLaplacian(num_nodes=2, feature_dim=2)

    with pytest.raises(ValueError, match="exactly 2"):
        sheaf.compute_sheaf_obstruction([np.zeros(2)])


def test_scheduler_rejects_non_positive_energy_cost():
    with pytest.raises(ValueError, match="energy_cost_coeff"):
        HJBPmpResourceScheduler(energy_cost_coeff=0)


def test_complexity_anchor_does_not_assume_proposed_loss_improves():
    anchor = CTMProgramAnchor(lambda_complexity=1.0)
    current = "a" * 100
    proposed = "abcdefghijklmnopqrstuvwxyz" * 4

    accepted_genome, accepted = anchor.apply_quine_anchor(current, proposed, loss_val=100)

    assert accepted is False
    assert accepted_genome == current


def test_complexity_anchor_accepts_explicitly_better_proposed_loss():
    anchor = CTMProgramAnchor(lambda_complexity=1.0)
    current = "a" * 100
    proposed = "abcdefghijklmnopqrstuvwxyz" * 4

    accepted_genome, accepted = anchor.apply_quine_anchor(
        current, proposed, loss_val=100, proposed_loss_val=90
    )

    assert accepted is True
    assert accepted_genome == proposed
