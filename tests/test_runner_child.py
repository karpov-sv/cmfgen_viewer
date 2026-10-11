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
