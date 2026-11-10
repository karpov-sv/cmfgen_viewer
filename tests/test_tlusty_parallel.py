import gzip
import io
import json
import tarfile

import numpy as np
import pytest

from scripts import download_tlusty_spectra as converter


def write_archive(path, model, suffixes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w") as archive:
        for suffix in suffixes:
            wave = np.geomspace(900, 30000, 2001)
            flux = (wave / 5000)**-2
            if suffix.endswith(".17"):
                wave, flux = wave[::20], flux[::20]
            if suffix == ".flux":
                first = converter.LIGHT_SPEED_ANGSTROM_PER_SECOND / wave
                second = flux * wave**2 / converter.LIGHT_SPEED_ANGSTROM_PER_SECOND
            else:
                first, second = wave, flux
            payload = "\n".join(f"{x:.17g} {y:.17g}" for x, y in zip(first, second)).encode()
            payload = gzip.compress(payload)
            member = tarfile.TarInfo(model + suffix + ".gz")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))


def read_spectra(root):
    spectra = {}
    for path in (root / "spectra").rglob("*.npz"):
        with np.load(path, allow_pickle=False) as payload:
            spectra[str(path.relative_to(root))] = {key: payload[key] for key in payload.files}
    return spectra


def test_process_workers_match_serial_results_and_reuse_completed_outputs(tmp_path):
    for grid, archive, model, products in (
        ("bstar", "BGuvspec_v2.tar", "BG25000g400v2", [".uv.7", ".uv.17"]),
        ("bstar", "BGvispec_v2.tar", "BG25000g400v2", [".vis.7", ".vis.17"]),
        ("bstar", "BGflux_v2.tar", "BG25000g400v2", [".flux"]),
        ("ostar", "Gflux.tar", "G35000g400v10", [".flux"]),
    ):
        write_archive(tmp_path / "raw" / grid / archive, model, products)
    arguments = ["--local-only", "--output-dir", str(tmp_path), "--resolving-power", "100",
                 "--samples-per-resolution", "3", "--sed-binning-power", "300"]
    assert converter.main(arguments + ["--workers", "1", "--force-process"]) == 0
    serial = read_spectra(tmp_path)
    serial_manifest = json.loads((tmp_path / "manifest.json").read_text())
    serial_manifest.pop("generated_at_utc")
    serial_csv = (tmp_path / "models.csv").read_bytes()

    assert converter.main(arguments + ["--workers", "4", "--force-process"]) == 0
    parallel = read_spectra(tmp_path)
    assert serial.keys() == parallel.keys()
    for path, arrays in serial.items():
        assert arrays.keys() == parallel[path].keys()
        for key, array in arrays.items():
            np.testing.assert_array_equal(array, parallel[path][key])
    parallel_manifest = json.loads((tmp_path / "manifest.json").read_text())
    parallel_manifest.pop("generated_at_utc")
    assert parallel_manifest == serial_manifest
    assert (tmp_path / "models.csv").read_bytes() == serial_csv

    timestamps = {path: (tmp_path / path).stat().st_mtime_ns for path in parallel}
    assert converter.main(arguments + ["--workers", "4"]) == 0
    assert all((tmp_path / path).stat().st_mtime_ns == stamp for path, stamp in timestamps.items())
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["total_models"] == len(serial)
    assert all(archive["spectra_saved"] == 0 for archive in manifest["archives"])


def test_worker_failure_preserves_indexes_and_finishes_valid_archives(tmp_path):
    raw = tmp_path / "raw" / "bstar"
    write_archive(raw / "BGuvspec_v2.tar", "BG25000g400v2", [".uv.7", ".uv.17"])
    (raw / "BGflux_v2.tar").write_bytes(b"not a tar archive")
    (tmp_path / "models.csv").write_text("previous csv")
    (tmp_path / "manifest.json").write_text("previous manifest")
    result = converter.main(["--local-only", "--grid", "bstar", "--output-dir", str(tmp_path), "--workers", "2"])
    assert result == 2
    assert (tmp_path / "models.csv").read_text() == "previous csv"
    assert (tmp_path / "manifest.json").read_text() == "previous manifest"
    assert len(read_spectra(tmp_path)) == 2


def test_overlapping_archive_output_folders_fall_back_to_serial(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw" / "bstar"
    write_archive(raw / "BGflux_v2.tar", "BG25000g400v2", [".flux"])
    (raw / "BGflux_v2.tgz").write_bytes((raw / "BGflux_v2.tar").read_bytes())
    def unexpected_pool(*args, **kwargs):
        raise AssertionError("Overlapping output directories must not run concurrently")
    monkeypatch.setattr(converter, "ProcessPoolExecutor", unexpected_pool)
    result = converter.main(["--local-only", "--grid", "bstar", "--output-dir", str(tmp_path), "--workers", "4"])
    assert result == 0
    assert "using one worker" in capsys.readouterr().out
    assert len(read_spectra(tmp_path)) == 1


@pytest.mark.parametrize("count", ["0", "-1", "33", "nan"])
def test_invalid_worker_count(count):
    with pytest.raises(SystemExit):
        converter.parse_args(["--workers", count])
