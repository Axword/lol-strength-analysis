#!/usr/bin/env python3
"""
GRID.gg API helpers for pro-play series discovery + event JSONL download.

Taken from Axword's local Grid client (endpoints + download shape). Secrets stay
out of git: set ``GRID_API_KEY`` in the environment or a gitignored ``.env``.

HARD CONSTRAINT (Axword): this key may ONLY be used for professional /
public competitive series. Never search, download, or cache scrims, practice
games, tryouts, or private scrim feeds. There is no override flag.

Endpoints:
  - Central GraphQL: series search (titleId=3 = LoL)
  - Series-state GraphQL: per-series game metadata
  - File download: ``/file-download/events/riot/series/{seriesId}/games/{n}``

Outputs land under ``artifacts/pro-grid/`` (gitignored). Convert with
``npm run grid:to-rfc461`` — research only, never product calculatorReady.

Usage:
  export GRID_API_KEY=...
  python3 scripts/grid_api.py search --team "Gen.G" --limit 5
  python3 scripts/grid_api.py download --series-id 2970110
  python3 scripts/grid_api.py download --series-id 2970110 --convert
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts" / "pro-grid"

GRAPHQL_ENDPOINT = "https://api.grid.gg/central-data/graphql"
SERIES_ENDPOINT = "https://api.grid.gg/live-data-feed/series-state/graphql"
FILE_LIST_BASE = "https://api.grid.gg/file-download/list"
FILE_DOWNLOAD_BASE = "https://api.grid.gg/file-download/events/riot/series"

# Official File Download API (helpjuice): list → fullURL.
# Never call Open Access hosts (api-op.grid.gg) for file download — OA has no File Download.

# LoL title on GRID central-data.
LOL_TITLE_ID = 3

# Central-data SeriesType. Pro competitive series are ESPORTS.
# Do not query SCRIM (or other non-ESPORTS) types with this key.
ALLOWED_SERIES_TYPE = "ESPORTS"

USER_AGENT = "lol-strength-analysis/grid-api (+pro-only; research)"

# Substrings that mark non-pro / scrim intent (matched case-insensitively).
SCRIM_MARKERS = (
    "scrim",
    "scrims",
    "scrimmage",
    "practice",
    "tryout",
    "tryouts",
    "bootcamp scrim",
    "private scrim",
)


class GridApiError(RuntimeError):
    """GRID request or response failure."""


class GridProOnlyError(GridApiError):
    """Blocked: GRID key must not be used for scrims / non-pro feeds."""


def load_dotenv(path: Optional[Path] = None) -> None:
    """Load KEY=VALUE lines from ``.env`` into os.environ (no overwrite)."""
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def api_key() -> str:
    load_dotenv()
    key = (os.environ.get("GRID_API_KEY") or "").strip()
    if not key:
        raise GridApiError(
            "GRID_API_KEY missing. Export it or put GRID_API_KEY=... in .env "
            "(gitignored)."
        )
    return key


def _headers(*, json_body: bool = False) -> Dict[str, str]:
    headers = {
        "x-api-key": api_key(),
        "Accept": "application/json,application/octet-stream,*/*",
        # Cloudflare blocks bare urllib signatures (Error 1010) without a UA.
        "User-Agent": USER_AGENT,
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _http_json(
    url: str,
    *,
    method: str = "GET",
    body: Optional[Mapping[str, Any]] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    data = None
    headers = _headers(json_body=body is not None)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise GridApiError(f"HTTP {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GridApiError(f"network error for {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GridApiError(f"non-object JSON from {url}")
    return payload


def _http_download(url: str, dest: Path, *, timeout: float = 180.0) -> int:
    """Download raw bytes to dest. Returns HTTP status (200 or 404)."""
    request = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as fh:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    fh.write(chunk)
            return 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise GridApiError(f"HTTP {exc.code} downloading {url}: {detail}") from exc


def sanitize_filename(name: str) -> str:
    text = re.sub(r"[^\w.\-]+", "_", str(name or "").strip(), flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("._")
    return text or "unnamed"


def looks_like_scrim(*parts: Any) -> bool:
    """True if any text part looks like a scrim/practice/tryout feed."""
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple, set)):
            if looks_like_scrim(*part):
                return True
            continue
        if isinstance(part, Mapping):
            if looks_like_scrim(*part.values()):
                return True
            continue
        text = str(part).strip().lower()
        if not text:
            continue
        for marker in SCRIM_MARKERS:
            if marker in text:
                return True
    return False


def assert_pro_use_allowed(*parts: Any, context: str = "GRID API") -> None:
    """Hard refuse scrim-shaped queries/labels before using GRID_API_KEY."""
    if looks_like_scrim(*parts):
        raise GridProOnlyError(
            f"{context}: blocked — GRID_API_KEY is pro-series only "
            "(Axword: do not use for scrims). Refusing request."
        )


def filter_pro_series(series_rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Drop any series whose teams/title/tournament look like scrims."""
    kept: List[Dict[str, Any]] = []
    for row in series_rows:
        if looks_like_scrim(
            row.get("id"),
            row.get("teams"),
            row.get("date"),
            row.get("tournament"),
            row.get("name"),
            row.get("title"),
        ):
            continue
        kept.append(dict(row))
    return kept


