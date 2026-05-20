from __future__ import annotations

from pathlib import Path


def format_block_name(name: str) -> str:
    return name.replace("-", " ")


def tail_lines(path: Path, count: int = 10) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-count:]
    except Exception:
        return []


def sort_blocks(block_report: dict) -> list[tuple[str, dict]]:
    return sorted(block_report.items(), key=lambda item: item[0])


def render_header(
    pct: int,
    run_id: str,
    active_block: str,
    concurrency: object,
    regression_mode: str,
    updated_at: str | None,
    phase: str | None,
    progress_seen_at: str | None,
) -> None:
    bar_len = 30
    filled = min(bar_len, max(0, int((pct / 100) * bar_len)))
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"[WAI-VALID] [{bar}] {pct}%")
    print(f"run={run_id}")
    print(
        f"mode={regression_mode}  "
        f"active_block={format_block_name(active_block) if active_block else 'n/a'}  "
        f"active_concurrency={concurrency or 'n/a'}"
    )
    if phase:
        print(f"phase={phase}")
    if updated_at:
        print(f"updated={updated_at}")
    if progress_seen_at:
        print(f"progress_seen={progress_seen_at}")


def render_summary(
    done: int,
    failed: int,
    total: int,
    running_count: int,
    queue: int,
    origin_report: dict,
    bootstrap_message: str | None,
    bootstrap_counts: dict | None,
) -> None:
    print()
    print("summary:")
    if bootstrap_message:
        print(f" - status={bootstrap_message}")
    if bootstrap_counts:
        print(
            f" - bootstrap:"
            f" input_paths={bootstrap_counts.get('input_paths', 0)}"
            f" processed_input_paths={bootstrap_counts.get('processed_input_paths', 0)}"
            f" block_specs={bootstrap_counts.get('block_specs', 0)}"
            f" discovered_tasks={bootstrap_counts.get('discovered_tasks', 0)}"
        )
        current_path = bootstrap_counts.get("current_path")
        if current_path:
            print(f" - collecting_now={current_path}")
    print(
        f" - passed={done}/{total}"
        f" failed={failed}"
        f" running={running_count}"
        f" queue={queue}"
    )
    print(
        f" - origins:"
        f" primary={origin_report.get('primary_total', 0)}"
        f" regression={origin_report.get('regression_total', 0)}"
        f" retry={origin_report.get('retry_total', 0)}"
    )


def render_blocks(block_report: dict) -> None:
    print()
    print("blocks:")
    for block_name, block_payload in sort_blocks(block_report):
        print(
            f" - {format_block_name(block_name)}"
            f" | pass {block_payload.get('completed_count', 0)}/{block_payload.get('total', 0)}"
            f" | fail {block_payload.get('failed_count', 0)}"
            f" | run {block_payload.get('running_count', 0)}"
            f" | queue {block_payload.get('queue_remaining', 0)}"
            f" | conc {block_payload.get('configured_concurrency', 'n/a')}"
        )
        origins = block_payload.get("origins") or {}
        print(
            f"   origins: primary={origins.get('primary', 0)}"
            f" regression={origins.get('regression', 0)}"
            f" retry={origins.get('retry', 0)}"
        )
        running_slots = block_payload.get("running_slots") or []
        if running_slots:
            print("   slots:")
            for slot in running_slots:
                source_path = slot.get("source_path")
                display = slot.get("display_name") or slot.get("shard", "n/a")
                label = f"{source_path} :: {display}" if source_path and source_path != display else display
                print(
                    f"    - {label}"
                    f" [{slot.get('origin', 'n/a')}]"
                )


def render_running_slots(running_slots: list[dict]) -> None:
    print()
    print("running slots:")
    if not running_slots:
        print(" - none")
        return
    for slot in running_slots:
        source_path = slot.get("source_path")
        display = slot.get("display_name") or slot.get("shard", "n/a")
        label = f"{source_path} :: {display}" if source_path and source_path != display else display
        print(
            f" - {label}"
            f" | block={format_block_name(str(slot.get('block', 'n/a')))}"
            f" | origin={slot.get('origin', 'n/a')}"
            f" | detail={slot.get('origin_detail', 'n/a')}"
        )


def render_recent_events(events_file: Path) -> None:
    print()
    print("recent events:")
    for line in tail_lines(events_file, 12):
        print(f" - {line}")


def render_progress_snapshot(progress_payload: dict, run_id: str) -> None:
    total = int(progress_payload.get("total") or 0)
    done = int(progress_payload.get("completed_count") or progress_payload.get("passed_count") or 0)
    failed = int(progress_payload.get("failed_count") or 0)
    running = list(progress_payload.get("running") or [])
    queue = int(progress_payload.get("queue_remaining") or 0)
    active_block = str(progress_payload.get("block") or progress_payload.get("active_block") or "")
    concurrency = progress_payload.get("concurrency") or progress_payload.get("block_concurrency") or ""
    regression_mode = str(progress_payload.get("regression_mode") or "n/a")
    report = progress_payload.get("report") or {}
    block_report = report.get("blocks") or {}
    origin_report = report.get("origins") or {}
    running_slots = progress_payload.get("running_slots") or []
    phase = progress_payload.get("phase")
    bootstrap = progress_payload.get("bootstrap") or {}
    pct = int(round((done / total) * 100)) if total else 0
    render_header(
        pct,
        run_id,
        active_block,
        concurrency,
        regression_mode,
        progress_payload.get("updated_at"),
        phase,
        progress_payload.get("updated_at"),
    )
    render_summary(
        done,
        failed,
        total,
        len(running),
        queue,
        origin_report,
        bootstrap.get("message"),
        {
            "input_paths": bootstrap.get("input_paths", 0),
            "block_specs": bootstrap.get("block_specs", 0),
            "discovered_tasks": bootstrap.get("discovered_tasks", 0),
        },
    )
    render_blocks(block_report)
    render_running_slots(running_slots)
    events_file_value = progress_payload.get("events_file_path")
    if events_file_value:
        render_recent_events(Path(str(events_file_value)))
    else:
        print()
        print("recent events:")
        print(" - n/a")
