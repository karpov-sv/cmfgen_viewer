from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import io
import math
from pathlib import Path
import re
import secrets
import tempfile
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from astropy.table import Table

from .parsers.common import parse_float_token

try:
    import astropy.units as u
    from astropy.coordinates import SkyCoord
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    u = None  # type: ignore[assignment]
    SkyCoord = None  # type: ignore[assignment]


VIZIER_SED_ENDPOINT = "https://vizier.cds.unistra.fr/viz-bin/sed"
DEFAULT_VIZIER_RADIUS_ARCSEC = 5.0
MAX_VIZIER_RADIUS_ARCSEC = 3600.0
DEFAULT_VIZIER_TIMEOUT_SECONDS = 20.0
DEFAULT_VIZIER_MAX_ROWS = 2000
VIZIER_DEBUG_DIR = (Path(tempfile.gettempdir()) / "cmfgen_viewer_vizier_debug").resolve()

LIGHT_SPEED_ANGSTROM_PER_S = 2.99792458e18
JANSKY_TO_CGS_HZ = 1e-23
LIGHT_SPEED_CM_PER_S = 2.99792458e10
ANGSTROM_PER_CM = 1e8
JY_TO_FLAMBDA_ANGSTROM_FACTOR = JANSKY_TO_CGS_HZ * LIGHT_SPEED_CM_PER_S * ANGSTROM_PER_CM

DECIMAL_PAIR_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*[, ]\s*([+-]?\d+(?:\.\d+)?)\s*$")
SEXAGESIMAL_PAIR_RE = re.compile(
    r"^\s*(\d{1,2})[:\s](\d{1,2})[:\s](\d{1,2}(?:\.\d+)?)\s+([+-]?)\s*(\d{1,3})[:\s](\d{1,2})[:\s](\d{1,2}(?:\.\d+)?)\s*$"
)
SOURCE_ID_SPLIT_RE = re.compile(r"[\s,;]+")


@dataclass(frozen=True)
class VizierCatalogOption:
    key: str
    label: str
    source_id: str


@dataclass(frozen=True)
class FilterMetadata:
    key: str
    catalog_key: str
    catalog_label: str
    filter_label: str
    lambda_eff_a: float
    band_width_a: float
    magnitude_system: str | None = None
    zero_point_jy: float | None = None


@dataclass(frozen=True)
class VizierPhotometryPoint:
    lambda_eff_a: float
    band_width_a: float
    flux: float
    flux_err: float | None
    comment: str


CATALOG_OPTIONS: tuple[VizierCatalogOption, ...] = (
    VizierCatalogOption("gaia_dr3_syntphot", "Gaia DR3 syntphot", "I/360/syntphot"),
    VizierCatalogOption("panstarrs_dr1", "Pan-STARRS", "II/349/ps1"),
    VizierCatalogOption("twomass", "2MASS", "II/246/out"),
    VizierCatalogOption("allwise", "AllWISE", "II/328/allwise"),
)
DEFAULT_CATALOG_KEYS: tuple[str, ...] = tuple(option.key for option in CATALOG_OPTIONS)
CATALOG_OPTIONS_BY_KEY: dict[str, VizierCatalogOption] = {option.key: option for option in CATALOG_OPTIONS}
CATALOG_OPTIONS_BY_SOURCE_ID: dict[str, VizierCatalogOption] = {
    option.source_id.lower(): option for option in CATALOG_OPTIONS
}

