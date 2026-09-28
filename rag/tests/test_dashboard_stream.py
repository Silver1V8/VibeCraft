"""Contratto del parser NDJSON usato dalla dashboard /ask."""
import json
import subprocess
from pathlib import Path


DASHBOARD = Path(__file__).parents[1] / "templates" / "dashboard.unified.html"


def test_dashboard_parser_gestisce_confini_utf8_e_terminale():
    chunks = [
        list(b'{"type":"meta"}\n{"type":"delta","text":"caf\xc3'),
        list(b'\xa8"}\n{"type":"result","value":{"status":"success"}}\n'),
    ]
    script = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const match = source.match(/\/\* ASK_STREAM_PARSER_START \*\/([\s\S]*?)\/\* ASK_STREAM_PARSER_END \*\//);
if (!match) throw new Error('parser markers missing');
eval(match[1]);
const events = [];
const parser = createAskStreamParser(event => events.push(event));
for (const chunk of JSON.parse(process.argv[2])) parser.push(Uint8Array.from(chunk), false);
parser.push(undefined, true);
process.stdout.write(JSON.stringify(events));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(DASHBOARD), json.dumps(chunks)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    events = json.loads(completed.stdout)
    assert [event["type"] for event in events] == ["meta", "delta", "result"]
    assert events[1]["text"] == "cafè"


def test_dashboard_parser_rifiuta_eof_senza_result_o_error():
    script = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const match = source.match(/\/\* ASK_STREAM_PARSER_START \*\/([\s\S]*?)\/\* ASK_STREAM_PARSER_END \*\//);
if (!match) throw new Error('parser markers missing');
eval(match[1]);
const parser = createAskStreamParser(() => {});
parser.push(new TextEncoder().encode('{"type":"delta","text":"x"}\n'), false);
try {
  parser.push(undefined, true);
  process.exitCode = 2;
} catch (error) {
  process.stdout.write(error.message);
}
"""
    completed = subprocess.run(
        ["node", "-e", script, str(DASHBOARD)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    assert "senza evento terminale" in completed.stdout
