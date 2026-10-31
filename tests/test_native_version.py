"""Executable version queries are isolated from models and identify our stream."""
from pathlib import Path
import sys

import pytest

from cmfgen_viewer.native_version import executable_revision, supports_revision


def executable(tmp_path, body):
    path = tmp_path/'cmfgen_dev.exe'
    path.write_text(f'#!{sys.executable}\n'+body)
    path.chmod(0o755)
    return path


@pytest.mark.parametrize('reported,eligible', [
    ('2026-10-30.99', False), ('2026-10-31.1', True), ('2026-10-31.2', True),
    ('2027-01-01.1', True), ('2026-02-30.1', False), ('2026-10-31.0', False),
    ('2026-10-31', False), ('unknown', False),
])
def test_dated_patch_stream_threshold(tmp_path, reported, eligible):
    exe = executable(tmp_path, f"print('CMFGEN_VIEWER_PATCH {reported}')\n")
    assert supports_revision({'executable': str(exe)}) is eligible


@pytest.mark.parametrize('output', [
    'Main program last changed on: 01-Jan-2030',
    'OTHER_FORK 2030-01-01.1',
    'CMFGEN_VIEWER_PATCH 2026-10-31.1\nCMFGEN_VIEWER_PATCH 2026-10-31.2',
    'CMFGEN_VIEWER_PATCH 2026-10-31.1 extra',
    'x'*4097,
])
def test_unidentified_or_ambiguous_executables_are_ineligible(tmp_path, output):
    exe = executable(tmp_path, f'print({output!r})\n')
    assert executable_revision(exe) is None


def test_legacy_query_cannot_touch_the_model(tmp_path, monkeypatch):
    model = tmp_path/'model';model.mkdir()
    (model/'OUTGEN').write_text('preserve existing output')
    exe = executable(tmp_path, "from pathlib import Path\nPath('OUTGEN').write_text('legacy side effect')\nprint('old version')\n")
    monkeypatch.chdir(model)
    assert executable_revision(exe) is None
    assert (model/'OUTGEN').read_text() == 'preserve existing output'
    assert sorted(p.name for p in model.iterdir()) == ['OUTGEN']


def test_binary_replacement_invalidates_cached_revision(tmp_path):
    exe = executable(tmp_path, "print('CMFGEN_VIEWER_PATCH 2026-10-31.1')\n")
    assert executable_revision(exe) == '2026-10-31.1'
    replacement = tmp_path/'replacement'
    replacement.write_text(f'#!{sys.executable}\nprint("CMFGEN_VIEWER_PATCH 2026-10-30.1")\n')
    replacement.chmod(0o755);replacement.replace(exe)
    assert not supports_revision({'executable': str(exe)})


def test_remedy_can_require_a_later_same_day_revision(tmp_path):
    exe = executable(tmp_path, "print('CMFGEN_VIEWER_PATCH 2026-10-31.1')\n")
    assert not supports_revision({'executable': str(exe)}, minimum='2026-10-31.2')


def test_output_stamp_is_historical_identity_only(tmp_path):
    from cmfgen_viewer.native_version import output_revision
    summary = tmp_path/'MOD_SUM'
    summary.write_text('Main program last changed on: 31-Oct-2026\nCMFGEN viewer patch revision: 2026-10-31.1\n')
    assert output_revision(summary) == '2026-10-31.1'
    assert not supports_revision({'executable': str(tmp_path/'missing.exe')})
    summary.write_text('Main program last changed on: 31-Oct-2030\n')
    assert output_revision(summary) is None


def test_mod_sum_keeps_upstream_and_patch_revision_separate(tmp_path):
    from cmfgen_viewer.parsers.mod_sum import read_mod_sum
    path = tmp_path/'MOD_SUM'
    path.write_text('Main program last changed on: 31-Oct-2026\n'
                    'CMFGEN viewer patch revision: 2026-10-31.1\n'
                    'CMFGEN upstream release: 18-Jun-2025\n')
    metadata = read_mod_sum(path).metadata
    assert metadata['main_program_last_changed_on'] == '31-Oct-2026'
    assert metadata['cmfgen_viewer_patch_revision'] == '2026-10-31.1'
    assert metadata['cmfgen_upstream_release'] == '18-Jun-2025'


def test_rvtj_revision_can_share_the_fixed_program_date_row(tmp_path):
    from cmfgen_viewer.native_version import output_revision
    path = tmp_path/'RVTJ'
    path.write_text(' Output format date:         15-Aug-2019\n'
                    ' Completion of Model:        31-Oct-2026 02:44:09\n'
                    ' Program Date:               31-Oct-2026 CMFGEN viewer patch revision: 2026-10-31.1\n'
                    ' ND:                            90\n')
    assert output_revision(path) == '2026-10-31.1'
    assert path.read_text().splitlines()[3].strip() == 'ND:                            90'


def test_legacy_build_record_cannot_authorize_an_unidentified_binary(tmp_path):
    import hashlib
    import json
    exe = executable(tmp_path, "print('Main program last changed on: 31-Oct-2026')\n")
    record = {'capabilities': ['line-jacobian-v1', 'ba-restart-v1'],
              'executables': {exe.name: {'sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}}}
    (tmp_path/'cmfgen-local-build.json').write_text(json.dumps(record))
    assert not supports_revision({'executable': str(exe)})
