SYNTHETIC FIXTURES: every HTML file in this directory is hand-constructed for
test coverage of `scraper/wayback_backfill.py` across the eras W1 surveyed
(`docs/specs/w1_wayback_coverage.md`); none of them is a byte-for-byte real
web.archive.org capture. `unclaimed_prizes_2026_current_era.html` mirrors the
current-era fixture at `tests/scraper/fixtures/unclaimed_prizes_2026-07-11.html`
(same table structure, trimmed game list). `unclaimed_prizes_2017_era.html`
and `unclaimed_prizes_2019_era.html` are synthetic era-representative samples
built from W1's finding that the current parser cleanly parses the 2017/2019
table format (same `table.tbstriped` + "as of" structure, different dates and
game data). `unclaimed_prizes_2013_pre_era.html` is a synthetic pre-2015
sample (missing the "as of ..." line, per W1's 2005/2013 parse-failure
finding) used only to prove the era guard skips it by CDX timestamp — never
parsed.

Live web.archive.org validation of real captures happens at CP2 (the
human-observed backfill run), per the M6a program spec.
