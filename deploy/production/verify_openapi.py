from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any


def _load_file(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _load_url(url: str) -> Any:
    request = urllib.request.Request(  # noqa: S310 - URL is constrained by deploy.sh
        url,
        headers={"Accept": "application/json", "User-Agent": "kanoon-deployment-verifier/1"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"OpenAPI endpoint returned HTTP {response.status}")
        content_type = response.headers.get_content_type()
        if content_type != "application/json":
            raise RuntimeError(f"OpenAPI endpoint returned unexpected media type {content_type}")
        return json.load(response)


def _canonical(document: Any) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare OpenAPI documents canonically")
    parser.add_argument("--expected", required=True, type=Path)
    actual = parser.add_mutually_exclusive_group(required=True)
    actual.add_argument("--actual-file", type=Path)
    actual.add_argument("--actual-url")
    arguments = parser.parse_args()

    expected_document = _load_file(arguments.expected)
    actual_document = (
        _load_file(arguments.actual_file)
        if arguments.actual_file is not None
        else _load_url(arguments.actual_url)
    )
    expected = _canonical(expected_document)
    observed = _canonical(actual_document)
    expected_hash = hashlib.sha256(expected).hexdigest()
    observed_hash = hashlib.sha256(observed).hexdigest()
    if expected != observed:
        sys.stderr.write(
            f"OpenAPI drift detected: expected_sha256={expected_hash} "
            f"observed_sha256={observed_hash}\n"
        )
        return 1
    paths = expected_document.get("paths", {}) if isinstance(expected_document, dict) else {}
    sys.stdout.write(f"OpenAPI matches: sha256={expected_hash} paths={len(paths)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
