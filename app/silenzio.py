"""Ore di silenzio: di notte (predefinito 23:00-08:00, ora italiana) arrivano solo le notifiche di massima urgenza (allarmi di sistema, tetto di spesa raggiunto).
Le altre restano in coda e al mattino, se sono tante, arrivano in un solo riepilogo."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

ROMA = ZoneInfo("Europe/Rome")
SOGLIA_RIEPILOGO = 3


def _imp(conn, k, d=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return (r["valore"] if r and r["valore"] != "" else d)


def _ora(s: str, d: time) -> time:
    try:
        h, m = s.strip().split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return d


def impostazioni(conn) -> dict:
    return {"attivo": _imp(conn, "silenzio_attivo", "true") == "true", "da": _imp(conn, "silenzio_da", "23:00"), "a": _imp(conn, "silenzio_a", "08:00")}


def in_silenzio(conn, adesso: datetime | None = None) -> bool:
    s = impostazioni(conn)
    if not s["attivo"]:
        return False
    t = (adesso or datetime.now(ROMA)).astimezone(ROMA).time()
    da, a = _ora(s["da"], time(23, 0)), _ora(s["a"], time(8, 0))
    return (t >= da or t < a) if da > a else (da <= t < a)


def da_spedire(conn, colonna: str, limite: int, adesso: datetime | None = None) -> list[dict]:
    """Notifiche ancora da spedire sul canale (colonna = inviata_il | push_il).
    In silenzio solo le critiche; fuori dal silenzio, se i messaggi in coda sono tanti, un unico riepilogo (voce con 'ids')."""
    assert colonna in ("inviata_il", "push_il")
    silenzio = in_silenzio(conn, adesso)
    righe = conn.execute(f"SELECT id, testo, urgente FROM notifiche WHERE {colonna} IS NULL AND creata_il > NOW() - interval '1 day' "
                         f"{'AND critica' if silenzio else ''} ORDER BY id LIMIT 50").fetchall()
    urgenti = [r for r in righe if r["urgente"]]
    normali = [r for r in righe if not r["urgente"]]
    out = [{"ids": [r["id"]], "testo": r["testo"], "urgente": True} for r in urgenti]
    if len(normali) > SOGLIA_RIEPILOGO:
        out.append({"ids": [r["id"] for r in normali], "urgente": False,
                    "testo": f"Riepilogo: {len(normali)} notifiche mentre non c'eri\n" + "\n".join("• " + r["testo"].split("\n")[0][:110] for r in normali[:12])
                             + (f"\n… e altre {len(normali) - 12}" if len(normali) > 12 else "")})
    else:
        out += [{"ids": [r["id"]], "testo": r["testo"], "urgente": False} for r in normali]
    return sorted(out, key=lambda x: x["ids"][0])[:limite]
