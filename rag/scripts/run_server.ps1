# Avvia il server RAG caricando prima le variabili d'ambiente locali da .env.local
# (mai committato — vedi .gitignore), cosi' VIBECRAFT_API_KEY non va reimpostata a
# ogni riavvio. Formato .env.local: una riga NOME=valore per variabile, righe vuote
# o che iniziano con # ignorate.
$envFile = Join-Path $PSScriptRoot '..\.env.local'
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$' -and -not $_.TrimStart().StartsWith('#')) {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2])
        }
    }
}
uv run python server.py
