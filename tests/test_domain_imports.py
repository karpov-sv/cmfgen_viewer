import subprocess
import sys


def test_scientific_and_job_modules_do_not_import_flask():
    subprocess.run(
        [sys.executable, "-c", "import sys; import cmfgen_viewer.grid_jobs, cmfgen_viewer.cache_jobs, cmfgen_viewer.summary_jobs, cmfgen_viewer.spectrum_fitting; assert 'flask' not in sys.modules"],
        check=True,
    )