FILTER_LIBRARY: dict[str, FilterMetadata] = {
    "GAIA_G": FilterMetadata(
        key="GAIA_G",
        catalog_key="gaia_dr3_syntphot",
        catalog_label="Gaia DR3 syntphot",
        filter_label="G",
        lambda_eff_a=6218.0,
        band_width_a=4050.0,
        magnitude_system="vega",
        zero_point_jy=2861.0,
    ),
    "GAIA_BP": FilterMetadata(
        key="GAIA_BP",
        catalog_key="gaia_dr3_syntphot",
        catalog_label="Gaia DR3 syntphot",
        filter_label="BP",
        lambda_eff_a=5109.0,
        band_width_a=2157.0,
        magnitude_system="vega",
        zero_point_jy=3323.0,
    ),
    "GAIA_RP": FilterMetadata(
        key="GAIA_RP",
        catalog_key="gaia_dr3_syntphot",
        catalog_label="Gaia DR3 syntphot",
        filter_label="RP",
        lambda_eff_a=7769.0,
        band_width_a=2924.0,
        magnitude_system="vega",
        zero_point_jy=2554.0,
    ),
    "PS1_G": FilterMetadata(
        key="PS1_G",
        catalog_key="panstarrs_dr1",
        catalog_label="Pan-STARRS",
        filter_label="g",
        lambda_eff_a=4810.0,
        band_width_a=1530.0,
        magnitude_system="ab",
        zero_point_jy=3631.0,
    ),
    "PS1_R": FilterMetadata(
        key="PS1_R",
        catalog_key="panstarrs_dr1",
        catalog_label="Pan-STARRS",
        filter_label="r",
        lambda_eff_a=6170.0,
        band_width_a=1440.0,
        magnitude_system="ab",
        zero_point_jy=3631.0,
    ),
    "PS1_I": FilterMetadata(
        key="PS1_I",
        catalog_key="panstarrs_dr1",
        catalog_label="Pan-STARRS",
        filter_label="i",
        lambda_eff_a=7520.0,
        band_width_a=1230.0,
        magnitude_system="ab",
        zero_point_jy=3631.0,
    ),
    "PS1_Z": FilterMetadata(
        key="PS1_Z",
        catalog_key="panstarrs_dr1",
        catalog_label="Pan-STARRS",
        filter_label="z",
        lambda_eff_a=8660.0,
        band_width_a=960.0,
        magnitude_system="ab",
        zero_point_jy=3631.0,
    ),
    "PS1_Y": FilterMetadata(
        key="PS1_Y",
        catalog_key="panstarrs_dr1",
        catalog_label="Pan-STARRS",
        filter_label="y",
        lambda_eff_a=9620.0,
        band_width_a=620.0,
        magnitude_system="ab",
        zero_point_jy=3631.0,
    ),
    "TMASS_J": FilterMetadata(
        key="TMASS_J",
        catalog_key="twomass",
        catalog_label="2MASS",
        filter_label="J",
        lambda_eff_a=12350.0,
        band_width_a=1620.0,
        magnitude_system="vega",
        zero_point_jy=1594.0,
    ),
    "TMASS_H": FilterMetadata(
        key="TMASS_H",
        catalog_key="twomass",
        catalog_label="2MASS",
        filter_label="H",
        lambda_eff_a=16620.0,
        band_width_a=2510.0,
        magnitude_system="vega",
        zero_point_jy=1024.0,
    ),
    "TMASS_KS": FilterMetadata(
        key="TMASS_KS",
        catalog_key="twomass",
        catalog_label="2MASS",
        filter_label="Ks",
        lambda_eff_a=21590.0,
        band_width_a=2620.0,
        magnitude_system="vega",
        zero_point_jy=666.7,
    ),
    "WISE_W1": FilterMetadata(
        key="WISE_W1",
        catalog_key="allwise",
        catalog_label="AllWISE",
        filter_label="W1",
        lambda_eff_a=33526.0,
        band_width_a=6626.0,
        magnitude_system="vega",
        zero_point_jy=309.540,
    ),
    "WISE_W2": FilterMetadata(
        key="WISE_W2",
        catalog_key="allwise",
        catalog_label="AllWISE",
        filter_label="W2",
        lambda_eff_a=46028.0,
        band_width_a=10422.0,
        magnitude_system="vega",
        zero_point_jy=171.787,
    ),
    "WISE_W3": FilterMetadata(
        key="WISE_W3",
        catalog_key="allwise",
        catalog_label="AllWISE",
        filter_label="W3",
        lambda_eff_a=115608.0,
        band_width_a=55055.0,
        magnitude_system="vega",
        zero_point_jy=31.674,
    ),
    "WISE_W4": FilterMetadata(
        key="WISE_W4",
        catalog_key="allwise",
        catalog_label="AllWISE",
        filter_label="W4",
        lambda_eff_a=220883.0,
        band_width_a=41010.0,
        magnitude_system="vega",
        zero_point_jy=8.363,
    ),
}

