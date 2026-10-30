"""Diagnostica: un file scaricabile con tutto cio' che serve per capire cosa e' andato storto nelle ultime ore (impostazioni, prompt, riunioni, task,
chiamate, errori, spese). I segreti (chiavi, token, password) sono sempre omessi. Solo il titolare puo' scaricarlo."""
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from .competenze_base import VERSIONE
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione", tags=["diagnostica"])

SEGRETO = re.compile(r"chiave|token|password|passw|hash|segret|secret|cifrat|cookie|credenzial|salt|pin\b|codice_recupero|otp|api_key|bearer|iscrizione_push|endpoint|p256dh|auth_key", re.I)
CONFIGURAZIONE = ["divisioni", "agenti", "agenti_aziende", "impostazioni_sistema", "competenze", "modelli_ai", "fornitori_ai", "trigger_agente", "aziende",
                  "progetti_agenti", "squadre", "agenti_connessioni", "regole_smistamento", "schede_impresa"]
ATTIVITA = ["tavoli", "tavoli_interventi", "tavoli_partecipanti", "chat_messaggi", "conversazioni", "chat_coda", "task", "task_commenti", "task_documenti",
            "documenti", "documenti_agenti", "consegne", "eventi_lavoro", "misure_chiamate", "registro_azioni", "registro_decisioni", "registro_uscite", "notifiche",
            "messaggi_agenti", "avvisi_agente", "esiti_fasi", "fasi_agente", "sandbox_esecuzioni", "trigger_esecuzioni", "uso_eventi", "note_aurora", "miglioramenti",
            "instradamenti", "richieste_informazioni", "conferme_vocali", "note_vocali", "sospensioni_agenti", "agenti_istruzioni_storico", "memorie_lavoro",
            "revisioni_incrociate", "valutazioni", "iniziative", "discussioni_proposte", "task_proposte", "progetti_decisioni", "briefing_manager", "casi_prova"]
CANDIDATE_TEMPO = ["creato_il", "creata_il", "creato_a", "quando", "data", "inizio", "avviato_il", "aggiornato_il", "ricevuto_il", "inviato_il", "salvato_il", "ts"]
MAX_CELLA = 20000
MAX_RIGHE = 3000


def _valore(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"[binario {len(v)} byte]"
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, str) and len(v) > MAX_CELLA:
        return v[:MAX_CELLA] + f"… [troncato, {len(v)} caratteri]"
    if isinstance(v, (int, float, bool, str, type(None), list, dict)):
        return v
    return str(v)


def _pulisci(riga: dict, tabella: str = "") -> dict:
    if tabella == "impostazioni_sistema" and "chiave" in riga:   # qui «chiave» e' il nome dell'impostazione: si nasconde il valore se e' un segreto
        r = {k: _valore(v) for k, v in riga.items()}
        if SEGRETO.search(str(riga.get("chiave"))) or "valore_cifrato" in riga:
            for k in ("valore", "valore_cifrato"):
                if k in r and r[k] not in (None, ""): r[k] = "[omesso]"
        return r
    return {k: ("[omesso]" if SEGRETO.search(k) and v not in (None, "", False) else _valore(v)) for k, v in riga.items()}


def _colonne(conn, tabella: str) -> list[dict]:
    return conn.execute("SELECT column_name AS n, data_type AS t FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position", (tabella,)).fetchall()


