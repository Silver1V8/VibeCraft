$ErrorActionPreference = 'Stop'
$ragRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
Set-Location -LiteralPath $ragRoot
$env:QDRANT_URL = 'http://127.0.0.1:16333'
$env:VIBECRAFT_OLLAMA_URL = 'http://127.0.0.1:21434'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:VIBECRAFT_ROLE = 'standalone'
$env:VIBECRAFT_INDEX_MODE = 'legacy'
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:OLLAMA_VULKAN = 'false'
$env:VIBECRAFT_DATABASE_DIR = Join-Path $ragRoot ('database/qdrant_data/horizontal-lab/offline-regression-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $env:VIBECRAFT_DATABASE_DIR -Force | Out-Null
foreach ($name in @('VIBECRAFT_TEST_QDRANT_URL', 'VIBECRAFT_REQUIRE_QDRANT', 'VIBECRAFT_REQUIRE_DOCLING', 'VIBECRAFT_REQUIRE_LIBREOFFICE', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN', 'OPENAI_API_KEY', 'QDRANT_API_KEY')) {
    Remove-Item -LiteralPath ('Env:' + $name) -ErrorAction SilentlyContinue
}
$logPath = Join-Path $PSScriptRoot 'offline-regression.txt'
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest tests -q -ra -o 'addopts=' --ignore=tests/test_agent_settings_isolation.py --ignore=tests/test_mcp_server.py --ignore=tests/test_intake_docling.py --ignore=tests/test_intake_libreoffice.py 2>&1 | Tee-Object -FilePath $logPath
$testExitCode = $LASTEXITCODE
Add-Content -LiteralPath $logPath -Value ('pytest exit code: ' + $testExitCode)
exit $testExitCode
