"""Final native links must preserve an already mapped/running executable."""
from pathlib import Path
import runpy
import shlex
import subprocess

import pytest


HELPER = Path(__file__).resolve().parents[1]/'doc/developer/cmfgen-review-tests/record_local_build.py'


def prepare(tmp_path, monkeypatch, fail=False):
    root = tmp_path/'cmfgen'
    (root/'exe').mkdir(parents=True)
    names = ['cmfgen_dev.exe', 'cmf_flux.exe', 'obs_frame.exe']
    for name in names:
        (root/'exe'/name).write_bytes(b'previous executable')

    def dry_run(args, **kwargs):
        selected = names[:1] if args[args.index('-C')+1].endswith('new_main') else names[1:]
        return '\n'.join(shlex.join(['compiler', 'objects.o', '-o', str(root/'exe'/name)]) for name in selected)

    def link(args, **kwargs):
        if fail:
            raise subprocess.CalledProcessError(1, args)
        target = Path(args[args.index('-o')+1])
        assert target.parent != root/'exe'
        target.write_bytes(b'new executable')

    monkeypatch.setattr(subprocess, 'check_output', dry_run)
    monkeypatch.setattr(subprocess, 'run', link)
    return root, names


def test_final_links_replace_paths_without_modifying_open_executable(tmp_path, monkeypatch):
    helper = runpy.run_path(str(HELPER))
    root, names = prepare(tmp_path, monkeypatch)
    with (root/'exe'/names[0]).open('rb') as active:
        commands = helper['relink'](root)
        assert active.read() == b'previous executable'
    assert all((root/'exe'/name).read_bytes() == b'new executable' for name in names)
    assert len(commands) == 3
    assert all(c['installation'] == 'atomic replacement' for c in commands)
    assert not list((root/'exe').glob('.cmfgen-link-*'))


def test_failed_link_preserves_installed_executable(tmp_path, monkeypatch):
    helper = runpy.run_path(str(HELPER))
    root, names = prepare(tmp_path, monkeypatch, fail=True)
    with pytest.raises(subprocess.CalledProcessError):
        helper['relink'](root)
    assert all((root/'exe'/name).read_bytes() == b'previous executable' for name in names)
    assert not list((root/'exe').glob('.cmfgen-link-*'))
