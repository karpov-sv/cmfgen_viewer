"""Real git application/update with settings preservation and transactional rollback."""
import difflib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess

import pytest

SPEC = importlib.util.spec_from_file_location('cmfgen_patch', Path(__file__).resolve().parents[1]/'cmfgen_patch.py')
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)

BASE = {'new_main/a.f': b'      A=1\n', 'new_main/obsolete.f': b'      ORIGINAL=1\n',
        'Makefile_definitions': b'vendor setup\n', 'com/aliases_for_cmfgen.sh': b'vendor paths\n'}


def release(folder, changes, revision):
    folder.mkdir()
    after = {**BASE, **changes}
    after['new_main/cmfgen_version.inc'] = f"      PATCH_REVISION='{revision}'\n".encode()
    after['Makefile_definitions'] = b'foreign platform setup\n'
    after['com/aliases_for_cmfgen.sh'] = b'foreign directories\n'
    files, sections = [], []
    for name in sorted(BASE.keys() | after.keys()):
        before, target = BASE.get(name), after.get(name)
        if before == target:
            continue
        item = {'path': name, 'status': 'added' if before is None else 'deleted' if target is None else 'modified',
                'sha256': patcher.digest(target) if target is not None else None}
        if before is not None:
            item['baseline_sha256'] = patcher.digest(before)
        files.append(item)
        header = f'diff --git a/{name} b/{name}\n'
        if before is None:
            header += 'new file mode 100644\n'
        if target is None:
            header += 'deleted file mode 100644\n'
        sections.append(header+''.join(difflib.unified_diff(
            before.decode().splitlines(True) if before is not None else [],
            target.decode().splitlines(True) if target is not None else [],
            fromfile='a/'+name if before is not None else '/dev/null',
            tofile='b/'+name if target is not None else '/dev/null')))
    patch = ''.join(sections).encode()
    manifest = {'schema_version': 1, 'baseline_release': 'test-release', 'patch_file': 'source.patch',
                'patch_sha256': patcher.digest(patch), 'files': files,
                'dated_patch_version': {'revision': revision}}
    (folder/'source.patch').write_bytes(patch)
    (folder/'manifest.json').write_text(json.dumps(manifest))
    return folder/'manifest.json', after


@pytest.fixture
def tree(tmp_path):
    root = tmp_path/'cmfgen';root.mkdir()
    for name, data in BASE.items():
        path = root/name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)
    (root/'Makefile_definitions').write_bytes(b'my Linux compiler settings\n')
    (root/'com/aliases_for_cmfgen.sh').write_bytes(b'my local directories\n')
    (root/'unrelated.f').write_bytes(b'private unrelated work\n')
    return root


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def assert_settings(root):
    assert (root/'Makefile_definitions').read_bytes() == b'my Linux compiler settings\n'
    assert (root/'com/aliases_for_cmfgen.sh').read_bytes() == b'my local directories\n'
    assert (root/'unrelated.f').read_bytes() == b'private unrelated work\n'


def test_preview_is_read_only_and_fresh_install_preserves_settings(tmp_path, tree):
    manifest, after = release(tmp_path/'release', {'new_main/a.f': b'      A=2\n'}, '2026-10-31.1')
    before = snapshot(tree)
    check = patcher.update(tree, manifest, check=True)
    assert check['status'] == 'ready' and not check['errors']
    assert snapshot(tree) == before
    assert not (tree/patcher.STATE_DIR).exists()
    report = patcher.update(tree, manifest)
    assert report['status'] == 'applied'
    assert (tree/'new_main/a.f').read_bytes() == after['new_main/a.f']
    assert (Path(report['backup'])/'files/new_main/a.f').read_bytes() == BASE['new_main/a.f']
    assert_settings(tree)
    state = patcher.read_state(tree)
    assert state.sha == json.loads(manifest.read_text())['patch_sha256']
    unchanged = snapshot(tree)
    assert patcher.update(tree, manifest)['status'] == 'current'
    assert snapshot(tree) == unchanged


