#!/usr/bin/env python3
"""Build pixel terrain / vision metadata from the Summoner's Rift minimap image."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path("/Users/river/Projects/lol-strength-analysis")
SRC = ROOT / "public/map/summoners_rift.png"
OUT_JSON = ROOT / "public/map/terrain.json"
OUT_MASK = ROOT / "public/map/terrain_mask.png"

# Palette indices for the mask
VOID = 0
WALL = 1
JUNGLE = 2
BRUSH = 3
RIVER = 4
LANE = 5
BASE_BLUE = 6
BASE_RED = 7
PIT = 8

W, H = 256, 256


def classify(r: int, g: int, b: int, x: float, y: float) -> int:
    """x,y in 0–1 image space (top-left origin)."""
    # Blue base (bottom-left on official minimap ≈ low x, high y in image)
    # Our game coords: y=0 bottom. Image: y=0 top. Convert later in consumer.
    lum = (r + g + b) / 3
    # Very dark = wall / void border
    if lum < 28:
        return WALL
    # Blue-ish water
    if b > r + 25 and b > g + 10 and b > 70:
        return RIVER
    # Bright lane / stone
    if lum > 140 and abs(r - g) < 35 and abs(g - b) < 40:
        return LANE
    # Deep green brush pockets
    if g > r + 18 and g > b + 18 and 40 < g < 130 and r < 90:
        return BRUSH
    # Jungle dirt / grass mid tones
    if 35 < lum < 120:
        # pits near known minimap regions (approx)
        # dragon pit lower-right river bend, baron upper-left
        if 0.55 < x < 0.72 and 0.52 < y < 0.68:
            return PIT
        if 0.28 < x < 0.45 and 0.32 < y < 0.48:
            return PIT
        return JUNGLE
    if lum >= 120:
        return LANE
    return JUNGLE


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}")
    im = Image.open(SRC).convert("RGB").resize((W, H), Image.Resampling.BOX)
    px = im.load()
    mask = Image.new("L", (W, H))
    mp = mask.load()
    brush_cells = []
    river_cells = []
    pit_cells = []

    for j in range(H):
        for i in range(W):
            r, g, b = px[i, j]
            # image y=0 at top; store class
            c = classify(r, g, b, i / (W - 1), j / (H - 1))
            # bases by corner brightness + position
            if i < W * 0.18 and j > H * 0.78:
                c = BASE_BLUE
            elif i > W * 0.82 and j < H * 0.22:
                c = BASE_RED
            mp[i, j] = c
            if c == BRUSH:
                brush_cells.append([i, j])
            elif c == RIVER:
                river_cells.append([i, j])
            elif c == PIT:
                pit_cells.append([i, j])

    mask.save(OUT_MASK)

    meta = {
        "width": W,
        "height": H,
        "sourceImage": "/map/summoners_rift.png",
        "maskImage": "/map/terrain_mask.png",
        "mapSpanGameUnits": 14870,
        "classes": {
            "0": "void",
            "1": "wall",
            "2": "jungle",
            "3": "brush",
            "4": "river",
            "5": "lane",
            "6": "base_blue",
            "7": "base_red",
            "8": "pit",
        },
        "vision": {
            "championSightRadiusNorm": 0.09,
            "wardSightRadiusNorm": 0.055,
            "blueTrinketRadiusNorm": 0.07,
            "brushHidesUnlessInsideOrWard": True,
            "wallBlocksVision": True,
        },
        "notes": [
            "Mask is derived from official SR minimap pixels (256²).",
            "Game y increases bot→top; image row 0 is top — convert with yImg = 1 - yGame when sampling.",
            "Fog of war = not in allied champion/ward sight, or occluded by wall; brush hides unless sharing brush.",
        ],
        "brushCellCount": len(brush_cells),
        "riverCellCount": len(river_cells),
        "pitCellCount": len(pit_cells),
    }
    OUT_JSON.write_text(json.dumps(meta, indent=2))
    print("wrote", OUT_MASK, OUT_JSON)
    print("brush", len(brush_cells), "river", len(river_cells), "pit", len(pit_cells))


if __name__ == "__main__":
    main()
