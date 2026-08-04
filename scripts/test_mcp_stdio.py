#!/usr/bin/env python3
"""Minimal MCP stdio handshake test for data-contract-mcp-server."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time


def read_line(stream, timeout: float = 10.0) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = stream.readline()
        if line:
            return line.decode().strip()
        if stream.closed:
            return None
        time.sleep(0.05)
    return None


def main() -> int:
    cmd = sys.argv[1:]
    if not cmd:
        print("usage: test_mcp_stdio.py <server-command> [args...]", file=sys.stderr)
        return 2

    env = os.environ.copy()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert proc.stdin and proc.stdout and proc.stderr

    def drain_stderr() -> None:
        assert proc.stderr
        for line in proc.stderr:
            text = line.decode(errors="replace").rstrip()
            if text:
                print(f"[stderr] {text}", file=sys.stderr)

    threading.Thread(target=drain_stderr, daemon=True).start()

    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-test", "version": "1.0"},
        },
    }
    proc.stdin.write((json.dumps(init) + "\n").encode())
    proc.stdin.flush()

    line = read_line(proc.stdout)
    if not line:
        proc.kill()
        print("FAIL: no initialize response", file=sys.stderr)
        return 1

    response = json.loads(line)
    if "error" in response:
        print(f"FAIL: initialize error: {response['error']}", file=sys.stderr)
        proc.kill()
        return 1

    server_info = response.get("result", {}).get("serverInfo", {})
    print(f"OK initialize: server={server_info.get('name')} version={server_info.get('version')}")

    proc.stdin.write(
        (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode()
    )
    proc.stdin.flush()

    tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    proc.stdin.write((json.dumps(tools_req) + "\n").encode())
    proc.stdin.flush()

    line = read_line(proc.stdout)
    if not line:
        proc.kill()
        print("FAIL: no tools/list response", file=sys.stderr)
        return 1

    tools_resp = json.loads(line)
    if "error" in tools_resp:
        print(f"FAIL: tools/list error: {tools_resp['error']}", file=sys.stderr)
        proc.kill()
        return 1

    tools = tools_resp.get("result", {}).get("tools", [])
    print(f"OK tools/list: {len(tools)} tools")
    for tool in tools[:5]:
        print(f"  - {tool.get('name')}")
    if len(tools) > 5:
        print(f"  ... and {len(tools) - 5} more")

    proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
