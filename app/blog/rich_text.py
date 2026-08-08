from __future__ import annotations

import html
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

MAX_NODES = 10_000
MAX_DEPTH = 32
MAX_TEXT_CHARS = 200_000


class RichTextError(ValueError):
    pass


def _mapping(value: object, message: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RichTextError(message)
    return value


def _keys(value: Mapping[str, Any], allowed: set[str]) -> None:
    if set(value) - allowed:
        raise RichTextError("rich-text node contains unsupported fields")


def _safe_href(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise RichTextError("link href is invalid")
    parsed = urlsplit(value)
    if parsed.scheme.casefold() not in {"", "http", "https", "mailto", "tel"}:
        raise RichTextError("link scheme is not allowed")
    if not parsed.scheme and not (value.startswith(("/", "#", "?"))):
        raise RichTextError("relative links must begin with /, #, or ?")
    return value


def validate_document(value: object, *, require_content: bool = False) -> dict[str, Any]:
    document = _mapping(value, "rich-text document must be an object")
    _keys(document, {"type", "content"})
    if document.get("type") != "doc":
        raise RichTextError("rich-text root type must be doc")
    content = document.get("content", [])
    if not isinstance(content, list):
        raise RichTextError("rich-text document content must be a list")
    root_types = {
        "paragraph",
        "heading",
        "blockquote",
        "bulletList",
        "orderedList",
        "horizontalRule",
        "image",
    }
    counters = {"nodes": 1, "text": 0, "meaningful": 0}
    for node in content:
        if _mapping(node, "rich-text node must be an object").get("type") not in root_types:
            raise RichTextError("rich-text document contains an unsupported root node")
        _validate_node(node, depth=1, parent="doc", counters=counters)
    if require_content and counters["meaningful"] == 0:
        raise RichTextError("rich-text document cannot be empty when published")
    return dict(document)


def _validate_node(raw: object, *, depth: int, parent: str, counters: dict[str, int]) -> None:
    if depth > MAX_DEPTH:
        raise RichTextError("rich-text document is nested too deeply")
    node = _mapping(raw, "rich-text node must be an object")
    node_type = node.get("type")
    if not isinstance(node_type, str):
        raise RichTextError("rich-text node type is required")
    counters["nodes"] += 1
    if counters["nodes"] > MAX_NODES:
        raise RichTextError("rich-text document contains too many nodes")

    if node_type == "text":
        _keys(node, {"type", "text", "marks"})
        text_value = node.get("text")
        if not isinstance(text_value, str) or not text_value:
            raise RichTextError("text node text must be non-empty")
        counters["text"] += len(text_value)
        counters["meaningful"] += int(bool(text_value.strip()))
        if counters["text"] > MAX_TEXT_CHARS:
            raise RichTextError("rich-text document is too large")
        marks = node.get("marks", [])
        if not isinstance(marks, list):
            raise RichTextError("text marks must be a list")
        seen: set[str] = set()
        for raw_mark in marks:
            mark = _mapping(raw_mark, "rich-text mark must be an object")
            mark_type = mark.get("type")
            if mark_type not in {"bold", "italic", "underline", "link"}:
                raise RichTextError("rich-text mark is not supported")
            if mark_type in seen:
                raise RichTextError("duplicate rich-text mark")
            seen.add(str(mark_type))
            if mark_type == "link":
                _keys(mark, {"type", "attrs"})
                attrs = _mapping(mark.get("attrs"), "link attrs are required")
                _keys(attrs, {"href"})
                _safe_href(attrs.get("href"))
            else:
                _keys(mark, {"type"})
        return

    if node_type == "image":
        _keys(node, {"type", "attrs"})
        attrs = _mapping(node.get("attrs"), "image attrs are required")
        _keys(attrs, {"media_id", "alt", "caption"})
        try:
            uuid.UUID(str(attrs.get("media_id")))
        except (TypeError, ValueError) as exc:
            raise RichTextError("image media_id must be a UUID") from exc
        for field, maximum in (("alt", 500), ("caption", 2000)):
            field_value = attrs.get(field)
            if field_value is not None and (
                not isinstance(field_value, str) or len(field_value) > maximum
            ):
                raise RichTextError(f"image {field} is invalid")
        counters["meaningful"] += 1
        return

    if node_type in {"horizontalRule", "hardBreak"}:
        _keys(node, {"type"})
        if node_type == "horizontalRule":
            counters["meaningful"] += 1
        return

    allowed_children: dict[str, set[str]] = {
        "paragraph": {"text", "hardBreak"},
        "heading": {"text", "hardBreak"},
        "blockquote": {"paragraph", "heading", "blockquote", "bulletList", "orderedList"},
        "bulletList": {"listItem"},
        "orderedList": {"listItem"},
        "listItem": {"paragraph", "heading", "blockquote", "bulletList", "orderedList"},
    }
    if node_type not in allowed_children:
        raise RichTextError("rich-text node type is not supported")
    allowed_fields = {"type", "content"}
    if node_type in {"heading", "orderedList"}:
        allowed_fields.add("attrs")
    _keys(node, allowed_fields)
    container_attrs = node.get("attrs")
    if node_type == "heading":
        attrs_map = _mapping(container_attrs, "heading attrs are required")
        _keys(attrs_map, {"level"})
        if attrs_map.get("level") not in {1, 2, 3, 4, 5, 6}:
            raise RichTextError("heading level must be between 1 and 6")
    elif node_type == "orderedList" and container_attrs is not None:
        attrs_map = _mapping(container_attrs, "ordered-list attrs must be an object")
        _keys(attrs_map, {"start"})
        if not isinstance(attrs_map.get("start"), int) or attrs_map["start"] < 1:
            raise RichTextError("ordered-list start must be positive")
    children = node.get("content", [])
    if not isinstance(children, list):
        raise RichTextError("rich-text node content must be a list")
    if node_type in {"bulletList", "orderedList", "listItem"} and not children:
        raise RichTextError(f"{node_type} cannot be empty")
    allowed = allowed_children[node_type]
    for child in children:
        child_map = _mapping(child, "rich-text child must be an object")
        if child_map.get("type") not in allowed:
            raise RichTextError(f"{node_type} contains an unsupported child")
        _validate_node(child, depth=depth + 1, parent=node_type, counters=counters)
    del parent


def referenced_media_ids(document: Mapping[str, Any]) -> set[uuid.UUID]:
    result: set[uuid.UUID] = set()

    def visit(node: Mapping[str, Any]) -> None:
        if node.get("type") == "image":
            attrs = _mapping(node.get("attrs"), "image attrs are required")
            result.add(uuid.UUID(str(attrs["media_id"])))
        for child in node.get("content", []):
            visit(_mapping(child, "rich-text child must be an object"))

    visit(document)
    return result


def render_document(document: Mapping[str, Any]) -> str:
    return "".join(
        _render_node(_mapping(node, "rich-text node must be an object"))
        for node in document.get("content", [])
    )


def _render_node(node: Mapping[str, Any]) -> str:
    node_type = node["type"]
    if node_type == "text":
        result = html.escape(str(node["text"]), quote=False)
        for raw_mark in node.get("marks", []):
            mark = _mapping(raw_mark, "rich-text mark must be an object")
            mark_type = mark["type"]
            if mark_type == "bold":
                result = f"<strong>{result}</strong>"
            elif mark_type == "italic":
                result = f"<em>{result}</em>"
            elif mark_type == "underline":
                result = f"<u>{result}</u>"
            else:
                href = _safe_href(_mapping(mark["attrs"], "link attrs are required")["href"])
                external = urlsplit(href).scheme.casefold() in {"http", "https"}
                security = ' target="_blank" rel="noopener noreferrer"' if external else ""
                result = f'<a href="{html.escape(href, quote=True)}"{security}>{result}</a>'
        return result
    if node_type == "image":
        attrs = _mapping(node["attrs"], "image attrs are required")
        media_id = uuid.UUID(str(attrs["media_id"]))
        alt = html.escape(str(attrs.get("alt") or ""), quote=True)
        image = f'<img src="/api/v1/public/media/{media_id}" alt="{alt}" loading="lazy">'
        caption = attrs.get("caption")
        if caption:
            return f"<figure>{image}<figcaption>{html.escape(str(caption))}</figcaption></figure>"
        return f"<figure>{image}</figure>"
    if node_type == "horizontalRule":
        return "<hr>"
    if node_type == "hardBreak":
        return "<br>"
    children = "".join(
        _render_node(_mapping(child, "rich-text child must be an object"))
        for child in node.get("content", [])
    )
    if node_type == "paragraph":
        return f"<p>{children}</p>"
    if node_type == "heading":
        level = int(_mapping(node["attrs"], "heading attrs are required")["level"])
        return f"<h{level}>{children}</h{level}>"
    if node_type == "blockquote":
        return f"<blockquote>{children}</blockquote>"
    if node_type == "bulletList":
        return f"<ul>{children}</ul>"
    if node_type == "orderedList":
        start = int(
            _mapping(node.get("attrs", {"start": 1}), "ordered attrs invalid").get("start", 1)
        )
        start_attr = f' start="{start}"' if start != 1 else ""
        return f"<ol{start_attr}>{children}</ol>"
    if node_type == "listItem":
        return f"<li>{children}</li>"
    raise RichTextError("rich-text node type is not supported")
