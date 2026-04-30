import argparse
import filecmp
import json
import shutil
import sys
import urllib.request
from pathlib import Path


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
    sup_parser.add_argument(
        "--supervisor-ws-url",
        default=None,
        help="Externally accessible Supervisor WebSocket URL (e.g. ws://host:port/workers). Defaults to ws://localhost:<ws-port>/workers",
    )
    sup_parser.set_defaults(func=_supervisor_command)

    sync_parser = subparsers.add_parser(
        "sync-models", help="Synchronize global templates into world-private agents/"
    )
    sync_parser.add_argument(
        "--world-dir", required=True, help="Path to world directory"
    )
    sync_parser.add_argument(
        "--force", action="store_true", help="Force overwrite existing files"
    )
    sync_parser.set_defaults(func=_sync_models_command)

    list_parser = subparsers.add_parser(
        "list-instances", help="List all instances in a running world"
    )
    list_parser.add_argument("--world-id", required=True, help="World ID")
    list_parser.add_argument(
        "--supervisor-url", default="http://localhost:8080", help="Supervisor HTTP URL"
    )
    list_parser.set_defaults(func=_list_instances_command)

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


def _sync_models_command(args):
    return sync_models(args.world_dir, force=args.force)


def _list_instances_command(args):
    url = f"{args.supervisor_url}/api/worlds/{args.world_id}/instances"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Error: HTTP {e.code} - {e.reason}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

    instances = data.get("instances", [])
    if not instances:
        print(f"No instances found in world '{args.world_id}'")
        return 0

    print(f"Instances in world '{args.world_id}':")
    print(f"{'ID':<20} {'Model':<20} {'Scope':<10} {'State':<15} {'Lifecycle':<10}")
    print("-" * 80)
    for inst in instances:
        print(
            f"{inst['id']:<20} {inst['model']:<20} {inst['scope']:<10} "
            f"{inst.get('state', 'N/A'):<15} {inst.get('lifecycle_state', 'N/A'):<10}"
        )
    return 0


def sync_models(world_dir: str, force: bool = False) -> int:
    """Synchronize global templates into world-private agents/."""
    from src.runtime.model_resolver import ModelResolver

    world_path = Path(world_dir)
    world_agents = world_path / "agents"

    # Discover global models
    global_paths = ["agents"]  # Default global path
    # TODO: read from config if available

    global_models: dict[str, Path] = {}
    for gp_str in global_paths:
        gp = Path(gp_str)
        if not gp.exists():
            continue
        for model_dir in gp.rglob("*/model"):
            if not model_dir.is_dir():
                continue
            model_id = model_dir.parent.name
            if model_id not in global_models:
                global_models[model_id] = model_dir

    # Discover world models
    world_models: dict[str, Path] = {}
    if world_agents.exists():
        for model_dir in world_agents.rglob("*/model"):
            if not model_dir.is_dir():
                continue
            model_id = model_dir.parent.name
            world_models[model_id] = model_dir

    resolver = ModelResolver(str(world_dir), global_paths)
    any_changes = False

    for model_id, template_dir in sorted(global_models.items()):
        if model_id in world_models:
            print(f"[SYNC] {model_id}")
            changed, force = _sync_single_model(template_dir, world_models[model_id], force)
            any_changes = any_changes or changed

            # Sync libs/ directory if present in template
            template_agent_dir = template_dir.parent
            template_libs_dir = template_agent_dir / "libs"
            if template_libs_dir.exists():
                world_agent_dir = world_models[model_id].parent
                world_libs_dir = world_agent_dir / "libs"
                changed_libs, force = _sync_single_model(
                    template_libs_dir, world_libs_dir, force
                )
                any_changes = any_changes or changed_libs
        else:
            print(f"[ADD] {model_id}")
            try:
                resolver._copy_from_template(template_dir, _find_global_root(template_dir, global_paths))
                any_changes = True
            except Exception as e:
                print(f"  [ERROR] Failed to copy {model_id}: {e}")

    private_models = set(world_models) - set(global_models)
    for model_id in sorted(private_models):
        print(f"[SKIP] {model_id}")

    # Synchronize shared/libs/ directory
    global_shared_libs = Path("agents/shared/libs")
    if global_shared_libs.exists():
        world_shared_libs = world_agents / "shared/libs"
        changed_libs, force = _sync_single_model(
            global_shared_libs, world_shared_libs, force
        )
        if changed_libs:
            print("[ADD] shared/libs")
        any_changes = any_changes or changed_libs

    if not any_changes and not private_models:
        print("No changes needed.")
    return 0


def _find_global_root(template_dir: Path, global_paths: list[str]) -> Path:
    """Find which global root a template directory belongs to."""
    if not global_paths:
        raise ValueError("global_paths is empty")
    for gp_str in global_paths:
        gp = Path(gp_str)
        try:
            template_dir.relative_to(gp)
            return gp
        except ValueError:
            continue
    raise ValueError(f"template_dir {template_dir} is not under any global path: {global_paths}")


def _sync_single_model(template_dir: Path, world_dir: Path, force: bool) -> tuple[bool, bool]:
    """Sync a single model directory, returning (changed, force)."""
    changed = False
    for src_file in template_dir.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(template_dir)
        dst_file = world_dir / rel

        if not dst_file.exists():
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            print(f"  [ADD] {rel}")
            changed = True
            continue

        if filecmp.cmp(src_file, dst_file, shallow=False):
            continue  # Identical content, skip

        if force:
            shutil.copy2(src_file, dst_file)
            print(f"  [OVERWRITE] {rel}")
            changed = True
        else:
            answer = input(f"  Conflict: {rel}. Overwrite? [Y/n/a(ll)/s(kip)] ")
            ans = answer.strip().lower()
            if ans in ("y", ""):
                shutil.copy2(src_file, dst_file)
                print(f"  [OVERWRITE] {rel}")
                changed = True
            elif ans == "a":
                force = True
                print("Force mode enabled for all remaining files.")
                shutil.copy2(src_file, dst_file)
                print(f"  [OVERWRITE] {rel}")
                changed = True
            # n or s -> skip
    return changed, force


if __name__ == "__main__":
    sys.exit(main())
