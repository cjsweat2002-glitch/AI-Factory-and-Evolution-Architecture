import math
import zlib
from typing import List, Optional, Tuple

import numpy as np


class PoincareHyperbolicSpace:
    """Math utilities for a Poincaré ball with curvature parameter c."""

    def __init__(self, dim: int = 4, c: float = 1.0):
        if dim < 1:
            raise ValueError("dim must be positive")
        if not math.isfinite(c) or c <= 0:
            raise ValueError("c must be finite and positive")
        self.dim = dim
        self.c = float(c)

    def _point(self, value: np.ndarray) -> np.ndarray:
        point = np.asarray(value, dtype=float)
        if point.shape != (self.dim,):
            raise ValueError(f"points must have shape ({self.dim},)")
        if not np.all(np.isfinite(point)):
            raise ValueError("points must contain only finite values")
        if self.c * float(np.dot(point, point)) >= 1.0:
            raise ValueError("points must lie inside the Poincare ball")
        return point

    def mobius_add(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Möbius addition in the Poincaré ball."""
        x = self._point(x)
        y = self._point(y)
        x2 = float(np.dot(x, x))
        y2 = float(np.dot(y, y))
        xy = float(np.dot(x, y))

        numerator = (1 + 2 * self.c * xy + self.c * y2) * x + (1 - self.c * x2) * y
        denominator = 1 + 2 * self.c * xy + self.c**2 * x2 * y2
        result = numerator / denominator
        norm = float(np.linalg.norm(result))
        radius = 1.0 / math.sqrt(self.c)
        if norm >= radius:
            result = result * (0.9999 * radius / norm)
        return result

    def poincare_distance(self, x: np.ndarray, y: np.ndarray) -> float:
        """Geodesic distance in the Poincaré ball."""
        x = self._point(x)
        y = self._point(y)
        x_denominator = 1 - self.c * float(np.dot(x, x))
        y_denominator = 1 - self.c * float(np.dot(y, y))
        squared_distance = float(np.dot(x - y, x - y))
        argument = 1 + 2 * self.c * squared_distance / (x_denominator * y_denominator)
        return math.acosh(max(argument, 1.0))

    def exp_map0(self, v: np.ndarray) -> np.ndarray:
        """Exponential map at the origin from the tangent space."""
        vector = np.asarray(v, dtype=float)
        if vector.shape != (self.dim,):
            raise ValueError(f"vectors must have shape ({self.dim},)")
        if not np.all(np.isfinite(vector)):
            raise ValueError("vectors must contain only finite values")
        norm = float(np.linalg.norm(vector))
        if norm < 1e-12:
            return np.zeros_like(vector)
        sqrt_c = math.sqrt(self.c)
        return (math.tanh(sqrt_c * norm) / (sqrt_c * norm)) * vector


class CaputoFractionalMemory:
    """Finite-history L1 approximation of the Caputo fractional derivative."""

    def __init__(self, gamma: float = 0.75, max_history: int = 50):
        if not math.isfinite(gamma) or not 0 < gamma < 1:
            raise ValueError("gamma must be between 0 and 1")
        if max_history < 1:
            raise ValueError("max_history must be positive")
        self.gamma = gamma
        self.max_history = max_history
        self.history: List[np.ndarray] = []

    def push(self, state: np.ndarray) -> None:
        value = np.asarray(state, dtype=float)
        if not np.all(np.isfinite(value)):
            raise ValueError("state must contain only finite values")
        if self.history and value.shape != self.history[-1].shape:
            raise ValueError("all historical states must have the same shape")
        self.history.append(value.copy())
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def compute_fractional_derivative(
        self, current_state: np.ndarray, dt: float = 0.1
    ) -> np.ndarray:
        """Approximate the derivative at current_state using prior pushed states."""
        current = np.asarray(current_state, dtype=float)
        if not np.all(np.isfinite(current)):
            raise ValueError("current_state must contain only finite values")
        if self.history and current.shape != self.history[-1].shape:
            raise ValueError("current_state must match historical state shape")
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be finite and positive")
        if not self.history:
            return np.zeros_like(current)

        states = self.history + [current]
        interval_count = len(states) - 1
        increments = [states[i + 1] - states[i] for i in range(interval_count)]
        weights = [
            (interval_count - i) ** (1 - self.gamma)
            - (interval_count - i - 1) ** (1 - self.gamma)
            for i in range(interval_count)
        ]
        weighted_increments = sum(
            (weight * increment for weight, increment in zip(weights, increments)),
            start=np.zeros_like(current),
        )
        return weighted_increments / (
            dt**self.gamma * math.gamma(2 - self.gamma)
        )


class HyperbolicSheafLaplacian:
    """Consensus discrepancy across node-local restriction maps."""

    def __init__(self, num_nodes: int = 4, feature_dim: int = 4):
        if num_nodes < 1 or feature_dim < 1:
            raise ValueError("num_nodes and feature_dim must be positive")
        self.num_nodes = num_nodes
        self.feature_dim = feature_dim
        rng = np.random.default_rng(42)
        self.restriction_maps = [
            np.eye(feature_dim) + 0.05 * rng.standard_normal((feature_dim, feature_dim))
            for _ in range(num_nodes)
        ]

    def compute_sheaf_obstruction(self, node_states: List[np.ndarray]) -> float:
        """Return the mean squared discrepancy across all node pairs."""
        if len(node_states) != self.num_nodes:
            raise ValueError(f"expected exactly {self.num_nodes} node states")
        states = [np.asarray(state, dtype=float) for state in node_states]
        if any(state.shape != (self.feature_dim,) for state in states):
            raise ValueError(f"node states must have shape ({self.feature_dim},)")
        if any(not np.all(np.isfinite(state)) for state in states):
            raise ValueError("node states must contain only finite values")

        total_obstruction = 0.0
        edge_count = 0
        for i in range(self.num_nodes):
            for j in range(i + 1, self.num_nodes):
                difference = self.restriction_maps[i] @ states[i] - self.restriction_maps[j] @ states[j]
                total_obstruction += float(np.sum(difference**2))
                edge_count += 1
        return total_obstruction / edge_count if edge_count else 0.0


class HJBPmpResourceScheduler:
    """Compute a bounded learning rate from the energy-gated control rule."""

    def __init__(self, energy_cost_coeff: float = 0.05):
        if not math.isfinite(energy_cost_coeff) or energy_cost_coeff <= 0:
            raise ValueError("energy_cost_coeff must be finite and positive")
        self.c_energy = energy_cost_coeff

    def compute_optimal_learning_rate(
        self, loss_gradient: np.ndarray, costate_lambda: float, pef_t: float
    ) -> float:
        gradient = np.asarray(loss_gradient, dtype=float)
        if not np.all(np.isfinite(gradient)):
            raise ValueError("loss_gradient must contain only finite values")
        if not math.isfinite(costate_lambda) or not math.isfinite(pef_t):
            raise ValueError("costate_lambda and pef_t must be finite")
        grad_norm_sq = float(np.sum(gradient**2))
        denominator = 2.0 * self.c_energy * max(pef_t, 0.1)
        return float(np.clip(costate_lambda * grad_norm_sq / denominator, 0.001, 0.5))


class CTMProgramAnchor:
    """Compressed-length complexity barrier for proposed genome updates."""

    def __init__(self, lambda_complexity: float = 0.1):
        if not math.isfinite(lambda_complexity) or lambda_complexity < 0:
            raise ValueError("lambda_complexity must be finite and non-negative")
        self.lambda_comp = lambda_complexity

    def estimate_kolmogorov_complexity(self, genome_str: str) -> float:
        """Approximate complexity as the compressed-to-original length ratio."""
        if not genome_str:
            return 0.0
        compressed = zlib.compress(genome_str.encode("utf-8"))
        return len(compressed) / len(genome_str)

    def apply_quine_anchor(
        self,
        current_genome: str,
        proposed_genome: str,
        loss_val: float,
        proposed_loss_val: Optional[float] = None,
    ) -> Tuple[str, bool]:
        """Accept a proposal only when its loss-plus-complexity objective improves."""
        if not math.isfinite(loss_val):
            raise ValueError("loss_val must be finite")
        proposed_loss = loss_val if proposed_loss_val is None else proposed_loss_val
        if not math.isfinite(proposed_loss):
            raise ValueError("proposed_loss_val must be finite")

        current_objective = loss_val + self.lambda_comp * (
            2.0 ** self.estimate_kolmogorov_complexity(current_genome)
        )
        proposed_objective = proposed_loss + self.lambda_comp * (
            2.0 ** self.estimate_kolmogorov_complexity(proposed_genome)
        )
        if proposed_objective <= current_objective:
            return proposed_genome, True
        return current_genome, False
