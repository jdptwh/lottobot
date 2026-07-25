@echo off
rem apply_harness.cmd — places the four files the Claude device bridge is
rem (correctly) not allowed to write itself: .claude\ config/hooks and the
rem GitHub Actions workflow. Run from anywhere; review the staged files in
rem _incoming_harness\ first if you like, then run this once.
setlocal
cd /d "%~dp0.."

copy /y "_incoming_harness\claude\agent.config"  ".claude\agent.config"  || goto :fail
copy /y "_incoming_harness\claude\hooks\gate.sh" ".claude\hooks\gate.sh" || goto :fail
copy /y "_incoming_harness\claude\settings.json" ".claude\settings.json" || goto :fail
if not exist ".github\workflows" mkdir ".github\workflows"
copy /y "_incoming_harness\github\workflows\winners.yml" ".github\workflows\winners.yml" || goto :fail

echo.
echo Applied: .claude\agent.config, .claude\hooks\gate.sh, .claude\settings.json,
echo          .github\workflows\winners.yml
echo You can delete the _incoming_harness\ folder now.
exit /b 0

:fail
echo APPLY FAILED — nothing partial should be trusted; check the message above.
exit /b 1
