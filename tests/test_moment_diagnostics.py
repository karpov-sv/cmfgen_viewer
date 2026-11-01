import os

import pytest

from cmfgen_viewer.moment_diagnostics import negative_moment_intensities
from cmfgen_viewer.runner_recipe import snapshot


ROW = ' 123 7.41 -0.00014 3.6e-14 9.5e-5 5.5e-6 .3 .09 0 1 2 -0.00014 4 5\n'
TAIL = '                       1 2 3 4 5\n'
FOOTER = ('\n Iteration No 42\n\n Error in MOM_J_CMF for the following frequencies:\n'
          ' Number of frequencies for which error occurs: 1\n 7.410000E+00\n')


def test_complete_fresh_compact_native_rows_use_transfer_grid_indices(tmp_path):
    path = tmp_path/'MOM_J_ERRORS'
    before = {'MOM_J_ERRORS': snapshot(path)}
    path.write_text(ROW+TAIL+ROW+TAIL+FOOTER)
    data = negative_moment_intensities(tmp_path, before, 0, 42)
    assert data['rows'] == 2 and data['frequencies'] == 1
    assert data['transfer_depth_max'] == 123  # May exceed the atmosphere ND.
    assert data['minimum_raw_r_squared_j'] == -.00014


@pytest.mark.parametrize('contents', [ROW, ROW+TAIL+'broken\n', ROW+TAIL+'Freq=7.41\n',
                                     ROW.replace('-0.00014', 'NaN')+TAIL,
                                     ROW.replace('-0.00014', '0.00014')+TAIL])
def test_incomplete_nonfinite_verbose_or_nonnegative_records_do_not_qualify(tmp_path, contents):
    path = tmp_path/'MOM_J_ERRORS'
    before = {'MOM_J_ERRORS': snapshot(path)}
    path.write_text(contents+FOOTER)
    assert negative_moment_intensities(tmp_path, before, 0, 42) is None


def test_stale_unchanged_untracked_and_symlinked_evidence_is_rejected(tmp_path):
    path = tmp_path/'MOM_J_ERRORS'
    path.write_text(ROW+TAIL+FOOTER)
    assert negative_moment_intensities(tmp_path, {'MOM_J_ERRORS': snapshot(path)}, 0, 42) is None
    assert negative_moment_intensities(tmp_path, {}, 0, 42) is None
    before = {'MOM_J_ERRORS': {'exists': False}}
    os.utime(path, (1, 1))
    assert negative_moment_intensities(tmp_path, before, 2, 42) is None
    path.rename(tmp_path/'source')
    path.symlink_to('source')
    assert negative_moment_intensities(tmp_path, before, 0, 42) is None


@pytest.mark.parametrize('footer', ['', FOOTER.replace('42', '41'),
                                  FOOTER.replace('occurs: 1', 'occurs: 2'),
                                  FOOTER.replace('7.410000', '7.500000')])
def test_missing_stale_or_inconsistent_completion_footer_is_rejected(tmp_path, footer):
    path = tmp_path/'MOM_J_ERRORS'
    before = {'MOM_J_ERRORS': snapshot(path)}
    path.write_text(ROW+TAIL+footer)
    assert negative_moment_intensities(tmp_path, before, 0, 42) is None
