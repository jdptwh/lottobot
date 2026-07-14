"""M6b (Phase 1) pooled distributed-lag detectability study.

Reads `data/panel/panel.jsonl` only (never `scraper/`, never the network).
Never imported by anything under `scraper/` — see
`docs/specs/m6_v2_program_spec.md` Phase 1 design rule 1 and the purity test
in `tests/analysis/test_phase1_synthetic.py`.
"""
