import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent-studio")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run worker process loading all worlds from base directory"
    )
    run_parser.add_argument(
        "--base-dir", required=True, help="Base directory containing world subdirectories"
    )
    run_parser.add_argument(
        "--supervisor-ws", default=None, help="Supervisor WebSocket URL to register with"
    )
    run_parser.add_argument(
        "--ws-port", type=int, default=None, help="Local WebSocket port to expose"
    )
    run_parser.add_argument(
        "--force-stop-on-shutdown",
        type=lambda x: x.lower() == "true",
        default=None,
        help="Force stop isolated scenes on shutdown",
    )
    run_parser.set_defaults(func=_run_command)

    inline_parser = subparsers.add_parser(
        "run-inline", help="Run multiple worlds in the current process"
    )
    inline_parser.add_argument(
        "--world-dir",
        action="append",
        required=True,
        help="Path to world directory (can be repeated)",
    )
    inline_parser.add_argument(
        "--supervisor-ws",
        default=None,
        help="Supervisor WebSocket URL for loopback registration",
    )
    inline_parser.set_defaults(func=_run_inline_command)

    sup_parser = subparsers.add_parser(
        "supervisor", help="Start the Supervisor management plane"
    )
    sup_parser.add_argument(
        "--base-dir", default="worlds", help="Base directory containing worlds"
    )
    sup_parser.add_argument(
        "--ws-port", type=int, default=8001, help="WebSocket port for runtime registration"
    )
    sup_parser.add_argument(
        "--http-port", type=int, default=8080, help="HTTP port for management API"
    )
    sup_parser.set_defaults(func=_supervisor_command)

    args = parser.parse_args(argv)
    return args.func(args)


def _run_command(args):
    from src.worker.cli.run_command import run_world
    return run_world(
        base_dir=args.base_dir,
        supervisor_ws=args.supervisor_ws,
        ws_port=args.ws_port,
        force_stop_on_shutdown=args.force_stop_on_shutdown,
    )


def _run_inline_command(args):
    from src.worker.cli.run_inline import run_inline
    return run_inline(
        world_dirs=args.world_dir,
        supervisor_ws=args.supervisor_ws,
    )


def _supervisor_command(args):
    from src.supervisor.cli import supervisor_main
    return supervisor_main(args)


if __name__ == "__main__":
    sys.exit(main())
