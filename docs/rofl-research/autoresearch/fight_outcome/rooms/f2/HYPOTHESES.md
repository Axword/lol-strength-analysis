# F2 Hypotheses (auto-pick R04–R06)

1. **Baseline measure** — Implement `fight_agreement_suite.ts`; score S0 2970132 Path1 windows before any KEEP.
2. **windowOk law** — Encode lethal≤0.75s, earlyMae≤50, burst≤90, full≤130, no invent, program.md hard fails.
3. **windowScore weights** — 0.40 lethal + 0.25 early + 0.20 path + 0.15 actionF1 (0 if unavailable).
4. **Audit JSON** — Every failing window → `fight_outcome/audits/<id>.json`.
5. **S1/S2 wire** — Holdout 2970137/2970120 + unused pro slim; no tune on S1.
6. **Selector default** — Product non-drop CUSUM/post_engage; `near_hp_drop` research-only flag.
