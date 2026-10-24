"""Versione installata (file VERSIONE nella cartella dell'applicazione)."""
from pathlib import Path

_FILE = Path(__file__).resolve().parent.parent / "VERSIONE"


def versione_corrente() -> str:
    try:
        return _FILE.read_text().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def come_numeri(v: str) -> tuple[int, int, int]:
    parti = (v.strip().lstrip("vV").split(".") + ["0", "0", "0"])[:3]
    try:
        return tuple(int(p) for p in parti)  # type: ignore[return-value]
    except ValueError:
        return (0, 0, 0)
