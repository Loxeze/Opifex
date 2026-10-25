"""Sandbox: uno spazio chiuso e contingentato sul server dove gli agenti provano il codice che scrivono.

Ogni prova gira in un contenitore usa-e-getta (Docker o Podman) senza rete, senza i dati ne' le chiavi di Opifex, con memoria, processori,
tempo, processi e disco limitati, utente senza privilegi, file system in sola lettura tranne la cartella di lavoro. Nulla viene installato o
scaricato da Opifex: l'immagine deve gia' esserci sul server. Rete o limiti piu' larghi richiedono l'approvazione di Lorenzo."""
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

LIMITI = {"memoria": "256m", "cpu": "0.5", "processi": "64", "tempo_s": 30, "disco_mb": "64", "uscita_max": 8000, "codice_max": 20000}
LINGUAGGI = {"python": ("py", ["python", "/work/main.py"]), "node": ("js", ["node", "/work/main.js"]), "bash": ("sh", ["sh", "/work/main.sh"])}
AVVISO = ("\n\nSANDBOX: con prova_codice puoi eseguire il codice che scrivi (python, node o bash) in uno spazio chiuso: niente rete, niente dati di Opifex, 30 secondi, 256 MB. "
          "Prova sempre il codice prima di consegnarlo e correggi gli errori che vedi. Se serve la rete indica rete=true e il motivo: la approva Lorenzo. "
          "Il codice che consegni va salvato nella cartella Drive del progetto, se hai gli strumenti Drive.")
STRUMENTO = {"name": "prova_codice",
             "description": "Esegue codice in una sandbox isolata (senza rete, tempo e memoria limitati) e restituisce l'output. linguaggio: python, node o bash. "
                            "rete=true richiede l'approvazione di Lorenzo (indica motivo_rete).",
             "input_schema": {"type": "object", "properties": {"linguaggio": {"type": "string", "enum": ["python", "node", "bash"]}, "codice": {"type": "string"},
                                                               "rete": {"type": "boolean"}, "motivo_rete": {"type": "string"}}, "required": ["linguaggio", "codice"]}}


