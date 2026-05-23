from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen


DEFAULT_HTTP_TIMEOUT_SECONDS = 20
MAX_FETCH_BYTES = 512 * 1024


@dataclass
class ReferenceSnippet:
    path: str
    snippet_filename: str
    text: str
    line_count: int
    sha256: str
    source_backend: str
    repo_url: str = ""
    branch: str = ""
    raw_url: str = ""

    def to_manifest_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "path": self.path,
            "snippet_filename": self.snippet_filename,
            "line_count": self.line_count,
            "sha256": self.sha256,
            "source_backend": self.source_backend,
        }
        optional = {
            "repo_url": self.repo_url,
            "branch": self.branch,
            "raw_url": self.raw_url,
        }
        for key, value in optional.items():
            if value:
                data[key] = value
        return data


@dataclass
class RepoIngestBundle:
    reference_manifest: dict[str, Any]
    snippets: list[ReferenceSnippet]

    def manifest_json(self) -> str:
        return json.dumps(self.reference_manifest, indent=2, ensure_ascii=False) + "\n"


def write_reference_artifacts(staging_dir: Path, bundle: RepoIngestBundle) -> None:
    snippets_dir = staging_dir / "reference_snippets"
    snippets_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "reference_manifest.json").write_text(
        bundle.manifest_json(),
        encoding="utf-8",
    )
    for snippet in bundle.snippets:
        (snippets_dir / snippet.snippet_filename).write_text(snippet.text, encoding="utf-8")


def ingest_reference_repository(
    *,
    reference_repo_url: str | None,
    reference_paths: list[str] | None,
    reference_branch: str | None = None,
    reference_root: str | None = None,
) -> RepoIngestBundle:
    selected_paths = normalize_selected_paths(reference_paths or [])
    if not selected_paths:
        raise ValueError("Reference repo ingestion requires at least one selected path.")

    if reference_root:
        return ingest_local_reference_paths(
            reference_root=Path(reference_root),
            selected_paths=selected_paths,
            repo_url=reference_repo_url or "",
        )
    if reference_repo_url:
        return ingest_github_reference_paths(
            repo_url=reference_repo_url,
            selected_paths=selected_paths,
            branch=reference_branch,
        )
    raise ValueError(
        "Reference repo ingestion requires either reference_root or reference_repo_url."
    )


