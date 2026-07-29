#!/usr/bin/env python3
"""Create, fetch, and verify reproducible same-match artifact bundles.

The bundle keeps the original ROFL, canonical rfc461 JSONL, and derived
timeline JSON together behind one content-addressed manifest.  Integrity and
same-match evidence are deliberately separate from product/calculator
eligibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

try:
    from rofl_metadata import RoflMetadataError, inspect_rofl_metadata
except ModuleNotFoundError:  # Imported as scripts.repro_bundle in unittest.
    from scripts.rofl_metadata import RoflMetadataError, inspect_rofl_metadata


SCHEMA = "lol-strength-repro-bundle-v1"
ROLES = (
    "replay_rofl",
    "canonical_rfc461_jsonl",
    "timeline_json",
)
ROLE_MEDIA_TYPES = {
    "replay_rofl": "application/octet-stream",
    "canonical_rfc461_jsonl": "application/x-ndjson",
    "timeline_json": "application/json",
}
ROLE_SUFFIXES = {
    "replay_rofl": ".rofl",
    "canonical_rfc461_jsonl": ".jsonl",
    "timeline_json": ".json",
}
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 1024


class BundleError(ValueError):
    """The bundle is malformed, mismatched, or failed integrity checks."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(DOWNLOAD_CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_filename(value: Any) -> str:
    filename = str(value or "").strip()
    if (
        not filename
        or filename in {".", ".."}
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
    ):
        raise BundleError(f"artifact filename must be a basename: {filename!r}")
    return filename


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise BundleError(f"{label} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise BundleError(f"{label} must be a positive integer") from exc
    if result <= 0:
        raise BundleError(f"{label} must be a positive integer")
    return result


def _patch(value: Any) -> Optional[str]:
    parts = [part for part in str(value or "").strip().split(".") if part]
    return ".".join(parts[:2]) if len(parts) >= 2 else None


def _champion_key(value: Any) -> str:
    key = str(value or "").replace(" ", "").casefold()
    if key == "wukong":
        return "monkeyking"
    return key


def _champion_roster(rows: Iterable[Mapping[str, Any]]) -> Counter[str]:
    champions: list[str] = []
    for row in rows:
        champion = row.get("championName")
        nested = row.get("champion")
        if not champion and isinstance(nested, Mapping):
            champion = nested.get("asset") or nested.get("raw")
        key = _champion_key(champion)
        if key:
            champions.append(key)
    return Counter(champions)


def _participant_puuids(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    puuids: set[str] = set()
    for row in rows:
        value = str(row.get("puuid") or "").strip()
        if not value:
            identity = row.get("sourceIdentity")
            if isinstance(identity, Mapping):
                value = str(identity.get("puuid") or "").strip()
        if value:
            puuids.add(value)
    return puuids


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise BundleError(f"{label} must contain one JSON object")
    return value


def _read_jsonl_identity(path: Path) -> dict[str, Any]:
    game_info: Optional[dict[str, Any]] = None
    coverage: Optional[dict[str, Any]] = None
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise BundleError(
                        f"canonical JSONL line {line_number} is invalid: {exc}"
                    ) from exc
                if not isinstance(row, dict):
                    raise BundleError(
                        f"canonical JSONL line {line_number} must be an object"
                    )
                schema = row.get("rfc461Schema")
                if schema == "game_info":
                    if game_info is not None:
                        raise BundleError("canonical JSONL has multiple game_info rows")
                    game_info = row
                elif schema == "rofl_coverage" and coverage is None:
                    coverage = row
    except (OSError, UnicodeDecodeError) as exc:
        raise BundleError(f"cannot read canonical JSONL: {exc}") from exc

    if game_info is None:
        raise BundleError("canonical JSONL has no rfc461 game_info row")
    participants = game_info.get("participants")
    if not isinstance(participants, list):
        raise BundleError("canonical JSONL game_info.participants must be an array")
    participant_rows = [row for row in participants if isinstance(row, Mapping)]
    game_id = _positive_int(game_info.get("gameID"), "JSONL game_info.gameID")
    provenance = (coverage or {}).get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    platform_id = str(
        game_info.get("platformID")
        or (coverage or {}).get("platformID")
        or provenance.get("platformID")
        or provenance.get("platformId")
        or ""
    ).strip().upper()
    if not platform_id:
        raise BundleError(
            "JSONL platform identity is required on game_info or rofl_coverage"
        )
    source_kind = (
        str(provenance.get("sourceKind") or "").strip()
    )
    if not source_kind:
        source_kind = str((coverage or {}).get("sourceKind") or "unknown").strip()
    return {
        "gameId": game_id,
        "platformId": platform_id,
        "gameVersion": str(game_info.get("gameVersion") or "").strip() or None,
        "patch": _patch(game_info.get("gameVersion")),
        "participants": participant_rows,
        "puuids": _participant_puuids(participant_rows),
        "champions": _champion_roster(participant_rows),
        "sourceKind": source_kind,
        "gridSeriesId": (coverage or {}).get("gridSeriesId"),
        "calculatorReadyDeclared": (coverage or {}).get("calculatorReady"),
        "productEligibleDeclared": (coverage or {}).get("productEligible"),
    }


def _read_timeline_identity(path: Path) -> dict[str, Any]:
    timeline = _read_json_object(path, "timeline JSON")
    provenance = timeline.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    candidates = [provenance.get("gameId"), provenance.get("matchCode")]
    timeline_id = str(timeline.get("id") or "").strip()
    if timeline_id.isdigit():
        candidates.append(timeline_id)
    game_ids: set[int] = set()
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        game_ids.add(_positive_int(candidate, "timeline game identity"))
    if not game_ids:
        raise BundleError("timeline JSON has no id/provenance game identity")
    if len(game_ids) != 1:
        raise BundleError(f"timeline JSON contains conflicting game ids: {game_ids}")
    participants = timeline.get("participants")
    if not isinstance(participants, list):
        raise BundleError("timeline JSON participants must be an array")
    participant_rows = [row for row in participants if isinstance(row, Mapping)]
    return {
        "gameId": next(iter(game_ids)),
        "patch": _patch(timeline.get("patch")),
        "participants": participant_rows,
        "champions": _champion_roster(participant_rows),
    }


def _inspect_same_match(
    rofl_path: Path,
    jsonl_path: Path,
    timeline_path: Path,
) -> dict[str, Any]:
    try:
        rofl = inspect_rofl_metadata(rofl_path)
    except RoflMetadataError as exc:
        raise BundleError(f"ROFL metadata validation failed: {exc}") from exc
    jsonl = _read_jsonl_identity(jsonl_path)
    timeline = _read_timeline_identity(timeline_path)

    rofl_game_id = _positive_int(rofl.get("gameId"), "ROFL gameId")
    game_ids = {rofl_game_id, jsonl["gameId"], timeline["gameId"]}
    if len(game_ids) != 1:
        raise BundleError(
            "same-match check failed: game identity differs across artifacts "
            f"({sorted(game_ids)})"
        )
    rofl_platform = str(rofl.get("platformId") or "").strip().upper()
    if not rofl_platform or rofl_platform != jsonl["platformId"]:
        raise BundleError(
            "same-match check failed: ROFL/JSONL platform differs "
            f"({rofl_platform!r} != {jsonl['platformId']!r})"
        )

    rofl_participants = [
        row for row in rofl.get("participants") or [] if isinstance(row, Mapping)
    ]
    rofl_puuids = _participant_puuids(rofl_participants)
    jsonl_puuids = jsonl["puuids"]
    if len(rofl_puuids) != 10 or len(jsonl_puuids) != 10:
        raise BundleError(
            "same-match check requires ten stable PUUIDs in ROFL and JSONL "
            f"(rofl={len(rofl_puuids)}, jsonl={len(jsonl_puuids)})"
        )
    if rofl_puuids != jsonl_puuids:
        raise BundleError("same-match check failed: ROFL/JSONL PUUID rosters differ")

    rofl_champions = _champion_roster(rofl_participants)
    jsonl_champions = jsonl["champions"]
    timeline_champions = timeline["champions"]
    if not (
        sum(rofl_champions.values())
        == sum(jsonl_champions.values())
        == sum(timeline_champions.values())
        == 10
    ):
        raise BundleError("same-match check requires ten champions in every artifact")
    if rofl_champions != jsonl_champions or rofl_champions != timeline_champions:
        raise BundleError("same-match check failed: champion rosters differ")

    known_patches = {
        patch
        for patch in (rofl.get("patch"), jsonl.get("patch"), timeline.get("patch"))
        if patch
    }
    if len(known_patches) > 1:
        raise BundleError(
            f"same-match check failed: patch differs across artifacts ({known_patches})"
        )

    return {
        "match": {
            "platformId": rofl_platform,
            "matchCode": str(rofl_game_id),
            "gameId": rofl_game_id,
            "patch": rofl.get("patch") or jsonl.get("patch") or timeline.get("patch"),
            "build": rofl.get("build"),
            "durationMs": rofl.get("durationMs"),
            "rosterHash": rofl.get("rosterHash"),
            "gridSeriesId": jsonl.get("gridSeriesId"),
        },
        "sameMatch": {
            "status": "verified",
            "method": "riot_match_identity_plus_puuid_and_champion_rosters",
            "evidence": [
                "ROFL filename and trailing metadata identity validated",
                "ROFL and rfc461 game_info share platform/game identity",
                "ROFL and rfc461 contain the same ten PUUIDs",
                "ROFL, rfc461, and timeline contain the same champion roster",
            ],
            "limits": (
                "Same-match verification and content hashes do not establish "
                "calculatorReady, product eligibility, calibration, or publication authority."
            ),
        },
        "jsonlSourceKind": jsonl["sourceKind"],
        "upstreamDeclarations": {
            "calculatorReady": jsonl["calculatorReadyDeclared"],
            "productEligible": jsonl["productEligibleDeclared"],
        },
    }


def _parse_artifact_urls(values: Sequence[str]) -> dict[str, str]:
    urls: dict[str, str] = {}
    for raw in values:
        role, separator, url = raw.partition("=")
        role = role.strip()
        url = url.strip()
        if not separator or role not in ROLES or not url:
            raise BundleError(
                "--artifact-url must be ROLE=URL where ROLE is one of "
                + ", ".join(ROLES)
            )
        _validate_download_url(url)
        urls[role] = url
    return urls


def _validate_download_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urllib.parse.urlparse(url)
    loopback_http = (
        parsed.scheme == "http"
        and (parsed.hostname or "").casefold() in {"127.0.0.1", "::1", "localhost"}
    )
    if parsed.scheme != "https" and not loopback_http:
        raise BundleError("artifact URLs must use HTTPS (HTTP is loopback-only)")
    if not parsed.netloc or parsed.username or parsed.password:
        raise BundleError("artifact URLs must have a host and must not embed credentials")
    return url


def _artifact_url(
    role: str,
    filename: str,
    *,
    url_base: Optional[str],
    overrides: Mapping[str, str],
) -> Optional[str]:
    if role in overrides:
        return overrides[role]
    if not url_base:
        return None
    base = _validate_download_url(url_base)
    if not base.endswith("/"):
        base += "/"
    return urllib.parse.urljoin(base, urllib.parse.quote(filename))


def _bundle_id(
    match: Mapping[str, Any],
    artifacts: Iterable[Mapping[str, Any]],
) -> str:
    by_role = {str(artifact.get("role") or ""): artifact for artifact in artifacts}
    contract = {
        "match": dict(match),
        "artifacts": [
            {
                "role": role,
                "sha256": by_role[role]["sha256"],
                "sizeBytes": by_role[role]["sizeBytes"],
            }
            for role in ROLES
        ],
    }
    digest = hashlib.sha256(_json_bytes(contract)).hexdigest()
    return (
        f"{str(match['platformId']).lower()}-"
        f"{int(match['gameId'])}-{digest[:16]}"
    )


def create_manifest(
    *,
    rofl_path: Path,
    jsonl_path: Path,
    timeline_path: Path,
    url_base: Optional[str] = None,
    artifact_urls: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    paths = {
        "replay_rofl": rofl_path.expanduser().resolve(),
        "canonical_rfc461_jsonl": jsonl_path.expanduser().resolve(),
        "timeline_json": timeline_path.expanduser().resolve(),
    }
    for role, path in paths.items():
        if not path.is_file():
            raise BundleError(f"{role} file not found: {path}")
        expected_suffix = ROLE_SUFFIXES[role]
        if path.suffix.casefold() != expected_suffix:
            raise BundleError(
                f"{role} must use {expected_suffix}, got {path.name!r}"
            )
    filenames = [_safe_filename(path.name) for path in paths.values()]
    if len(set(filenames)) != len(filenames):
        raise BundleError("artifact filenames must be unique")

    identity = _inspect_same_match(
        paths["replay_rofl"],
        paths["canonical_rfc461_jsonl"],
        paths["timeline_json"],
    )
    url_overrides = dict(artifact_urls or {})
    artifacts: list[dict[str, Any]] = []
    for role in ROLES:
        path = paths[role]
        artifact: dict[str, Any] = {
            "role": role,
            "filename": path.name,
            "mediaType": ROLE_MEDIA_TYPES[role],
            "sizeBytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "url": _artifact_url(
                role,
                path.name,
                url_base=url_base,
                overrides=url_overrides,
            ),
        }
        if role == "canonical_rfc461_jsonl":
            artifact["sourceKind"] = identity["jsonlSourceKind"]
        elif role == "timeline_json":
            artifact["derivedFromRole"] = "canonical_rfc461_jsonl"
        artifacts.append(artifact)

    manifest = {
        "schema": SCHEMA,
        "bundleId": _bundle_id(identity["match"], artifacts),
        "createdAt": _utc_now(),
        "match": identity["match"],
        "sameMatch": identity["sameMatch"],
        "policy": {
            "dataScope": "professional_competitive_only",
            "publicationStatus": "development_research_bundle",
            "secretsIncluded": False,
            "upstreamDeclarations": identity["upstreamDeclarations"],
            "limits": (
                "Do not use this manifest as authority to publish a match or to "
                "set calculatorReady. Run the repository product validator separately."
            ),
        },
        "artifacts": artifacts,
    }
    validate_manifest(manifest, require_urls=False)
    return manifest


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    require_urls: bool,
) -> dict[str, Mapping[str, Any]]:
    if manifest.get("schema") != SCHEMA:
        raise BundleError(f"unsupported manifest schema: {manifest.get('schema')!r}")
    if not str(manifest.get("bundleId") or "").strip():
        raise BundleError("manifest bundleId is required")
    match = manifest.get("match")
    if not isinstance(match, Mapping):
        raise BundleError("manifest match must be an object")
    game_id = _positive_int(match.get("gameId"), "manifest match.gameId")
    match_code = str(match.get("matchCode") or "").strip()
    if match_code != str(game_id):
        raise BundleError("manifest matchCode must equal gameId")
    if not str(match.get("platformId") or "").strip():
        raise BundleError("manifest match.platformId is required")

    same_match = manifest.get("sameMatch")
    if not isinstance(same_match, Mapping) or same_match.get("status") != "verified":
        raise BundleError("manifest sameMatch.status must be verified")
    if (
        same_match.get("method")
        != "riot_match_identity_plus_puuid_and_champion_rosters"
    ):
        raise BundleError("manifest sameMatch.method is unsupported")
    policy = manifest.get("policy")
    if not isinstance(policy, Mapping):
        raise BundleError("manifest policy must be an object")
    if policy.get("secretsIncluded") is not False:
        raise BundleError("manifest must explicitly declare secretsIncluded=false")
    if policy.get("dataScope") != "professional_competitive_only":
        raise BundleError("manifest dataScope must be professional_competitive_only")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise BundleError("manifest artifacts must be an array")
    by_role: dict[str, Mapping[str, Any]] = {}
    filenames: set[str] = set()
    for raw in artifacts:
        if not isinstance(raw, Mapping):
            raise BundleError("every manifest artifact must be an object")
        role = str(raw.get("role") or "")
        if role not in ROLES or role in by_role:
            raise BundleError(f"invalid or duplicate artifact role: {role!r}")
        filename = _safe_filename(raw.get("filename"))
        if filename in filenames:
            raise BundleError(f"duplicate artifact filename: {filename!r}")
        filenames.add(filename)
        if not filename.casefold().endswith(ROLE_SUFFIXES[role]):
            raise BundleError(f"{role} filename has the wrong extension")
        if raw.get("mediaType") != ROLE_MEDIA_TYPES[role]:
            raise BundleError(f"{role}.mediaType does not match its role")
        size = _positive_int(raw.get("sizeBytes"), f"{role}.sizeBytes")
        digest = str(raw.get("sha256") or "").strip().casefold()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise BundleError(f"{role}.sha256 must be a lowercase SHA-256 hex digest")
        if size <= 0:
            raise BundleError(f"{role}.sizeBytes must be positive")
        url = raw.get("url")
        if url:
            _validate_download_url(url)
        elif require_urls:
            raise BundleError(f"{role} has no download URL")
        if role == "canonical_rfc461_jsonl" and not str(
            raw.get("sourceKind") or ""
        ).strip():
            raise BundleError("canonical_rfc461_jsonl.sourceKind is required")
        if (
            role == "timeline_json"
            and raw.get("derivedFromRole") != "canonical_rfc461_jsonl"
        ):
            raise BundleError(
                "timeline_json.derivedFromRole must be canonical_rfc461_jsonl"
            )
        by_role[role] = raw
    missing = [role for role in ROLES if role not in by_role]
    if missing:
        raise BundleError(f"manifest is missing artifact roles: {missing}")
    expected_bundle_id = _bundle_id(match, by_role.values())
    if manifest.get("bundleId") != expected_bundle_id:
        raise BundleError(
            "manifest bundleId does not match its match/artifact content"
        )
    return by_role


def verify_local_bundle(
    manifest: Mapping[str, Any],
    root: Path,
) -> dict[str, Any]:
    by_role = validate_manifest(manifest, require_urls=False)
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise BundleError(f"bundle directory not found: {root}")
    paths: dict[str, Path] = {}
    verified: list[dict[str, Any]] = []
    for role in ROLES:
        artifact = by_role[role]
        path = root / _safe_filename(artifact.get("filename"))
        if not path.is_file():
            raise BundleError(f"bundle artifact missing: {path}")
        expected_size = int(artifact["sizeBytes"])
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise BundleError(
                f"{role} size mismatch: expected {expected_size}, got {actual_size}"
            )
        expected_hash = str(artifact["sha256"])
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise BundleError(
                f"{role} SHA-256 mismatch: expected {expected_hash}, got {actual_hash}"
            )
        paths[role] = path
        verified.append(
            {
                "role": role,
                "filename": path.name,
                "sizeBytes": actual_size,
                "sha256": actual_hash,
            }
        )

    identity = _inspect_same_match(
        paths["replay_rofl"],
        paths["canonical_rfc461_jsonl"],
        paths["timeline_json"],
    )
    match = manifest["match"]
    if (
        identity["match"]["gameId"] != int(match["gameId"])
        or identity["match"]["platformId"] != str(match["platformId"]).upper()
        or identity["match"]["rosterHash"] != match.get("rosterHash")
    ):
        raise BundleError("downloaded artifact identity does not match manifest match")
    return {
        "ok": True,
        "schema": SCHEMA,
        "bundleId": manifest["bundleId"],
        "sameMatch": identity["sameMatch"]["status"],
        "artifacts": verified,
        "limits": identity["sameMatch"]["limits"],
    }


def _load_manifest_source(source: str) -> tuple[dict[str, Any], Optional[str]]:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in {"http", "https"}:
        url = _validate_download_url(source)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                _validate_download_url(response.geturl())
                payload = response.read(MAX_MANIFEST_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BundleError(f"cannot download manifest: {exc}") from exc
        if len(payload) > MAX_MANIFEST_BYTES:
            raise BundleError("manifest exceeds 2 MiB limit")
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"remote manifest is invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise BundleError("remote manifest must be a JSON object")
        return value, url
    return _read_json_object(Path(source).expanduser(), "bundle manifest"), None


def _download_artifact(url: str, destination: Path, expected_size: int) -> None:
    url = _validate_download_url(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            _validate_download_url(response.geturl())
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{destination.name}.",
                suffix=".part",
                dir=destination.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                downloaded = 0
                while True:
                    block = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not block:
                        break
                    downloaded += len(block)
                    if downloaded > expected_size:
                        raise BundleError(
                            f"download exceeded declared size for {destination.name}"
                        )
                    handle.write(block)
        if temp_path is None or temp_path.stat().st_size != expected_size:
            actual = temp_path.stat().st_size if temp_path and temp_path.exists() else 0
            raise BundleError(
                f"download size mismatch for {destination.name}: "
                f"expected {expected_size}, got {actual}"
            )
        os.replace(temp_path, destination)
        temp_path = None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BundleError(f"cannot download {url}: {exc}") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def fetch_bundle(manifest_source: str, out_dir: Path) -> dict[str, Any]:
    manifest, _manifest_url = _load_manifest_source(manifest_source)
    by_role = validate_manifest(manifest, require_urls=True)
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        artifact = by_role[role]
        destination = out_dir / _safe_filename(artifact["filename"])
        if destination.exists():
            if (
                destination.is_file()
                and destination.stat().st_size == int(artifact["sizeBytes"])
                and sha256_file(destination) == artifact["sha256"]
            ):
                continue
            raise BundleError(
                f"refusing to overwrite non-matching destination: {destination}"
            )
        _download_artifact(
            str(artifact["url"]),
            destination,
            int(artifact["sizeBytes"]),
        )
    manifest_path = out_dir / "repro-bundle.json"
    if manifest_path.exists():
        existing = _read_json_object(manifest_path, "existing bundle manifest")
        if _json_bytes(existing) != _json_bytes(manifest):
            raise BundleError(
                f"refusing to overwrite non-matching manifest: {manifest_path}"
            )
    else:
        _write_json(manifest_path, manifest)
    return verify_local_bundle(manifest, out_dir)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a verified bundle manifest")
    create.add_argument("--rofl", required=True, type=Path)
    create.add_argument("--jsonl", required=True, type=Path)
    create.add_argument("--json", required=True, dest="timeline", type=Path)
    create.add_argument("--out", required=True, type=Path)
    create.add_argument(
        "--url-base",
        help="HTTPS directory containing files with their original basenames",
    )
    create.add_argument(
        "--artifact-url",
        action="append",
        default=[],
        metavar="ROLE=URL",
        help="Per-artifact HTTPS URL override; may be repeated",
    )

    verify = subparsers.add_parser("verify", help="Verify local files and identity")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--root", required=True, type=Path)

    fetch = subparsers.add_parser("fetch", help="Download and verify a remote bundle")
    fetch.add_argument("--manifest", required=True, help="Local path or HTTPS URL")
    fetch.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "create":
            manifest = create_manifest(
                rofl_path=args.rofl,
                jsonl_path=args.jsonl,
                timeline_path=args.timeline,
                url_base=args.url_base,
                artifact_urls=_parse_artifact_urls(args.artifact_url),
            )
            _write_json(args.out, manifest)
            result = {
                "ok": True,
                "manifest": str(args.out.expanduser().resolve()),
                "bundleId": manifest["bundleId"],
                "sameMatch": manifest["sameMatch"]["status"],
                "remoteReady": all(
                    bool(artifact.get("url")) for artifact in manifest["artifacts"]
                ),
            }
        elif args.command == "verify":
            manifest = _read_json_object(args.manifest.expanduser(), "bundle manifest")
            result = verify_local_bundle(manifest, args.root)
        else:
            result = fetch_bundle(args.manifest, args.out)
    except BundleError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
