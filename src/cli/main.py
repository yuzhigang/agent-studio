import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent-studio")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run a single project in isolated process mode"
    )
    run_parser.add_argument(
        "--project-dir", required=True, help="Path to project directory"
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
        "run-inline", help="Run multiple projects in the current process"
    )
    inline_parser.add_argument(
        "--project-dir",
        action="append",
        required=True,
        help="Path to project directory (can be repeated)",
    )
    inline_parser.set_defaults(func=_run_inline_command)

    sup_parser = subparsers.add_parser(
        "supervisor", help="Start the Supervisor management plane"
    )
    sup_parser.add_argument(
        "--base-dir", default="projects", help="Base directory containing projects"
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
    from src.worker.cli.run_command import run_project
    return run_project(
        project_dir=args.project_dir,
        supervisor_ws=args.supervisor_ws,
        ws_port=args.ws_port,
        force_stop_on_shutdown=args.force_stop_on_shutdown,
    )


def _run_inline_command(args):
    from src.worker.cli.run_inline import run_inline
    return run_inline(project_dirs=args.project_dir)


def _supervisor_command(args):
    from src.supervisor.cli import supervisor_main
    return supervisor_main(args)


if __name__ == "__main__":
    sys.exit(main())