def test_update_replaces_old_patch_and_retires_removed_hunk(tmp_path, tree):
    first, _ = release(tmp_path/'first', {'new_main/a.f': b'      A=2\n',
                     'new_main/obsolete.f': b'      OLD_FIX=1\n'}, '2026-10-31.1')
    second, after = release(tmp_path/'second', {'new_main/a.f': b'      A=3\n',
                           'new_main/new.f': b'      NEW_FIX=1\n'}, '2026-11-01.1')
    patcher.update(tree, first)
    result = patcher.update(tree, second)
    assert result['status'] == 'applied'
    for name in ['new_main/a.f', 'new_main/new.f', 'new_main/obsolete.f']:
        assert (tree/name).read_bytes() == after[name]
    assert_settings(tree)
    assert patcher.read_state(tree).revision == '2026-11-01.1'


def test_local_edit_blocks_all_writes(tmp_path, tree):
    first, _ = release(tmp_path/'first', {'new_main/a.f': b'      A=2\n'}, '2026-10-31.1')
    second, _ = release(tmp_path/'second', {'new_main/a.f': b'      A=3\n'}, '2026-11-01.1')
    patcher.update(tree, first)
    (tree/'new_main/a.f').write_bytes(b'my private edits\n')
    before = snapshot(tree)
    assert patcher.update(tree, second, check=True)['errors']
    with pytest.raises(patcher.PatchError, match='unrecognized local edits'):
        patcher.update(tree, second)
    assert snapshot(tree) == before


@pytest.mark.parametrize('after_replace', [False, True])
def test_failed_install_restores_original_source(tmp_path, tree, monkeypatch, after_replace):
    manifest, _ = release(tmp_path/'release', {'new_main/a.f': b'      A=2\n'}, '2026-10-31.1')
    write = patcher.atomic_write
    count = 0
    def fail(path, data, mode=0o644):
        nonlocal count
        count += 1
        if count == 2:
            if after_replace:
                write(path, data, mode)
            raise OSError('injected write failure')
        write(path, data, mode)
    monkeypatch.setattr(patcher, 'atomic_write', fail)
    with pytest.raises(patcher.PatchError, match='rolled back'):
        patcher.update(tree, manifest)
    assert (tree/'new_main/a.f').read_bytes() == BASE['new_main/a.f']
    assert not (tree/'new_main/cmfgen_version.inc').exists()
    assert not (tree/patcher.STATE_DIR/'installed.json').exists()
    assert_settings(tree)


def test_failure_after_state_publication_restores_previous_install(tmp_path, tree, monkeypatch):
    first, _ = release(tmp_path/'first', {'new_main/a.f': b'      A=2\n'}, '2026-10-31.1')
    second, _ = release(tmp_path/'second', {'new_main/a.f': b'      A=3\n'}, '2026-11-01.1')
    patcher.update(tree, first)
    before = snapshot(tree)
    write = patcher.atomic_write
    failed = False
    def fail(path, data, mode=0o644):
        nonlocal failed
        write(path, data, mode)
        if path.name == 'installed.json' and not failed:
            failed = True
            raise OSError('after publication')
    monkeypatch.setattr(patcher, 'atomic_write', fail)
    with pytest.raises(patcher.PatchError, match='rolled back'):
        patcher.update(tree, second)
    assert (tree/'new_main/a.f').read_bytes() == before['new_main/a.f']
    assert (tree/patcher.STATE_DIR/'installed.json').read_bytes() == before[patcher.STATE_DIR+'/installed.json']
    assert patcher.read_state(tree).revision == '2026-10-31.1'


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'parent_link'])
def test_shared_or_linked_source_is_never_overwritten(tmp_path, tree, kind):
    manifest, _ = release(tmp_path/'release', {'new_main/a.f': b'      A=2\n'}, '2026-10-31.1')
    external = tmp_path/'external';external.mkdir();target = external/'a.f';target.write_bytes(BASE['new_main/a.f'])
    path = tree/'new_main/a.f'
    if kind == 'parent_link':
        shutil.rmtree(tree/'new_main');(tree/'new_main').symlink_to(external)
    else:
        path.unlink()
        if kind == 'symlink':path.symlink_to(target)
        else:path.hardlink_to(target)
    with pytest.raises(patcher.PatchError):
        patcher.update(tree, manifest)
    assert target.read_bytes() == BASE['new_main/a.f']


