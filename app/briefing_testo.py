"""Costruzione del testo del briefing a partire dai dati (nessuna dipendenza: si puo' collaudare da sola)."""
from datetime import date, datetime


def _data(v) -> str:
    if isinstance(v, (date, datetime)):
        return v.strftime("%d/%m")
    return str(v) if v else "senza data"


def _elenco(righe, formato, massimo=8):
    out = [formato(r) for r in righe[:massimo]]
    if len(righe) > massimo:
        out.append(f"... e altri {len(righe) - massimo}")
    return out


def riepilogo_testuale(tipo: str, d: dict) -> str:
    """tipo: 'mattina' | 'sera'. d: dati raccolti dal database."""
    intestazione = "Briefing del mattino" if tipo == "mattina" else "Briefing della sera"
    righe = [intestazione, ""]

    appr = d.get("approvazioni", [])
    righe.append(f"DA APPROVARE ({len(appr)})")
    if appr:
        righe += _elenco(appr, lambda r: f"- {r.get('titolo') or 'Compito'}: {r.get('sintesi', '')}")
    else:
        righe.append("- Niente in attesa")

    rich = d.get("richieste", [])
    if rich:
        righe += ["", f"INFORMAZIONI CHE MI SERVONO DA TE ({len(rich)})"]
        righe += _elenco(rich, lambda r: f"- {'[BLOCCANTE] ' if r.get('bloccante') else ''}{r['agente']}: {r['domanda']}", 12)

    prop = d.get("proposte", [])
    if prop:
        righe += ["", f"PROPOSTE DI SVILUPPO IN ATTESA ({len(prop)})"]
        righe += _elenco(prop, lambda r: f"- {r['titolo']} ({r.get('gravita', 'media')})")

    sc = d.get("scadenze", [])
    righe += ["", f"SCADENZE VICINE ({len(sc)})"]
    if sc:
        righe += _elenco(sc, lambda r: f"- {_data(r.get('scadenza'))}: {r['titolo']} [{r.get('stato', '')}]")
    else:
        righe.append("- Nessuna nei prossimi giorni")

    fatti = d.get("completati", [])
    etichetta = "COMPLETATI DA IERI" if tipo == "mattina" else "COMPLETATI OGGI"
    righe += ["", f"{etichetta} ({len(fatti)})"]
    if fatti:
        righe += _elenco(fatti, lambda r: f"- {r['titolo']}")
    else:
        righe.append("- Nessuno")

    stati = d.get("compiti_per_stato", {})
    if stati:
        righe += ["", "COMPITI APERTI: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(stati.items()))]

    righe += ["", f"COSTI AI ULTIME 24 ORE: {float(d.get('costi_24h', 0)):.2f}",
              f"USCITE DATI BLOCCATE ULTIME 24 ORE: {int(d.get('blocchi_24h', 0))}"]
    return "\n".join(righe)
