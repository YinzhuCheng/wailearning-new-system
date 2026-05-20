from __future__ import annotations

import ast
import fnmatch
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"
PROTECTION_RULES = TESTS_ROOT / "TEST_PROTECTION_RULES.json"
REPORT_PATH = REPO_ROOT / "docs" / "development" / "TEST_REDUNDANCY_AUDIT.md"


@dataclass
class TestFile:
    path: Path
    relative_path: str
    category: str
    language: str
    protected: bool
    protection_reason: str | None = None
    test_functions: list["TestFunction"] = field(default_factory=list)


@dataclass
class TestFunction:
    file_path: str
    name: str
    body_hash: str
    body_shape: str
    helper_calls: tuple[str, ...]
    string_literals: tuple[str, ...]
    assert_count: int


class _NormalizeFunctionBody(ast.NodeTransformer):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        return ast.copy_location(ast.Constant(value=type(node.value).__name__), node)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="VAR", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.copy_location(ast.arg(arg="ARG", annotation=None), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        node.attr = "ATTR"
        return node


def load_protection_rules() -> list[dict[str, str]]:
    data = json.loads(PROTECTION_RULES.read_text(encoding="utf-8"))
    return data["protected_globs"]


def is_protected(rel_path: str, rules: list[dict[str, str]]) -> tuple[bool, str | None]:
    unix_path = rel_path.replace("\\", "/")
    for rule in rules:
        if fnmatch.fnmatch(unix_path, rule["pattern"]):
            return True, rule["reason"]
    return False, None


def classify_test_file(rel_path: str) -> tuple[str, str]:
    path = rel_path.replace("\\", "/")
    if path.endswith(".spec.js"):
        return "e2e-web-school", "javascript"
    if path.startswith("tests/behavior/") and path.endswith(".py"):
        return "behavior", "python"
    if path.startswith("tests/backend/") and path.endswith(".py"):
        parts = path.split("/")
        if len(parts) >= 4:
            return f"backend-{parts[2]}", "python"
        return "backend-uncategorized", "python"
    if path.startswith("tests/scenarios/") and path.endswith(".py"):
        return "scenario-support", "python"
    if path.startswith("tests/fixtures/"):
        return "fixtures", "other"
    if path.endswith("conftest.py") or path.endswith("__init__.py"):
        return "test-support", "python"
    if path.endswith(".py"):
        return "uncategorized-python", "python"
    return "other", "other"


def normalize_string(value: str) -> str:
    value = re.sub(r"\d+", "<N>", value)
    value = re.sub(r"[0-9a-f]{8,}", "<HEX>", value, flags=re.IGNORECASE)
    return value.strip()


def iter_python_test_files() -> Iterable[TestFile]:
    rules = load_protection_rules()
    for path in sorted(TESTS_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        # Maintenance utilities live alongside tests but are not pytest modules.
        if rel_path.startswith("tests/devtools/"):
            continue
        category, language = classify_test_file(rel_path)
        protected, reason = is_protected(rel_path, rules)
        yield TestFile(
            path=path,
            relative_path=rel_path,
            category=category,
            language=language,
            protected=protected,
            protection_reason=reason,
        )


def collect_test_functions(test_file: TestFile) -> None:
    if test_file.language != "python":
        return
    if not test_file.relative_path.endswith(".py"):
        return
    if not test_file.path.name.startswith("test_"):
        return

    tree = ast.parse(test_file.path.read_text(encoding="utf-8"))
    normalizer = _NormalizeFunctionBody()

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue

        cloned = normalizer.visit(ast.fix_missing_locations(ast.Module(body=node.body, type_ignores=[])))
        body_shape = ast.dump(cloned, annotate_fields=False, include_attributes=False)

        helper_calls: list[str] = []
        string_literals: list[str] = []
        assert_count = 0
        for subnode in ast.walk(node):
            if isinstance(subnode, ast.Call):
                func_name = None
                if isinstance(subnode.func, ast.Name):
                    func_name = subnode.func.id
                elif isinstance(subnode.func, ast.Attribute):
                    func_name = subnode.func.attr
                if func_name:
                    helper_calls.append(func_name)
            elif isinstance(subnode, ast.Constant) and isinstance(subnode.value, str):
                normalized = normalize_string(subnode.value)
                if normalized:
                    string_literals.append(normalized)
            elif isinstance(subnode, ast.Assert):
                assert_count += 1

        signature = json.dumps(
            {
                "body": body_shape,
                "helpers": sorted(helper_calls),
                "strings": sorted(set(string_literals)),
                "asserts": assert_count,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        test_file.test_functions.append(
            TestFunction(
                file_path=test_file.relative_path,
                name=node.name,
                body_hash=str(hash(signature)),
                body_shape=body_shape,
                helper_calls=tuple(sorted(helper_calls)),
                string_literals=tuple(sorted(set(string_literals))),
                assert_count=assert_count,
            )
        )


def group_exact_duplicate_functions(files: list[TestFile]) -> list[list[TestFunction]]:
    clusters: dict[str, list[TestFunction]] = defaultdict(list)
    for test_file in files:
        for func in test_file.test_functions:
            clusters[func.body_hash].append(func)
    return [cluster for cluster in clusters.values() if len(cluster) > 1]


def split_duplicate_clusters(
    files: list[TestFile], exact_duplicates: list[list[TestFunction]]
) -> tuple[list[list[TestFunction]], list[list[TestFunction]]]:
    file_to_obj = {f.relative_path: f for f in files}
    safe_delete_candidates: list[list[TestFunction]] = []
    parameterization_candidates: list[list[TestFunction]] = []
    for cluster in exact_duplicates:
        involved_files = sorted({item.file_path for item in cluster})
        protected = any(file_to_obj[item.file_path].protected for item in cluster)
        if len(involved_files) == 1:
            parameterization_candidates.append(cluster)
            continue
        if protected:
            parameterization_candidates.append(cluster)
            continue
        safe_delete_candidates.append(cluster)
    return safe_delete_candidates, parameterization_candidates


def file_signature(test_file: TestFile) -> str:
    function_names = sorted(func.name for func in test_file.test_functions)
    helper_calls = sorted({helper for func in test_file.test_functions for helper in func.helper_calls})
    string_literals = sorted({s for func in test_file.test_functions for s in func.string_literals})
    payload = {
        "category": test_file.category,
        "function_names": [normalize_string(name) for name in function_names],
        "helpers": helper_calls,
        "strings": string_literals[:25],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def build_merge_candidates(files: list[TestFile], protected_only: bool = False) -> list[dict[str, object]]:
    comparable = [
        f
        for f in files
        if f.path.name.startswith("test_")
        and f.category.startswith("backend-")
        and (not protected_only or f.protected)
    ]
    candidates: list[dict[str, object]] = []
    for idx, left in enumerate(comparable):
        for right in comparable[idx + 1 :]:
            if left.category != right.category:
                continue
            if left.protected or right.protected:
                continue
            ratio = SequenceMatcher(None, file_signature(left), file_signature(right)).ratio()
            if ratio < 0.86:
                continue
            candidates.append(
                {
                    "category": left.category,
                    "left": left.relative_path,
                    "right": right.relative_path,
                    "similarity": round(ratio, 3),
                    "reason": "High structural similarity. Prefer manual review for parameterization or merge, not direct deletion.",
                }
            )
    candidates.sort(key=lambda item: (item["category"], -float(item["similarity"]), item["left"], item["right"]))
    return candidates[:20]


def build_name_similarity_candidates(files: list[TestFile]) -> list[dict[str, object]]:
    comparable = [
        f for f in files if f.path.name.startswith("test_") and f.category.startswith("backend-") and not f.protected
    ]
    candidates: list[dict[str, object]] = []
    for idx, left in enumerate(comparable):
        left_tokens = {token for token in re.split(r"[_\W]+", left.path.stem) if token and token not in {"test", "behavior"}}
        for right in comparable[idx + 1 :]:
            if left.category != right.category:
                continue
            right_tokens = {
                token for token in re.split(r"[_\W]+", right.path.stem) if token and token not in {"test", "behavior"}
            }
            union = left_tokens | right_tokens
            if not union:
                continue
            score = len(left_tokens & right_tokens) / len(union)
            if score < 0.4:
                continue
            candidates.append(
                {
                    "category": left.category,
                    "left": left.relative_path,
                    "right": right.relative_path,
                    "similarity": round(score, 3),
                    "reason": "Filename/topic overlap suggests review for overlapping coverage or possible parameterization.",
                }
            )
    candidates.sort(key=lambda item: (item["category"], -float(item["similarity"]), item["left"], item["right"]))
    return candidates[:20]


def summarize_counts(files: list[TestFile]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for test_file in files:
        if test_file.path.name.startswith("test_") or test_file.relative_path.endswith(".spec.js"):
            counts[test_file.category] += 1
    return counts


def summarize_test_case_counts(files: list[TestFile]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for test_file in files:
        if test_file.path.name.startswith("test_"):
            counts[test_file.category] += len(test_file.test_functions)
        elif test_file.relative_path.endswith(".spec.js"):
            counts[test_file.category] += 1
    return counts


def projected_test_case_counts_after_safe_deletes(
    files: list[TestFile], safe_delete_candidates: list[list[TestFunction]]
) -> Counter[str]:
    counts = summarize_test_case_counts(files)
    file_to_obj = {f.relative_path: f for f in files}
    for cluster in safe_delete_candidates:
        involved_files = sorted({item.file_path for item in cluster})
        for _ in involved_files[1:]:
            category = file_to_obj[involved_files[0]].category
            counts[category] -= 1
    return counts


def projected_counts_after_safe_deletes(files: list[TestFile], safe_delete_candidates: list[list[TestFunction]]) -> Counter[str]:
    removable_files: set[str] = set()
    file_to_obj = {f.relative_path: f for f in files}
    for cluster in safe_delete_candidates:
        seen_file_paths = sorted({item.file_path for item in cluster})
        for file_path in seen_file_paths[1:]:
            removable_files.add(file_path)

    counts = summarize_counts(files)
    for rel_path in removable_files:
        category = file_to_obj[rel_path].category
        counts[category] -= 1
    return counts


def render_report(
    files: list[TestFile],
    safe_delete_candidates: list[list[TestFunction]],
    parameterization_candidates: list[list[TestFunction]],
    merge_candidates: list[dict[str, object]],
) -> str:
    counts_before = summarize_counts(files)
    counts_after = projected_counts_after_safe_deletes(files, safe_delete_candidates)
    case_counts_before = summarize_test_case_counts(files)
    case_counts_after = projected_test_case_counts_after_safe_deletes(files, safe_delete_candidates)
    protected_files = [f for f in files if f.protected]

    lines: list[str] = []
    lines.append("# Test Redundancy Audit")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append("This report is generated by `tests/devtools/audit_test_redundancy.py`.")
    lines.append("It is a deletion-safety aid, not an autonomous delete decision.")
    lines.append("")
    lines.append("The audit distinguishes between:")
    lines.append("")
    lines.append("- safe-delete candidates: exact duplicate test bodies outside the protection policy")
    lines.append("- merge-only candidates: structurally similar tests that may be parameterized or consolidated after manual review")
    lines.append("- protected tests: high-value or high-difficulty tests that should not be deleted automatically")
    lines.append("")
    lines.append("## Protected Tests")
    lines.append("")
    lines.append(f"Protected test files matched by policy: **{len(protected_files)}**")
    lines.append("")
    for item in protected_files:
        lines.append(f"- `{item.relative_path}`")
        lines.append(f"  Reason: {item.protection_reason}")
    lines.append("")
    lines.append("## Inventory By Category")
    lines.append("")
    lines.append("| Category | Before | After safe deletes |")
    lines.append("| --- | ---: | ---: |")
    for category in sorted(counts_before):
        lines.append(f"| `{category}` | {counts_before[category]} | {counts_after[category]} |")
    lines.append("")
    lines.append("### Test-case counts")
    lines.append("")
    lines.append("| Category | Before | After safe deletes |")
    lines.append("| --- | ---: | ---: |")
    for category in sorted(case_counts_before):
        lines.append(f"| `{category}` | {case_counts_before[category]} | {case_counts_after[category]} |")
    lines.append("")
    lines.append("## Safe-Delete Candidates")
    lines.append("")
    if not safe_delete_candidates:
        lines.append("No exact duplicate non-protected test files were found.")
    else:
        for idx, cluster in enumerate(safe_delete_candidates, start=1):
            lines.append(f"### Cluster {idx}")
            lines.append("")
            for func in cluster:
                lines.append(f"- `{func.file_path}::{func.name}`")
            lines.append("")
    lines.append("")
    lines.append("## Parameterization Candidates")
    lines.append("")
    if not parameterization_candidates:
        lines.append("No same-file exact duplicate test bodies were found.")
    else:
        for idx, cluster in enumerate(parameterization_candidates, start=1):
            lines.append(f"### Cluster {idx}")
            lines.append("")
            for func in cluster:
                lines.append(f"- `{func.file_path}::{func.name}`")
            lines.append("")
    lines.append("")
    lines.append("## Merge-Only Candidates")
    lines.append("")
    if not merge_candidates:
        lines.append("No high-similarity backend file pairs crossed the current review threshold.")
    else:
        for item in merge_candidates:
            lines.append(
                f"- `{item['left']}` <-> `{item['right']}` | similarity `{item['similarity']}` | {item['reason']}"
            )
    lines.append("")
    lines.append("## Interpretation Rules")
    lines.append("")
    lines.append("- Do not delete any protected file from this report without an explicit human decision.")
    lines.append("- Treat merge-only candidates as review prompts, not deletion commands.")
    lines.append("- Prefer parameterization, shared helper extraction, or narrower assertion factoring before removing coverage.")
    lines.append("")
    lines.append("## Recommended Next Review Targets")
    lines.append("")
    lines.append("- `backend-courses` and `backend-roster`: many related enrollment and roster rules with similar helper usage")
    lines.append("- `backend-homework`: review overlapping happy-path setup before deleting anything")
    lines.append("- `backend-llm`: preserve concurrency and stress tests, but inspect low-level API variants for parameterization opportunities")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    files = list(iter_python_test_files())
    for test_file in files:
        collect_test_functions(test_file)

    exact_duplicates = group_exact_duplicate_functions(files)
    safe_delete_candidates, parameterization_candidates = split_duplicate_clusters(files, exact_duplicates)
    merge_candidates = build_merge_candidates(files) + build_name_similarity_candidates(files)
    deduped_pairs: dict[tuple[str, str], dict[str, object]] = {}
    for item in merge_candidates:
        key = tuple(sorted((str(item["left"]), str(item["right"]))))
        deduped_pairs[key] = item
    merge_candidates = sorted(
        deduped_pairs.values(),
        key=lambda item: (str(item["category"]), -float(item["similarity"]), str(item["left"]), str(item["right"])),
    )[:20]
    report = render_report(files, safe_delete_candidates, parameterization_candidates, merge_candidates)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print("")
    print("Category counts:")
    counts = summarize_counts(files)
    for category in sorted(counts):
        print(f"- {category}: {counts[category]}")
    print("")
    print(f"Protected files: {sum(1 for f in files if f.protected)}")
    print(f"Safe-delete clusters: {len(safe_delete_candidates)}")
    print(f"Parameterization clusters: {len(parameterization_candidates)}")
    print(f"Merge-only candidates: {len(merge_candidates)}")


if __name__ == "__main__":
    main()
