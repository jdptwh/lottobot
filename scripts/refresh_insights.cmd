@echo off
rem refresh_insights.cmd — owner convenience: refresh winner data + rebuild
rem both research artifacts + run the gate, from the repo root on Windows.
rem (docs/specs/winners_location_spec.md runbook. The one-time wayback
rem backfill is separate and long-running: python -m scraper.winners wayback)
setlocal
cd /d "%~dp0.."

for /f %%d in ('powershell -NoProfile -Command "(Get-Date).ToUniversalTime().ToString(\"yyyy-MM-dd\")"') do set AS_OF=%%d

echo == winners fetch (one polite request) ==
python -m scraper.winners fetch --as-of %AS_OF% || goto :fail

echo == location trends ==
python -m analysis.location_trends --winners data/winners/winners.jsonl --as-of %AS_OF% --out data/insights/location_trends.json || goto :fail

echo == complexity x burn ==
python -m analysis.complexity --panel data/panel/panel.jsonl --games data/games.json --articles tests/scraper/fixtures/games --as-of %AS_OF% --out data/insights/complexity_burn.json || goto :fail

echo == gate (fast slice) ==
python -m pytest -q tests/scraper/test_winners.py tests/analysis/test_complexity.py tests/analysis/test_location_trends.py tests/site || goto :fail

echo.
echo refresh complete — review with git diff, then commit data/winners/ and data/insights/.
exit /b 0

:fail
echo.
echo REFRESH FAILED — nothing should be committed. Inspect the output above.
exit /b 1
