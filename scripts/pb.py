#!/usr/bin/env python3
"""pb — push research findings from this machine into production.

The sync endpoints are not reachable from the internet: nginx refuses
``/api/admin/sync/`` and this client opens its own SSH tunnel to uvicorn on the
VPS for the duration of a command. The token is a second factor, not the only
one.

Standard library only, by design — nothing gets installed on this machine.

    pb requests [--status new]          what is waiting
    pb claim 7                          new -> in_progress
    pb prod 175376051 204741372         what production already holds
    pb push 7 bundle.json               DRY RUN, prints the diff
    pb push 7 bundle.json --apply       commits
    pb push-bulk bundle.json [--apply]  bundle not tied to a request

Reads RESEARCH_API_TOKEN and VPS_HOST/VPS_USER/VPS_PORT from the repo .env.
Never prints the token or the host.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_PORT = 8787
REMOTE_PORT = 8000
TUNNEL_TIMEOUT = 15.0


def load_env(path: Path) -> dict:
    """Minimal .env reader — KEY=value, ignoring blanks, comments and `export`."""
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


class Tunnel:
    """SSH port-forward held open for the duration of one command."""

    def __init__(self, env: dict):
        self.host = env.get("VPS_HOST", "app.example.com")
        self.user = env.get("VPS_USER", "mvp")
        self.port = env.get("VPS_PORT", "22")
        self.proc: Optional[subprocess.Popen] = None

    def __enter__(self) -> str:
        self.proc = subprocess.Popen(
            ["ssh", "-N", "-p", self.port,
             "-L", f"{LOCAL_PORT}:127.0.0.1:{REMOTE_PORT}",
             f"{self.user}@{self.host}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        deadline = time.time() + TUNNEL_TIMEOUT
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise SystemExit("ssh tunnel failed to start — check your SSH access")
            with socket.socket() as sock:
                sock.settimeout(0.3)
                if sock.connect_ex(("127.0.0.1", LOCAL_PORT)) == 0:
                    return f"http://127.0.0.1:{LOCAL_PORT}"
            time.sleep(0.3)
        self.__exit__(None, None, None)
        raise SystemExit("ssh tunnel did not come up within 15s")

    def __exit__(self, *exc) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=5)


def call(base: str, token: str, method: str, path: str,
         params: Optional[list] = None, body: Optional[dict] = None) -> dict:
    url = base + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Sync-Token", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read() or "null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}")


def format_report(body: dict) -> str:
    """Human-readable push result. Never includes credentials."""
    head = "DRY RUN — nothing was written" if body["dry_run"] else "APPLIED"
    lines = [head]
    if body.get("request_id") is not None:
        lines.append(f"request {body['request_id']} -> status {body.get('status')}")
    for table, stat in sorted(body.get("tables", {}).items()):
        lines.append(
            f"  {table:<16} created {stat['created']}  updated {stat['updated']}"
            f"  unchanged {stat['unchanged']}  skipped {stat['skipped']}"
        )
    changes = body.get("changes") or []
    if changes:
        lines.append("  changes:")
        for c in changes:
            lines.append(f"    {c['table']} {c['key']}: {c['field']} "
                         f"{c['from']!r} -> {c['to']!r}")
    for w in body.get("warnings") or []:
        lines.append(f"  ! {w}")
    return "\n".join(lines)


def format_requests(rows: list) -> str:
    if not rows:
        return "nothing waiting"
    out = []
    for r in rows:
        checked = r.get("court_checked_at") or "never"
        out.append(
            f"#{r['id']:<4} {r['status']:<12} {r['order_type']:<15} "
            f"{(r['company_eik'] or '—'):<11} {r['company_name'][:34]:<34} "
            f"in_db={'y' if r['in_db'] else 'n'} court={checked}"
        )
    return "\n".join(out)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="pb", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("requests", help="list research requests")
    p.add_argument("--status", default="new")

    p = sub.add_parser("claim", help="mark a request in_progress")
    p.add_argument("request_id", type=int)

    p = sub.add_parser("prod", help="what production holds for these ЕИКs")
    p.add_argument("eik", nargs="+")

    p = sub.add_parser("push", help="push findings for a request")
    p.add_argument("request_id", type=int)
    p.add_argument("bundle", type=Path)
    p.add_argument("--apply", action="store_true", help="commit (default: dry run)")

    p = sub.add_parser("push-bulk", help="push a bundle not tied to a request")
    p.add_argument("bundle", type=Path)
    p.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)

    env = load_env(REPO_ROOT / ".env")
    token = env.get("RESEARCH_API_TOKEN")
    if not token:
        raise SystemExit("RESEARCH_API_TOKEN is not set in .env")

    with Tunnel(env) as base:
        if args.cmd == "requests":
            print(format_requests(
                call(base, token, "GET", "/api/admin/sync/requests",
                     params=[("status", args.status)])))
        elif args.cmd == "claim":
            body = call(base, token, "POST",
                        f"/api/admin/sync/requests/{args.request_id}/claim")
            print(f"request {body['id']} -> {body['status']}")
        elif args.cmd == "prod":
            body = call(base, token, "GET", "/api/admin/sync/entities",
                        params=[("eik", e) for e in args.eik])
            print(json.dumps(body, indent=2, ensure_ascii=False))
        elif args.cmd in ("push", "push-bulk"):
            bundle = json.loads(args.bundle.read_text())
            params = [("dry_run", "false" if args.apply else "true")]
            path = ("/api/admin/sync/bundle" if args.cmd == "push-bulk"
                    else f"/api/admin/sync/requests/{args.request_id}/findings")
            print(format_report(
                call(base, token, "POST", path, params=params, body=bundle)))
            if not args.apply:
                print("\nre-run with --apply to commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
