"""HTTP/MCP abbinati, solo lettura: python -m scripts.bench_mcp --pairs 30.

Backend da VIBECRAFT_MCP_BACKEND_URL; JSON su stdout, nessun report/corpus scritto.
Warm-up escluso; p95 nearest-rank sul delta MCP-HTTP di ogni coppia.
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from mcp_server import backend_url, project_headers

OVERHEAD_LIMIT_MS = 10_000


def quantiles(values):
    values = sorted(values)
    return {f'p{p}': values[math.ceil(len(values) * p / 100) - 1] for p in (50, 95)}


async def benchmark(pairs):
    environment = dict(os.environ)
    url = backend_url(environment.get('VIBECRAFT_MCP_BACKEND_URL', 'http://127.0.0.1:8000'))
    key = environment.get('VIBECRAFT_API_KEY')
    headers = {'X-API-Key': key} if key else {}
    headers.update(project_headers(environment.get('VIBECRAFT_PROJECT_ID')))
    params = StdioServerParameters(command=sys.executable,
        args=['-B', str(Path(__file__).resolve().parents[1] / 'mcp_server.py')], env=environment)
    cases = [
        ('vibecraft_retrieve', '/api/retrieve',
         {'q': 'quali regole governano audit e sicurezza', 'k': 5, 'include_text': True, 'text_max_chars': 2000}),
        ('vibecraft_code_search', '/api/code/search',
         {'q': 'validazione ordine', 'k': 8, 'dev_type': '', 'snippet': True}),
        ('vibecraft_graph_query', '/api/graph/query', {'q': 'quali documenti esistono', 'limit': 10}),
    ]
    report = {'pairs_per_tool': pairs, 'warmup_pairs_per_tool': 3, 'tools': {}}
    async with Client(params) as mcp, httpx.AsyncClient(base_url=url, headers=headers,
            trust_env=False, follow_redirects=False, timeout=120) as http:
        assert {t.name for t in (await mcp.list_tools()).tools} == {c[0] for c in cases}
        versions = set()
        for name, path, payload in cases:
            rows = []
            async def call_http():
                start = time.perf_counter()
                response = await http.get(path, params=payload)
                response.raise_for_status()
                return (time.perf_counter() - start) * 1000, response.json()

            async def call_mcp():
                start = time.perf_counter()
                response = await mcp.call_tool(name, {'params': payload})
                assert not response.is_error, str(response)
                return (time.perf_counter() - start) * 1000, response.structured_content

            for i in range(pairs + 3):
                if i % 2:
                    mt, mb = await call_mcp()
                    ht, hb = await call_http()
                else:
                    ht, hb = await call_http()
                    mt, mb = await call_mcp()
                assert hb == mb, f'HTTP/MCP differiscono: {name}'
                versions.add(hb['index_version'])
                assert len(versions) == 1, 'Indice cambiato durante il benchmark'
                if i >= 3:
                    rows.append({'http_ms': ht, 'mcp_ms': mt, 'delta_ms': mt - ht,
                                 'sha256': hashlib.sha256(json.dumps(hb, sort_keys=True).encode()).hexdigest()})
            report['tools'][name] = {'payload': payload, 'pairs': rows,
                'http_ms': quantiles([r['http_ms'] for r in rows]),
                'mcp_ms': quantiles([r['mcp_ms'] for r in rows]),
                'delta_ms': quantiles([r['delta_ms'] for r in rows])}
    report['index_version'] = versions.pop()
    report['overhead_limit_ms'] = OVERHEAD_LIMIT_MS
    report['overhead_pass'] = all(t['delta_ms']['p95'] <= OVERHEAD_LIMIT_MS for t in report['tools'].values())
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=int, default=30)
    args = parser.parse_args()
    if args.pairs < 30:
        parser.error('servono almeno 30 coppie per tool')
    report = asyncio.run(benchmark(args.pairs))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report['overhead_pass'] else 1)