def is_team_match(search_query: str, api_team_name: str, threshold: float = 0.97) -> bool:
    search = search_query.lower().strip()
    target = api_team_name.lower().strip()
    if not search or not target:
        return False
    if search == target:
        return True
    if search in target or target in search:
        return True
    return difflib.SequenceMatcher(None, search, target).ratio() >= threshold


def graphql(
    endpoint: str,
    query: str,
    variables: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload = _http_json(
        endpoint,
        body={"query": query, "variables": dict(variables or {})},
    )
    if payload.get("errors"):
        raise GridApiError(f"GraphQL errors: {payload['errors']}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise GridApiError("GraphQL response missing data object")
    return data


def fetch_series_central(series_id: str) -> Dict[str, Any]:
    """Central-data series row (type, tournament, teams) for pro gate."""
    query = """
    query ($id: ID!) {
      series(id: $id) {
        id
        type
        startTimeScheduled
        tournament { id name }
        teams { baseInfo { id name } }
      }
    }
    """
    data = graphql(GRAPHQL_ENDPOINT, query, {"id": str(series_id)})
    series = data.get("series")
    if not isinstance(series, Mapping):
        raise GridApiError(f"series {series_id} not found in central-data")
    return dict(series)


def assert_series_is_pro(series_id: str) -> Dict[str, Any]:
    """
    Hard pro gate before file-download.

    Requires Central Data ``series.type == ESPORTS`` and no scrim-like
    tournament/team labels. Never queries non-ESPORTS series types.
    """
    assert_pro_use_allowed(series_id, context="grid series pro-check")
    series = fetch_series_central(str(series_id))
    series_type = str(series.get("type") or "").strip().upper()
    tournament = series.get("tournament") or {}
    tournament_name = (
        str(tournament.get("name") or "") if isinstance(tournament, Mapping) else ""
    )
    teams = []
    for team in series.get("teams") or []:
        if isinstance(team, Mapping) and isinstance(team.get("baseInfo"), Mapping):
            name = str(team["baseInfo"].get("name") or "").strip()
            if name:
                teams.append(name)
    assert_pro_use_allowed(
        series_type,
        tournament_name,
        teams,
        context=f"grid series {series_id}",
    )
    if series_type != ALLOWED_SERIES_TYPE:
        raise GridProOnlyError(
            f"grid series {series_id}: blocked — type={series_type!r} "
            f"(only {ALLOWED_SERIES_TYPE} allowed; Axword: no scrims)."
        )
    if not tournament_name:
        raise GridProOnlyError(
            f"grid series {series_id}: blocked — missing tournament name "
            "(refusing untitled/private feeds)."
        )
    return {
        "id": str(series.get("id") or series_id),
        "type": series_type,
        "tournament": tournament_name,
        "tournamentId": str(tournament.get("id") or "")
        if isinstance(tournament, Mapping)
        else "",
        "teams": teams,
        "date": series.get("startTimeScheduled"),
    }


def list_series_files(series_id: str) -> List[Dict[str, Any]]:
    """GET /file-download/list/{seriesId} (official File Download API)."""
    assert_series_is_pro(str(series_id))
    payload = _http_json(f"{FILE_LIST_BASE}/{series_id}")
    files = payload.get("files")
    if not isinstance(files, list):
        raise GridApiError(f"file list for {series_id} missing files[]")
    return [dict(f) for f in files if isinstance(f, Mapping)]


def fetch_series_for_team(
    team_name: str,
    *,
    start_date: str = "2026-05-01T00:00:00Z",
    end_date: str = "2026-12-31T23:59:59Z",
    limit: int = 20,
    page_size: int = 50,
) -> List[Dict[str, Any]]:
    """Page central-data allSeries (ESPORTS only) and filter by team name."""
    assert_pro_use_allowed(team_name, context="grid search --team")
    found: List[Dict[str, Any]] = []
    after_cursor: Optional[str] = None
    has_next = True

    while has_next and len(found) < limit:
        # Official filter: type: ESPORTS (SeriesType enum; bare enum value).
        query = f"""
        query ($after: Cursor) {{
          allSeries(
            first: {int(page_size)},
            after: $after,
            filter: {{
              titleId: {LOL_TITLE_ID},
              type: {ALLOWED_SERIES_TYPE},
              startTimeScheduled: {{
                gte: "{start_date}"
                lte: "{end_date}"
              }}
            }},
            orderBy: StartTimeScheduled,
            orderDirection: DESC
          ) {{
            pageInfo {{ hasNextPage, endCursor }}
            edges {{
              node {{
                id
                type
                startTimeScheduled
                tournament {{ id name }}
                teams {{ baseInfo {{ name }} }}
              }}
            }}
          }}
        }}
        """
        data = graphql(
            GRAPHQL_ENDPOINT,
            query,
            {"after": after_cursor},
        )
        block = data.get("allSeries") or {}
        edges = block.get("edges") or []
        for edge in edges:
            node = (edge or {}).get("node") or {}
            if str(node.get("type") or "").upper() != ALLOWED_SERIES_TYPE:
                continue
            tournament = node.get("tournament") or {}
            tournament_name = (
                str(tournament.get("name") or "")
                if isinstance(tournament, Mapping)
                else ""
            )
            raw_teams = node.get("teams") or []
            clean_names: List[str] = []
            for team in raw_teams:
                if isinstance(team, Mapping) and isinstance(team.get("baseInfo"), Mapping):
                    name = str(team["baseInfo"].get("name") or "").strip()
                    if name:
                        clean_names.append(name)
                elif isinstance(team, str) and team.strip():
                    clean_names.append(team.strip())
            if looks_like_scrim(clean_names, node.get("id"), tournament_name):
                continue
            if not tournament_name:
                continue
            if any(is_team_match(team_name, name) for name in clean_names):
                found.append(
                    {
                        "id": str(node.get("id") or ""),
                        "type": ALLOWED_SERIES_TYPE,
                        "teams": clean_names,
                        "tournament": tournament_name,
                        "date": node.get("startTimeScheduled"),
                    }
                )
                if len(found) >= limit:
                    break
        page_info = block.get("pageInfo") or {}
        has_next = bool(page_info.get("hasNextPage"))
        after_cursor = page_info.get("endCursor")
        if not edges:
            break
    return filter_pro_series(found)


def get_game_metadata(series_id: str) -> List[Dict[str, Any]]:
    pro = assert_series_is_pro(str(series_id))
    query = """
    query ($id: ID!) {
      seriesState(id: $id) {
        games {
          id
          teams { name }
        }
      }
    }
    """
    data = graphql(SERIES_ENDPOINT, query, {"id": str(series_id)})
    series_state = data.get("seriesState") or {}
    games = series_state.get("games") or []
    out: List[Dict[str, Any]] = []
    for game in games:
        if not isinstance(game, Mapping):
            continue
        teams = [
            str(t.get("name") or "").strip()
            for t in (game.get("teams") or [])
            if isinstance(t, Mapping)
        ]
        teams = [t for t in teams if t] or list(pro.get("teams") or [])
        assert_pro_use_allowed(teams, context=f"grid meta series {series_id}")
        if len(teams) >= 2:
            base = f"{teams[0]}_vs_{teams[1]}"
        elif teams:
            base = f"{teams[0]}_vs_Unknown"
        else:
            base = f"Series_{series_id}"
        assert_pro_use_allowed(base, context=f"grid meta series {series_id}")
        out.append(
            {
                "game_id": str(game.get("id") or ""),
                "filename_base": sanitize_filename(base),
                "teams": teams,
                "tournament": pro.get("tournament"),
                "seriesType": pro.get("type"),
            }
        )
    return out


def download_series_files(
    series_id: str,
    *,
    out_dir: Path = DEFAULT_OUT,
    skip_existing: bool = True,
    include: Sequence[str] = ("events-grid", "events-riot", "replay-riot"),
) -> List[Dict[str, Any]]:
    """
    Official File Download flow: list → download fullURL for ready files.

    Default includes:
      - events-grid  → events_<id>_grid.jsonl.zip
      - events-riot-* → events_<id>_<n>_riot.jsonl (dense Riot live-stats)
      - replay-riot-* → replay_riot_<id>_<n>.rofl
    """
    files = list_series_files(str(series_id))
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = {str(x).strip().lower() for x in include}
    results: List[Dict[str, Any]] = []

    for file_info in files:
        file_id = str(file_info.get("id") or "")
        status = str(file_info.get("status") or "")
        file_name = str(file_info.get("fileName") or file_id)
        url = str(file_info.get("fullURL") or "")
        kind = file_id
        if file_id == "events-grid" or file_id.startswith("events-grid"):
            kind_key = "events-grid"
        elif file_id.startswith("events-riot"):
            kind_key = "events-riot"
        elif file_id.startswith("replay-riot"):
            kind_key = "replay-riot"
        elif file_id.startswith("state-"):
            kind_key = "state"
        else:
            kind_key = file_id
        if kind_key not in wanted and file_id not in wanted:
            continue
        if status and status != "ready":
            results.append(
                {
                    "id": file_id,
                    "status": f"not_ready:{status}",
                    "fileName": file_name,
                }
            )
            continue
        if not url:
            results.append({"id": file_id, "status": "missing_url", "fileName": file_name})
            continue
        dest = out_dir / sanitize_filename(file_name)
        if skip_existing and dest.is_file() and dest.stat().st_size > 0:
            results.append(
                {
                    "id": file_id,
                    "path": str(dest),
                    "status": "skipped_exists",
                    "bytes": dest.stat().st_size,
                    "kind": kind_key,
                }
            )
            continue
        code = _http_download(url, dest)
        if code == 404:
            results.append({"id": file_id, "status": "not_found", "url": url})
            continue
        results.append(
            {
                "id": file_id,
                "path": str(dest),
                "status": "downloaded",
                "bytes": dest.stat().st_size,
                "kind": kind_key,
                "url": url,
            }
        )
    return results


def download_series_games(
    series_id: str,
    *,
    out_dir: Path = DEFAULT_OUT,
    filename_base: Optional[str] = None,
    teams: Optional[Sequence[str]] = None,
    max_games: int = 7,
    skip_existing: bool = True,
    require_live_pro_check: bool = True,
) -> List[Dict[str, Any]]:
    """
    Backward-compatible helper: download Riot live-stats JSONL per game index.

    Prefer ``download_series_files`` (official list → fullURL). This path still
    enforces ESPORTS + scrim name guards before any file-download.
    """
    assert_pro_use_allowed(series_id, filename_base, teams, context="grid download")
    meta: List[Dict[str, Any]] = []
    if require_live_pro_check:
        meta = get_game_metadata(str(series_id))
        for game in meta:
            assert_pro_use_allowed(
                game.get("teams"),
                game.get("filename_base"),
                game.get("tournament"),
                context=f"grid download series {series_id}",
            )
    else:
        assert_pro_use_allowed(series_id, filename_base, teams, context="grid download")
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    base = sanitize_filename(
        filename_base or (meta[0]["filename_base"] if meta else f"series_{series_id}")
    )
    assert_pro_use_allowed(base, context="grid download filename")
    results: List[Dict[str, Any]] = []

    for game_index in range(1, max_games + 1):
        url = f"{FILE_DOWNLOAD_BASE}/{series_id}/games/{game_index}"
        dest = out_dir / f"events_{series_id}_{game_index}_riot.jsonl"
        if skip_existing and dest.is_file() and dest.stat().st_size > 0:
            results.append(
                {
                    "gameIndex": game_index,
                    "path": str(dest),
                    "status": "skipped_exists",
                    "bytes": dest.stat().st_size,
                }
            )
            continue
        status = _http_download(url, dest)
        if status == 404:
            if dest.exists() and dest.stat().st_size == 0:
                dest.unlink(missing_ok=True)
            results.append({"gameIndex": game_index, "status": "not_found", "url": url})
            break
        results.append(
            {
                "gameIndex": game_index,
                "path": str(dest),
                "status": "downloaded",
                "bytes": dest.stat().st_size,
                "filenameBase": base,
                "url": url,
            }
        )
    return results


def cmd_search(args: argparse.Namespace) -> int:
    assert_pro_use_allowed(args.team, context="grid search")
    series = fetch_series_for_team(
        args.team,
        start_date=args.start,
        end_date=args.end,
        limit=args.limit,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "team": args.team,
                "count": len(series),
                "series": series,
                "proOnly": True,
            },
            indent=2,
        )
    )
    return 0


