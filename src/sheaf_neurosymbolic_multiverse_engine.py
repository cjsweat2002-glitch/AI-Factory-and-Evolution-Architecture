import math
from typing import Dict, List, Tuple

import numpy as np

from src.automorphic_engine_core import HJBPmpResourceScheduler


class PoincareHyperbolicSpace:
    """Poincare-ball geometry for curvature parameter c > 0."""

    def __init__(self, dim: int = 4, curvature: float = 1.0, eps: float = 1e-7):
        if dim < 1:
            raise ValueError("dim must be positive")
        if not math.isfinite(curvature) or curvature <= 0:
            raise ValueError("curvature must be finite and positive")
        if not math.isfinite(eps) or not 0 < eps < 1:
            raise ValueError("eps must be between 0 and 1")
        self.dim = dim
        self.c = float(curvature)
        self.eps = eps
        self.radius = 1.0 / math.sqrt(self.c)

    def _point(self, value: np.ndarray) -> np.ndarray:
        point = np.asarray(value, dtype=float)
        if point.shape != (self.dim,):
            raise ValueError(f"points must have shape ({self.dim},)")
        if not np.all(np.isfinite(point)):
            raise ValueError("points must contain only finite values")
        if float(np.dot(point, point)) >= self.radius**2:
            raise ValueError("point must lie inside the Poincare ball")
        return point

    def mobius_add(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        x = self._point(x)
        y = self._point(y)
        x2, y2 = float(np.dot(x, x)), float(np.dot(y, y))
        xy = float(np.dot(x, y))
        numerator = (1 + 2 * self.c * xy + self.c * y2) * x + (1 - self.c * x2) * y
        denominator = 1 + 2 * self.c * xy + self.c**2 * x2 * y2
        if denominator <= 0:
            raise ArithmeticError("Möbius addition denominator must be positive")
        result = numerator / denominator
        norm = float(np.linalg.norm(result))
        max_norm = self.radius * (1 - self.eps)
        if norm >= max_norm:
            result = result * (max_norm / norm)
        return result

    def hyperbolic_distance(self, x: np.ndarray, y: np.ndarray) -> float:
        x = self._point(x)
        y = self._point(y)
        delta = float(np.linalg.norm(self.mobius_add(-x, y)))
        return float(
            2.0 / math.sqrt(self.c) * math.atanh(min(math.sqrt(self.c) * delta, 1 - self.eps))
        )

    def exp_map(self, x: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Map tangent vector v at x into the open Poincare ball."""
        x = self._point(x)
        vector = np.asarray(v, dtype=float)
        if vector.shape != (self.dim,) or not np.all(np.isfinite(vector)):
            raise ValueError(f"tangent vectors must be finite with shape ({self.dim},)")
        norm = float(np.linalg.norm(vector))
        if norm < self.eps:
            return x.copy()
        lambda_x = 2.0 / (1.0 - self.c * float(np.dot(x, x)))
        tangent = (
            math.tanh(math.sqrt(self.c) * lambda_x * norm / 2.0)
            * vector
            / (math.sqrt(self.c) * norm)
        )
        return self.mobius_add(x, tangent)

    def log_map(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Map point y in the ball to the tangent space at x."""
        x = self._point(x)
        y = self._point(y)
        delta = self.mobius_add(-x, y)
        norm = float(np.linalg.norm(delta))
        if norm < self.eps:
            return np.zeros_like(x)
        lambda_x = 2.0 / (1.0 - self.c * float(np.dot(x, x)))
        scale = (
            2.0
            / (math.sqrt(self.c) * lambda_x)
            * math.atanh(min(math.sqrt(self.c) * norm, 1 - self.eps))
            / norm
        )
        return scale * delta


class CellularSheafNetwork:
    """Finite cellular sheaf over a connected ring-and-spoke graph."""

    def __init__(self, num_nodes: int = 5, node_dim: int = 4, seed: int = 42):
        if num_nodes < 2 or node_dim < 1:
            raise ValueError("num_nodes must be at least 2 and node_dim must be positive")
        self.num_nodes = num_nodes
        self.node_dim = node_dim
        ring = {
            tuple(sorted((i, (i + 1) % num_nodes))) for i in range(num_nodes)
        }
        spokes = {tuple(sorted((0, i))) for i in range(1, num_nodes)}
        self.edges: List[Tuple[int, int]] = sorted(ring | spokes)
        rng = np.random.default_rng(seed)
        self.restriction_maps: Dict[Tuple[int, int], np.ndarray] = {}
        for edge_index, (u, v) in enumerate(self.edges):
            for node in (u, v):
                self.restriction_maps[(node, edge_index)] = (
                    np.eye(node_dim)
                    + 0.05 * rng.standard_normal((node_dim, node_dim))
                )

    def compute_sheaf_laplacian(self) -> np.ndarray:
        dimension = self.num_nodes * self.node_dim
        laplacian = np.zeros((dimension, dimension), dtype=float)
        for edge_index, (u, v) in enumerate(self.edges):
            f_u = self.restriction_maps[(u, edge_index)]
            f_v = self.restriction_maps[(v, edge_index)]
            u_slice = slice(u * self.node_dim, (u + 1) * self.node_dim)
            v_slice = slice(v * self.node_dim, (v + 1) * self.node_dim)
            laplacian[u_slice, u_slice] += f_u.T @ f_u
            laplacian[v_slice, v_slice] += f_v.T @ f_v
            laplacian[u_slice, v_slice] -= f_u.T @ f_v
            laplacian[v_slice, u_slice] -= f_v.T @ f_u
        return laplacian

    def sheaf_obstruction_index(self, global_state: np.ndarray) -> float:
        state = np.asarray(global_state, dtype=float)
        if state.shape != (self.num_nodes, self.node_dim):
            raise ValueError(
                f"global_state must have shape ({self.num_nodes}, {self.node_dim})"
            )
        if not np.all(np.isfinite(state)):
            raise ValueError("global_state must contain only finite values")
        flat_state = state.reshape(-1)
        obstruction = 0.5 * float(flat_state @ self.compute_sheaf_laplacian() @ flat_state)
        return max(obstruction, 0.0)


class CaputoFractionalMemory:
    """L1 discretization of a Caputo derivative over regularly spaced states."""

    def __init__(self, gamma: float = 0.65, dt: float = 0.01):
        if not math.isfinite(gamma) or not 0 < gamma < 1:
            raise ValueError("gamma must be between 0 and 1")
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be finite and positive")
        self.gamma = gamma
        self.dt = dt

    def compute_fractional_derivative(
        self, history_states: List[np.ndarray]
    ) -> np.ndarray:
        if not history_states:
            raise ValueError("history_states must not be empty")
        states = [np.asarray(state, dtype=float) for state in history_states]
        shape = states[0].shape
        if any(state.shape != shape for state in states):
            raise ValueError("all history states must have the same shape")
        if any(not np.all(np.isfinite(state)) for state in states):
            raise ValueError("history states must contain only finite values")
        if len(states) < 2:
            return np.zeros_like(states[-1])

        interval_count = len(states) - 1
        derivative = np.zeros_like(states[-1])
        for interval in range(interval_count):
            age = interval_count - interval
            weight = (
                age ** (1 - self.gamma) - (age - 1) ** (1 - self.gamma)
            ) / math.gamma(2 - self.gamma)
            derivative += weight * (states[interval + 1] - states[interval]) / self.dt**self.gamma
        return derivative


class NeurosymbolicCTMAnchor:
    """Quantized block-complexity estimate and symbolic potential projection."""

    def __init__(self, lambda_ctm: float = 0.1):
        if not math.isfinite(lambda_ctm) or lambda_ctm < 0:
            raise ValueError("lambda_ctm must be finite and non-negative")
        self.lambda_ctm = lambda_ctm

    def bdm_complexity(self, state_vector: np.ndarray) -> float:
        state = np.asarray(state_vector, dtype=float)
        if state.ndim != 1 or state.size == 0 or not np.all(np.isfinite(state)):
            raise ValueError("state_vector must be a non-empty finite vector")
        quantized = np.clip(np.round((state + 1.0) * 7.5), 0, 15).astype(int)
        _, counts = np.unique(quantized, return_counts=True)
        probabilities = counts / counts.sum()
        entropy = -float(np.sum(probabilities * np.log2(probabilities)))
        return entropy * len(quantized) + math.log2(1 + len(counts))

    def apply_symbolic_potential_barrier(
        self, state_vector: np.ndarray, loss: float
    ) -> Tuple[np.ndarray, float, float]:
        state = np.asarray(state_vector, dtype=float)
        if not math.isfinite(loss):
            raise ValueError("loss must be finite")
        complexity = self.bdm_complexity(state)
        barrier = self.lambda_ctm * 2.0 ** (complexity / 10.0)
        quantized_target = np.round(state * 4.0) / 4.0
        anchored_state = state - 0.02 * (state - quantized_target)
        return anchored_state, loss + barrier, complexity


class HJPOptimalControlGate:
    """Bounded HJB-PMP control rate with a configurable positive energy cost."""

    def __init__(self, c_energy: float = 0.04):
        self.scheduler = HJBPmpResourceScheduler(energy_cost_coeff=c_energy)

    @staticmethod
    def primary_energy_factor(hour: float) -> float:
        if not math.isfinite(hour):
            raise ValueError("hour must be finite")
        return 1.2 + 0.8 * math.sin(2.0 * math.pi * hour / 24.0) + 0.3 * math.cos(
            4.0 * math.pi * hour / 24.0
        )

    def compute_optimal_learning_rate(
        self, grad_norm: float, costate_lambda: float, hour: float
    ) -> Tuple[float, float]:
        if not math.isfinite(grad_norm) or grad_norm < 0:
            raise ValueError("grad_norm must be finite and non-negative")
        pef = self.primary_energy_factor(hour)
        if pef <= 0:
            raise ValueError("primary energy factor must be positive")
        eta = self.scheduler.compute_optimal_learning_rate(
            np.array([grad_norm]), costate_lambda, pef
        )
        return eta, pef


class SheafNeurosymbolicMultiverseEngine:
    """Run stable sheaf-diffusion iterations and return metric records."""

    def __init__(
        self,
        num_nodes: int = 5,
        dim: int = 4,
        total_steps: int = 100,
        seed: int = 42,
    ):
        if total_steps < 1:
            raise ValueError("total_steps must be positive")
        self.num_nodes = num_nodes
        self.dim = dim
        self.total_steps = total_steps
        self.seed = seed
        self.poincare = PoincareHyperbolicSpace(dim=dim)
        self.sheaf = CellularSheafNetwork(num_nodes, dim, seed=seed)
        self.caputo = CaputoFractionalMemory(gamma=0.65, dt=0.01)
        self.ctm = NeurosymbolicCTMAnchor(lambda_ctm=0.1)
        self.hjb = HJPOptimalControlGate(c_energy=0.04)

    def run_simulation(self) -> List[Dict[str, float]]:
        rng = np.random.default_rng(self.seed)
        states = rng.normal(0.0, 0.05, size=(self.num_nodes, self.dim))
        states = np.array([self.poincare._point(state) for state in states])
        history = [states.copy()]
        laplacian = self.sheaf.compute_sheaf_laplacian()
        spectral_radius = float(np.linalg.eigvalsh(laplacian).max())
        stable_step = 0.5 / max(spectral_radius, 1e-12)
        costate_lambda = 1.0
        records: List[Dict[str, float]] = []

        for step in range(1, self.total_steps + 1):
            flat_state = states.reshape(-1)
            gradient = (laplacian @ flat_state).reshape(self.num_nodes, self.dim)
            grad_norm = float(np.linalg.norm(gradient))
            obstruction = self.sheaf.sheaf_obstruction_index(states)
            eta_raw, pef = self.hjb.compute_optimal_learning_rate(
                grad_norm, costate_lambda, step % 24
            )
            eta = min(eta_raw, stable_step)
            caputo_derivative = self.caputo.compute_fractional_derivative(history)
            updated = np.empty_like(states)
            for node in range(self.num_nodes):
                tangent = -eta * gradient[node] - 0.002 * caputo_derivative[node]
                updated[node] = self.poincare.exp_map(states[node], tangent)

            complexities = []
            anchored_states = np.empty_like(updated)
            for node in range(self.num_nodes):
                anchored_states[node], _, complexity = self.ctm.apply_symbolic_potential_barrier(
                    updated[node], obstruction
                )
                complexities.append(complexity)
            states = anchored_states
            history.append(states.copy())
            avg_complexity = float(np.mean(complexities))
            quality = math.exp(-obstruction / max(self.num_nodes, 1))
            simulated_value = 10.0 * math.exp(
                0.05 * step * (quality - 0.5)
            )
            costate_lambda = max(0.1, costate_lambda * 0.985 + 0.015 * obstruction)
            records.append(
                {
                    "Generation": float(step),
                    "Sheaf_Obstruction": obstruction,
                    "HJB_Learning_Rate": eta,
                    "Raw_HJB_Learning_Rate": eta_raw,
                    "Primary_Energy_Factor": pef,
                    "Average_BDM_Complexity": avg_complexity,
                    "Neurosymbolic_Quality": quality,
                    "Simulated_Value_Index": simulated_value,
                    "Costate_Lambda": costate_lambda,
                    "D_Positive": 4.0 + 0.5 * math.sin(step / 10.0),
                    "D_Negative": -2.0 - 0.3 * math.cos(step / 12.0),
                    "Poincare_Norm": float(
                        np.mean([np.linalg.norm(state) for state in states])
                    ),
                }
            )
        return records
