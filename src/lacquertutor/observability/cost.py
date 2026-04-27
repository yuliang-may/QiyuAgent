"""Token counting and cost estimation per model.

Provides approximate cost tracking for LLM calls within a session.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Approximate pricing per 1M tokens (USD) — DashScope Qwen models
# Update these as pricing changes
MODEL_PRICING = {
    "qwen-plus": {"input": 0.8, "output": 2.0},
    "qwen3.5-plus": {"input": 1.0, "output": 3.0},
    "qwen-max": {"input": 2.0, "output": 6.0},
    "text-embedding-v3": {"input": 0.35, "output": 0.0},
    "gte-rerank": {"input": 0.5, "output": 0.0},
}


@dataclass
class CostTracker:
    """Tracks approximate token usage and cost per session."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    cost_limit_usd: float = 5.0
    call_count: int = 0
    _model_breakdown: dict[str, dict] = field(default_factory=dict)

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record token usage for a single LLM call."""
        pricing = MODEL_PRICING.get(model, {"input": 1.0, "output": 3.0})
        cost = (
            input_tokens * pricing["input"] / 1_000_000
            + output_tokens * pricing["output"] / 1_000_000
        )

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost
        self.call_count += 1

        if model not in self._model_breakdown:
            self._model_breakdown[model] = {"input": 0, "output": 0, "cost": 0.0, "calls": 0}
        self._model_breakdown[model]["input"] += input_tokens
        self._model_breakdown[model]["output"] += output_tokens
        self._model_breakdown[model]["cost"] += cost
        self._model_breakdown[model]["calls"] += 1

    @property
    def is_over_budget(self) -> bool:
        """Check if the session has exceeded its cost limit."""
        return self.total_cost_usd > self.cost_limit_usd

    @property
    def remaining_budget(self) -> float:
        return max(0.0, self.cost_limit_usd - self.total_cost_usd)

    def summary(self) -> dict:
        """Return a summary of cost tracking."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cost_limit_usd": self.cost_limit_usd,
            "remaining_usd": round(self.remaining_budget, 4),
            "call_count": self.call_count,
            "model_breakdown": self._model_breakdown,
        }
