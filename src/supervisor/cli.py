def supervisor_main(args):
    from src.supervisor.server import run_supervisor
    return run_supervisor(base_dir=args.base_dir, ws_port=args.ws_port, http_port=args.http_port)
