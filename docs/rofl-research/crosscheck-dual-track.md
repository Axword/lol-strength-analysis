# Dual-track investigation (early + late)

Trades are mixed. Do **not** pick one phase and ignore the other.
Do **not** fit one coefficient to both.

Sign convention: `meanErr = modelHp − actualHp`
- **negative** → model HP too low → **overdamage**
- **positive** → model HP too high → **underdamage**

## Track A — Early (opener / all-in from t=0)

| Check | Lens | What happens |
|-------|------|----------------|
| 01 | full 0–5s | meanErr **−158** (overdamage from second 0) |
| 02 | full 0–5s | meanErr **−814** (hard overdamage) |
| 01 | burst 0–2.2s | high variance; mean near 0 but swingy |
| 02 | burst 0–2s | meanErr **−480** (burst opener too hot) |

**Hypothesis (not a fix yet):** model fights continuously from window start; real play has spacing / waiting / incomplete kits.

**Investigate (no fitting):**
1. Count real `skill_used` in early bin vs model casts
2. Ask: is early error “too many actions” or “wrong damage per action”?

## Track B — Late (finish / lethal window)

| Check | Lens | What happens |
|-------|------|----------------|
| 01 | full 15–20s | highest priority; meanErr **−317** then kill lands |
| 02 | full 15–20s | var spike **73k**; still overdamage then snap to 0 |
| 03 | full 15–25s | mixed; late underdamage (LeeSin HP samples never 0) |
| 03 | burst last slice | var spike; finish timing off |

**Hypothesis:** finish combo / lethality curve wrong even when long-window “kills.”

**Investigate (no fitting):**
1. Align model lethal tick vs actual kill (±0.5s band)
2. Ask: missing burst ability? missing item active? assist damage?

## Anti-overfit while doing both
1. Keep Track A and Track B as **separate** notebooks / notes
2. A change that helps early must be re-scored on late bins (and vice versa)
3. A change that helps both on 2970110 still needs a **holdout game**

## Commands

```bash
npm run crosscheck:sqrt -- --segment full
npm run crosscheck:sqrt -- --segment burst
```

Look for `activeTracks: ["early","late"]` — that is the dual green light to investigate both, not to tune both at once.
