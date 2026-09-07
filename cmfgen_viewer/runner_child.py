"""Private single-process bootstrap: apply resource limits, then exec directly.

Kept separate to avoid preexec_fn in a future multithreaded app worker.
"""
import os
import resource
import sys


def main():
    executable, memory_mib = sys.argv[1:3]
    limit = int(memory_mib) * 1024**2
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    resource.setrlimit(resource.RLIMIT_STACK, (hard, hard))
    os.execv(executable, [executable])


if __name__ == "__main__":
    main()
