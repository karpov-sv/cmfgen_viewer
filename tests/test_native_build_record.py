"""Final native links must preserve an already mapped/running executable."""
from pathlib import Path
import hashlib
import json
import os
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


def built_checkout(tmp_path, monkeypatch, *, newer_library=False, newer_source=False, fail=False):
    root, names = prepare(tmp_path, monkeypatch, fail=fail)
    (root/'lib').mkdir()
    source = root/'scientific.f'
    source.write_text('validated scientific source')
    os.utime(source, ns=(100, 300 if newer_source else 100))
    for name in names:
        os.utime(root/'exe'/name, ns=(200, 200))
    for name in ('libsubs.a', 'libmod.a'):
        library = root/'lib'/name
        library.write_bytes(b'compiled library')
        os.utime(library, ns=(100, 300 if newer_library else 100))
    manifest = {'patch_sha256': 'validated patch', 'files': [
        {'path': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]}
    return root, names, manifest


def test_normal_recursive_build_automatically_finalizes_links(tmp_path, monkeypatch):
    helper = runpy.run_path(str(HELPER))
    root, names, manifest = built_checkout(tmp_path, monkeypatch, newer_library=True)
    result = helper['finalize'](root, manifest)
    assert len(result['final_link_commands']) == 3
    assert all((root/'exe'/name).read_bytes() == b'new executable' for name in names)
    saved = json.loads((root/'cmfgen-local-build.json').read_text())
    assert saved == result
    assert saved['executables'][names[0]]['sha256'] == hashlib.sha256(b'new executable').hexdigest()


def test_current_build_does_not_relink(tmp_path, monkeypatch):
    helper = runpy.run_path(str(HELPER))
    root, names, manifest = built_checkout(tmp_path, monkeypatch)
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: pytest.fail('Unexpected relink'))
    result = helper['finalize'](root, manifest)
    assert 'final_link_commands' not in result
    assert all((root/'exe'/name).read_bytes() == b'previous executable' for name in names)


@pytest.mark.parametrize('mode', ['auto', 'always'])
def test_relink_cannot_mask_unbuilt_source_change(tmp_path, monkeypatch, mode):
    helper = runpy.run_path(str(HELPER))
    root, names, manifest = built_checkout(tmp_path, monkeypatch, newer_source=True)
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: pytest.fail('Unexpected relink'))
    with pytest.raises(ValueError, match='predates scientific source'):
        helper['finalize'](root, manifest, link_mode=mode)
    assert not (root/'cmfgen-local-build.json').exists()


def test_changed_source_is_rejected_before_relink(tmp_path, monkeypatch):
    helper = runpy.run_path(str(HELPER))
    root, names, manifest = built_checkout(tmp_path, monkeypatch, newer_library=True)
    (root/'scientific.f').write_text('unknown scientific source')
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: pytest.fail('Unexpected relink'))
    with pytest.raises(ValueError, match='Source differs'):
        helper['finalize'](root, manifest)


def test_failed_automatic_link_preserves_previous_record(tmp_path, monkeypatch):
    helper = runpy.run_path(str(HELPER))
    root, names, manifest = built_checkout(tmp_path, monkeypatch, newer_library=True, fail=True)
    previous = root/'cmfgen-local-build.json'
    previous.write_text('{"previous": true}\n')
    with pytest.raises(subprocess.CalledProcessError):
        helper['finalize'](root, manifest)
    assert previous.read_text() == '{"previous": true}\n'


def test_no_relink_mode_refuses_stale_links(tmp_path, monkeypatch):
    helper = runpy.run_path(str(HELPER))
    root, names, manifest = built_checkout(tmp_path, monkeypatch, newer_library=True)
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: pytest.fail('Unexpected relink'))
    with pytest.raises(ValueError, match='predates source/libraries'):
        helper['finalize'](root, manifest, link_mode='never')
    assert not (root/'cmfgen-local-build.json').exists()


@pytest.fixture
def captured_build(tmp_path):
    root = tmp_path/'cmfgen'
    files = {'new_main/model.f': b'validated scientific source',
             'new_main/mod_subs/Makefile': b'validated forwarding rule',
             'Makefile_definitions': b'captured foreign platform options',
             'com/aliases_for_cmfgen.sh': b'captured foreign aliases'}
    manifest = {'patch_sha256': 'validated patch digest', 'files': []}
    for name, contents in files.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        os.utime(path, ns=(1, 1))
        manifest['files'].append({'path': name, 'sha256': hashlib.sha256(contents).hexdigest()})
    (root/'Makefile_definitions').write_bytes(b'local macOS compiler options')
    (root/'com/aliases_for_cmfgen.sh').write_bytes(b'local directory aliases')
    for name in ['lib/libsubs.a', 'lib/libmod.a', 'exe/cmfgen_dev.exe',
                 'exe/cmf_flux.exe', 'exe/obs_frame.exe']:
        path = root/name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'existing build product')
        os.utime(path, ns=(2, 2))
    return root, manifest


@pytest.mark.parametrize('missing', [False, True])
def test_record_refuses_missing_captured_build_fix(captured_build, missing):
    helper = runpy.run_path(str(HELPER))
    root, manifest = captured_build
    path = root/'new_main/mod_subs/Makefile'
    if missing:
        path.unlink()
    else:
        path.write_bytes(b'old Makefile without forwarding rule')
    with pytest.raises(ValueError, match='new_main/mod_subs/Makefile'):
        helper['record'](root, manifest)
    assert not (root/'cmfgen-local-build.json').exists()


def test_record_captures_build_rules_and_preserves_local_platform_settings(captured_build):
    helper = runpy.run_path(str(HELPER))
    root, manifest = captured_build
    result = helper['record'](root, manifest)
    assert result['build_files'] == {'new_main/mod_subs/Makefile': manifest['files'][1]['sha256']}
    assert result['sources'] == {'new_main/model.f': manifest['files'][0]['sha256']}
    assert (root/'Makefile_definitions').read_bytes() == b'local macOS compiler options'
    assert (root/'com/aliases_for_cmfgen.sh').read_bytes() == b'local directory aliases'


@pytest.mark.parametrize('mode', ['auto', 'always'])
def test_missing_build_fix_is_rejected_before_final_links(tmp_path, monkeypatch, mode):
    helper = runpy.run_path(str(HELPER))
    root, names, manifest = built_checkout(tmp_path, monkeypatch, newer_library=True)
    path = root/'new_main/mod_subs/Makefile'
    path.parent.mkdir(parents=True)
    expected = b'validated forwarding rule'
    manifest['files'].append({'path': 'new_main/mod_subs/Makefile',
                              'sha256': hashlib.sha256(expected).hexdigest()})
    path.write_bytes(b'old Makefile without forwarding rule')
    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **k: pytest.fail('Unexpected relink'))
    with pytest.raises(ValueError, match='Build file differs'):
        helper['finalize'](root, manifest, link_mode=mode)
    assert not (root/'cmfgen-local-build.json').exists()
    assert all((root/'exe'/name).read_bytes() == b'previous executable' for name in names)
