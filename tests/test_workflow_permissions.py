"""Published workflow data stays readable even with private source permissions."""

import os

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
