"""
LLM group routing: priority across groups, weighted round-robin + adaptive order within each group.

Used by apps.backend.courseeval_backend.llm_grading to pick endpoints without calling the network; actual HTTP is in _request_grade_from_endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.backend.courseeval_backend.db.models import CourseLLMConfigEndpoint, LLMGroup

# Non-retryable auth: keep order; do not shift to end (same member would fail again).
NON_RETRYABLE_STATUS_CODES = {401, 403}


@dataclass
class _GroupState:
    base_order: list[CourseLLMConfigEndpoint]
    current_order: list[CourseLLMConfigEndpoint]

    @classmethod
    def from_group(cls, group: "LLMGroup") -> Optional["_GroupState"]:
        members = [m for m in (group.members or []) if m is not None]
        if not members:
            return None
        ordered = sorted(members, key=lambda m: (m.priority, m.id))
        return cls(base_order=ordered, current_order=list(ordered))

    def apply_round_robin_start(self, task_id: int) -> None:
        """Rotate member order so different grading tasks start at different presets (task_id % n)."""
        if not self.current_order:
            return
        n = len(self.current_order)
        if n == 0:
            return
        start = int(task_id) % n
        self.current_order = self.current_order[start:] + self.current_order[:start]

    def after_failed_attempt(
        self,
        link: CourseLLMConfigEndpoint,
        exc: Exception,
    ) -> None:
        if not self.current_order:
            return
        if self._should_move_to_end(exc):
            self._move_to_end(link)

    def _move_to_end(self, link: CourseLLMConfigEndpoint) -> None:
        matches = [x for x in self.current_order if x.id == link.id]
        if not matches:
            return
        for m in matches:
            self.current_order.remove(m)
            self.current_order.append(m)

    def remove_member(self, link: CourseLLMConfigEndpoint) -> None:
        self.current_order = [x for x in self.current_order if x.id != link.id]

    @staticmethod
    def _should_move_to_end(exc: Exception) -> bool:
        # Avoid importing apps.backend.courseeval_backend.llm_grading (circular); match by class name.
        name = type(exc).__name__
        if name == "RetryableLLMError":
            return True
        if name == "NonRetryableLLMError":
            text = str(exc)
            for code in NON_RETRYABLE_STATUS_CODES:
                if f"HTTP {code}" in text:
                    return False
            if "鉴权" in text or "权限" in text:
                return False
        return True


@dataclass
class GroupRoutingContext:
    """Holds per-task routing state; safe to use for one _grade_with_endpoint_group call."""

    group_states: list[_GroupState] = field(default_factory=list)
    task_id: int = 0
    _artifact: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(cls, group_rows: list["LLMGroup"], *, task_id: int) -> "GroupRoutingContext":
        states: list[_GroupState] = []
        for g in sorted(group_rows, key=lambda x: (x.priority, x.id)):
            st = _GroupState.from_group(g)
            if st:
                states.append(st)
        if not states:
            return cls(group_states=[], task_id=task_id, _artifact={})
        return cls(group_states=states, task_id=task_id, _artifact={})

    def routing_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "mode": "groups",
            "status": "routing",
            "task_id": self.task_id,
            "groups": [
                {
                    "group_id": g.base_order[0].group_id if g.base_order else None,
                    "order_preset_ids": [m.preset_id for m in g.current_order],
                }
                for g in self.group_states
            ],
        }

    def build_artifact(self) -> dict[str, Any]:
        return {"llm_routing": self.routing_payload()}

    def note_failure(self, group_state: _GroupState, link: CourseLLMConfigEndpoint, exc: Exception) -> None:
        group_state.after_failed_attempt(link, exc)
