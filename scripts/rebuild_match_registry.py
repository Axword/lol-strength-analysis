#!/usr/bin/env python3
"""Build the product match registry from validated published artifacts only."""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATCHES_ROOT = ROOT / "public/data/matches"
REGISTRY_VERSION = 1
PREFERRED_DEFAULT_MATCH_CODE = "3264361042"
MATCH_CODE_RE = re.compile(r"^\d{7,}$")
NON_PRODUCT_MARKERS = (
    "schema_proof",
    "schema-proof",
    "synthetic",
    "fur_parity",
    "research_only",
    "research-only",
    "static_snapshot",
    "static snapshot",
    "fixture",
)


class RegistryError(RuntimeError):
    """A published candidate cannot safely enter the product registry."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"{path.name}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RegistryError(f"{path.name}: root must be an object")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegistryError(f"{label} must be an object")
    return value


def _local_path_strings(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            found.extend(_local_path_strings(child, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_local_path_strings(child, f"{prefix}[{index}]"))
    elif isinstance(value, str):
        text = value.strip()
        if (
            text.startswith(("file://", "/Users/", "/tmp/", "/private/"))
            or re.match(r"^[A-Za-z]:[\\/]", text)
        ):
            found.append(prefix)
    return found


def _assert_sanitized(value: Any, label: str) -> None:
    local_paths = _local_path_strings(value)
    if local_paths:
        raise RegistryError(
            f"{label} contains absolute local paths at {local_paths[:5]}"
        )


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _assert_product_sources(manifest: Mapping[str, Any], timeline: Mapping[str, Any]) -> None:
    provenance = _object(timeline.get("provenance"), "timeline provenance")
    source_text = " ".join(
        _norm(value)
        for value in (
            timeline.get("source"),
            provenance.get("source"),
            provenance.get("sourceKind"),
            manifest.get("source"),
        )
    )
    marker = next((item for item in NON_PRODUCT_MARKERS if item in source_text), None)
    if marker:
        raise RegistryError(f"non-product source marker {marker!r}")


def _manifest_champion(participant: Mapping[str, Any]) -> str:
    champion = _object(participant.get("champion"), "manifest participant champion")
    return str(
        champion.get("display")
        or champion.get("asset")
        or champion.get("raw")
        or ""
    )


def _timeline_champion(participant: Mapping[str, Any]) -> str:
    return str(participant.get("championName") or "")


def _manifest_riot_id(participant: Mapping[str, Any]) -> str:
    riot_id = participant.get("riotId")
    if riot_id is None:
        return ""
    riot_id = _object(riot_id, "manifest participant riotId")
    return str(riot_id.get("full") or "")


def _roster_contract(
    manifest: Mapping[str, Any],
    timeline: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_rows = list(manifest.get("participants") or [])
    timeline_rows = list(timeline.get("participants") or [])
    if len(manifest_rows) != 10 or len(timeline_rows) != 10:
        raise RegistryError(
            "published roster must contain exactly 10 manifest and timeline participants"
        )
    if not all(isinstance(row, Mapping) for row in manifest_rows + timeline_rows):
        raise RegistryError("published roster rows must be objects")
    product_gates = _object(manifest.get("productGates"), "manifest productGates")
    if not product_gates.get("stableIdentityComplete"):
        raise RegistryError("published roster lacks complete stable identities")

    manifest_counts = Counter(
        (
            int(row.get("teamId") or 0),
            _norm(_manifest_champion(row)),
        )
        for row in manifest_rows
    )
    timeline_counts = Counter(
        (
            int(row.get("teamID") or 0),
            _norm(_timeline_champion(row)),
        )
        for row in timeline_rows
    )
    if manifest_counts != timeline_counts:
        raise RegistryError(
            "manifest/timeline roster champion or team identity mismatch"
        )
    manifest_riot_ids = [_norm(_manifest_riot_id(row)) for row in manifest_rows]
    if all(manifest_riot_ids):
        timeline_names = [_norm(row.get("summonerName")) for row in timeline_rows]
        if Counter(manifest_riot_ids) != Counter(timeline_names):
            raise RegistryError("manifest/timeline Riot ID roster mismatch")

    team_counts = Counter(int(row.get("teamId") or 0) for row in manifest_rows)
    if team_counts != Counter({100: 5, 200: 5}):
        raise RegistryError(f"invalid team roster counts: {dict(team_counts)}")

    champions = []
    for row in manifest_rows:
        champion = _object(row.get("champion"), "manifest participant champion")
        champions.append(
            {
                "teamId": int(row.get("teamId") or 0),
                "display": champion.get("display"),
                "asset": champion.get("asset"),
            }
        )
    champions.sort(
        key=lambda row: (
            row["teamId"],
            _norm(row.get("display")),
            _norm(row.get("asset")),
        )
    )
    return {
        "participantCount": 10,
        "blueCount": 5,
        "redCount": 5,
        "champions": champions,
    }


def _coverage(manifest: Mapping[str, Any]) -> dict[str, Any]:
    source = _object(manifest.get("sourceCoverage"), "manifest sourceCoverage")
    fields = {
        "positions": "positions",
        "history": "careerHistory",
        "hp": "hp",
        "combat": "combatStats",
        "ranks": "abilityRanks",
    }
    for public_name, source_name in fields.items():
        if not isinstance(source.get(source_name), str):
            raise RegistryError(
                f"manifest coverage {public_name}/{source_name} missing or invalid"
            )
    return {
        public_name: source[source_name]
        for public_name, source_name in fields.items()
    }


def registry_entry(match_dir: Path) -> dict[str, Any]:
    match_code = match_dir.name
    if not MATCH_CODE_RE.fullmatch(match_code):
        raise RegistryError(f"unsafe published match directory {match_code!r}")
    manifest_path = match_dir / "manifest.json"
    timeline_path = match_dir / "timeline.json"
    if not manifest_path.is_file() or not timeline_path.is_file():
        missing = [
            path.name
            for path in (manifest_path, timeline_path)
            if not path.is_file()
        ]
        raise RegistryError(f"missing published files: {missing}")

    manifest = _load_object(manifest_path)
    timeline = _load_object(timeline_path)
    _assert_sanitized(manifest, "manifest")
    _assert_sanitized(timeline, "timeline")
    _assert_product_sources(manifest, timeline)

    match = _object(manifest.get("match"), "manifest match")
    gates = _object(manifest.get("productGates"), "manifest productGates")
    validation = _object(manifest.get("validation"), "manifest validation")
    phase = _object(manifest.get("phase"), "manifest phase")
    if str(match.get("matchCode") or "") != match_code:
        raise RegistryError("directory and manifest matchCode mismatch")
    try:
        game_id = int(match.get("gameId"))
    except (TypeError, ValueError):
        raise RegistryError("manifest gameId missing/invalid") from None
    if str(game_id) != match_code:
        raise RegistryError("manifest gameId and matchCode mismatch")
    game_name = match.get("gameName")
    if not isinstance(game_name, str) or game_name != match_code:
        raise RegistryError("manifest gameName missing or inconsistent")
    if str(timeline.get("id") or "") != match_code:
        raise RegistryError("timeline id and matchCode mismatch")
    timeline_name = str(timeline.get("name") or "")
    if timeline_name != game_name:
        raise RegistryError("timeline name and manifest gameName mismatch")
    timeline_provenance = _object(timeline.get("provenance"), "timeline provenance")
    if str(timeline_provenance.get("matchCode") or "") != match_code:
        raise RegistryError("timeline provenance matchCode mismatch")
    try:
        timeline_game_id = int(timeline_provenance.get("gameId"))
    except (TypeError, ValueError):
        raise RegistryError("timeline provenance gameId missing/invalid") from None
    if timeline_game_id != game_id:
        raise RegistryError("timeline provenance gameId mismatch")
    if validation.get("ok") is not True or gates.get("productValidated") is not True:
        raise RegistryError("published manifest lacks successful product validation")
    if gates.get("stableIdentityComplete") is not True:
        raise RegistryError("published manifest lacks stable identity gate")
    if not isinstance(gates.get("calculatorReady"), bool) or (
        validation.get("calculatorReady") is not gates.get("calculatorReady")
    ):
        raise RegistryError("manifest calculator gate/validation is inconsistent")
    if phase.get("current") != "publish" or phase.get("status") != "complete":
        raise RegistryError("published manifest phase is not complete")
    publication = _object(manifest.get("publication"), "manifest publication")
    if publication != {
        "directory": f"public/data/matches/{match_code}",
        "timeline": "timeline.json",
        "manifest": "manifest.json",
    }:
        raise RegistryError("published manifest paths are missing or inconsistent")

    roster = _roster_contract(manifest, timeline)
    rofl = _object(manifest.get("rofl"), "manifest rofl")
    manifest_patch = str(rofl.get("patch") or "")
    timeline_patch = str(timeline.get("patch") or "")
    if manifest_patch and timeline_patch and manifest_patch != timeline_patch:
        raise RegistryError("manifest/timeline patch mismatch")
    patch = manifest_patch or timeline_patch
    if not patch:
        raise RegistryError("published match patch missing")
    frames = timeline.get("frames")
    try:
        frame_count = int(timeline.get("frameCount"))
    except (TypeError, ValueError):
        raise RegistryError("timeline frameCount missing/invalid") from None
    if not isinstance(frames, list) or not frames or frame_count != len(frames):
        raise RegistryError("timeline frame list/count is invalid")
    try:
        duration_ms = int(timeline.get("durationMs"))
    except (TypeError, ValueError):
        raise RegistryError("timeline durationMs missing/invalid") from None
    if duration_ms <= 0:
        raise RegistryError("timeline durationMs must be positive")

    coverage = _coverage(manifest)
    hp_trusted = bool(gates.get("hpTrusted"))
    if hp_trusted and coverage["hp"] not in ("full", "partial"):
        raise RegistryError("hpTrusted gate requires full/partial HP coverage")
    entry = {
        "matchCode": match_code,
        "gameId": game_id,
        "name": timeline_name,
        "timelineUrl": f"{match_code}/timeline.json",
        "manifestUrl": f"{match_code}/manifest.json",
        "patch": patch,
        "durationMs": duration_ms,
        "roster": roster,
        "coverage": coverage,
        "productGates": {
            "productValidated": True,
            "stableIdentityComplete": True,
            "hpTrusted": hp_trusted,
            "calculatorReady": gates["calculatorReady"],
        },
    }
    _assert_sanitized(entry, "registry entry")
    return entry


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def build_registry(
    matches_root: Path = DEFAULT_MATCHES_ROOT,
    *,
    strict: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    matches_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    candidates = sorted(
        (
            path
            for path in matches_root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ),
        key=lambda path: path.name,
    )
    for candidate in candidates:
        try:
            entries.append(registry_entry(candidate))
        except RegistryError as exc:
            errors.append(f"{candidate.name}: {exc}")
    if errors and strict:
        raise RegistryError(
            "registry rebuild refused invalid published entries:\n- "
            + "\n- ".join(errors)
        )
    entries.sort(key=lambda entry: int(entry["matchCode"]))
    codes = {entry["matchCode"] for entry in entries}
    default_code = (
        PREFERRED_DEFAULT_MATCH_CODE
        if PREFERRED_DEFAULT_MATCH_CODE in codes
        else entries[0]["matchCode"]
        if entries
        else None
    )
    registry = {
        "version": REGISTRY_VERSION,
        "defaultMatchCode": default_code,
        "matches": entries,
    }
    _assert_sanitized(registry, "registry")
    return registry, errors


def rebuild_registry(
    matches_root: Path = DEFAULT_MATCHES_ROOT,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    registry, errors = build_registry(matches_root, strict=strict)
    _atomic_write_json(matches_root / "index.json", registry)
    return {
        "ok": True,
        "path": "public/data/matches/index.json",
        "matchCount": len(registry["matches"]),
        "defaultMatchCode": registry["defaultMatchCode"],
        "excluded": errors,
        "registry": registry,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matches-root",
        type=Path,
        default=DEFAULT_MATCHES_ROOT,
        help="Published matches root (default public/data/matches)",
    )
    args = parser.parse_args(argv)
    try:
        result = rebuild_registry(args.matches_root, strict=True)
    except RegistryError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
