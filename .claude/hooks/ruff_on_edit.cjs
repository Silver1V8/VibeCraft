// PostToolUse: ruff sul solo file .py appena modificato sotto rag/, con la selezione
// di rag/pyproject.toml (la stessa del gate CI). Exit 2 rimanda l'errore a Claude.
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const file = input.tool_input && input.tool_input.file_path;
const root = process.env.CLAUDE_PROJECT_DIR || input.cwd;
const rag = path.join(root, "rag");
if (!file || !file.endsWith(".py")) process.exit(0);
const rel = path.relative(rag, path.resolve(file));
// Fuori da rag/ o dentro il venv: la config di ruff non si applica.
if (rel.startsWith("..") || path.isAbsolute(rel) || rel.split(path.sep)[0] === ".venv") process.exit(0);

const venvRuff = path.join(rag, ".venv", process.platform === "win32" ? "Scripts/ruff.exe" : "bin/ruff");
const [cmd, args] = fs.existsSync(venvRuff)
  ? [venvRuff, ["check", rel]]
  : ["uv", ["run", "--frozen", "ruff", "check", rel]];
const r = spawnSync(cmd, args, { cwd: rag, encoding: "utf8" });
if (r.error) process.exit(0); // ruff non disponibile: non bloccare il lavoro
if (r.status !== 0) {
  process.stderr.write(`ruff (gate CI) segnala problemi in ${rel}:\n${r.stdout}${r.stderr}`);
  process.exit(2);
}
