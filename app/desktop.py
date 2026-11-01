"""App per computer (Windows): l'eseguibile si aggiorna da solo da qui, a ogni avvio, insieme a Opifex.
Il manifesto e i file sono pubblici (nessun segreto: solo il programma dell'indice); l'integrita' si verifica con SHA-256."""
import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from .versione import versione_corrente

router = APIRouter(prefix="/desktop", tags=["desktop"])
CARTELLA = Path(__file__).resolve().parent / "desktop"
# pacchetti Python dell'app per computer: se cambia questo elenco, aumenta REQUISITI_REV e l'app li reinstalla da sola
REQUISITI_REV = 1
REQUISITI = ["numpy", "pillow", "pypdf", "imageio-ffmpeg", "faster-whisper", "open_clip_torch"]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def manifesto() -> dict:
    ind = CARTELLA / "indice.py"
    exe = CARTELLA / "IndiceArchivio.exe"
    try:
        lv = int((CARTELLA / "lanciatore.txt").read_text().strip())
    except (OSError, ValueError):
        lv = 0
    m = {"opifex": versione_corrente(), "requisiti": {"rev": REQUISITI_REV, "pacchetti": REQUISITI},
         "indice": {"sha256": _sha(ind), "url": "/desktop/indice.py"} if ind.exists() else None,
         "lanciatore": {"versione": lv, "sha256": _sha(exe), "url": "/desktop/IndiceArchivio.exe"} if exe.exists() else None}
    return m


@router.get("/manifesto")
def il_manifesto():
    return manifesto()


@router.get("/indice.py")
def file_indice():
    p = CARTELLA / "indice.py"
    if not p.exists():
        raise HTTPException(404, "Non disponibile")
    return Response(p.read_bytes(), media_type="text/x-python; charset=utf-8")


@router.get("/IndiceArchivio.exe")
def file_exe():
    p = CARTELLA / "IndiceArchivio.exe"
    if not p.exists():
        raise HTTPException(404, "Non disponibile")
    return FileResponse(p, media_type="application/vnd.microsoft.portable-executable", filename="Opifex-Archivio.exe")