def _tabella(conn, nome: str, ore: int | None) -> dict | None:
    cols = _colonne(conn, nome)
    if not cols:
        return None
    nomi = [c["n"] for c in cols]
    sel = ", ".join(f'"{c["n"]}"' for c in cols if c["t"] != "bytea")
    tempo = next((c for c in CANDIDATE_TEMPO if c in nomi and next(x["t"] for x in cols if x["n"] == c).startswith("timestamp")), None)
    ordine = '"id" DESC' if "id" in nomi else (f'"{tempo}" DESC' if tempo else "1")
    try:
        if ore is not None and tempo:
            righe = conn.execute(f'SELECT {sel} FROM "{nome}" WHERE "{tempo}" >= NOW() - (%s || \' hours\')::interval ORDER BY {ordine} LIMIT {MAX_RIGHE}', (str(ore),)).fetchall()
            finestra = f"ultime {ore} ore (campo {tempo})"
        else:
            righe = conn.execute(f'SELECT {sel} FROM "{nome}" ORDER BY {ordine} LIMIT {MAX_RIGHE}').fetchall()
            finestra = "tutte" if ore is None else f"ultime {MAX_RIGHE} righe (nessun campo data)"
    except Exception as e:  # noqa: BLE001 - una tabella rotta non blocca il file
        conn.rollback()
        return {"errore_lettura": str(e)[:200]}
    righe = [_pulisci(r, nome) for r in reversed(righe)]
    out = {"finestra": finestra, "righe": len(righe), "dati": righe}
    if len(righe) >= MAX_RIGHE:
        out["avviso"] = f"limitato alle {MAX_RIGHE} righe piu' recenti"
    return out


def _sospetti(conn, ore: int) -> list[str]:
    """Segnali che spesso spiegano un blocco: li metto in cima al file."""
    s = []
    def q(sql, *a):
        try:
            return conn.execute(sql, a).fetchall()
        except Exception:  # noqa: BLE001
            conn.rollback(); return []
    for r in q("SELECT id, titolo, stato, occupato, errore FROM tavoli WHERE (occupato AND creato_il < NOW() - interval '10 minutes') OR stato = 'errore' OR errore IS NOT NULL"):
        s.append(f"Riunione/tavolo {r['id']} «{r['titolo']}»: stato {r['stato']}" + (", occupato da piu' di 10 minuti (risposte rimaste in sospeso)" if r["occupato"] else "") + (f", errore: {r['errore']}" if r["errore"] else ""))
    for r in q("SELECT nome FROM agenti WHERE NOT attivo"):
        s.append(f"Agente spento: {r['nome']}")
    for r in q("SELECT a.nome, sp.motivo FROM sospensioni_agenti sp JOIN agenti a ON a.id = sp.agente_id WHERE sp.riattivato_il IS NULL"):
        s.append(f"Agente sospeso: {r['nome']} ({r['motivo']})")
    for r in q("SELECT nome, tetto_spesa_mese AS tetto_mensile FROM divisioni WHERE tetto_spesa_mese IS NOT NULL"):
        s.append(f"Reparto con tetto di spesa mensile: {r['nome']} ({r['tetto_mensile']}): controlla se e' stato raggiunto")
    for r in q("SELECT t.id, t.titolo, t.stato FROM task t WHERE t.stato IN ('in_corso','assegnato') AND t.aggiornato_il < NOW() - interval '1 hour'"):
        s.append(f"Task fermo da piu' di un'ora: {r['id']} «{r['titolo']}» ({r['stato']})")
    return s


@router.get("/diagnostica")
def scarica(ore: int = Query(24, ge=1, le=168), riunione: int | None = None, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        out = {"generato_il": datetime.now(timezone.utc).isoformat(), "versione_opifex": VERSIONE, "finestra_ore": ore,
               "nota": "Segreti (chiavi, token, password) omessi. Dentro ci sono conversazioni e prompt reali: condividilo solo con chi deve analizzarlo."}
        out["sospetti"] = _sospetti(conn, ore)
        if riunione:
            out["riunione_richiesta"] = riunione
        # tutti gli errori registrati nelle tabelle (colonna «errore» valorizzata) nella finestra
        errori = {}
        for nome in ATTIVITA:
            cols = {c["n"] for c in _colonne(conn, nome)}
            if "errore" in cols:
                t = _tabella(conn, nome, ore)
                if t and t.get("dati"):
                    ev = [r for r in t["dati"] if r.get("errore")]
                    if ev:
                        errori[nome] = ev
        out["errori"] = errori
        out["configurazione"] = {n: t for n in CONFIGURAZIONE if (t := _tabella(conn, n, None))}
        out["attivita"] = {n: t for n in ATTIVITA if (t := _tabella(conn, n, ore))}
    corpo = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    nome = "diagnostica-opifex-" + datetime.now().strftime("%Y%m%d-%H%M") + ".json"
    return Response(content=corpo, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{nome}"'})
