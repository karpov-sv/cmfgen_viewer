"""Private single-process bootstrap: apply resource limits, then exec directly.

Kept separate to avoid preexec_fn in a future multithreaded app worker.
"""
import argparse
import os
import resource
import sys


def _raise_stack_limit():
    # macOS reserves the main-thread stack at link time (-Wl,-stack_size,...).
    # Raising RLIMIT_STACK from Python can fail even at the reported hard limit.
    if sys.platform == "darwin":
        return
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    if soft != hard:
        resource.setrlimit(resource.RLIMIT_STACK, (hard, hard))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable")
    parser.add_argument("--memory-mib", type=int)
    parser.add_argument("--no-core-dumps", action="store_true")
    args = parser.parse_args()
    if args.memory_mib is not None:
        limit = args.memory_mib * 1024**2
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    if args.no_core_dumps:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _raise_stack_limit()
    os.execv(args.executable, [args.executable])


if __name__ == "__main__":
    main()
