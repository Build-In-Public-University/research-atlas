#!/usr/bin/env python3
"""Import public GitHub source metadata and build deterministic atlas views."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources/repositories.yaml"
MANIFESTS = ROOT / "sources/import-manifests"
CATALOG = ROOT / "catalog"
GENERATED = ROOT / "generated"
EXTRACTIONS = CATALOG / "extractions.jsonl"
REVIEW_QUEUE = CATALOG / "review-queue.jsonl"
REVIEW_STATUSES = {"source_changed", "source_deleted", "fetch_error", "missing_manifest"}


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


def raw_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "research-atlas/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(url) from exc
        raise RuntimeError(f"raw source request failed for {url}: {exc}") from exc
    except URLError as exc:
        raise RuntimeError(f"raw source request failed for {url}: {exc}") from exc


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


def source_repo_id(source_url: str) -> str:
    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"cannot derive repository from {source_url}")
    return f"{parts[0]}/{parts[1]}"


def classify_drift(previous: dict | None, current_commit: str, current_sha: str, baseline_commit: str | None, baseline_sha: str | None) -> str:
    """Classify current source state against the first recorded baseline."""
    if not previous:
        return "baseline"
    if current_commit == baseline_commit and current_sha == baseline_sha:
        return "unchanged"
    if current_sha == baseline_sha:
        return "repository_advanced_source_unchanged"
    return "source_changed"


def review_event_id(row: dict) -> str:
    material = "|".join(str(row.get(key, "")) for key in ("repository", "source_path", "baseline_commit", "current_commit"))
    return sha256(material.encode("utf-8")).hexdigest()[:16]


def update_review_queue(output: list[dict], now: str, path: Path = REVIEW_QUEUE) -> list[dict]:
    """Merge current flags into the append-only review ledger."""
    prior_queue = {row["event_id"]: row for row in read_jsonl(path) if row.get("event_id")}
    queue = list(prior_queue.values())
    queue_by_id = {row["event_id"]: row for row in queue}
    current_ids = set()
    for row in output:
        if row.get("status") not in REVIEW_STATUSES:
            continue
        event_id = review_event_id(row)
        current_ids.add(event_id)
        event = queue_by_id.get(event_id)
        if event:
            event.update({**row, "last_seen": now, "last_observed_status": row["status"]})
        else:
            queue.append({**row, "event_id": event_id, "first_seen": now, "last_seen": now, "last_observed_status": row["status"], "required_action": "inspect_source_and_update_claim", "resolved": False, "resolution": None})
    for event in queue:
        if event.get("event_id") not in current_ids:
            event["last_observed_status"] = "not_currently_flagged"
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in queue))
    return queue


def drift_check(check_only: bool = False) -> int:
    """Compare indexed paths at the live default branch with the recorded baseline."""
    manifests = {json.loads(path.read_text())["repository"]: json.loads(path.read_text()) for path in MANIFESTS.glob("*.json")}
    records = read_jsonl(EXTRACTIONS)
    previous = {(row["repository"], row["source_path"]): row for row in records}
    candidates = {}
    for catalog_file in (CATALOG / "claims.jsonl", CATALOG / "artifacts.jsonl"):
        for row in read_jsonl(catalog_file):
            if row.get("source_path") and row.get("source"):
                repo = source_repo_id(row["source"])
                candidates[(repo, row["source_path"])] = {"repository": repo, "source_path": row["source_path"], "source_url": row["source"]}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    live_commits = {}
    output = []
    for key in sorted(candidates):
        item = candidates[key]
        manifest = manifests.get(item["repository"])
        if not manifest:
            item.update({"status": "missing_manifest", "observed_at": now})
        else:
            try:
                branch = manifest.get("default_branch", "main")
                if item["repository"] not in live_commits:
                    live = github_json(f"https://api.github.com/repos/{item['repository']}/commits/{quote(branch, safe='')}")
                    live_commits[item["repository"]] = live["sha"]
                current_commit = live_commits[item["repository"]]
                owner, repo = item["repository"].split("/", 1)
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{current_commit}/{quote(item['source_path'], safe='/')}"
                content = raw_text(raw_url).encode("utf-8")
                current_sha = sha256(content).hexdigest()
                prior = previous.get(key, {})
                baseline_commit = prior.get("baseline_commit", prior.get("source_commit", manifest["source_commit"]))
                baseline_sha = prior.get("baseline_sha256", prior.get("sha256"))
                status = classify_drift(prior, current_commit, current_sha, baseline_commit, baseline_sha)
                item.update({"baseline_commit": baseline_commit, "baseline_sha256": baseline_sha, "current_commit": current_commit, "current_sha256": current_sha, "bytes": len(content), "status": status, "observed_at": now})
            except FileNotFoundError:
                item.update({"baseline_commit": manifest["source_commit"], "status": "source_deleted", "observed_at": now})
            except (RuntimeError, KeyError) as exc:
                item.update({"baseline_commit": manifest["source_commit"], "status": "fetch_error", "error": str(exc), "observed_at": now})
        output.append(item)
    if not check_only:
        EXTRACTIONS.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in output))
        update_review_queue(output, now)
    statuses = ("baseline", "unchanged", "repository_advanced_source_unchanged", "source_changed", "source_deleted", "fetch_error", "missing_manifest")
    counts = {status: sum(row.get("status") == status for row in output) for status in statuses}
    print(f"drift: {len(output)} extracted sources; " + ", ".join(f"{key}={value}" for key, value in counts.items() if value))
    if check_only and any(row.get("status") in {"source_changed", "source_deleted", "fetch_error", "missing_manifest"} for row in output):
        return 2
    return len(output)


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
    surfaces = read_jsonl(CATALOG / "repository-surfaces.jsonl")
    manifests = sorted(MANIFESTS.glob("*.json"))
    overview = ["# Research Atlas Overview", "", f"Generated: {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}", "", "This page is generated from the catalog and source import manifests.", "", "## Counts", "", f"- Families: {len(families)}", f"- Claims: {len(claims)}", f"- Artifacts: {len(artifacts)}", f"- Proposed repository surfaces: {len(surfaces)}", f"- Imported source repositories: {len(manifests)}", "", "## Families", ""]
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
    source_urls = {json.loads(path.read_text())["repository"]: json.loads(path.read_text())["source_url"] for path in manifests}
    surface_lines = ["# Proposed Repository Surfaces", "", "These mappings are candidate classifications derived from public repository metadata. They are not claim validation and should be promoted only after reading the source artifacts.", "", "| Repository | Candidate family | Confidence | Surface types |", "|---|---|---|---|"]
    for surface in surfaces:
        surface_lines.append(f"| [{surface['repository']}]({source_urls.get(surface['repository'], '')}) | `{surface['candidate_family']}` | `{surface['confidence']}` | {', '.join(surface['surface_types'])} |")
    (GENERATED / "repository-surfaces.md").write_text("\n".join(surface_lines) + "\n")
    extractions = read_jsonl(EXTRACTIONS)
    corrections = read_jsonl(CATALOG / "corrections.jsonl")
    digest_lines = ["# Research Atlas Release Digest", "", f"Generated: {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}", "", "This is a release-candidate digest. It reports source state and editorial boundaries; it does not promote claims automatically.", "", "## Source extraction state", ""]
    if extractions:
        for row in extractions:
            digest_lines.append(f"- `{row['repository']}:{row['source_path']}` — `{row.get('status', 'unknown')}`; baseline `{row.get('baseline_commit', 'unknown')[:12]}`, current `{row.get('current_commit', 'unknown')[:12]}`")
    else:
        digest_lines.append("No source extractions recorded yet. Run `python3 tools/atlas.py drift`.")
    digest_lines += ["", "## Corrections and preserved boundaries", ""]
    if corrections:
        for row in corrections:
            digest_lines.append(f"- `{row.get('id', 'unknown')}` — {row.get('summary', '')} (`{row.get('status', 'unresolved')}`)")
    else:
        digest_lines.append("No correction records indexed yet.")
    digest_lines += ["", "## Promotion rule", "", "Only source-read observations with verified pointers may enter the catalog. Changed or deleted source files require review before a claim status can advance."]
    (GENERATED / "release-digest.md").write_text("\n".join(digest_lines) + "\n")
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
    surfaces = read_jsonl(CATALOG / "repository-surfaces.jsonl")
    extractions = read_jsonl(EXTRACTIONS)
    review_queue = read_jsonl(REVIEW_QUEUE)
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
    for row in surfaces:
        required = {"repository", "candidate_family", "surface_types", "confidence", "mapping_status", "rationale"}
        missing = required - row.keys()
        if missing:
            raise ValueError(f"surface {row.get('repository', '?')} missing {sorted(missing)}")
        if row["repository"] not in source_ids:
            raise ValueError(f"surface references unknown repository {row['repository']}")
    for row in extractions:
        required = {"repository", "source_path", "status", "observed_at"}
        if not required <= row.keys():
            raise ValueError(f"extraction {row.get('repository', '?')}:{row.get('source_path', '?')} missing {sorted(required - row.keys())}")
        if row["repository"] not in source_ids:
            raise ValueError(f"extraction references unknown repository {row['repository']}")
    for row in review_queue:
        required = {"event_id", "repository", "source_path", "status", "first_seen", "last_seen", "last_observed_status", "required_action", "resolved", "resolution"}
        if not required <= row.keys():
            raise ValueError(f"review queue record missing {sorted(required - row.keys())}")
        if row["status"] not in REVIEW_STATUSES:
            raise ValueError(f"review queue contains non-review status {row['status']}")
    for manifest_path in MANIFESTS.glob("*.json"):
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("repository") not in source_ids:
            raise ValueError(f"manifest references unknown repository: {manifest_path}")
        for key in ("source_commit", "tree_sha", "fetched_at", "path_count", "top_level_paths"):
            if key not in manifest:
                raise ValueError(f"manifest {manifest_path} missing {key}")
    print(f"validation: PASS ({len(families)} families, {len(claims)} claims, {len(artifacts)} artifacts, {len(list(MANIFESTS.glob('*.json')))} manifests)")


def review_list() -> int:
    rows = read_jsonl(REVIEW_QUEUE)
    unresolved = [row for row in rows if not row.get("resolved", False)]
    for row in unresolved:
        print(f"{row['event_id']} {row['repository']}:{row['source_path']} {row.get('status')} last={row.get('last_observed_status')}")
    print(f"review queue: {len(unresolved)} unresolved / {len(rows)} total")
    return 0


def resolve_review(event_id: str, resolution: str, resolver: str) -> int:
    rows = read_jsonl(REVIEW_QUEUE)
    for row in rows:
        if row.get("event_id") == event_id:
            if row.get("resolved"):
                raise ValueError(f"review event {event_id} is already resolved")
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            row.update({"resolved": True, "resolution": resolution, "resolved_by": resolver, "resolved_at": now})
            REVIEW_QUEUE.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in rows))
            print(f"resolved review event {event_id}")
            return 0
    raise ValueError(f"unknown review event {event_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("import", "drift", "review", "resolve", "build", "validate", "all"))
    parser.add_argument("--check", action="store_true", help="for drift, report changes without writing the extraction ledger")
    parser.add_argument("event_id", nargs="?", help="review event ID for resolve")
    parser.add_argument("--resolution", help="resolution explanation for resolve")
    parser.add_argument("--resolver", default=os.environ.get("USER", "unknown"), help="resolver identity for resolve")
    args = parser.parse_args()
    if args.command in ("import", "all"):
        import_repositories()
    if args.command in ("drift", "all"):
        result = drift_check(check_only=args.check)
        if args.check and result == 2:
            return 2
    if args.command == "review":
        return review_list()
    if args.command == "resolve":
        if not args.event_id or not args.resolution:
            parser.error("resolve requires EVENT_ID and --resolution")
        return resolve_review(args.event_id, args.resolution, args.resolver)
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
