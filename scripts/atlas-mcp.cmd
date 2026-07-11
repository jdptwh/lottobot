@echo off
REM Launch the Atlas Cloud MCP. atlascloud-mcp needs Node 20+ (undici's `File` global).
REM Portable resolution order (no machine-specific paths):
REM   1. NODE20_DIR env var, if set, is prepended to PATH (point it at any Node 20+
REM      directory, e.g. an nvm-managed version directory under %APPDATA%).
REM   2. Otherwise the ambient `node` is probed and used if it is v20 or newer.
REM Set ATLAS_MCP_CHECK=1 to run ONLY the version check and exit (used by tests).
if defined NODE20_DIR set "PATH=%NODE20_DIR%;%PATH%"
set "NODEMAJ="
for /f "delims=v. tokens=1" %%v in ('node -v 2^>nul') do if not defined NODEMAJ set "NODEMAJ=%%v"
if not defined NODEMAJ (
  echo [atlas-mcp] node not found on PATH. Install Node 20+, or set NODE20_DIR to a Node 20+ directory. 1>&2
  exit /b 1
)
if %NODEMAJ% LSS 20 (
  echo [atlas-mcp] node v%NODEMAJ% is too old — atlascloud-mcp needs Node 20+. Set NODE20_DIR to a Node 20+ directory ^(e.g. an nvm version dir^). 1>&2
  exit /b 1
)
if defined ATLAS_MCP_CHECK (
  echo [atlas-mcp] check OK: node major version %NODEMAJ%
  exit /b 0
)
npx -y atlascloud-mcp %*
