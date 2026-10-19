import os

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_convergence import inspect_model_convergence
from cmfgen_viewer.parsers import parse_known_file
from cmfgen_viewer.parsers.correction_link import read_correction_link


SNAPSHOT = """
 5 largest reductions at depth: 1
 SOL(J,L) Species SL I(STEQ)
 5.6569D-01 FeIV 2 1816
 -8.5852E-03 Ne 0 2232
 5 largest increases at depth: 3
 -2.2802E+01 SIII 24 1124
 -1.4088E+01 SIII 23 1123
 5 largest reductions at depth: 4
 1.7623E-02 T 0 2233
"""


def model(tmp_path):
    (tmp_path / "VADAT").write_text("1 [RSTAR]\n")
    (tmp_path / "MODEL_SPEC").write_text("4 [ND]\n1 [NC]\n5 [NP]\n")
    (tmp_path / 'OUTGEN').write_text(
        'Model started on: 01-Jan-2026 00:00:00\n'
        'Current great iteration count is 203\n'
        'Maximm changes as returned by SOLVEBA_V13 is 2280.2\n')
    (tmp_path / 'CORRECTION_LINK').write_text(SNAPSHOT)
    return tmp_path


def check(path):
    return next(c for c in inspect_model_convergence(path)['quality']['checks']
                if c['code'] == 'correction_drivers')


def test_parser_preserves_solver_sign_section_and_variable_indices(tmp_path):
    model(tmp_path)
    path = tmp_path / 'CORRECTION_LINK'
    entries = read_correction_link(path)['entries']
    assert len(entries) == 5
    assert entries[1]['section'] == 'reductions'
    assert entries[1]['change_percent'] == pytest.approx(0.85852)
    assert entries[1]['superlevel'] == 0
    parsed = parse_known_file(path)
    assert parsed['parser'] == 'CORRECTION_LINK'
    row = parsed['tables'][0]['rows'][0]
    assert row[:6] == ['3', 'increases', '1', 'SIII', '24', '1124']
    assert not parsed['warnings']
    diagnostic = check(tmp_path)
    assert diagnostic['level'] == 'warning'
    assert 'SIII SL 24 (equation 1124): +2280% at depth 3' in diagnostic['detail']
    assert 'FeIV SL 2' in diagnostic['detail']
    assert 'CORRECTION_LINK' in inspect_model_convergence(tmp_path)['diagnostic_links']


@pytest.mark.parametrize('bad', ['NaN SIII 24 1124', 'Inf SIII 24 1124',
                                  '***** SIII 24 1124', '1D308 SIII 24 1124',
                                  '1 SIII 2.5 1124', '1 SIII 24', 'garbage'])
def test_invalid_rows_are_visible_and_diagnostics_do_not_accept_partial_maxima(tmp_path, bad):
    model(tmp_path)
    path = tmp_path / 'CORRECTION_LINK'
    path.write_text(SNAPSHOT + bad + '\n')
    assert parse_known_file(path)['warnings']
    assert check(tmp_path)['level'] == 'unknown'


def test_stale_empty_and_small_snapshots(tmp_path):
    model(tmp_path)
    path = tmp_path / 'CORRECTION_LINK'
    os.utime(path, (1_000_000_000, 1_000_000_000))
    assert check(tmp_path)['level'] == 'unknown'
    assert 'predates' in check(tmp_path)['detail']
    path.write_text('')
    assert check(tmp_path)['level'] == 'unknown'
    path.write_text('5 largest increases at depth: 3\n-1D-4 HI 1 1\n')
    assert check(tmp_path)['level'] == 'info'


def test_outgen_cache_and_page_follow_correction_link(tmp_path):
    model(tmp_path)
    def detail():
        tables = parse_known_file(tmp_path / 'OUTGEN')['tables']
        rows = next(t['rows'] for t in tables if t['title'].startswith('Convergence and numerical'))
        return next(r[2] for r in rows if r[1] == 'Species driving solver corrections')
    assert 'SIII SL 24' in detail()
    path = tmp_path / 'CORRECTION_LINK'
    stat = path.stat()
    path.write_text(SNAPSHOT.replace('SIII', 'OIII'))
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert 'OIII SL 24' in detail()  # Digest invalidates even same-size, same-mtime edits.
    app = create_app(basepath=str(tmp_path.parent), read_write_enabled=True, secret_key='test')
    client = app.test_client()
    response = client.get(f'/view/{tmp_path.name}/CORRECTION_LINK?display=parsed')
    assert response.status_code == 200
    assert b'CORRECTION_LINK species and superlevel corrections' in response.data
    response = client.get(f'/model-actions/main-computation/{tmp_path.name}')
    assert response.status_code == 200
    assert b'OIII SL 24' in response.data
    assert b'Open CORRECTION_LINK' in response.data


def test_depth_plots_preserve_sparse_entries_sign_and_hover_details(tmp_path):
    model(tmp_path)
    path = tmp_path / 'CORRECTION_LINK'
    path.write_text(SNAPSHOT + '5 largest increases at depth: 9\n0 SIII 25 1125\n')
    parsed = parse_known_file(path)
    magnitude, signed = parsed['plots']
    assert parsed['default_plot_mode'] == 'separate'
    assert magnitude['default_y_scale'] == 'log'
    assert signed['default_y_scale'] == 'linear'
    assert magnitude['point_count'] == 5
    assert signed['point_count'] == 6
    assert all(t['mode'] == 'markers' for t in signed['data'])
    m = next(t for t in magnitude['data'] if t['name'] == 'SIII')
    s = next(t for t in signed['data'] if t['name'] == 'SIII')
    assert m['x'] == [3, 3]  # No interpolated or zero-filled depths.
    assert s['x'] == [3, 3, 9]
    assert s['y'][-1] == 0
    assert m['customdata'][1] == ['SIII', 24, 1124, 2280.2, 'increases', 1]
    fe = next(t for t in magnitude['data'] if t['name'] == 'FeIV')
    assert fe['y'] == pytest.approx([56.569])
    assert fe['customdata'][0][3] == pytest.approx(-56.569)
    assert fe['marker']['symbol'] == ['triangle-down']
    ne = next(t for t in signed['data'] if t['name'] == 'Ne')
    assert ne['marker']['symbol'] == ['triangle-up']  # Sign, independent of section label.
    path.write_text('')
    assert parse_known_file(path)['plots'] == []
