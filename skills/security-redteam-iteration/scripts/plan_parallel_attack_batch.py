from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

DEFAULT_SURFACES = [
    "notifications",
    "score_appeals",
    "homework_submissions",
    "bootstrap_first_write",
]


@dataclass
class AttackSlot:
    attack_id: str
    surface: str
    lane: str
    risk: str
    test_anchor: str
    why_this_slot_now: str


def build_slots(surfaces: list[str]) -> list[AttackSlot]:
    pool = list(surfaces or DEFAULT_SURFACES)
    while len(pool) < 4:
        pool.append(DEFAULT_SURFACES[len(pool) % len(DEFAULT_SURFACES)])
    chosen = pool[:4]
    slots: list[AttackSlot] = []
    for index, surface in enumerate(chosen, start=1):
        lane = "backend-pytest"
        test_anchor = "tests/backend/<target>.py"
        risk = "state convergence under concurrent or stale writes"
        why = "nearby repeated flaw class"
        if index == 1:
            lane = "school-playwright-e2e"
            test_anchor = "tests/e2e/web-school/e2e-scenario-resilience.spec.js"
            why = "required browser-backed E2E slot for the batch"
        elif surface == "notifications":
            lane = "behavior-pytest"
            test_anchor = "tests/behavior/test_notification_sync_api_edge_behavior.py"
        elif surface == "score_appeals":
            lane = "backend-pytest"
            test_anchor = "tests/backend/scores/test_score_composition.py"
        elif surface == "homework_submissions":
            lane = "behavior-pytest"
            test_anchor = "tests/behavior/test_course_roster_homework_edge_behavior.py"
        elif surface == "bootstrap_first_write":
            lane = "backend-pytest"
            test_anchor = "tests/backend/e2e_dev/test_demo_course_seed.py"
        slots.append(
            AttackSlot(
                attack_id=f"{index}/4",
                surface=surface,
                lane=lane,
                risk=risk,
                test_anchor=test_anchor,
                why_this_slot_now=why,
            )
        )
    return slots


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit a four-slot red-team attack batch with at least one E2E slot."
    )
    parser.add_argument("--surface", action="append", default=[])
    args = parser.parse_args()
    slots = build_slots(args.surface)
    if not any(slot.lane == "school-playwright-e2e" for slot in slots):
        raise SystemExit("at least one E2E slot is required")
    print(json.dumps([asdict(slot) for slot in slots], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
