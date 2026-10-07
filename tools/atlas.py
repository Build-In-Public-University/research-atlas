#!/usr/bin/env python3
"""Import public GitHub source metadata and build deterministic atlas views."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources/repositories.yaml"
MANIFESTS = ROOT / "sources/import-manifests"
CATALOG = ROOT / "catalog"
GENERATED = ROOT / "generated"


def parse_source_manifest(path: Path = SOURCES) -> list[dict[str, str]]:
    """Parse the deliberately small repositories.yaml without external dependencies."""
    rows: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line == "repositories:":
            continue
        if line.startswith("- "):
            if current:
                rows.append(current)
            current = {}
            line = line[2:].strip()
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        current[key.strip()] = value.strip().strip('"\'')
    if current:
        rows.append(current)
    if not rows:
        raise ValueError(f"no repositories found in {path}")
    return rows


def github_json(url: str) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "research-atlas/0.1"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"GitHub request failed for {url}: {exc}") from exc


def safe_name(repo_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "__", repo_id) + ".json"


def import_repositories() -> int:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    count = 0
    for source in parse_source_manifest():
        repo_id = source["id"]
        if source.get("role") == "external_catalogue_model":
            continue
        owner, repo = repo_id.split("/", 1)
        repo_data = github_json(f"https://api.github.com/repos/{owner}/{repo}")
        branch = repo_data["default_branch"]
        commit = github_json(f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}")
        tree = github_json(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{commit['sha']}?recursive=1")
        entries = tree.get("tree", [])
        top_level = sorted({item["path"].split("/", 1)[0] for item in entries})
        manifest = {
            "schema_version": "0.1",
            "repository": repo_id,
            "source_url": source["url"],
            "source_role": source.get("role", "source"),
            "default_branch": branch,
            "source_commit": commit["sha"],
            "tree_sha": tree["sha"],
            "tree_truncated": bool(tree.get("truncated", False)),
            "fetched_at": fetched_at,
            "path_count": len(entries),
            "blob_count": sum(item.get("type") == "blob" for item in entries),
            "tree_count": sum(item.get("type") == "tree" for item in entries),
            "top_level_paths": top_level,
        }
        (MANIFESTS / safe_name(repo_id)).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(f"imported {repo_id} @ {commit['sha'][:12]} ({len(entries)} paths)")
        count += 1
    return count


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: {exc}") from exc
    return rows


def parse_families() -> list[dict[str, str]]:
    # Parse the known flat family records; quoted values may contain colons.
    families: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in (CATALOG / "families.yaml").read_text().splitlines():
        line = raw.strip()
        if line.startswith("- id:"):
            if current:
                families.append(current)
            current = {"id": line.split(":", 1)[1].strip()}
            continue
        if current is not None and re.match(r"^[a-z_]+:", line):
            key, value = line.split(":", 1)
            current[key] = value.strip().strip('"\'')
    if current:
        families.append(current)
    return families


def build_views() -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    families = parse_families()
    claims = read_jsonl(CATALOG / "claims.jsonl")
    artifacts = read_jsonl(CATALOG / "artifacts.jsonl")
    manifests = sorted(MANIFESTS.glob("*.json"))
    overview = ["# Research Atlas Overview", "", f"Generated: {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}", "", "This page is generated from the catalog and source import manifests.", "", "## Counts", "", f"- Families: {len(families)}", f"- Claims: {len(claims)}", f"- Artifacts: {len(artifacts)}", f"- Imported source repositories: {len(manifests)}", "", "## Families", ""]
    for family in families:
        family_id = family["id"]
        overview.append(f"- [{family['title']}](families/{family_id}.md) — `{family.get('status', 'unspecified')}`; evidence ceiling `{family.get('evidence_ceiling', 'unspecified')}`")
        body = [f"# {family['title']}", "", f"- ID: `{family_id}`", f"- Source repository: {family['source_repo']}", f"- Status: `{family.get('status', 'unspecified')}`", f"- Evidence ceiling: `{family.get('evidence_ceiling', 'unspecified')}`", "", family.get("notes", ""), "", "## Claims", ""]
        matching_claims = [row for row in claims if row.get("family") == family_id]
        if matching_claims:
            for row in matching_claims:
                body.append(f"- `{row['id']}` — `{row.get('status', 'unspecified')}`: {row.get('wording', '')}")
        else:
            body.append("No claim records indexed yet.")
        body += ["", "## Artifacts", ""]
        matching_artifacts = [row for row in artifacts if row.get("family") == family_id]
        if matching_artifacts:
            for row in matching_artifacts:
                path = row.get("source_path", "")
                suffix = f" (`{path}`)" if path else ""
                body.append(f"- [{row['id']}]({row.get('url', '')}) — `{row.get('status', 'unspecified')}`{suffix}")
        else:
            body.append("No artifact records indexed yet.")
        (GENERATED / "families").mkdir(parents=True, exist_ok=True)
        (GENERATED / "families" / f"{family_id}.md").write_text("\n".join(body) + "\n")
    (GENERATED / "overview.md").write_text("\n".join(overview) + "\n")
    source_lines = ["# Imported Source Inventory", "", "Generated from `sources/import-manifests/`. These are repository-state receipts, not claim-validation receipts.", "", "| Repository | Commit | Paths | Fetched |", "|---|---|---:|---|"]
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        source_lines.append(f"| [{manifest['repository']}]({manifest['source_url']}) | `{manifest['source_commit'][:12]}` | {manifest['path_count']} | {manifest['fetched_at']} |")
    (GENERATED / "source-inventory.md").write_text("\n".join(source_lines) + "\n")
    print(f"built {len(families)} family pages and overview.md")


def validate() -> None:
    sources = parse_source_manifest()
    source_ids = {row["id"] for row in sources}
    families = parse_families()
    family_ids = {row["id"] for row in families}
    if len(family_ids) != len(families):
        raise ValueError("duplicate family id")
    claims = read_jsonl(CATALOG / "claims.jsonl")
    artifacts = read_jsonl(CATALOG / "artifacts.jsonl")
    for row in claims:
        required = {"id", "family", "type", "status", "source", "evidence_boundary"}
        missing = required - row.keys()
        if missing:
            raise ValueError(f"claim {row.get('id', '?')} missing {sorted(missing)}")
        if row["family"] not in family_ids:
            raise ValueError(f"claim {row['id']} references unknown family {row['family']}")
    for row in artifacts:
        if not {"id", "family", "kind", "url", "status"} <= row.keys():
            raise ValueError(f"artifact {row.get('id', '?')} missing required fields")
        if row["family"] not in family_ids:
            raise ValueError(f"artifact {row['id']} references unknown family {row['family']}")
    for manifest_path in MANIFESTS.glob("*.json"):
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("repository") not in source_ids:
            raise ValueError(f"manifest references unknown repository: {manifest_path}")
        for key in ("source_commit", "tree_sha", "fetched_at", "path_count", "top_level_paths"):
            if key not in manifest:
                raise ValueError(f"manifest {manifest_path} missing {key}")
    print(f"validation: PASS ({len(families)} families, {len(claims)} claims, {len(artifacts)} artifacts, {len(list(MANIFESTS.glob('*.json')))} manifests)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("import", "build", "validate", "all"))
    args = parser.parse_args()
    if args.command in ("import", "all"):
        import_repositories()
    if args.command in ("build", "all"):
        build_views()
    if args.command in ("validate", "all"):
        validate()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
