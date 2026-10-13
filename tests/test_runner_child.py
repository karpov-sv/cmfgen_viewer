import pytest

from cmfgen_viewer import runner_child


def test_macos_preserves_stack_without_attempting_rejected_limit_change(monkeypatch):
    monkeypatch.setattr(runner_child.sys, "platform", "darwin")

    def rejected(*args):
        pytest.fail("macOS stack limits must be preserved")

    monkeypatch.setattr(runner_child.resource, "getrlimit", rejected)
    monkeypatch.setattr(runner_child.resource, "setrlimit", rejected)
    runner_child._raise_stack_limit()


@pytest.mark.parametrize("hard", [64 * 1024**2, runner_child.resource.RLIM_INFINITY])
def test_linux_raises_stack_to_hard_limit(monkeypatch, hard):
    monkeypatch.setattr(runner_child.sys, "platform", "linux")
    monkeypatch.setattr(runner_child.resource, "getrlimit", lambda limit: (8 * 1024**2, hard))
    changes = []
    monkeypatch.setattr(runner_child.resource, "setrlimit", lambda *args: changes.append(args))
    runner_child._raise_stack_limit()
    assert changes == [(runner_child.resource.RLIMIT_STACK, (hard, hard))]


def test_macos_exec_bootstrap_raises_stack_using_positional_arguments(monkeypatch):
    monkeypatch.setattr(runner_child.sys, 'platform', 'darwin')
    monkeypatch.setattr(runner_child.resource, 'getrlimit', lambda _: (8 * 1024**2, 64 * 1024**2))
    command = runner_child._native_command('/tmp/executable with spaces')
    assert command[:2] == ['/bin/sh', '-c']
    assert command[-2:] == ['65536', '/tmp/executable with spaces']
    assert '/tmp/executable with spaces' not in command[2]


@pytest.mark.skipif(runner_child.sys.platform != 'darwin', reason='macOS inherited stack bootstrap')
def test_macos_bootstrap_preserves_lock_descriptor_and_resource_settings(tmp_path):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    executable = tmp_path / 'native check with spaces'
    executable.write_text(f'#!{sys.executable}\n' + '''import json,os,resource
print(json.dumps({'stack':resource.getrlimit(resource.RLIMIT_STACK),
                 'core':resource.getrlimit(resource.RLIMIT_CORE),
                 'inherited_fd':os.fstat(int(os.environ['TEST_LOCK_FD'])).st_ino}))
''')
    executable.chmod(0o755)
    descriptor = os.open(tmp_path / 'lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        expected = os.fstat(descriptor).st_ino
        result = subprocess.run([sys.executable, str(Path(runner_child.__file__)), str(executable), '--no-core-dumps'],
            env={**os.environ, 'TEST_LOCK_FD':str(descriptor)}, pass_fds=(descriptor,), capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data['stack'][0] == data['stack'][1]
        assert data['core'] == [0,0]
        assert data['inherited_fd'] == expected
    finally:
        os.close(descriptor)
