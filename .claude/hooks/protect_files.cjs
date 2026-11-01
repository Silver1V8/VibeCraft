// PreToolUse: niente modifiche dirette a segreti locali e lockfile.
const fs = require("fs");
const path = require("path");

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const file = (input.tool_input && (input.tool_input.file_path || input.tool_input.notebook_path)) || "";
const name = path.basename(file);

if (name === ".env" || (name.startsWith(".env.") && name !== ".env.example")) {
  process.stderr.write(`${name} contiene segreti locali (VIBECRAFT_API_KEY ecc.): modificalo a mano, non tramite Claude. Per documentare una variabile nuova usa .env.example.\n`);
  process.exit(2);
}
if (name === "uv.lock") {
  process.stderr.write("uv.lock si cambia solo con `uv add` / `uv lock` (la CI fa `uv sync --frozen`): non modificarlo a mano.\n");
  process.exit(2);
}
