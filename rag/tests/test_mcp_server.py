"""SDK e HTTP reali su loopback, dati sintetici: nessun corpus/provider."""
import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from mcp_server import backend_url, create_server
from agent_bridge import _build_agent_options


@pytest.mark.parametrize('url', ['https://example.org', 'http://127.0.0.1.evil',
    'http://127.0.0.1@evil', 'http://evil@127.0.0.1', 'http://2130706433',
    'http://127.1', 'http://0.0.0.0', 'http://[::ffff:192.168.1.1]',
    'http://127.0.0.1/api', 'http://127.0.0.1?x=y', 'http://127.0.0.1#x',
    'http://localhost:0', 'file:///etc/passwd'])
def test_loopback_rejects_ambiguous_urls(url):
    with pytest.raises(ValueError, match='loopback'):
        backend_url(url)


def test_localhost_is_pinned_without_dns():
    assert backend_url('http://localhost:8000') == 'http://127.0.0.1:8000'
    assert backend_url('http://[::1]:8000') == 'http://[::1]:8000'


def test_http_failures_are_sanitized(monkeypatch):
    secret = 'session5-synthetic-secret'
    monkeypatch.setenv('VIBECRAFT_API_KEY', secret)

    async def run():
        for status in (301, 307, 401, 403, 422, 503):
            calls = []

            def handler(request):
                calls.append(request)
                assert request.headers['X-API-Key'] == secret
                return httpx.Response(status, text=secret, headers={'location': 'https://example.org'})

            server = create_server(transport=httpx.MockTransport(handler))
            async with Client(server) as client:
                response = await client.call_tool('vibecraft_retrieve', {'params': {'q': 'test'}})
                assert response.is_error
                assert secret not in str(response)
                assert len(calls) == 1

        for error in (httpx.ConnectError(secret), httpx.ReadTimeout(secret)):
            def handler(request):
                raise error
            async with Client(create_server(transport=httpx.MockTransport(handler))) as client:
                response = await client.call_tool('vibecraft_retrieve', {'params': {'q': 'test'}})
                assert response.is_error and secret not in str(response)

    asyncio.run(run())


def test_real_stdio_exact_tools_equivalence_validation_and_no_secrets(capfd):
    calls = []
    secret = 'session5-synthetic-secret'

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers.get('X-API-Key') == secret
            calls.append(self.path)
            data = json.dumps({'results': [{'chunk_id': 'b', 'score': 0.9},
                                            {'chunk_id': 'a', 'score': 0.8}],
                               'index_version': 'synthetic', 'path': self.path}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{http.server_port}'

    async def run():
        env = {**os.environ, 'VIBECRAFT_MCP_BACKEND_URL': url, 'VIBECRAFT_API_KEY': secret}
        options = _build_agent_options('suggest', 'sonnet')
        config = options.mcp_servers['vibecraft']
        params = StdioServerParameters(command=config['command'], args=config['args'], env=env)
        async with Client(params) as client:
            listing = await client.list_tools()
            expected = {'vibecraft_retrieve': '/api/retrieve',
                        'vibecraft_code_search': '/api/code/search',
                        'vibecraft_graph_query': '/api/graph/query'}
            assert {tool.name for tool in listing.tools} == set(expected)
            assert {t for t in options.allowed_tools if t.startswith('mcp__')} == {
                'mcp__vibecraft__' + name for name in expected}
            assert all(tool.annotations.read_only_hint for tool in listing.tools)
            assert not (await client.list_resources()).resources
            assert not (await client.list_prompts()).prompts
            for name, path in expected.items():
                result = await client.call_tool(name, {'params': {'q': 'test'}})
                assert not result.is_error
                body = result.structured_content
                assert body['path'].startswith(path + '?')
                async with httpx.AsyncClient(trust_env=False) as equivalent:
                    response = await equivalent.get(url + body['path'], headers={'X-API-Key': secret})
                assert body == response.json()
                assert secret not in str(result)
            before = len(calls)
            for arguments in ({'q': ''}, {'q': 'x', 'k': 51}, {'q': 'x', 'url': 'https://example.org'},
                              {'q': 'x', 'k': True}, {'q': 'x', 'text_max_chars': 8001}):
                result = await client.call_tool('vibecraft_retrieve', {'params': arguments})
                assert result.is_error
            assert len(calls) == before
            assert all(p.startswith(tuple(expected.values())) for p in calls)

    try:
        asyncio.run(run())
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
    captured = capfd.readouterr()
    assert secret not in captured.out + captured.err


def test_response_limit_bad_json_and_total_deadline(monkeypatch):
    monkeypatch.setenv('VIBECRAFT_MCP_TIMEOUT_SECONDS', '0.1')

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(0.2)
            yield b'{}'

    async def run():
        responses = [httpx.Response(200, content=b'x' * (2 * 1024 * 1024 + 1)),
                     httpx.Response(200, text='not-json'),
                     httpx.Response(200, json=[]),
                     httpx.Response(200, stream=SlowBody())]
        for response in responses:
            server = create_server(transport=httpx.MockTransport(lambda request: response))
            async with Client(server) as client:
                result = await client.call_tool('vibecraft_graph_query', {'params': {'q': 'documenti'}})
                assert result.is_error
    asyncio.run(run())
