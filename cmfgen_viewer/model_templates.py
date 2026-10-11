"""Resolve reusable workflow files in the same layout as a model directory."""

from pathlib import Path

PACKAGED_TEMPLATE_ROOT = Path(__file__).parent / "data" / "templates"


def resolve_model_template(model: Path, relative_path: str, *, template_root=None) -> dict:
    """Resolve one file: model, explicit root, ancestor roots, packaged defaults.

    Template directories mirror the model layout directly. Model inputs and products
    must never be passed here unless they are deliberately reusable setup files.
    """
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Template path must be relative to the model layout")
    model = model.expanduser().resolve()
    candidates = [(model / relative, "source model", model)]
    if template_root is not None:
        root = Path(template_root).expanduser().resolve()
        candidates.append((root / relative, "explicit templates", root))
    for parent in (model, *model.parents):
        root = parent / "templates"
        candidates.append((root / relative, "model-tree templates", root))
    candidates.append((PACKAGED_TEMPLATE_ROOT / relative,
                       "packaged templates", PACKAGED_TEMPLATE_ROOT))
    seen = set()
    for path, origin, root in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.is_file() and not path.is_symlink():
            return {"path": str(path), "origin": origin, "root": str(root), "exists": True}
    return {"path": "", "origin": "", "root": "", "exists": False}
