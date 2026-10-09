"""Create complete observed-spectrum bundles, rolling back failed uploads."""

from __future__ import annotations

import shutil
import time
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from werkzeug.utils import secure_filename

from .observed_spectrum import (
    generate_upload_token,
    normalize_photometry_table,
    parse_uploaded_spectrum,
    remove_upload_bundle,
    uploaded_photometry_table,
    write_upload_manifest,
)


def create_upload_bundle(
    upload_root: Path,
    *,
    filename: str,
    stream: BinaryIO,
    flux_mode: str = "auto",
    lambda_min: float | None = None,
    lambda_max: float | None = None,
    photometry: bool = False,
    empty_photometry: bool = False,
) -> dict[str, object]:
    """Persist a source and its manifest as one operation.

    The caller owns the input stream. A bundle is discoverable only after its
    manifest is committed; any save, parse, or manifest failure removes it.
    """
    safe_name = secure_filename(filename) or "observed-spectrum"
    suffix = ".phot" if photometry else Path(safe_name).suffix.lower() or ".dat"
    token = generate_upload_token()
    token_dir = upload_root / token
    token_dir.mkdir(parents=True, exist_ok=False)
    stored_name = f"source{suffix}"
    try:
        source = token_dir / stored_name
        with source.open("wb") as destination:
            shutil.copyfileobj(stream, destination)
        canonical = uploaded_photometry_table(source)
        original_stored_name = ""
        if canonical is not None:
            original_stored_name = stored_name
            stored_name = "source.phot"
            source = token_dir / stored_name
            source.write_text(canonical, encoding="utf-8")
        if photometry and empty_photometry:
            parsed = {
                "detected_flux_mode": "absolute",
                "flux_mode": "absolute",
                "format": "photometry-text",
                "observation_type": "photometry",
                "wavelength": [],
            }
        else:
            parsed = parse_uploaded_spectrum(
                source,
                flux_mode=flux_mode,
                lambda_min=lambda_min,
                lambda_max=lambda_max,
            )
        manifest = {
            "token": token,
            "filename": safe_name,
            "stored_name": stored_name,
            "requested_flux_mode": flux_mode,
            "detected_flux_mode": str(parsed.get("detected_flux_mode", "")),
            "resolved_flux_mode": str(parsed.get("flux_mode", "")),
            "format": str(parsed.get("format", "")),
            "observation_type": str(parsed.get("observation_type", "spectrum")),
            "points": len(parsed.get("wavelength", [])),
            "created_at": time.time(),
        }
        if original_stored_name:
            manifest["original_stored_name"] = original_stored_name
        write_upload_manifest(upload_root, token, manifest)
    except Exception:
        remove_upload_bundle(upload_root, token)
        raise
    return manifest


def create_photometry_bundle(
    *,
    upload_root: Path,
    filename: str,
    photometry_table: str,
    lambda_min: float,
    lambda_max: float,
) -> str:
    canonical_table = normalize_photometry_table(photometry_table)
    manifest = create_upload_bundle(
        upload_root,
        filename=filename,
        stream=BytesIO(canonical_table.encode("utf-8")),
        flux_mode="absolute",
        lambda_min=lambda_min,
        lambda_max=lambda_max,
        photometry=True,
        empty_photometry=not canonical_table,
    )
    return str(manifest["token"])