ASTROQUERY_MAG_COLUMNS_BY_SOURCE: dict[str, tuple[tuple[str, str, str], ...]] = {
    "i/360/syntphot": (
        ("Gmag", "e_Gmag", "GAIA_G"),
        ("BPmag", "e_BPmag", "GAIA_BP"),
        ("RPmag", "e_RPmag", "GAIA_RP"),
    ),
    "ii/349/ps1": (
        ("gmag", "e_gmag", "PS1_G"),
        ("rmag", "e_rmag", "PS1_R"),
        ("imag", "e_imag", "PS1_I"),
        ("zmag", "e_zmag", "PS1_Z"),
        ("ymag", "e_ymag", "PS1_Y"),
    ),
    "ii/246/out": (
        ("Jmag", "e_Jmag", "TMASS_J"),
        ("Hmag", "e_Hmag", "TMASS_H"),
        ("Kmag", "e_Kmag", "TMASS_KS"),
        ("Ksmag", "e_Ksmag", "TMASS_KS"),
    ),
    "ii/328/allwise": (
        ("W1mag", "e_W1mag", "WISE_W1"),
        ("W2mag", "e_W2mag", "WISE_W2"),
        ("W3mag", "e_W3mag", "WISE_W3"),
        ("W4mag", "e_W4mag", "WISE_W4"),
    ),
}


def vizier_catalog_options_payload() -> list[dict[str, str]]:
    return [{"key": item.key, "label": item.label, "source_id": item.source_id} for item in CATALOG_OPTIONS]


