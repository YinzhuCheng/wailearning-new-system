from types import SimpleNamespace

from apps.backend.courseeval_backend.domains.homework.serialization import preview_text, task_call_log


def test_preview_text_normalizes_and_truncates():
    assert preview_text("  hello\r\nworld  ") == "hello\nworld"
    assert preview_text("abcdef", 3) == "abc…"
    assert preview_text("   ") is None


def test_task_call_log_reads_only_list_manifests():
    assert task_call_log(None) is None
    assert task_call_log(SimpleNamespace(artifact_manifest=None)) is None
    assert task_call_log(SimpleNamespace(artifact_manifest={"llm_call_log": "bad"})) is None
    assert task_call_log(SimpleNamespace(artifact_manifest={"llm_call_log": [{"status": "ok"}]})) == [
        {"status": "ok"}
    ]