def test_source_modes_and_preserved_setting_links(tmp_path, tree):
    manifest, _ = release(tmp_path/'release', {'new_main/a.f': b'      A=2\n'}, '2026-10-31.1')
    (tree/'new_main/a.f').chmod(0o600)
    external = tmp_path/'settings';external.write_bytes(b'local settings\n')
    (tree/'Makefile_definitions').unlink();(tree/'Makefile_definitions').symlink_to(external)
    patcher.update(tree, manifest)
    assert stat.S_IMODE((tree/'new_main/a.f').stat().st_mode) == 0o600
    assert (tree/'Makefile_definitions').is_symlink()
    assert external.read_bytes() == b'local settings\n'


def test_checksum_tampering_and_downgrades_are_refused(tmp_path, tree):
    manifest, _ = release(tmp_path/'release', {'new_main/a.f': b'      A=2\n'}, '2026-10-31.1')
    patcher.update(tree, manifest)
    older, _ = release(tmp_path/'older', {'new_main/a.f': b'      A=0\n'}, '2026-10-30.1')
    with pytest.raises(patcher.PatchError, match='downgrade'):
        patcher.update(tree, older)
    (manifest.parent/'source.patch').write_bytes(b'unknown patch')
    with pytest.raises(patcher.PatchError, match='checksum'):
        patcher.update(tree, manifest)


def test_unrecorded_old_patch_is_recognized_from_local_git_history(tmp_path, tree):
    repo = tmp_path/'repo';repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    manifest, _ = release(repo/'release', {'new_main/a.f': b'      A=2\n'}, '2026-10-31.1')
    for args in [['add', '.'], ['-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                              'commit', '-qm', 'old patch']]:
        subprocess.run(['git', '-C', str(repo), *args], check=True)
    patcher.update(tree, manifest)
    shutil.rmtree(tree/patcher.STATE_DIR)  # Simulate a pre-updater installation.
    newer, after = release(tmp_path/'newer', {'new_main/a.f': b'      A=3\n'}, '2026-11-01.1')
    # Keep the desired bundle at the same repository path, now uncommitted.
    shutil.copy2(newer, manifest);shutil.copy2(newer.parent/'source.patch', manifest.parent/'source.patch')
    report = patcher.update(tree, manifest, repo=repo)
    assert report['status'] == 'applied'
    assert (tree/'new_main/a.f').read_bytes() == after['new_main/a.f']
    assert_settings(tree)


def test_concurrent_edit_is_preserved_and_owned_changes_rolled_back(tmp_path, tree, monkeypatch):
    manifest, _ = release(tmp_path/'release', {'new_main/a.f': b'      A=2\n',
                           'new_main/obsolete.f': b'      NEW_FIX=1\n'}, '2026-10-31.1')
    write = patcher.atomic_write
    def concurrent(path, data, mode=0o644):
        write(path, data, mode)
        if path.name == 'a.f':
            (tree/'new_main/obsolete.f').write_bytes(b'external concurrent edit\n')
    monkeypatch.setattr(patcher, 'atomic_write', concurrent)
    with pytest.raises(patcher.PatchError, match='changed during installation'):
        patcher.update(tree, manifest)
    assert (tree/'new_main/a.f').read_bytes() == BASE['new_main/a.f']
    assert (tree/'new_main/obsolete.f').read_bytes() == b'external concurrent edit\n'
    assert not (tree/patcher.STATE_DIR/'installed.json').exists()


def test_removed_added_file_is_retired_on_update(tmp_path, tree):
    first, _ = release(tmp_path/'first', {'new_main/temporary.f': b'      OLD_FIX=1\n'}, '2026-10-31.1')
    second, _ = release(tmp_path/'second', {'new_main/a.f': b'      A=3\n'}, '2026-11-01.1')
    patcher.update(tree, first)
    patcher.update(tree, second)
    assert not (tree/'new_main/temporary.f').exists()
    assert (tree/'new_main/a.f').read_bytes() == b'      A=3\n'


def test_malformed_manifest_paths_are_refused(tmp_path):
    manifest, _ = release(tmp_path/'release', {'new_main/a.f': b'      A=2\n'}, '2026-10-31.1')
    data = json.loads(manifest.read_text())
    data['files'][0]['path'] = '../outside.f'
    manifest.write_text(json.dumps(data))
    with pytest.raises(patcher.PatchError, match='Unsafe source path'):
        patcher.Bundle.load(manifest)
