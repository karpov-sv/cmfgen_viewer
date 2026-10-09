from io import BytesIO

import pytest

from cmfgen_viewer.observed_spectrum import parse_uploaded_spectrum, read_upload_manifest, write_upload_manifest
from cmfgen_viewer.upload_service import create_photometry_bundle, create_upload_bundle


@pytest.mark.parametrize("filename,content", [
    ("sed.txt", b'# wavelength bandwidth flux flux_error comment\n5000 100 1e-12 nan "Survey B"\n6000 200 2e-12 3e-14 "Survey V"\n'),
    ("sed.csv", b'wavelength,bandwidth,flux,flux_error,comment\n5000,100,1e-12,nan,"Survey B"\n6000,200,2e-12,3e-14,"Survey V"\n'),
])
def test_file_photometry_upload_is_canonical_and_keeps_original(tmp_path, filename, content):
    manifest = create_upload_bundle(tmp_path, filename=filename, stream=BytesIO(content), lambda_min=5500)
    bundle = tmp_path / manifest["token"]
    assert manifest["stored_name"] == "source.phot"
    assert manifest["observation_type"] == "photometry"
    assert manifest["format"] == "photometry-text"
    assert manifest["points"] == 1
    assert (bundle / manifest["original_stored_name"]).read_bytes() == content
    canonical = (bundle / "source.phot").read_text()
    assert "5000 100 1e-12 0 1 # Survey B" in canonical  # Store all rows, not just current window.
    assert parse_uploaded_spectrum(bundle / "source.phot")["point_comment"] == ["Survey B", "Survey V"]


def test_votable_upload_normalizes_to_photometry(tmp_path):
    table_module = pytest.importorskip("astropy.table")
    original = tmp_path / "sed.vot"
    table_module.Table({"wavelength": [5000], "bandwidth": [100], "flux": [1e-12], "comment": ["B"]}).write(original, format="votable")
    with original.open("rb") as stream:
        manifest = create_upload_bundle(tmp_path / "uploads", filename=original.name, stream=stream)
    assert manifest["observation_type"] == "photometry"
    assert manifest["stored_name"] == "source.phot"
    bundle = tmp_path / "uploads" / manifest["token"]
    assert (bundle / "source.vot").read_bytes() == original.read_bytes()
    assert "5000 100 1e-12 0 1 # B" in (bundle / "source.phot").read_text()


def test_invalid_photometry_upload_rolls_back_bundle(tmp_path):
    with pytest.raises(ValueError, match="Invalid photometry row"):
        create_upload_bundle(tmp_path, filename="sed.csv", stream=BytesIO(b"wavelength,bandwidth,flux\n5000,-1,1e-12\n"))
    assert list(tmp_path.iterdir()) == []


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
