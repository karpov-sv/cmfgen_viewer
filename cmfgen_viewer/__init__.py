"""CMFGEN viewer package; scientific helpers can be imported without Flask."""

__all__ = ["create_app"]


def __getattr__(name: str):
    if name == "create_app":
        from .app import create_app

        globals()[name] = create_app
        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
