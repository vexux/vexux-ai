from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.specialized_agents.planner import DelegationPlanner
from core.contracts.orchestrator import DelegationPlan
from core.specialized_agents.registry import SpecializedAgentRegistry
from core.model_gateway.gateway import ModelGateway


class LLMDelegationPlanner:
    """Delegation planner that can (optionally) ask an LLM for a proposed plan.

    Behavior:
    - If the incoming request already contains 'delegations', delegate to the
      deterministic DelegationPlanner for coercion/validation.
    - If the incoming request lacks 'delegations' and autonomous planning is
      desired, call the provided ModelGateway once to obtain a JSON plan and
      validate it via DelegationPlanner.

    The model is only allowed to propose a bounded number of delegations; this
    class enforces the bound after parsing the model output.
    """

    def __init__(
        self,
        model_gateway: ModelGateway,
        base_planner: Optional[DelegationPlanner] = None,
        specialized_agent_registry: Optional[SpecializedAgentRegistry] = None,
        max_delegations: int = 4,
    ) -> None:
        self.model_gateway = model_gateway
        self.base_planner = base_planner or DelegationPlanner(specialized_agent_registry)
        self.registry = specialized_agent_registry
        self.max_delegations = int(max_delegations or 4)

    def build_plan(self, request: Any) -> DelegationPlan:
        # If client already supplied delegations, reuse deterministic planner
        if isinstance(request, dict) and request.get("delegations"):
            return self.base_planner.build_plan(request)

        # Expect a dict with a top-level query for autonomous planning
        if not isinstance(request, dict):
            raise ValueError("Autonomous delegation requires a dict request with a 'query' field")

        query = request.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Autonomous delegation requires a non-empty 'query' field")

        # Build the model prompt including available agents metadata and a short schema
        agents_meta = []
        if self.registry is not None:
            try:
                agents_meta = self.registry.describe_agents()
            except Exception:
                agents_meta = []

        prompt = self._build_prompt(query, agents_meta, self.max_delegations)

        # Single model call only
        raw = self.model_gateway.generate(prompt, max_new_tokens=800, do_sample=False)

        # Model must return JSON only; parse safely
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"Model returned invalid JSON: {exc}") from exc

        # Normalize to a delegation plan dict shape
        plan_dict = {}
        if isinstance(parsed, dict) and parsed.get("delegations"):
            plan_dict = parsed
        elif isinstance(parsed, dict) and parsed.get("delegations") is None and parsed.get("delegations") != []:
            # allow models that return 'delegations' key but empty
            plan_dict = parsed
        else:
            # If model returns a list of delegations at top level
            if isinstance(parsed, list):
                plan_dict = {"delegations": parsed}
            else:
                raise ValueError("Model JSON must be an object with a 'delegations' list or a list of delegations.")

        delegations = plan_dict.get("delegations") or []
        if not isinstance(delegations, list):
            raise ValueError("Model 'delegations' must be a list.")

        if len(delegations) > self.max_delegations:
            raise ValueError(f"Model proposed {len(delegations)} delegations which exceeds the allowed maximum of {self.max_delegations}.")

        # Let base planner coerce and validate the structured proposal
        plan = self.base_planner.build_plan(plan_dict)
        self.base_planner.validate(plan)
        return plan

    def validate(self, plan: DelegationPlan) -> None:
        # Delegate to base planner validation
        return self.base_planner.validate(plan)

    def supports_autonomous(self) -> bool:
        return True

    @staticmethod
    def _build_prompt(query: str, agents_meta: List[Dict[str, Any]], max_delegations: int) -> str:
        agents_text = json.dumps(agents_meta, indent=2)
        prompt = f"""
You are an assistant that proposes a structured, deterministic multi-agent delegation plan in JSON.

Constraints:
- Return JSON only (no explanations).
- The top-level object must include a 'delegations' key with a list of items.
- Each delegation item must include: id or delegation_id, agent (target_agent), request (query or input), optional depends_on (list of ids).
- Do not include executable code or arbitrary fields. Only the allowed fields are permitted.
- Maximum delegations allowed: {max_delegations}

Available specialized agents metadata:
{agents_text}

User request:
{query}

Produce a JSON object with a 'delegations' list proposing at most {max_delegations} delegations to fulfill the user request. Use short stable ids in the 'id' field (e.g., 'research-1').
"""
        return prompt
