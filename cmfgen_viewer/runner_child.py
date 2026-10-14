"""Private single-process bootstrap: apply resource limits, then exec native code.

Kept separate to avoid preexec_fn in a future multithreaded app worker.
"""
import argparse
import os
import resource
import sys


def _raise_stack_limit():
    # macOS can reject growth of the running Python process's stack. Its
    # shell/exec bootstrap below changes the inherited limit before native exec.
    if sys.platform == "darwin":
        return
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    if soft != hard:
        resource.setrlimit(resource.RLIMIT_STACK, (hard, hard))


def _native_command(executable):
    if sys.platform == "darwin":
        soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
        if soft != hard:
            limit = "unlimited" if hard == resource.RLIM_INFINITY else str(hard // 1024)
            # Fixed internal bootstrap only: executable paths remain positional
            # arguments. No model scripts or shell setup are sourced.
            return ["/bin/sh", "-c", 'ulimit -S -s "$1" || exit; shift; exec "$@"',
                    "cmfgen-stack", limit, executable]
    return [executable]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable")
    parser.add_argument("--memory-mib", type=int)
    parser.add_argument("--no-core-dumps", action="store_true")
    args = parser.parse_args()
    if args.memory_mib is not None:
        if sys.platform == "darwin":
            parser.error("--memory-mib is unsupported on macOS; omit it to inherit host limits")
        limit = args.memory_mib * 1024**2
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (OSError, ValueError) as exc:
            parser.error(f"Cannot apply --memory-mib={args.memory_mib}: {exc}")
    if args.no_core_dumps:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _raise_stack_limit()
    command = _native_command(args.executable)
    os.execv(command[0], command)


if __name__ == "__main__":
    main()
