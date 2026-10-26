"""python -m silverlake.oracle {capture,diff,compare,scenarios}"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ..net import server as srv
from ..screens.signon import SignonController
from .client import CaptureError
from .diff import diff_captures
from .scenario import SCENARIOS, check_target, reanalyze, run_scenario

CAPTURES = Path("captures")


def _split(target: str) -> tuple[str, int]:
    host, _, port = target.rpartition(":")
    if not host:
        host, port = target, "23"
    return host, int(port)


async def _capture(target: str, scenario: str) -> dict:
    if target == "local":
        server = await srv.serve("127.0.0.1", 0, SignonController)
        try:
            port = server.sockets[0].getsockname()[1]
            return await run_scenario("127.0.0.1", port, scenario)
        finally:
            server.close()
            await server.wait_closed()
    host, port = _split(target)
    check_target(host, CAPTURES)
    return await run_scenario(host, port, scenario)


def _report(diffs: list[str]) -> int:
    if not diffs:
        print("no structural differences")
        return 0
    print("\n".join(diffs))
    print(f"\n{len(diffs)} difference(s)")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="silverlake.oracle")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="run a scenario against a host and save the capture")
    c.add_argument("target", help="host:port, or 'local' for an in-process Silverlake")
    c.add_argument("scenario", choices=sorted(SCENARIOS))
    c.add_argument("--out", type=Path, required=True)

    d = sub.add_parser("diff", help="structural diff of two capture files (A is the reference)")
    d.add_argument("a", type=Path)
    d.add_argument("b", type=Path)
    d.add_argument("--text", action="store_true", help="also compare wording (local use only)")
    d.add_argument("--fields-only", action="store_true")

    m = sub.add_parser("compare", help="run a scenario on local Silverlake and diff against a saved capture")
    m.add_argument("real", type=Path, help="saved capture of the reference system")
    m.add_argument("--text", action="store_true")
    m.add_argument("--fields-only", action="store_true")

    sub.add_parser("scenarios", help="list scenarios")

    args = p.parse_args(argv)
    try:
        if args.cmd == "scenarios":
            for name, actions in sorted(SCENARIOS.items()):
                print(f"{name}  ({len(actions)} action(s))")
            return 0
        if args.cmd == "capture":
            result = asyncio.run(_capture(args.target, args.scenario))
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2))
            print(f"saved {len(result['snapshots'])} screen(s) to {args.out}")
            return 0
        if args.cmd == "diff":
            a, b = (reanalyze(json.loads(f.read_text())) for f in (args.a, args.b))
            return _report(diff_captures(a, b, args.text, args.fields_only))
        real = reanalyze(json.loads(args.real.read_text()))
        mine = asyncio.run(_capture("local", real["scenario"]))
        return _report(diff_captures(real, mine, args.text, args.fields_only))
    except CaptureError as exc:
        print(f"silverlake.oracle: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
