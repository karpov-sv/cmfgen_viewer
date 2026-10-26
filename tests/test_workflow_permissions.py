"""Published workflow data stays readable even with private source permissions."""

import os
from pathlib import Path

import pytest

from cmfgen_viewer.workflow_permissions import copy_readable, make_readable, mkdir_readable, open_readable


def test_permissions_preserve_writes_executable_access_and_symlink_targets(tmp_path):
    source = tmp_path / 'source.sh'
    source.write_text('script')
    source.chmod(0o700)
    old_mask = os.umask(0o077)
    try:
        directory = tmp_path / 'new' / 'workspace'
        mkdir_readable(directory, parents=True)
        copied = directory / 'script.sh'
        copy_readable(source, copied)
        with open_readable(directory / 'result.txt', 'x') as stream:
            stream.write('result')
    finally:
        os.umask(old_mask)
    assert directory.stat().st_mode & 0o777 == 0o755
    assert directory.parent.stat().st_mode & 0o777 == 0o755
    assert copied.stat().st_mode & 0o777 == 0o755
    assert source.stat().st_mode & 0o777 == 0o700
    assert (directory / 'result.txt').stat().st_mode & 0o777 == 0o644
    copied.chmod(0o770)
    make_readable(copied)
    assert copied.stat().st_mode & 0o777 == 0o775
    link = directory / 'linked-script'
    link.symlink_to(source)
    make_readable(link)
    assert source.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('directory,mode', [
    (False, 0o644), (False, 0o666), (False, 0o755), (False, 0o777),
    (True, 0o755), (True, 0o777),
])
def test_already_readable_shared_artifacts_do_not_require_chmod(tmp_path, monkeypatch, directory, mode):
    path = tmp_path / 'shared'
    if directory:
        path.mkdir()
    else:
        path.write_text('native output')
    path.chmod(mode)

    def deny_chmod(*args, **kwargs):
        raise PermissionError('Only the owner may change permissions')

    monkeypatch.setattr(Path, 'chmod', deny_chmod)
    make_readable(path)
    assert path.stat().st_mode & 0o777 == mode


@pytest.mark.parametrize('mode', [0o644, 0o666, 0o777])
def test_open_already_readable_shared_file_does_not_require_fchmod(tmp_path, monkeypatch, mode):
    path = tmp_path / 'shared'
    path.write_text('existing')
    path.chmod(mode)

    def deny_fchmod(*args, **kwargs):
        raise PermissionError('Only the owner may change permissions')

    monkeypatch.setattr(os, 'fchmod', deny_fchmod)
    with open_readable(path, 'a') as stream:
        stream.write(' output')
    assert path.read_text() == 'existing output'
    assert path.stat().st_mode & 0o777 == mode


@pytest.mark.parametrize('source_mode,destination_mode', [(0o444,0o644),(0o555,0o755)])
def test_working_copies_are_writable_without_changing_readonly_sources(tmp_path, source_mode, destination_mode):
    from cmfgen_viewer.workflow_permissions import copy_working_file
    source=tmp_path/'source';source.write_text('contents');source.chmod(source_mode)
    working=tmp_path/'working';backup=tmp_path/'backup'
    copy_working_file(source,working)
    copy_readable(source,backup)
    assert working.stat().st_mode & 0o777 == destination_mode
    assert backup.stat().st_mode & 0o777 == source_mode
    assert source.stat().st_mode & 0o777 == source_mode
    with working.open('a') as stream: stream.write(' editable')
    assert source.read_text() == 'contents'
