"""Unit tests for Markdown image expansion for LLM prompts."""

from apps.backend.courseeval_backend.markdown_llm import append_markdown_with_dataurl_images_to_parts, expand_markdown_images_for_llm


def test_expand_markdown_images_empty():
    assert expand_markdown_images_for_llm(None) == ""
    assert expand_markdown_images_for_llm("") == ""


def test_expand_markdown_preserves_plain_text():
    s = "Hello **world** no images here."
    assert expand_markdown_images_for_llm(s) == s


def test_append_markdown_splits_data_url_images():
    tiny = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAusB9Y9nKXUAAAAASUVORK5CYII="
    md = f"Before ![x]({tiny}) after"
    parts: list = []
    append_markdown_with_dataurl_images_to_parts(parts, md)
    assert len(parts) == 4
    assert parts[0]["type"] == "text" and "Before" in parts[0]["text"]
    assert parts[1]["type"] == "text" and "INSTRUCTOR_MD_IMAGE" in parts[1]["text"]
    assert parts[2]["type"] == "image_url" and parts[2]["image_url"]["url"] == tiny
    assert parts[3]["type"] == "text" and "after" in parts[3]["text"]
