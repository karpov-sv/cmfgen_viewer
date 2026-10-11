from types import SimpleNamespace

import pytest

from cmfgen_viewer import process_monitor as monitor
from cmfgen_viewer.model_activity import inspect_model_activity, model_mutation_guard
from cmfgen_viewer.model_runtime import inspect_workflow_runtime


class Process:
    def __init__(self, pid, cwd, name='cmfgen.exe', arguments=None, status='running', error=None):
        self.pid = pid
        self.info = dict(name=name, cmdline=arguments or [name], status=status)
        self.data = dict(cwd=str(cwd) if cwd else None, create_time=100,
                         cpu_times=SimpleNamespace(user=2, system=1),
                         memory_info=SimpleNamespace(rss=2048), num_threads=2, ppid=1)
        self.error = error

    def is_running(self):
        return True

    def as_dict(self, **kwargs):
        if self.error:
            raise self.error
        return self.data


def install_processes(monkeypatch, processes):
    monkeypatch.setattr(monitor.psutil, 'process_iter', lambda *args, **kwargs: iter(processes))


def test_native_detector_scopes_processes_and_ignores_path_arguments(tmp_path, monkeypatch):
    install_processes(monkeypatch, [
        Process(101, tmp_path),
        Process(102, tmp_path / 'lte', name='main_lte.exe'),
        Process(103, tmp_path.parent / 'other'),
        Process(104, tmp_path, name='python', arguments=['python', '--dir', '/tmp/cmfgen_viewer']),
        Process(105, tmp_path, status=monitor.psutil.STATUS_ZOMBIE),
        Process(106, tmp_path, name='sh', arguments=['sh', '/tmp/batch.sh']),
    ])
    records, errors = monitor.scan_model_processes(tmp_path, now_epoch=110)
    assert not errors
    assert {p['pid'] for p in records} == {101, 106}
    assert records[0]['elapsed_seconds'] == 10
    assert records[0]['cpu_seconds'] == 3
    state = inspect_model_activity(tmp_path)
    assert {p['pid'] for p in state['processes']} == {101, 102, 106}
    assert not state['safe_to_modify']
    with pytest.raises(ValueError, match='active'):
        with model_mutation_guard(tmp_path):
            pytest.fail('Must refuse to modify an active workspace')


def test_native_detector_handles_denied_and_exited_processes(tmp_path, monkeypatch):
    install_processes(monkeypatch, [Process(101, tmp_path, error=monitor.psutil.NoSuchProcess(101))])
    assert inspect_model_activity(tmp_path)['state'] == 'idle'
    install_processes(monkeypatch, [Process(101, None)])
    assert inspect_model_activity(tmp_path)['state'] == 'unknown'
    runtime = inspect_workflow_runtime(tmp_path, 'main')
    assert not runtime['monitoring_available']
    assert runtime['monitoring_uncertainties']
    install_processes(monkeypatch, [Process(101, tmp_path, error=monitor.psutil.AccessDenied(101))])
    assert not inspect_model_activity(tmp_path)['safe_to_modify']


def test_native_metrics_are_optional_and_missing_dependency_is_unknown(tmp_path, monkeypatch):
    process = Process(101, tmp_path)
    process.data.update(cpu_times=None, memory_info=None, create_time=None, num_threads=None)
    install_processes(monkeypatch, [process])
    runtime = inspect_workflow_runtime(tmp_path, 'main')
    assert runtime['active']
    assert runtime['processes'][0]['cpu_time'] == '—'
    assert runtime['processes'][0]['rss'] == '—'
    monkeypatch.setattr(monitor, 'psutil', None)
    assert inspect_model_activity(tmp_path)['state'] == 'unknown'
    assert not inspect_workflow_runtime(tmp_path, 'main')['monitoring_available']


@pytest.mark.parametrize('kind,name', [('main', 'cmfgen.exe'), ('flux', 'cmf_flux.exe'),
                                      ('lte', 'main_lte.exe'), ('hydro', 'wind_hyd.exe')])
def test_native_workflow_runtime_tracks_start_and_completion(tmp_path, monkeypatch, kind, name):
    install_processes(monkeypatch, [Process(101, tmp_path, name=name)])
    runtime = inspect_workflow_runtime(tmp_path, kind, now_epoch=110)
    assert runtime['active'] and runtime['monitoring_available']
    assert runtime['processes'][0]['cpu_percent'] == 30
    install_processes(monkeypatch, [])
    runtime = inspect_workflow_runtime(tmp_path, kind)
    assert not runtime['active'] and runtime['monitoring_available']


def test_main_monitor_detects_flux_child_workspace(tmp_path, monkeypatch):
    (tmp_path / 'obs').mkdir()
    install_processes(monkeypatch, [Process(101, tmp_path / 'obs', name='cmf_flux.exe')])
    runtime = inspect_workflow_runtime(tmp_path, 'main')
    assert runtime['active'] and runtime['phase'] == 'flux'