def normalize_catalog_keys(raw_keys: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    resolved: list[str] = []
    for raw in raw_keys:
        key = str(raw).strip().lower()
        if not key or key not in CATALOG_OPTIONS_BY_KEY or key in seen:
            continue
        seen.add(key)
        resolved.append(key)
    return resolved


def normalize_source_ids(raw_source_ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    resolved: list[str] = []
    for raw in raw_source_ids:
        source_id = str(raw).strip()
        if not source_id:
            continue
        source_key = source_id.lower()
        if source_key in seen:
            continue
        seen.add(source_key)
        resolved.append(source_id)
    return resolved


def parse_source_ids_text(raw_source_ids: object) -> list[str]:
    text = str(raw_source_ids or "").strip()
    if not text:
        return []
    return normalize_source_ids(SOURCE_ID_SPLIT_RE.split(text))


def normalize_radius_arcsec(raw_radius: object, *, default: float = DEFAULT_VIZIER_RADIUS_ARCSEC) -> float:
    text = str(raw_radius or "").strip()
    if not text:
        return float(default)
    parsed = parse_float_token(text)
    if parsed is None:
        raise ValueError("Search radius must be a numeric value in arcsec.")
    radius = float(parsed)
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Search radius must be a positive finite value in arcsec.")
    if radius > MAX_VIZIER_RADIUS_ARCSEC:
        raise ValueError(f"Search radius must be <= {MAX_VIZIER_RADIUS_ARCSEC:g} arcsec.")
    return radius


def normalize_center_query(raw_center: str) -> str:
    center = str(raw_center or "").strip()
    if not center:
        raise ValueError("Center coordinates are required.")

    decimal = DECIMAL_PAIR_RE.match(center)
    if decimal:
        ra = float(decimal.group(1))
        dec = float(decimal.group(2))
        if 0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0:
            return f"{ra:.8f} {dec:.8f}"

    sexagesimal = SEXAGESIMAL_PAIR_RE.match(center)
    if sexagesimal:
        ra_h = float(sexagesimal.group(1))
        ra_m = float(sexagesimal.group(2))
        ra_s = float(sexagesimal.group(3))
        dec_sign = -1.0 if sexagesimal.group(4) == "-" else 1.0
        dec_d = float(sexagesimal.group(5))
        dec_m = float(sexagesimal.group(6))
        dec_s = float(sexagesimal.group(7))
        ra = 15.0 * (ra_h + (ra_m / 60.0) + (ra_s / 3600.0))
        dec = dec_sign * (dec_d + (dec_m / 60.0) + (dec_s / 3600.0))
        if 0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0:
            return f"{ra:.8f} {dec:.8f}"

    if SkyCoord is not None and u is not None:
        try:
            coord = SkyCoord(center, unit=(u.hourangle, u.deg), frame="icrs")
            return f"{coord.ra.deg:.8f} {coord.dec.deg:.8f}"
        except Exception:
            pass
        try:
            coord = SkyCoord(center, frame="icrs")
            return f"{coord.ra.deg:.8f} {coord.dec.deg:.8f}"
        except Exception:
            pass

    # Keep unresolved names as-is so CDS name resolver can still handle them.
    return center


def query_vizier_photometry_points(
    *,
    center: str,
    radius_arcsec: float = DEFAULT_VIZIER_RADIUS_ARCSEC,
    catalog_keys: Iterable[str] = DEFAULT_CATALOG_KEYS,
    source_ids: Iterable[str] = (),
    include_all_catalogs: bool = False,
    timeout_seconds: float = DEFAULT_VIZIER_TIMEOUT_SECONDS,
    max_rows: int = DEFAULT_VIZIER_MAX_ROWS,
) -> list[VizierPhotometryPoint]:
    center_query = normalize_center_query(center)
    radius = normalize_radius_arcsec(radius_arcsec, default=DEFAULT_VIZIER_RADIUS_ARCSEC)
    selected_catalog_keys = normalize_catalog_keys(catalog_keys)
    selected_sources = [CATALOG_OPTIONS_BY_KEY[key].source_id for key in selected_catalog_keys]
    selected_sources.extend(normalize_source_ids(source_ids))
    selected_sources = normalize_source_ids(selected_sources)
    if not include_all_catalogs and not selected_sources:
        raise ValueError("At least one catalog or source ID must be selected.")

    try:
        return _query_vizier_sed_endpoint(
            center_query=center_query,
            radius_arcsec=radius,
            source_ids=selected_sources,
            include_all_catalogs=include_all_catalogs,
            timeout_seconds=timeout_seconds,
            max_rows=max_rows,
        )
    except Exception as exc:
        try:
            return _query_astroquery_fallback(
                center_query=center_query,
                radius_arcsec=radius,
                source_ids=selected_sources,
                include_all_catalogs=include_all_catalogs,
                max_rows=max_rows,
            )
        except Exception as fallback_exc:
            raise ValueError(f"VizieR query failed ({exc}); astroquery fallback failed ({fallback_exc}).") from exc


def format_photometry_table_rows(points: Iterable[VizierPhotometryPoint]) -> str:
    rows: list[str] = []
    for point in points:
        line = f"{point.lambda_eff_a:.3f} {point.band_width_a:.3f} {point.flux:.8e}"
        err_value = 0.0
        if point.flux_err is not None and math.isfinite(point.flux_err) and point.flux_err > 0.0:
            err_value = float(point.flux_err)
        line = f"{line} {err_value:.8e} 1"
        comment = point.comment.strip()
        if comment:
            line = f"{line} # {comment}"
        rows.append(line)
    return "\n".join(rows)


def _query_vizier_sed_endpoint(
    *,
    center_query: str,
    radius_arcsec: float,
    source_ids: list[str],
    include_all_catalogs: bool,
    timeout_seconds: float,
    max_rows: int,
) -> list[VizierPhotometryPoint]:
    params = _build_vizier_query_params(
        center_query=center_query,
        radius_arcsec=radius_arcsec,
        source_ids=source_ids,
        include_all_catalogs=include_all_catalogs,
        max_rows=max_rows,
    )

    query = urlencode(params)
    url = f"{VIZIER_SED_ENDPOINT}?{query}"
    request = Request(
        url,
        headers={
            "User-Agent": "cmfgen-viewer/1.0",
            "Accept": "application/x-votable+xml, text/xml, application/xml, text/plain;q=0.5",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - user input is query-only
            payload = response.read()
    except HTTPError as exc:
        raise ValueError(f"HTTP {exc.code} from VizieR SED service.") from exc
    except URLError as exc:
        raise ValueError(f"Could not reach VizieR SED service: {exc.reason}.") from exc

    _persist_vizier_raw_payload(query_url=url, payload=payload)

    table = _parse_response_table(payload)
    points = _extract_points_from_sed_table(table)
    points.sort(key=lambda item: item.lambda_eff_a)
    return points


def _build_vizier_query_params(
    *,
    center_query: str,
    radius_arcsec: float,
    source_ids: list[str],
    include_all_catalogs: bool,
    max_rows: int,
) -> dict[str, str]:
    params = {
        "-c": center_query,
        "-c.rs": f"{radius_arcsec:g}",
        "-out.max": str(max(1, int(max_rows))),
        "-out.form": "VOTable",
    }
    if not include_all_catalogs and source_ids:
        params["-source"] = ",".join(source_ids)
    return params


def _parse_response_table(payload: bytes) -> Table:
    if not payload:
        raise ValueError("Empty response from VizieR SED service.")

    try:
        table = Table.read(io.BytesIO(payload), format="votable")
        if len(table.colnames) > 0:
            return table
    except Exception:
        pass

    text = payload.decode("utf-8", errors="replace")
    if "<html" in text.lower():
        head = " ".join(text.split())[:160]
        raise ValueError(f"VizieR SED service returned HTML instead of a data table: {head}")

    try:
        table = Table.read(io.StringIO(text), format="ascii.tab")
    except Exception as exc:
        raise ValueError("Could not parse VizieR SED response.") from exc
    if len(table.colnames) <= 0:
        raise ValueError("VizieR SED response does not include tabular columns.")
    return table


def _persist_vizier_raw_payload(*, query_url: str, payload: bytes) -> None:
    """Best-effort debug dump of raw VizieR payload to /tmp for operator inspection."""
    try:
        VIZIER_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    token = secrets.token_hex(4)
    stem = f"vizier_sed_{stamp}_{token}"

    payload_path = VIZIER_DEBUG_DIR / f"{stem}.votable"
    url_path = VIZIER_DEBUG_DIR / f"{stem}.url.txt"
    latest_payload_path = VIZIER_DEBUG_DIR / "latest.votable"
    latest_url_path = VIZIER_DEBUG_DIR / "latest.url.txt"

    try:
        payload_path.write_bytes(payload)
        url_path.write_text(f"{query_url}\n", encoding="utf-8")
        latest_payload_path.write_bytes(payload)
        latest_url_path.write_text(f"{query_url}\n", encoding="utf-8")
    except OSError:
        return


def _extract_points_from_sed_table(table: Table) -> list[VizierPhotometryPoint]:
    lookup = {name.lower(): name for name in table.colnames}
    freq_column = _find_column_name(
        lookup,
        ("sed_freq", "freq", "nu", "frequency"),
    )
    flux_column = _find_column_name(
        lookup,
        ("sed_flux", "flux", "fnu"),
    )
    eflux_column = _find_column_name(
        lookup,
        ("sed_eflux", "e_sed_flux", "flux_err", "e_flux", "eflux"),
    )
    filter_column = _find_column_name(
        lookup,
        ("sed_filter", "filter", "band", "passband"),
    )
    source_column = _find_column_name(
        lookup,
        ("sed_source", "sed_cat", "source", "catalog", "cat", "_tabname", "_tab"),
    )

    if freq_column is None or flux_column is None:
        raise ValueError("VizieR SED response does not provide sed_freq/sed_flux columns.")

    freq_factor = _frequency_unit_to_hz_factor(getattr(table[freq_column], "unit", None))
    flux_factor = _flux_unit_to_jy_factor(getattr(table[flux_column], "unit", None))
    eflux_factor = _flux_unit_to_jy_factor(getattr(table[eflux_column], "unit", None)) if eflux_column else flux_factor

    points: list[VizierPhotometryPoint] = []
    for row in table:
        freq_raw = _safe_float(row[freq_column])
        flux_raw = _safe_float(row[flux_column])
        if freq_raw is None or flux_raw is None:
            continue
        freq_hz = freq_raw * freq_factor
        if not math.isfinite(freq_hz) or freq_hz <= 0.0:
            continue
        flux_jy = flux_raw * flux_factor
        if not math.isfinite(flux_jy) or flux_jy <= 0.0:
            continue

        lambda_eff_a = LIGHT_SPEED_ANGSTROM_PER_S / freq_hz
        if not math.isfinite(lambda_eff_a) or lambda_eff_a <= 0.0:
            continue

        flux = _flux_jy_to_flambda(flux_jy, lambda_eff_a)
        if not math.isfinite(flux) or flux <= 0.0:
            continue

        flux_err: float | None = None
        if eflux_column is not None:
            eflux_raw = _safe_float(row[eflux_column])
            if eflux_raw is not None:
                eflux_jy = abs(eflux_raw * eflux_factor)
                flux_err_candidate = _flux_jy_to_flambda(eflux_jy, lambda_eff_a)
                if math.isfinite(flux_err_candidate) and flux_err_candidate > 0.0:
                    flux_err = flux_err_candidate

        filter_name = str(row[filter_column]).strip() if filter_column is not None else ""
        source_name = str(row[source_column]).strip() if source_column is not None else ""
        metadata = _match_filter_metadata(filter_name, source_name)
        band_width = metadata.band_width_a if metadata is not None else _fallback_band_width(lambda_eff_a)
        comment = _build_comment(
            metadata=metadata,
            source_name=source_name,
            filter_name=filter_name,
        )
        points.append(
            VizierPhotometryPoint(
                lambda_eff_a=float(lambda_eff_a),
                band_width_a=float(band_width),
                flux=float(flux),
                flux_err=flux_err,
                comment=comment,
            )
        )

    return points


def _find_column_name(lookup: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    for lowered, original in lookup.items():
        for candidate in candidates:
            if candidate in lowered:
                return original
    return None


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if getattr(value, "mask", False) is True:
        return None
    if isinstance(value, float | int):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    parsed = parse_float_token(str(value))
    if parsed is None:
        return None
    numeric = float(parsed)
    return numeric if math.isfinite(numeric) else None


def _frequency_unit_to_hz_factor(unit: object) -> float:
    text = str(unit or "").strip().lower()
    if "ghz" in text:
        return 1e9
    if "mhz" in text:
        return 1e6
    if "khz" in text:
        return 1e3
    if "hz" in text:
        return 1.0
    # VizieR SED API documents sed_freq in GHz.
    return 1e9


def _flux_unit_to_jy_factor(unit: object) -> float:
    text = str(unit or "").strip().lower()
    if "mjy" in text:
        return 1e-3
    if "ujy" in text or "µjy" in text:
        return 1e-6
    if "njy" in text:
        return 1e-9
    if "jy" in text:
        return 1.0
    # VizieR SED API documents sed_flux/sed_eflux in Jy.
    return 1.0


def _flux_jy_to_flambda(flux_jy: float, lambda_eff_a: float) -> float:
    if lambda_eff_a <= 0.0:
        return math.nan
    return flux_jy * JY_TO_FLAMBDA_ANGSTROM_FACTOR / (lambda_eff_a * lambda_eff_a)


def _fallback_band_width(lambda_eff_a: float) -> float:
    # Conservative fallback for unknown filters: 10% of effective wavelength.
    return max(1.0, 0.10 * float(lambda_eff_a))


def _match_filter_metadata(filter_name: str, source_name: str) -> FilterMetadata | None:
    filter_text = str(filter_name or "").strip().upper()
    source_text = str(source_name or "").strip().lower()

    is_gaia = "gaia" in filter_text.lower() or "i/360/syntphot" in source_text
    is_ps1 = "ps1" in filter_text.lower() or "pan" in filter_text.lower() or "ii/349/ps1" in source_text
    is_tmass = "2mass" in filter_text.lower() or "ii/246/out" in source_text
    is_wise = "wise" in filter_text.lower() or "ii/328/allwise" in source_text

    if is_gaia:
        if "BP" in filter_text or "GBP" in filter_text:
            return FILTER_LIBRARY["GAIA_BP"]
        if "RP" in filter_text or "GRP" in filter_text:
            return FILTER_LIBRARY["GAIA_RP"]
        if re.search(r"(^|[^A-Z0-9])G([^A-Z0-9]|$)", filter_text):
            return FILTER_LIBRARY["GAIA_G"]

    if is_ps1:
        if re.search(r"(^|[^A-Z0-9])G([^A-Z0-9]|$)", filter_text):
            return FILTER_LIBRARY["PS1_G"]
        if re.search(r"(^|[^A-Z0-9])R([^A-Z0-9]|$)", filter_text):
            return FILTER_LIBRARY["PS1_R"]
        if re.search(r"(^|[^A-Z0-9])I([^A-Z0-9]|$)", filter_text):
            return FILTER_LIBRARY["PS1_I"]
        if re.search(r"(^|[^A-Z0-9])Z([^A-Z0-9]|$)", filter_text):
            return FILTER_LIBRARY["PS1_Z"]
        if re.search(r"(^|[^A-Z0-9])Y([^A-Z0-9]|$)", filter_text):
            return FILTER_LIBRARY["PS1_Y"]

    if is_tmass:
        if re.search(r"(^|[^A-Z0-9])J([^A-Z0-9]|$)", filter_text):
            return FILTER_LIBRARY["TMASS_J"]
        if re.search(r"(^|[^A-Z0-9])H([^A-Z0-9]|$)", filter_text):
            return FILTER_LIBRARY["TMASS_H"]
        if "KS" in filter_text or re.search(r"(^|[^A-Z0-9])K([^A-Z0-9]|$)", filter_text):
            return FILTER_LIBRARY["TMASS_KS"]

    if is_wise:
        if "W1" in filter_text:
            return FILTER_LIBRARY["WISE_W1"]
        if "W2" in filter_text:
            return FILTER_LIBRARY["WISE_W2"]
        if "W3" in filter_text:
            return FILTER_LIBRARY["WISE_W3"]
        if "W4" in filter_text:
            return FILTER_LIBRARY["WISE_W4"]

    return None


def _build_comment(
    *,
    metadata: FilterMetadata | None,
    source_name: str,
    filter_name: str,
) -> str:
    source_text = str(source_name or "").strip()

    if metadata is not None:
        if source_text:
            return f"{source_text} {metadata.catalog_label} {metadata.filter_label}"
        return f"{metadata.catalog_label} {metadata.filter_label}"

    if source_text:
        option = CATALOG_OPTIONS_BY_SOURCE_ID.get(source_text.lower())
        if option is not None:
            source_text = source_text + " " + option.label
    filter_text = str(filter_name or "").strip()
    if source_text and filter_text:
        return f"{source_text} {filter_text}"
    if filter_text:
        return filter_text
    if source_text:
        return source_text
    return "VizieR SED"


def _query_astroquery_fallback(
    *,
    center_query: str,
    radius_arcsec: float,
    source_ids: list[str],
    include_all_catalogs: bool,
    max_rows: int,
) -> list[VizierPhotometryPoint]:
    try:
        from astroquery.vizier import Vizier
    except ModuleNotFoundError as exc:
        raise ValueError("astroquery is not installed.") from exc

    if u is None or SkyCoord is None:
        raise ValueError("Astropy coordinates support is unavailable.")

    center_coord = _parse_center_skycoord(center_query)
    if center_coord is None:
        raise ValueError("Could not parse center coordinates for astroquery fallback.")

    query_sources = [source.lower() for source in source_ids]
    if include_all_catalogs or not query_sources:
        query_sources = [item.source_id.lower() for item in CATALOG_OPTIONS]

    vizier = Vizier(columns=["**"], row_limit=max(1, int(max_rows)))
    radius = radius_arcsec * u.arcsec

    points: list[VizierPhotometryPoint] = []
    for source_id in query_sources:
        source_display = source_id.upper()
        try:
            tables = vizier.query_region(center_coord, radius=radius, catalog=source_display)
        except Exception:
            continue
        for table in tables:
            points.extend(_extract_points_from_catalog_table(source_id, table))

    points.sort(key=lambda item: item.lambda_eff_a)
    return points


def _parse_center_skycoord(center_query: str):
    if SkyCoord is None or u is None:
        return None
    try:
        ra_text, dec_text = center_query.split()
    except ValueError:
        return None
    parsed_ra = parse_float_token(ra_text)
    parsed_dec = parse_float_token(dec_text)
    if parsed_ra is None or parsed_dec is None:
        return None
    ra = float(parsed_ra)
    dec = float(parsed_dec)
    if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0):
        return None
    try:
        return SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
    except Exception:
        return None


def _extract_points_from_catalog_table(source_id: str, table: Table) -> list[VizierPhotometryPoint]:
    source_key = str(source_id).strip().lower()
    columns = ASTROQUERY_MAG_COLUMNS_BY_SOURCE.get(source_key)
    if not columns:
        return []

    name_lookup = {name.lower(): name for name in table.colnames}
    points: list[VizierPhotometryPoint] = []
    for mag_column, err_column, filter_key in columns:
        if mag_column.lower() not in name_lookup:
            continue
        metadata = FILTER_LIBRARY.get(filter_key)
        if metadata is None:
            continue
        mag_name = name_lookup[mag_column.lower()]
        err_name = name_lookup.get(err_column.lower())
        for row in table:
            mag = _safe_float(row[mag_name])
            if mag is None:
                continue
            mag_err = _safe_float(row[err_name]) if err_name is not None else None
            flux_jy, flux_err_jy = _magnitude_to_flux_jy(mag, mag_err, metadata=metadata)
            if flux_jy is None:
                continue
            flux = _flux_jy_to_flambda(flux_jy, metadata.lambda_eff_a)
            if not math.isfinite(flux) or flux <= 0.0:
                continue
            flux_err = (
                _flux_jy_to_flambda(flux_err_jy, metadata.lambda_eff_a)
                if flux_err_jy is not None and flux_err_jy > 0.0
                else None
            )
            points.append(
                VizierPhotometryPoint(
                    lambda_eff_a=metadata.lambda_eff_a,
                    band_width_a=metadata.band_width_a,
                    flux=flux,
                    flux_err=flux_err,
                    comment=f"{metadata.catalog_label} {metadata.filter_label}",
                )
            )
    return points


def _magnitude_to_flux_jy(
    magnitude: float,
    magnitude_error: float | None,
    *,
    metadata: FilterMetadata,
) -> tuple[float | None, float | None]:
    if metadata.zero_point_jy is None or metadata.zero_point_jy <= 0.0:
        return None, None
    if not math.isfinite(magnitude):
        return None, None
    flux_jy = metadata.zero_point_jy * (10.0 ** (-0.4 * magnitude))
    if not math.isfinite(flux_jy) or flux_jy <= 0.0:
        return None, None

    if magnitude_error is None or not math.isfinite(magnitude_error) or magnitude_error <= 0.0:
        return flux_jy, None
    flux_error_jy = flux_jy * (math.log(10.0) / 2.5) * float(abs(magnitude_error))
    if not math.isfinite(flux_error_jy) or flux_error_jy <= 0.0:
        return flux_jy, None
    return flux_jy, flux_error_jy