def ingest_local_reference_paths(
    *,
    reference_root: Path,
    selected_paths: list[str],
    repo_url: str = "",
) -> RepoIngestBundle:
    normalized_root = reference_root.expanduser().resolve()
    if not normalized_root.exists():
        raise FileNotFoundError(f"Reference root does not exist: {normalized_root}")
    if not normalized_root.is_dir():
        raise NotADirectoryError(f"Reference root must be a directory: {normalized_root}")

    snippets: list[ReferenceSnippet] = []
    for rel_path in normalize_selected_paths(selected_paths):
        file_path = (normalized_root / rel_path).resolve()
        _ensure_within_root(file_path, normalized_root, rel_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Reference file does not exist: {rel_path}")
        if not file_path.is_file():
            raise ValueError(f"Reference path must point to a file: {rel_path}")
        text = file_path.read_text(encoding="utf-8")
        snippets.append(
            _build_snippet(
                path=rel_path,
                text=text,
                source_backend="local_files",
                repo_url=repo_url,
            )
        )

    manifest = _build_reference_manifest(
        repo_url=repo_url,
        selected_paths=selected_paths,
        fetch_mode="selected_paths",
        source_backend="local_files",
        extra={
            "reference_root": str(normalized_root),
            "reference_root_name": normalized_root.name,
            "strict_mode": True,
        },
        snippets=snippets,
    )
    return RepoIngestBundle(reference_manifest=manifest, snippets=snippets)


def ingest_github_reference_paths(
    *,
    repo_url: str,
    selected_paths: list[str],
    branch: str | None = None,
    timeout_seconds: int = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> RepoIngestBundle:
    owner, repo, parsed_branch = parse_github_repo_url(repo_url)
    resolved_branch = branch or parsed_branch or "main"

    snippets: list[ReferenceSnippet] = []
    for rel_path in normalize_selected_paths(selected_paths):
        raw_url = build_github_raw_url(
            owner=owner,
            repo=repo,
            branch=resolved_branch,
            relative_path=rel_path,
        )
        text = fetch_github_raw_text(raw_url, timeout_seconds=timeout_seconds)
        snippets.append(
            _build_snippet(
                path=rel_path,
                text=text,
                source_backend="github_raw",
                repo_url=normalize_repo_url(repo_url),
                branch=resolved_branch,
                raw_url=raw_url,
            )
        )

    manifest = _build_reference_manifest(
        repo_url=normalize_repo_url(repo_url),
        selected_paths=selected_paths,
        fetch_mode="selected_paths",
        source_backend="github_raw",
        extra={
            "github_owner": owner,
            "github_repo": repo,
            "reference_branch": resolved_branch,
            "strict_mode": True,
        },
        snippets=snippets,
    )
    return RepoIngestBundle(reference_manifest=manifest, snippets=snippets)


def normalize_selected_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        path = normalize_reference_path(raw)
        if path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def normalize_reference_path(value: str) -> str:
    candidate = value.strip().replace("\\", "/")
    if not candidate:
        raise ValueError("Reference path cannot be empty.")
    if candidate.startswith("/"):
        raise ValueError(f"Reference path must be relative, got absolute path: {value!r}")

    normalized = PurePosixPath(candidate)
    parts = list(normalized.parts)
    cleaned_parts: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(f"Reference path cannot escape the repo root: {value!r}")
        cleaned_parts.append(part)
    if not cleaned_parts:
        raise ValueError(f"Reference path cannot be empty after normalization: {value!r}")
    return str(PurePosixPath(*cleaned_parts))


def parse_github_repo_url(repo_url: str) -> tuple[str, str, str | None]:
    parsed = urlparse(repo_url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "github.com":
        raise ValueError(f"Only github.com URLs are supported, got: {repo_url!r}")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"GitHub repo URL must include owner and repo: {repo_url!r}")

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    branch: str | None = None
    if len(parts) >= 4 and parts[2] == "tree":
        branch = parts[3]
    return owner, repo, branch


def normalize_repo_url(repo_url: str) -> str:
    owner, repo, _branch = parse_github_repo_url(repo_url)
    return f"https://github.com/{owner}/{repo}"


def build_github_raw_url(
    *,
    owner: str,
    repo: str,
    branch: str,
    relative_path: str,
) -> str:
    safe_path = normalize_reference_path(relative_path)
    return (
        f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{safe_path}"
    )


def fetch_github_raw_text(raw_url: str, *, timeout_seconds: int) -> str:
    try:
        with urlopen(raw_url, timeout=timeout_seconds) as response:
            payload = response.read(MAX_FETCH_BYTES + 1)
    except HTTPError as exc:
        raise RuntimeError(f"Failed to fetch reference snippet: {raw_url} ({exc.code})") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch reference snippet: {raw_url} ({exc.reason})") from exc

    if len(payload) > MAX_FETCH_BYTES:
        raise RuntimeError(
            f"Reference snippet exceeds size limit of {MAX_FETCH_BYTES} bytes: {raw_url}"
        )
    return payload.decode("utf-8", errors="replace")


def snippet_filename_for_path(relative_path: str) -> str:
    normalized = normalize_reference_path(relative_path)
    if "/" not in normalized:
        return normalized
    flattened = normalized.replace("/", "__")
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in flattened)
    return f"{safe}.txt"


def _build_snippet(
    *,
    path: str,
    text: str,
    source_backend: str,
    repo_url: str = "",
    branch: str = "",
    raw_url: str = "",
) -> ReferenceSnippet:
    normalized_path = normalize_reference_path(path)
    return ReferenceSnippet(
        path=normalized_path,
        snippet_filename=snippet_filename_for_path(normalized_path),
        text=text,
        line_count=max(1, len(text.splitlines())) if text else 0,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source_backend=source_backend,
        repo_url=repo_url,
        branch=branch,
        raw_url=raw_url,
    )


def _build_reference_manifest(
    *,
    repo_url: str,
    selected_paths: list[str],
    fetch_mode: str,
    source_backend: str,
    extra: dict[str, Any],
    snippets: list[ReferenceSnippet],
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "repo_url": repo_url,
        "selected_paths": list(selected_paths),
        "normalized_paths": [snippet.path for snippet in snippets],
        "fetch_mode": fetch_mode,
        "source_backend": source_backend,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "snippet_count": len(snippets),
        "snippets": [snippet.to_manifest_dict() for snippet in snippets],
    }
    manifest.update(extra)
    return manifest


def _ensure_within_root(file_path: Path, root: Path, relative_path: str) -> None:
    try:
        file_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Reference path escapes the configured root: {relative_path!r}"
        ) from exc
