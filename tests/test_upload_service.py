from io import BytesIO

import pytest

from cmfgen_viewer.observed_spectrum import read_upload_manifest, write_upload_manifest
from cmfgen_viewer.upload_service import create_photometry_bundle, create_upload_bundle


def test_manifest_failure_rolls_back_bundle(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("cmfgen_viewer.upload_service.write_upload_manifest", fail)
    with pytest.raises(OSError, match="disk full"):
        create_upload_bundle(
            tmp_path,
            filename="spectrum.dat",
            stream=BytesIO(b"5000 1\n6000 2\n"),
        )
    assert list(tmp_path.iterdir()) == []


def test_failed_manifest_replacement_preserves_previous_manifest(tmp_path, monkeypatch):
    token = "ExampleToken123"
    write_upload_manifest(tmp_path, token, {"points": 3})

    def fail(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("cmfgen_viewer.observed_spectrum.os.replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        write_upload_manifest(tmp_path, token, {"points": 4})
    assert read_upload_manifest(tmp_path, token) == {"points": 3}
    assert [p.name for p in (tmp_path / token).iterdir()] == ["meta.json"]


def test_create_photometry_bundle_persists_canonical_schema(tmp_path):
    token = create_photometry_bundle(
        upload_root=tmp_path,
        filename="photometry-points.txt",
        photometry_table="5000 100 1.2e-12\n",
        lambda_min=800.0,
        lambda_max=250000.0,
    )

    manifest = read_upload_manifest(tmp_path, token)
    assert isinstance(manifest, dict)
    assert manifest["stored_name"] == "source.phot"
    stored = (tmp_path / token / "source.phot").read_text(encoding="utf-8")
    assert stored.startswith("# wavelength_A band_width_A flux flux_error enabled")
    assert "5000 100 1.2e-12 0 1" in stored