def _impostazione(conn, chiave, difetto=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return r["valore"] if r else difetto


def motore() -> str | None:
    return shutil.which("docker") or shutil.which("podman")


def _lancia(args: list[str], timeout: int) -> tuple[int, str]:
    """Esegue un comando e ne restituisce (codice, uscita). Isolato qui per poterlo sostituire nei collaudi."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError as e:
        return 127, str(e)


def stato(conn) -> dict:
    m = motore()
    pronto = False
    immagini = {}
    if m:
        code, _ = _lancia([m, "info"], 15)
        pronto = code == 0
        for k in ("python", "node"):
            img = _impostazione(conn, "sandbox_immagine_" + k)
            immagini[k] = {"nome": img, "presente": pronto and _lancia([m, "image", "inspect", img], 15)[0] == 0}
    return {"attiva": _impostazione(conn, "sandbox_attiva") == "true", "motore": m, "motore_pronto": pronto, "immagini": immagini, "limiti": LIMITI}


def comando(motore_: str, nome: str, immagine: str, linguaggio: str, cartella: str, rete: bool) -> list[str]:
    cmd = [motore_, "run", "--rm", "--name", nome, "--network", "bridge" if rete else "none",
           "--memory", LIMITI["memoria"], "--memory-swap", LIMITI["memoria"], "--cpus", LIMITI["cpu"], "--pids-limit", LIMITI["processi"],
           "--read-only", "--tmpfs", f"/tmp:rw,noexec,nosuid,size={LIMITI['disco_mb']}m", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--user", "65534:65534", "-v", f"{cartella}:/work:rw", "-w", "/work", "-e", "HOME=/tmp"]
    return cmd + [immagine] + LINGUAGGI[linguaggio][1]


def _esegui_ora(conn, esec_id: int, linguaggio: str, codice: str, rete: bool) -> tuple[str, str, int | None, int]:
    """Lancia davvero il contenitore. Restituisce (stato, uscita, codice_uscita, durata_ms)."""
    m = motore()
    if not m:
        return "non_disponibile", "Nessun motore di contenitori (Docker o Podman) sul server: la sandbox non e' disponibile.", None, 0
    img = _impostazione(conn, "sandbox_immagine_" + ("python" if linguaggio == "bash" else linguaggio))
    if _lancia([m, "image", "inspect", img], 15)[0] != 0:
        return "non_disponibile", f"L'immagine «{img}» non e' presente sul server. Va scaricata una volta da Lorenzo (Opifex non installa nulla da solo).", None, 0
    nome = "opifex-sandbox-" + uuid.uuid4().hex[:10]
    ext = LINGUAGGI[linguaggio][0]
    with tempfile.TemporaryDirectory(prefix="opifex-sb-") as cart:
        (Path(cart) / f"main.{ext}").write_text(codice, encoding="utf-8")
        Path(cart).chmod(0o777)
        t0 = time.monotonic()
        code, out = _lancia(comando(m, nome, img, linguaggio, cart, rete), LIMITI["tempo_s"] + 10)
        ms = int((time.monotonic() - t0) * 1000)
        if code == 124 or ms > LIMITI["tempo_s"] * 1000:
            _lancia([m, "rm", "-f", nome], 15)
            return "timeout", (out or "")[:LIMITI["uscita_max"]] + f"\n[interrotto dopo {LIMITI['tempo_s']} secondi]", code, ms
    return ("ok" if code == 0 else "errore"), out[:LIMITI["uscita_max"]], code, ms


def prova(conn, agente_id: int, dati: dict) -> str:
    ling = dati.get("linguaggio")
    codice = str(dati.get("codice") or "")
    if ling not in LINGUAGGI:
        return "ERRORE: linguaggio non valido (python, node, bash)"
    if not codice.strip() or len(codice) > LIMITI["codice_max"]:
        return f"ERRORE: il codice deve essere presente e non superare {LIMITI['codice_max']} caratteri"
    if _impostazione(conn, "sandbox_attiva") != "true":
        return "ERRORE: la sandbox e' spenta: la accende Lorenzo in Impostazioni → Sandbox."
    rete = bool(dati.get("rete"))
    motivo = " ".join(str(dati.get("motivo_rete") or "").split())[:300] or None
    if rete:
        if not motivo:
            return "ERRORE: per usare la rete indica il motivo (motivo_rete)"
        eid = conn.execute("INSERT INTO sandbox_esecuzioni (agente_id, linguaggio, codice, rete, motivo_rete, stato) VALUES (%s,%s,%s,TRUE,%s,'in_attesa') RETURNING id",
                           (agente_id, ling, codice, motivo)).fetchone()["id"]
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Un agente chiede di provare del codice CON RETE nella sandbox: «{motivo[:120]}». Da approvare in Impostazioni → Sandbox.",))
        return f"Richiesta #{eid} registrata: la rete la approva Lorenzo. Intanto prova il codice senza rete se puoi; l'esito ti arrivera' come avviso."
    eid = conn.execute("INSERT INTO sandbox_esecuzioni (agente_id, linguaggio, codice, rete) VALUES (%s,%s,%s,FALSE) RETURNING id", (agente_id, ling, codice)).fetchone()["id"]
    conn.commit()
    st, out, rc, ms = _esegui_ora(conn, eid, ling, codice, False)
    conn.execute("UPDATE sandbox_esecuzioni SET stato=%s, uscita=%s, codice_uscita=%s, durata_ms=%s WHERE id=%s", (st, out, rc, ms, eid))
    return f"[{st}] codice di uscita {rc}, {ms} ms\n{out or '(nessun output)'}"


def decidi(conn, eid: int, approva: bool) -> dict:
    r = conn.execute("SELECT * FROM sandbox_esecuzioni WHERE id = %s AND stato = 'in_attesa'", (eid,)).fetchone()
    if r is None:
        raise LookupError("Richiesta non trovata o gia' decisa")
    if not approva:
        conn.execute("UPDATE sandbox_esecuzioni SET stato='rifiutata' WHERE id=%s", (eid,))
        esito = "rifiutata"
        testo = "Lorenzo non ha approvato l'uso della rete: prova il codice senza rete."
    else:
        st, out, rc, ms = _esegui_ora(conn, eid, r["linguaggio"], r["codice"], True)
        conn.execute("UPDATE sandbox_esecuzioni SET stato=%s, uscita=%s, codice_uscita=%s, durata_ms=%s WHERE id=%s", (st, out, rc, ms, eid))
        esito = st
        testo = f"Prova con rete #{eid}: [{st}] codice {rc}\n{(out or '')[:1500]}"
    if r["agente_id"]:
        conn.execute("INSERT INTO avvisi_agente (agente_id, testo) VALUES (%s,%s)", (r["agente_id"], testo))
    return {"esito": esito}


def strumento(agente_id: int, connessione):
    def f(nome, dati):
        with connessione() as conn:
            return prova(conn, agente_id, dati)
    return f