def cmd_meta(args: argparse.Namespace) -> int:
    pro = assert_series_is_pro(str(args.series_id))
    games = get_game_metadata(str(args.series_id))
    files = list_series_files(str(args.series_id))
    print(
        json.dumps(
            {
                "ok": True,
                "seriesId": str(args.series_id),
                "pro": pro,
                "games": games,
                "files": files,
                "proOnly": True,
            },
            indent=2,
        )
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    files = list_series_files(str(args.series_id))
    print(
        json.dumps(
            {
                "ok": True,
                "seriesId": str(args.series_id),
                "files": files,
                "proOnly": True,
            },
            indent=2,
        )
    )
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    assert_pro_use_allowed(
        args.series_id,
        args.filename_base,
        context="grid download",
    )
    out_dir = Path(args.out)
    pro = assert_series_is_pro(str(args.series_id))
    include = [x.strip() for x in str(args.include).split(",") if x.strip()]
    results = download_series_files(
        str(args.series_id),
        out_dir=out_dir,
        skip_existing=not args.force,
        include=include,
    )
    summary: Dict[str, Any] = {
        "ok": True,
        "seriesId": str(args.series_id),
        "outDir": str(out_dir.resolve()),
        "pro": pro,
        "files": results,
        "proOnly": True,
    }
    if args.convert:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import grid_events_to_rfc461 as grid
        import grid_riot_events_to_rfc461 as grid_riot
        from rfc461_emit import write_jsonl

        converted = []
        for row in results:
            if row.get("status") not in {"downloaded", "skipped_exists"}:
                continue
            if row.get("kind") not in {"events-grid", "events-riot"}:
                continue
            src = Path(row["path"])
            series_dir = out_dir / str(args.series_id)
            series_dir.mkdir(parents=True, exist_ok=True)
            if row.get("kind") == "events-riot":
                dest = series_dir / f"{src.stem}.rfc461.research.jsonl"
                conv_summary = grid_riot.convert_riot_livestats_file(
                    src,
                    dest,
                    series_id_hint=str(args.series_id),
                )
                converted.append(
                    {
                        "src": str(src),
                        "out": str(dest),
                        "kind": "events-riot",
                        "participants": conv_summary.get("participants"),
                        "statsUpdates": conv_summary.get("statsUpdates"),
                        "suggestedProductRofl": conv_summary.get(
                            "suggestedProductRofl"
                        ),
                        "productEligible": conv_summary.get("productEligible"),
                        "calculatorReady": conv_summary.get("calculatorReady"),
                    }
                )
            else:
                dest = series_dir / f"{src.stem}.rfc461.research.jsonl"
                rows = list(grid._iter_jsonl_rows(src))
                rfc_rows, conv_summary = grid.convert_grid_events(
                    rows, series_id_hint=str(args.series_id)
                )
                write_jsonl(dest, rfc_rows)
                converted.append(
                    {
                        "src": str(src),
                        "out": str(dest),
                        "kind": "events-grid",
                        "participants": conv_summary.get("participants"),
                        "statsUpdates": conv_summary.get("statsUpdates"),
                        "championKills": conv_summary.get("championKills"),
                        "productEligible": conv_summary.get("productEligible"),
                    }
                )
        summary["converted"] = converted
    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Find LoL ESPORTS series by team name")
    search.add_argument("--team", required=True)
    search.add_argument("--start", default="2026-05-01T00:00:00Z")
    search.add_argument("--end", default="2026-12-31T23:59:59Z")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)

    meta = sub.add_parser("meta", help="Pro-check + games + file list for a series id")
    meta.add_argument("--series-id", required=True)
    meta.set_defaults(func=cmd_meta)

    list_cmd = sub.add_parser("list", help="Official file-download list for a series")
    list_cmd.add_argument("--series-id", required=True)
    list_cmd.set_defaults(func=cmd_list)

    download = sub.add_parser(
        "download",
        help="Download series files via official list→fullURL (ESPORTS only)",
    )
    download.add_argument("--series-id", required=True)
    download.add_argument("--out", type=Path, default=DEFAULT_OUT)
    download.add_argument("--filename-base", default="")
    download.add_argument(
        "--include",
        default="events-grid,events-riot,replay-riot",
        help="Comma kinds: events-grid,events-riot,replay-riot,state",
    )
    download.add_argument("--force", action="store_true", help="Re-download even if present")
    download.add_argument(
        "--convert",
        action="store_true",
        help=(
            "Also convert: events-grid → grid_events_to_rfc461; "
            "events-riot → grid_riot_events_to_rfc461"
        ),
    )
    download.set_defaults(func=cmd_download)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except GridProOnlyError as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "proOnly": True, "blocked": "scrim"},
                indent=2,
            )
        )
        return 3
    except GridApiError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
