from backend.main import app


def main() -> None:
    """Console entry point for quick smoke checks."""
    print("Backend package is installed. Run `uv run uvicorn backend.main:app --reload`.")


__all__ = ["app"]
