from __future__ import annotations

import uuid

import pytest

from app.blog.rich_text import (
    RichTextError,
    referenced_media_ids,
    render_document,
    validate_document,
)


def test_valid_nested_document_renders_deterministically() -> None:
    document = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "A heading"}],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Safe link",
                                        "marks": [
                                            {
                                                "type": "link",
                                                "attrs": {"href": "https://example.test/page"},
                                            },
                                            {"type": "bold"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {"type": "blockquote", "content": [{"type": "paragraph", "content": []}]},
        ],
    }
    validated = validate_document(document, require_content=True)
    rendered = render_document(validated)
    assert rendered.startswith("<h2>A heading</h2><ul><li><p>")
    assert 'rel="noopener noreferrer"' in rendered
    assert rendered.endswith("<blockquote><p></p></blockquote>")


@pytest.mark.parametrize(
    "document",
    [
        {"type": "html", "content": []},
        {"type": "doc", "content": [{"type": "script", "content": []}]},
        {"type": "doc", "content": [{"type": "paragraph", "html": "<b>x</b>"}]},
        {"type": "doc", "content": "not-a-list"},
    ],
)
def test_malformed_or_unsupported_documents_are_rejected(document: object) -> None:
    with pytest.raises(RichTextError):
        validate_document(document)


def test_script_text_is_escaped_and_cannot_execute() -> None:
    document = validate_document(
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": '<script>alert(1)</script><img onerror="x">',
                        }
                    ],
                }
            ],
        }
    )
    rendered = render_document(document)
    assert "<script>" not in rendered
    assert "<img" not in rendered
    assert "&lt;script&gt;" in rendered


def test_javascript_link_is_rejected() -> None:
    with pytest.raises(RichTextError):
        validate_document(
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "click",
                                "marks": [
                                    {"type": "link", "attrs": {"href": "javascript:alert(1)"}}
                                ],
                            }
                        ],
                    }
                ],
            }
        )


def test_image_uses_stable_media_identity_not_presigned_url() -> None:
    media_id = uuid.uuid4()
    document = validate_document(
        {
            "type": "doc",
            "content": [
                {
                    "type": "image",
                    "attrs": {"media_id": str(media_id), "alt": "Alt", "caption": "Caption"},
                }
            ],
        }
    )
    assert referenced_media_ids(document) == {media_id}
    assert f"/api/v1/public/media/{media_id}" in render_document(document)
    assert "X-Amz-Signature" not in render_document(document)
