import copy
import hashlib
import json
import math
from typing import Any, Dict, List

import numpy as np

from src.automorphic_engine_core import (
    CTMProgramAnchor,
    CaputoFractionalMemory,
    HJBPmpResourceScheduler,
    HyperbolicSheafLaplacian,
    PoincareHyperbolicSpace,
)


class BrandEntity:
    """Brand state and generated product artifacts for one factory run."""

    def __init__(self, brand_id: str, name: str, core_mission: str):
        if not brand_id.strip() or not name.strip() or not core_mission.strip():
            raise ValueError("brand_id, name, and core_mission must not be empty")
        self.brand_id = brand_id
        self.name = name
        self.core_mission = core_mission
        self.generation = 0
        seed = int.from_bytes(hashlib.sha256(brand_id.encode("utf-8")).digest()[:8], "big")
        self.vector_h4 = np.random.default_rng(seed).uniform(-0.2, 0.2, size=4)
        self.value_proposition = "AI-Driven Hyperdimensional Product Synthesis"
        self.products: List[Dict[str, Any]] = []
        self.campaign_narratives: List[str] = []
        self.code_artifacts: Dict[str, str] = {}
        self.quality_score = 0.85
        self.sheaf_obstruction = 0.25
        self.simulated_net_worth = 10.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brand_id": self.brand_id,
            "name": self.name,
            "generation": self.generation,
            "core_mission": self.core_mission,
            "value_proposition": self.value_proposition,
            "vector_h4": self.vector_h4.tolist(),
            "quality_score": round(self.quality_score, 4),
            "sheaf_obstruction": round(self.sheaf_obstruction, 6),
            "simulated_net_worth": round(self.simulated_net_worth, 4),
            "products_count": len(self.products),
            "products": self.products,
            "campaign_narratives": self.campaign_narratives,
            "code_artifacts_keys": sorted(self.code_artifacts),
        }

    def to_json_str(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


class WorkerAgent:
    """Base type for workers that update a brand entity."""

    def __init__(self, agent_id: str, role: str):
        self.agent_id = agent_id
        self.role = role

    def process(
        self,
        brand: BrandEntity,
        input_signal: Dict[str, Any],
        engine_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        raise NotImplementedError


class BrandArchitectWorker(WorkerAgent):
    """Update brand positioning and its H^4 embedding from the current signal."""

    def __init__(self):
        super().__init__("worker_architect", "Brand Architecture & Strategy")

    def process(
        self,
        brand: BrandEntity,
        input_signal: Dict[str, Any],
        engine_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        market_demand = input_signal.get("market_demand", "high_efficiency_sustainability")
        if not isinstance(market_demand, str) or not market_demand.strip():
            raise ValueError("market_demand must be a non-empty string")
        tangent = engine_params["eta"] * engine_params["demand_gradient"]
        tangent -= 0.05 * engine_params["memory_derivative"]
        space = PoincareHyperbolicSpace()
        brand.vector_h4 = space.mobius_add(
            brand.vector_h4, space.exp_map0(tangent)
        )
        brand.value_proposition = (
            f"Automorphic {brand.name} - Next-Gen {market_demand.replace('_', ' ').title()} Engine"
        )
        narrative = (
            f"Gen {brand.generation}: Unifying {market_demand} with "
            "CTM-anchored autopoietic intelligence."
        )
        brand.campaign_narratives.append(narrative)
        return {
            "status": "success",
            "updated_value_prop": brand.value_proposition,
            "narrative": narrative,
        }


class ProductSynthesizerWorker(WorkerAgent):
    """Add a product concept with explicitly illustrative estimates."""

    def __init__(self):
        super().__init__("worker_synthesizer", "Autonomous Product Synthesis")

    def process(
        self,
        brand: BrandEntity,
        input_signal: Dict[str, Any],
        engine_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        target_audience = input_signal.get(
            "target_audience", "Autonomous AI Agents & Enterprise Engineers"
        )
        if not isinstance(target_audience, str) or not target_audience.strip():
            raise ValueError("target_audience must be a non-empty string")
        product = {
            "product_id": f"PROD-{brand.generation:03d}",
            "name": f"{brand.name} Core-X Module v{brand.generation}.0",
            "category": "Autonomous Software/Hardware Artifact",
            "target_audience": target_audience,
            "specifications": {
                "h4_embedding": brand.vector_h4.tolist(),
                "throughput_tokens_per_sec_estimate": 10000
                * (1 + 0.15 * (brand.generation - 1)),
                "energy_efficiency_pef_estimate": max(
                    1.1, 2.5 - 0.2 * (brand.generation - 1)
                ),
                "ctm_complexity_estimate": round(
                    0.45 + 0.02 * (brand.generation - 1), 4
                ),
            },
            "features": [
                "Zero-copy SoA memory layout",
                "HJB-PMP real-time costate resource throttling",
                "Self-healing CTM quine anchor",
            ],
        }
        brand.products.append(product)
        return {"status": "success", "new_product": product}


class MarketResonanceEvaluatorWorker(WorkerAgent):
    """Evaluate synthetic consensus, quality, and valuation metrics."""

    def __init__(self):
        super().__init__("worker_evaluator", "Synthetic Market Resonance & Sheaf Consensus")
        self.sheaf = HyperbolicSheafLaplacian()
        self.ctm_anchor = CTMProgramAnchor()

    def process(
        self,
        brand: BrandEntity,
        input_signal: Dict[str, Any],
        engine_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        offsets = (
            np.array([0.01, -0.01, 0.02, 0.00]),
            np.array([-0.02, 0.01, 0.00, 0.01]),
            np.array([0.00, 0.02, -0.01, -0.01]),
        )
        node_states = [brand.vector_h4] + [
            brand.vector_h4 + offset for offset in offsets
        ]
        brand.sheaf_obstruction = self.sheaf.compute_sheaf_obstruction(node_states)
        complexity = self.ctm_anchor.estimate_kolmogorov_complexity(brand.to_json_str())
        brand.quality_score = min(
            0.99, max(0.5, 1.0 - 1.2 * brand.sheaf_obstruction + 0.1 * (1.0 - complexity))
        )
        brand.simulated_net_worth *= math.exp(0.05 * brand.quality_score)
        return {
            "status": "success",
            "quality_score": brand.quality_score,
            "sheaf_obstruction": brand.sheaf_obstruction,
            "simulated_net_worth": brand.simulated_net_worth,
        }


class AutopoieticCodeMutatorWorker(WorkerAgent):
    """Create reviewable Python examples; never executes them."""

    def __init__(self):
        super().__init__("worker_code_mutator", "Autopoietic Code & Workflow Generation")

    def process(
        self,
        brand: BrandEntity,
        input_signal: Dict[str, Any],
        engine_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        script_key = f"auto_brand_pipeline_gen{brand.generation}.py"
        script_content = (
            "# Generated illustrative pipeline metadata; not executed by the factory.\n"
            "import json\n\n"
            f"BRAND_ID = {json.dumps(brand.brand_id)}\n"
            f"BRAND_NAME = {json.dumps(brand.name)}\n"
            f"GENERATION = {brand.generation}\n"
            f"QUALITY_SCORE = {brand.quality_score:.4f}\n\n"
            "def execute_branding_task():\n"
            "    print(f'Brand rollout for {BRAND_NAME} (Gen {GENERATION})')\n"
            "    print(f'Target quality metric: {QUALITY_SCORE}')\n\n"
            "if __name__ == '__main__':\n"
            "    execute_branding_task()\n"
        )
        brand.code_artifacts[script_key] = script_content
        return {"status": "success", "generated_script_key": script_key}


class AutonomousBrandEngine:
    """Run deterministic, bounded brand-evolution iterations."""

    def __init__(
        self,
        brand_name: str = "Plantable-AI",
        brand_id: str = "BRAND-001",
        core_mission: str = "Autopoietic Self-Evolving AI Products",
    ):
        self.brand = BrandEntity(brand_id, brand_name, core_mission)
        self.architect = BrandArchitectWorker()
        self.synthesizer = ProductSynthesizerWorker()
        self.evaluator = MarketResonanceEvaluatorWorker()
        self.mutator = AutopoieticCodeMutatorWorker()
        self.memory = CaputoFractionalMemory()
        self.hjb_scheduler = HJBPmpResourceScheduler()
        self.ctm_anchor = CTMProgramAnchor()
        self.memory.push(self.brand.vector_h4)

    def run_successive_iteration(
        self, input_signal: Dict[str, Any], pef_t: float = 1.2
    ) -> Dict[str, Any]:
        if not isinstance(input_signal, dict):
            raise ValueError("input_signal must be a dictionary")
        if not math.isfinite(pef_t) or pef_t <= 0:
            raise ValueError("pef_t must be finite and positive")

        market_demand = input_signal.get("market_demand", "high_efficiency_sustainability")
        if not isinstance(market_demand, str) or not market_demand.strip():
            raise ValueError("market_demand must be a non-empty string")
        demand_seed = int.from_bytes(
            hashlib.sha256(market_demand.encode("utf-8")).digest()[:8], "big"
        )
        demand_gradient = (
            np.random.default_rng(demand_seed).uniform(-0.1, 0.1, size=4)
            - self.brand.vector_h4
        )
        memory_derivative = self.memory.compute_fractional_derivative(
            self.brand.vector_h4
        )
        eta = self.hjb_scheduler.compute_optimal_learning_rate(
            demand_gradient, costate_lambda=1.1, pef_t=pef_t
        )
        snapshot = copy.deepcopy(self.brand)
        previous_genome = self.brand.to_json_str()
        previous_obstruction = self.brand.sheaf_obstruction
        self.brand.generation += 1
        engine_params = {
            "eta": eta,
            "pef_t": pef_t,
            "demand_gradient": demand_gradient,
            "memory_derivative": memory_derivative,
        }

        architect_result = self.architect.process(self.brand, input_signal, engine_params)
        synthesizer_result = self.synthesizer.process(
            self.brand, input_signal, engine_params
        )
        evaluator_result = self.evaluator.process(
            self.brand, input_signal, engine_params
        )
        mutator_result = self.mutator.process(self.brand, input_signal, engine_params)

        candidate_genome = self.brand.to_json_str()
        anchored_genome, accepted = self.ctm_anchor.apply_quine_anchor(
            previous_genome,
            candidate_genome,
            loss_val=previous_obstruction,
            proposed_loss_val=self.brand.sheaf_obstruction,
        )
        if not accepted:
            self.brand = snapshot
            return {
                "generation": self.brand.generation,
                "eta_t": eta,
                "accepted_by_ctm": False,
                "brand_summary": self.brand.to_dict(),
                "worker_results": {},
            }

        self.memory.push(self.brand.vector_h4)
        return {
            "generation": self.brand.generation,
            "eta_t": eta,
            "accepted_by_ctm": True,
            "anchored_genome": anchored_genome,
            "brand_summary": self.brand.to_dict(),
            "worker_results": {
                "architect": architect_result,
                "synthesizer": synthesizer_result,
                "evaluator": evaluator_result,
                "code_mutator": mutator_result,
            },
        }
