# Registra l'MCP locale di sola lettura (mcp_server.py) in Claude Code.
# Uso: .\scripts\install_mcp.ps1 [-Scope user|local|project] [-BackendUrl http://127.0.0.1:8000]
# Il backend (scripts\run_server.ps1) va avviato a parte: l'MCP lo interroga via HTTP.
param(
    [ValidateSet('user', 'local', 'project')] [string]$Scope = 'user',
    [string]$BackendUrl = 'http://127.0.0.1:8000'
)
$ErrorActionPreference = 'Stop'
$rag = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw 'CLI claude non trovata nel PATH.' }

Push-Location $rag
try { uv sync --frozen; if ($LASTEXITCODE) { throw 'uv sync fallito.' } } finally { Pop-Location }

$python = Join-Path $rag '.venv\Scripts\python.exe'
$server = Join-Path $rag 'mcp_server.py'

# '--' tra apici: PowerShell altrimenti lo consuma e -B arriva a claude.
# Rimuove una registrazione precedente per rendere lo script rieseguibile.
claude mcp remove vibecraft --scope $Scope 2>$null | Out-Null
claude mcp add vibecraft --scope $Scope -e "VIBECRAFT_MCP_BACKEND_URL=$BackendUrl" '--' $python -B $server
if ($LASTEXITCODE) { throw 'claude mcp add fallito.' }

claude mcp get vibecraft
