"""Recommend validation targets from changed repository paths.

This is a conservative first-version selector. It does not run tests and it
does not edit the test execution ledger. It reads changed paths from `git diff`
or from explicit `--paths`, matches them against the machine-readable registry
in `tests/TEST_SELECTION_TARGETS.json`, and emits a reviewable recommendation.

Examples:

    python ops/scripts/dev/select_validation_targets.py
    python ops/scripts/dev/select_validation_targets.py --base origin/main
    python ops/scripts/dev/select_validation_targets.py --base origin/main --head HEAD --json
    python ops/scripts/dev/select_validation_targets.py --staged
    python ops/scripts/dev/select_validation_targets.py --paths apps/backend/courseeval_backend/api/routers/learning_notes.py
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from validation_history import (
    DEFAULT_HISTORY,
    changed_paths_signature,
    latest_records_by_target,
    load_history_entries,
)


DEFAULT_REGISTRY = "tests/TEST_SELECTION_TARGETS.json"
DEFAULT_LEDGER = "docs/testing/test-execution-targets.csv"
DEFAULT_HIGH_RISK_METADATA = "docs/governance/high-risk-path-metadata.json"
RISK_ORDER = {
    "static": 0,
    "targeted": 1,
    "broad": 2,
    "full": 3,
}
DEFAULT_POLICY_REQUIREMENT_BY_CATEGORY = {
    "static-check": "required",
    "backend-pytest": "required",
    "behavior-pytest": "required",
    "frontend-build": "required",
    "frontend-node-test": "required",
    "security-pytest": "required-review",
    "postgres-pytest": "required-review",
    "school-playwright": "recommended",
    "parent-playwright": "recommended",
    "full-suite": "required-review",
}


@dataclass(frozen=True)
class ChangedPath:
    path: str
    status: str = "M"


@dataclass
class Recommendation:
    target: dict[str, Any]
    reasons: list[str] = field(default_factory=list)
    matched_paths: list[str] = field(default_factory=list)
    source_rules: list[str] = field(default_factory=list)
    ledger: dict[str, str] | None = None
    structured_history: dict[str, Any] | None = None
    history_status: str = "unknown"
    history_reason: str = "history was not evaluated"

    @property
    def target_id(self) -> str:
        return str(self.target["id"])

    @property
    def risk(self) -> str:
        return str(self.target.get("risk", "targeted"))

    @property
    def policy_requirement(self) -> str:
        category = str(self.target.get("category", ""))
        return str(
            self.target.get("policy_requirement")
            or DEFAULT_POLICY_REQUIREMENT_BY_CATEGORY.get(category, "recommended")
        )

    @property
    def policy_class(self) -> str:
        return str(self.target.get("policy_class") or self.target.get("category") or "unknown")


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def current_upstream(repo_root: Path) -> str | None:
    try:
        value = run_git(repo_root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return value or None


def git_changed_paths(repo_root: Path, base: str | None, head: str, staged: bool) -> list[ChangedPath]:
    if staged:
        args = ["diff", "--cached", "--name-status", "--no-renames"]
    elif base == "__WORKTREE__":
        args = ["diff", "--name-status", "--no-renames"]
    else:
        resolved_base = base or current_upstream(repo_root)
        if resolved_base:
            args = ["diff", "--name-status", "--no-renames", f"{resolved_base}...{head}"]
        else:
            args = ["diff", "--name-status", "--no-renames", head]

    output = run_git(repo_root, args)
    paths: list[ChangedPath] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) == 1:
            paths.append(ChangedPath(path=normalize_path(parts[0]), status="M"))
        elif len(parts) >= 2:
            paths.append(ChangedPath(path=normalize_path(parts[-1]), status=parts[0]))
    return paths


def git_untracked_paths(repo_root: Path) -> list[ChangedPath]:
    output = run_git(repo_root, ["ls-files", "--others", "--exclude-standard"])
    return [
        ChangedPath(path=normalize_path(line), status="??")
        for line in output.splitlines()
        if line.strip()
    ]


def merge_changed_paths(paths: list[ChangedPath]) -> list[ChangedPath]:
    merged: dict[str, ChangedPath] = {}
    for item in paths:
        merged[item.path] = item
    return list(merged.values())


def load_registry(repo_root: Path, registry_path: str) -> dict[str, Any]:
    path = repo_root / registry_path
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    target_ids = [target.get("id") for target in data.get("targets", [])]
    duplicate_ids = sorted({item for item in target_ids if target_ids.count(item) > 1})
    if duplicate_ids:
        raise ValueError(f"duplicate target id(s) in {registry_path}: {', '.join(duplicate_ids)}")
    return data


def load_high_risk_path_metadata(repo_root: Path, metadata_path: str) -> list[dict[str, Any]]:
    path = repo_root / metadata_path
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = payload.get("paths", [])
    return rows if isinstance(rows, list) else []


def parse_ledger(repo_root: Path, ledger_path: str) -> dict[str, dict[str, str]]:
    path = repo_root / ledger_path
    if not path.exists():
        return {}

    if path.suffix.lower() == ".csv":
        entries: dict[str, dict[str, str]] = {}
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                test_id = str(row.get("test_id") or "").strip()
                if not test_id:
                    continue
                entries[test_id] = {
                    "last_branch": str(row.get("last_branch") or "").strip(),
                    "last_commit": str(row.get("last_commit") or "").strip(),
                    "last_result": str(row.get("last_result") or "").strip(),
                    "last_run_date": str(row.get("last_run_date") or "").strip(),
                    "pass_count": str(row.get("pass_count") or "").strip(),
                    "run_count": str(row.get("run_count") or "").strip(),
                }
        return entries

    text = path.read_text(encoding="utf-8")
    entries: dict[str, dict[str, str]] = {}
    current_id: str | None = None

    heading_re = re.compile(r"^### Test ID: `([^`]+)`\s*$")
    field_re = re.compile(r"^\*\*(Last branch|Last commit|Last result|Last run date|Pass count|Run count):\*\* `?([^`\n]+)`?\s*$")

    for line in text.splitlines():
        heading_match = heading_re.match(line)
        if heading_match:
            current_id = heading_match.group(1)
            entries[current_id] = {}
            continue

        if current_id is None:
            continue

        field_match = field_re.match(line)
        if field_match:
            key = field_match.group(1).lower().replace(" ", "_")
            entries[current_id][key] = field_match.group(2).strip()

    return entries


def path_matches_pattern(path: str, pattern: str) -> bool:
    path = normalize_path(path)
    pattern = normalize_path(pattern)
    if pattern.endswith("/"):
        return path == pattern.rstrip("/") or path.startswith(pattern)
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatchcase(path, pattern)
    return path == pattern


def path_matches_any(path: str, patterns: list[str]) -> bool:
    return any(path_matches_pattern(path, pattern) for pattern in patterns)


def match_target(target: dict[str, Any], changed_paths: list[ChangedPath]) -> tuple[list[str], list[str]]:
    patterns = target_trigger_patterns(target)
    matched: list[str] = []
    reasons: list[str] = []
    for changed in changed_paths:
        for pattern in patterns:
            if path_matches_pattern(changed.path, pattern):
                matched.append(changed.path)
                reasons.append(f"{changed.path} matched {pattern}")
                break
    return sorted(set(matched)), reasons


def target_trigger_patterns(target: dict[str, Any]) -> list[str]:
    triggers = target.get("triggers", {})
    return list(triggers.get("paths", [])) + list(triggers.get("globs", []))


def assess_history_status(item: Recommendation, changed_paths: list[ChangedPath]) -> tuple[str, str]:
    if item.structured_history is not None:
        result = str(item.structured_history.get("result") or "").strip().lower()
        failure_class = item.structured_history.get("failure_class")
        ended_at = item.structured_history.get("ended_at", "unknown time")
        current_signature = changed_paths_signature(
            [{"status": changed.status, "path": changed.path} for changed in changed_paths]
        )
        history_signature = str(item.structured_history.get("changed_paths_signature") or "")
        if history_signature and history_signature != current_signature:
            return "stale", f"latest structured run at {ended_at} covered a different changed-path snapshot"
        if result == "passed":
            return "fresh", f"latest structured run passed at {ended_at}"
        if result == "skipped":
            return "unknown", f"latest structured run was dry-run/skipped at {ended_at}"
        if result == "blocked":
            class_note = f" ({failure_class})" if failure_class else ""
            return "blocked", f"latest structured run was blocked{class_note} at {ended_at}"
        if result:
            return "stale", f"latest structured run result is `{result}` at {ended_at}"

    if item.ledger is None:
        if item.target.get("ledger_id"):
            return "not-recorded", "target has a ledger_id but no parsed ledger entry was found"
        return "not-recorded", "target has no ledger_id yet"

    last_result = (item.ledger.get("last_result") or "").strip().lower()
    if last_result and last_result != "passed":
        return "stale", f"last recorded result is `{last_result}`, not passing evidence"

    patterns = target_trigger_patterns(item.target)
    trigger_matches = [
        changed.path
        for changed in changed_paths
        if any(path_matches_pattern(changed.path, pattern) for pattern in patterns)
    ]
    if trigger_matches:
        return "stale", "target trigger changed in current diff"

    if item.source_rules:
        return "stale", f"target was recommended by fallback rule(s): {', '.join(item.source_rules)}"

    if not last_result:
        return "unknown", "ledger entry did not include a last result"

    return "fresh", "last recorded passing result is not invalidated by direct target triggers"


def is_product_source_path(path: str) -> bool:
    normalized = normalize_path(path)
    product_patterns = [
        "apps/backend/courseeval_backend/*.py",
        "apps/backend/courseeval_backend/**/*.py",
        "apps/web/school/src/**",
        "apps/web/parent/src/**",
        "apps/web/school/package.json",
        "apps/web/school/package-lock.json",
        "apps/web/school/vite.config.js",
        "apps/web/school/playwright.config.cjs",
        "apps/web/parent/package.json",
        "apps/web/parent/package-lock.json",
        "apps/web/parent/vite.config.js",
    ]
    return path_matches_any(normalized, product_patterns)


def build_non_full_validation_summary(
    recommendations: list[Recommendation],
    unmatched: list[str],
    changed_paths: list[ChangedPath],
) -> dict[str, Any]:
    if not changed_paths:
        return {
            "status": "acceptable",
            "reason": "no changed paths were detected",
            "blocking_reasons": [],
            "review_reasons": [],
        }

    blocking_reasons: list[str] = []
    review_reasons: list[str] = []

    unmatched_product_paths = [path for path in unmatched if is_product_source_path(path)]
    if unmatched_product_paths:
        blocking_reasons.append(
            "unmatched product source path(s): " + ", ".join(f"`{path}`" for path in unmatched_product_paths)
        )

    full_targets = [item.target_id for item in recommendations if item.risk == "full"]
    if full_targets:
        blocking_reasons.append("full validation target(s) recommended: " + ", ".join(f"`{target}`" for target in full_targets))

    broad_targets = [item.target_id for item in recommendations if item.risk == "broad"]
    if broad_targets:
        review_reasons.append("broad validation target(s) recommended: " + ", ".join(f"`{target}`" for target in broad_targets))

    blocked_history_targets = [
        f"`{item.target_id}`: {item.history_reason}"
        for item in recommendations
        if item.history_status == "blocked"
    ]
    if blocked_history_targets:
        review_reasons.append("target(s) have blocked latest structured run: " + "; ".join(blocked_history_targets))

    review_targets = [
        f"`{item.target_id}`: {item.target.get('requires_review_reason')}"
        for item in recommendations
        if item.target.get("requires_review_reason")
    ]
    if review_targets:
        review_reasons.append("target(s) require operator review: " + "; ".join(review_targets))

    unmatched_non_product = [path for path in unmatched if path not in unmatched_product_paths]
    if unmatched_non_product:
        review_reasons.append("unmatched non-product path(s): " + ", ".join(f"`{path}`" for path in unmatched_non_product))

    if not recommendations:
        review_reasons.append("no validation targets were selected")

    if blocking_reasons:
        status = "not_sufficient"
        reason = blocking_reasons[0]
    elif review_reasons:
        status = "needs_review"
        reason = review_reasons[0]
    else:
        status = "acceptable"
        reason = "only static or targeted validation was recommended; run the recommended targets before claiming coverage"

    return {
        "status": status,
        "reason": reason,
        "blocking_reasons": blocking_reasons,
        "review_reasons": review_reasons,
    }


def build_required_validation_summary(recommendations: list[Recommendation]) -> dict[str, Any]:
    def serialize(items: list[Recommendation]) -> list[dict[str, Any]]:
        return [
            {
                "id": item.target_id,
                "category": item.target.get("category"),
                "risk": item.risk,
                "policy_requirement": item.policy_requirement,
                "policy_class": item.policy_class,
                "requires_review_reason": item.target.get("requires_review_reason"),
                "matched_paths": item.matched_paths,
                "reasons": item.reasons,
            }
            for item in items
        ]

    required_targets = [item for item in recommendations if item.policy_requirement == "required"]
    required_review_targets = [item for item in recommendations if item.policy_requirement == "required-review"]
    optional_targets = [item for item in recommendations if item.policy_requirement == "recommended"]

    if required_review_targets:
        status = "review_required"
        reason = "review-required validation target(s) were selected for this diff"
    elif required_targets:
        status = "auto_runnable_required"
        reason = "auto-runnable required validation target(s) were selected for this diff"
    else:
        status = "no_required_targets"
        reason = "the current diff selected only recommended validation targets"

    required_policy_classes = sorted({item.policy_class for item in [*required_targets, *required_review_targets]})

    return {
        "status": status,
        "reason": reason,
        "required_policy_classes": required_policy_classes,
        "required_targets": serialize(required_targets),
        "required_review_targets": serialize(required_review_targets),
        "optional_targets": serialize(optional_targets),
    }


def ensure_recommendation(
    recommendations: dict[str, Recommendation],
    target_by_id: dict[str, dict[str, Any]],
    target_id: str,
    reason: str,
    matched_paths: list[str] | None = None,
    source_rule: str | None = None,
) -> None:
    target = target_by_id.get(target_id)
    if target is None:
        raise ValueError(f"fallback references unknown target id: {target_id}")
    item = recommendations.setdefault(target_id, Recommendation(target=target))
    item.reasons.append(reason)
    if matched_paths:
        item.matched_paths.extend(matched_paths)
    if source_rule:
        item.source_rules.append(source_rule)


def apply_fallback_rules(
    registry: dict[str, Any],
    changed_paths: list[ChangedPath],
    recommendations: dict[str, Recommendation],
    target_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    notes: list[str] = []
    path_values = [item.path for item in changed_paths]
    already_matched_paths: set[str] = set()
    for item in recommendations.values():
        already_matched_paths.update(normalize_path(path) for path in item.matched_paths)

    for rule in registry.get("fallback_rules", []):
        rule_id = str(rule.get("id", "<unnamed-rule>"))
        unless_target_ids = set(str(item) for item in rule.get("unless_recommended_targets", []))
        if unless_target_ids and any(target_id in recommendations for target_id in unless_target_ids):
            continue
        unless_categories = set(str(item) for item in rule.get("unless_recommended_categories", []))
        if unless_categories and any(
            str(item.target.get("category")) in unless_categories for item in recommendations.values()
        ):
            continue

        matched_paths: list[str] = []
        rule_applies = False

        all_patterns = list(rule.get("if_all_paths_match", []))
        if all_patterns and path_values:
            rule_applies = all(path_matches_any(path, all_patterns) for path in path_values)
            if rule_applies:
                matched_paths = path_values

        any_patterns = list(rule.get("if_any_path_matches", []))
        if any_patterns:
            any_matches = [path for path in path_values if path_matches_any(path, any_patterns)]
            if any_matches:
                rule_applies = True
                matched_paths.extend(any_matches)

        unmatched_any_patterns = list(rule.get("if_any_unmatched_path_matches", []))
        if unmatched_any_patterns:
            unmatched_values = [path for path in path_values if normalize_path(path) not in already_matched_paths]
            unmatched_matches = [path for path in unmatched_values if path_matches_any(path, unmatched_any_patterns)]
            if unmatched_matches:
                rule_applies = True
                matched_paths.extend(unmatched_matches)

        if not rule_applies:
            continue

        notes.append(f"Fallback rule {rule_id}: {rule.get('description', '').strip()}")
        for target_id in rule.get("recommend", []):
            ensure_recommendation(
                recommendations,
                target_by_id,
                str(target_id),
                f"fallback {rule_id}: {rule.get('description', '').strip()}",
                matched_paths=sorted(set(matched_paths)),
                source_rule=rule_id,
            )
    return notes


def classify_unmatched(changed_paths: list[ChangedPath], recommendations: dict[str, Recommendation]) -> list[str]:
    matched_paths: set[str] = set()
    for item in recommendations.values():
        matched_paths.update(normalize_path(path) for path in item.matched_paths)
    return [changed.path for changed in changed_paths if changed.path not in matched_paths]


def select_targets(
    registry: dict[str, Any],
    changed_paths: list[ChangedPath],
    ledger_entries: dict[str, dict[str, str]],
    structured_history: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Recommendation], list[str], list[str]]:
    targets = list(registry.get("targets", []))
    target_by_id = {str(target["id"]): target for target in targets}
    recommendations: dict[str, Recommendation] = {}

    for target in targets:
        matched_paths, reasons = match_target(target, changed_paths)
        if not matched_paths:
            continue
        item = recommendations.setdefault(str(target["id"]), Recommendation(target=target))
        item.matched_paths.extend(matched_paths)
        item.reasons.extend(reasons)

    notes = apply_fallback_rules(registry, changed_paths, recommendations, target_by_id)
    unmatched = classify_unmatched(changed_paths, recommendations)

    ordered = sorted(
        recommendations.values(),
        key=lambda item: (RISK_ORDER.get(item.risk, 99), item.target_id),
    )
    for item in ordered:
        item.matched_paths = sorted(set(item.matched_paths))
        item.reasons = sorted(set(reason for reason in item.reasons if reason))
        item.source_rules = sorted(set(item.source_rules))
        ledger_id = item.target.get("ledger_id")
        if ledger_id:
            item.ledger = ledger_entries.get(str(ledger_id))
        if structured_history:
            item.structured_history = structured_history.get(item.target_id)
        item.history_status, item.history_reason = assess_history_status(item, changed_paths)
    return ordered, unmatched, notes


def command_to_string(command: dict[str, Any]) -> str:
    return " ".join(str(part) for part in command.get("argv", []))


def build_json_result(
    registry: dict[str, Any],
    changed_paths: list[ChangedPath],
    recommendations: list[Recommendation],
    unmatched: list[str],
    notes: list[str],
    matched_high_risk_metadata: list[dict[str, Any]],
) -> dict[str, Any]:
    non_full_summary = build_non_full_validation_summary(recommendations, unmatched, changed_paths)
    required_validation = build_required_validation_summary(recommendations)
    return {
        "registry_version": registry.get("version"),
        "selection_policy": registry.get("defaults", {}).get("selection_policy"),
        "non_full_validation": non_full_summary,
        "required_validation": required_validation,
        "changed_paths": [{"status": item.status, "path": item.path} for item in changed_paths],
        "matched_high_risk_paths": matched_high_risk_metadata,
        "recommendations": [
            {
                "id": item.target_id,
                "category": item.target.get("category"),
                "risk": item.risk,
                "policy_requirement": item.policy_requirement,
                "policy_class": item.policy_class,
                "description": item.target.get("description"),
                "working_directory": item.target.get("working_directory"),
                "commands": item.target.get("commands", []),
                "requires_review_reason": item.target.get("requires_review_reason"),
                "coverage_tags": item.target.get("coverage_tags", []),
                "risk_escalation": item.target.get("risk_escalation"),
                "matched_paths": item.matched_paths,
                "reasons": item.reasons,
                "source_rules": item.source_rules,
                "ledger_id": item.target.get("ledger_id"),
                "ledger": item.ledger,
                "structured_history": item.structured_history,
                "history_status": item.history_status,
                "history_reason": item.history_reason,
                "notes": item.target.get("notes"),
            }
            for item in recommendations
        ],
        "unmatched_paths": unmatched,
        "notes": notes,
        "ledger_snippet_template": [
            {
                "target_id": item.target_id,
                "result": "<passed|failed|blocked|timed out|interrupted|skipped>",
                "summary": "<observed output summary>",
                "notes": "<environment/product/orchestrator notes with private paths redacted>",
            }
            for item in recommendations
        ],
    }


def render_markdown(
    registry: dict[str, Any],
    changed_paths: list[ChangedPath],
    recommendations: list[Recommendation],
    unmatched: list[str],
    notes: list[str],
    matched_high_risk_metadata: list[dict[str, Any]],
) -> str:
    non_full_summary = build_non_full_validation_summary(recommendations, unmatched, changed_paths)
    required_validation = build_required_validation_summary(recommendations)
    lines: list[str] = []
    lines.append("# Validation Target Recommendation")
    lines.append("")
    lines.append(f"Registry version: `{registry.get('version')}`")
    lines.append(f"Selection policy: `{registry.get('defaults', {}).get('selection_policy', 'unknown')}`")
    lines.append(f"Non-full validation status: `{non_full_summary['status']}`")
    lines.append(f"Non-full validation reason: {non_full_summary['reason']}")
    lines.append(f"Required validation status: `{required_validation['status']}`")
    lines.append(f"Required validation reason: {required_validation['reason']}")
    lines.append("")

    lines.append("## High-Risk Path Metadata")
    lines.append("")
    if matched_high_risk_metadata:
        for item in matched_high_risk_metadata:
            families = ", ".join(f"`{value}`" for value in item.get("required_validation_families", []))
            lines.append(
                f"- `{item['path']}` owner=`{item['owner_area']}` risk=`{item['risk_class']}` migration=`{item['migration_sensitivity']}` required-families={families}"
            )
    else:
        lines.append("- No committed high-risk path metadata matched the current diff.")
    lines.append("")

    lines.append("## Changed Paths")
    lines.append("")
    if changed_paths:
        for item in changed_paths:
            lines.append(f"- `{item.status}` `{item.path}`")
    else:
        lines.append("- No changed paths were detected.")
    lines.append("")

    lines.append("## Recommended Targets")
    lines.append("")
    if not recommendations:
        lines.append("- No target was selected. Review unmatched paths and consider full validation if this is unexpected.")
    else:
        for index, item in enumerate(recommendations, start=1):
            lines.append(f"### {index}. `{item.target_id}`")
            lines.append("")
            lines.append(f"- Category: `{item.target.get('category')}`")
            lines.append(f"- Risk: `{item.risk}`")
            lines.append(f"- Policy requirement: `{item.policy_requirement}`")
            lines.append(f"- Policy class: `{item.policy_class}`")
            lines.append(f"- Working directory: `{item.target.get('working_directory')}`")
            if item.target.get("coverage_tags"):
                tags = ", ".join(f"`{tag}`" for tag in item.target.get("coverage_tags", []))
                lines.append(f"- Coverage tags: {tags}")
            if item.target.get("requires_review_reason"):
                lines.append(f"- Requires review: {item.target.get('requires_review_reason')}")
            if item.target.get("risk_escalation"):
                lines.append(f"- Risk escalation: {item.target.get('risk_escalation')}")
            if item.target.get("ledger_id"):
                lines.append(f"- Ledger ID: `{item.target.get('ledger_id')}`")
                if item.ledger:
                    lines.append(
                        "- Ledger last run: "
                        f"result `{item.ledger.get('last_result', 'unknown')}`, "
                        f"commit `{item.ledger.get('last_commit', 'unknown')}`, "
                        f"pass/run `{item.ledger.get('pass_count', '?')}/{item.ledger.get('run_count', '?')}`"
                    )
                else:
                    lines.append("- Ledger last run: not found in parsed ledger")
            else:
                lines.append("- Ledger ID: not yet recorded")
            lines.append(f"- History status: `{item.history_status}` ({item.history_reason})")
            if item.structured_history:
                lines.append(
                    "- Structured history: "
                    f"result `{item.structured_history.get('result', 'unknown')}`, "
                    f"commit `{item.structured_history.get('commit', 'unknown')}`, "
                    f"ended `{item.structured_history.get('ended_at', 'unknown')}`"
                )
            description = item.target.get("description")
            if description:
                lines.append(f"- Description: {description}")
            if item.matched_paths:
                lines.append("- Matched paths:")
                for path in item.matched_paths:
                    lines.append(f"  - `{path}`")
            if item.reasons:
                lines.append("- Reasons:")
                for reason in item.reasons:
                    lines.append(f"  - {reason}")
            commands = item.target.get("commands", [])
            if commands:
                lines.append("- Commands:")
                for command in commands:
                    label = command.get("label", "command")
                    lines.append(f"  - `{label}`: `{command_to_string(command)}`")
                    if command.get("requires_env"):
                        env_list = ", ".join(f"`{value}`" for value in command["requires_env"])
                        lines.append(f"    Requires environment: {env_list}")
            if item.target.get("notes"):
                lines.append(f"- Notes: {item.target.get('notes')}")
            lines.append("")

    lines.append("## Required Validation Policy")
    lines.append("")
    lines.append(f"- Status: `{required_validation['status']}`")
    lines.append(f"- Reason: {required_validation['reason']}")
    if required_validation["required_policy_classes"]:
        classes = ", ".join(f"`{value}`" for value in required_validation["required_policy_classes"])
        lines.append(f"- Required policy classes: {classes}")
    else:
        lines.append("- Required policy classes: none")
    lines.append("")

    lines.append("## Fallback Notes")
    lines.append("")
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- No fallback rule fired.")
    lines.append("")

    lines.append("## Unmatched Paths")
    lines.append("")
    if unmatched:
        for path in unmatched:
            lines.append(f"- `{path}`")
        lines.append("")
        lines.append(
            "Unmatched paths do not mean no tests are needed. They mean the first-version registry has no precise mapping for those paths."
        )
    else:
        lines.append("- Every changed path matched at least one target or fallback rule.")
    lines.append("")

    lines.append("## Ledger Snippet Template")
    lines.append("")
    lines.append("After running any recommended command, record only observed executions. Use placeholders for private paths.")
    lines.append("")
    for item in recommendations:
        lines.append(f"- Target: `{item.target_id}`")
        lines.append("  - Result: `<passed|failed|blocked|timed out|interrupted|skipped>`")
        lines.append("  - Summary: `<observed output summary>`")
        lines.append("  - Notes: `<environment/product/orchestrator notes with private paths redacted>`")
    if not recommendations:
        lines.append("- No snippet generated because no target was selected.")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help=f"Target registry path. Defaults to {DEFAULT_REGISTRY}.")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER, help=f"Execution ledger path. Defaults to {DEFAULT_LEDGER}.")
    parser.add_argument("--high-risk-metadata", default=DEFAULT_HIGH_RISK_METADATA, help=f"High-risk path metadata JSON path. Defaults to {DEFAULT_HIGH_RISK_METADATA}.")
    parser.add_argument("--history", default=DEFAULT_HISTORY, help=f"Ignored JSONL run history path. Defaults to {DEFAULT_HISTORY}.")
    parser.add_argument("--no-history", action="store_true", help="Do not read ignored structured run history.")
    parser.add_argument("--base", default=None, help="Base ref for git diff. Defaults to upstream when available.")
    parser.add_argument("--head", default="HEAD", help="Head ref for git diff. Defaults to HEAD.")
    parser.add_argument("--staged", action="store_true", help="Use staged diff instead of base...head.")
    parser.add_argument("--worktree", action="store_true", help="Use unstaged worktree diff instead of base...head.")
    parser.add_argument(
        "--include-untracked",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include untracked non-ignored files. Defaults to true with --worktree and false otherwise.",
    )
    parser.add_argument("--paths", nargs="*", help="Explicit repo-relative changed paths; skips git diff.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    registry = load_registry(repo_root, args.registry)
    high_risk_metadata = load_high_risk_path_metadata(repo_root, args.high_risk_metadata)
    ledger_entries = parse_ledger(repo_root, args.ledger)
    structured_history = {} if args.no_history else latest_records_by_target(load_history_entries(repo_root, args.history))

    if args.paths:
        changed_paths = [ChangedPath(path=normalize_path(path), status="M") for path in args.paths]
    else:
        try:
            base = "__WORKTREE__" if args.worktree else args.base
            changed_paths = git_changed_paths(repo_root, base, args.head, args.staged)
            include_untracked = args.include_untracked
            if include_untracked is None:
                include_untracked = bool(args.worktree)
            if include_untracked:
                changed_paths = merge_changed_paths([*changed_paths, *git_untracked_paths(repo_root)])
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"ERROR unable to read git diff: {exc}", file=sys.stderr)
            return 2

    recommendations, unmatched, notes = select_targets(registry, changed_paths, ledger_entries, structured_history)
    matched_high_risk_metadata = []
    for item in high_risk_metadata:
        path = normalize_path(str(item.get("path") or ""))
        if not path:
            continue
        matched = any(
            changed.path == path or changed.path.startswith(path + "/")
            for changed in changed_paths
        )
        if matched:
            matched_high_risk_metadata.append(item)

    if args.json:
        print(
            json.dumps(
                build_json_result(registry, changed_paths, recommendations, unmatched, notes, matched_high_risk_metadata),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_markdown(registry, changed_paths, recommendations, unmatched, notes, matched_high_risk_metadata))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
