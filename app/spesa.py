"""Tetto di spesa: limite giornaliero e mensile sul costo stimato delle chiamate AI, con avviso all'80% e blocco al 100%.
Il costo si calcola dai prezzi per milione di token inseriti per ogni modello (Impostazioni → Sicurezza → Registra un modello)."""
from datetime import datetime, timezone

SOGLIA = 0.8


def _imp(conn, chiave, difetto=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (chiave,)).fetchone()
    return r["valore"] if r else difetto


def limiti(conn) -> dict:
    def num(k):
        try:
            v = float(_imp(conn, k, "") or 0)
        except ValueError:
            v = 0.0
        return v if v > 0 else None
    return {"giorno": num("tetto_spesa_giorno"), "mese": num("tetto_spesa_mese")}


def consumo(conn) -> dict:
    r = conn.execute("""SELECT COALESCE(SUM(costo_stimato) FILTER (WHERE creato_il >= date_trunc('day', NOW())), 0) AS giorno,
                               COALESCE(SUM(costo_stimato) FILTER (WHERE creato_il >= date_trunc('month', NOW())), 0) AS mese
                        FROM costi_api WHERE creato_il >= date_trunc('month', NOW())""").fetchone()
    return {"giorno": float(r["giorno"]), "mese": float(r["mese"])}


def _avvisa(conn, periodo: str, livello: str, testo: str):
    """Una sola notifica per periodo e livello (chiave con la data)."""
    adesso = datetime.now(timezone.utc)
    marca = adesso.strftime("%Y-%m-%d") if periodo == "giorno" else adesso.strftime("%Y-%m")
    chiave = f"spesa_avviso_{periodo}_{livello}"
    if _imp(conn, chiave) == marca:
        return
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (chiave, marca))
    conn.execute("INSERT INTO notifiche (testo, urgente, critica) VALUES (%s, TRUE, %s)", (testo, livello == "100"))


def controlla(conn) -> str | None:
    """Ritorna il motivo del blocco se un tetto e' raggiunto, altrimenti None. Invia gli avvisi all'80%."""
    lim = limiti(conn)
    if not lim["giorno"] and not lim["mese"]:
        return None
    c = consumo(conn)
    blocco = None
    for periodo, nome, fem in (("giorno", "giornaliero", "giornaliera"), ("mese", "mensile", "mensile")):
        tetto = lim[periodo]
        if not tetto:
            continue
        if c[periodo] >= tetto:
            _avvisa(conn, periodo, "100", f"Tetto di spesa {nome} raggiunto ({c[periodo]:.2f} su {tetto:.2f}): gli agenti sono fermi finche' non lo alzi o non cambia il periodo.")
            blocco = blocco or f"Tetto di spesa {nome} raggiunto ({c[periodo]:.2f} su {tetto:.2f})"
        elif c[periodo] >= tetto * SOGLIA:
            _avvisa(conn, periodo, "80", f"Spesa {fem} all'{round(c[periodo] / tetto * 100)}% del tetto ({c[periodo]:.2f} su {tetto:.2f}).")
    return blocco


def modelli_senza_prezzo(conn) -> list[str]:
    return [r["nome"] for r in conn.execute(
        """SELECT m.nome FROM modelli_ai m WHERE (m.costo_input_per_milione IS NULL OR m.costo_output_per_milione IS NULL)
           AND EXISTS (SELECT 1 FROM agenti a WHERE a.modello = m.nome AND a.attivo) ORDER BY m.nome""").fetchall()]


# ---------- tetto per reparto ----------
def reparti(conn) -> list[dict]:
    """Per ogni reparto: spesa del mese (costo stimato degli agenti che vi appartengono) e tetto mensile, se impostato."""
    return conn.execute("""
        SELECT d.id, d.nome, d.tetto_spesa_mese AS tetto,
               COALESCE((SELECT SUM(c.costo_stimato) FROM costi_api c JOIN agenti a ON a.id = c.agente_id
                         WHERE a.divisione_id = d.id AND c.creato_il >= date_trunc('month', NOW())), 0)::float AS speso
        FROM divisioni d ORDER BY d.nome""").fetchall()


def controlla_reparto(conn, divisione_id: int) -> str | None:
    """Motivo del blocco se il reparto ha esaurito il tetto del mese; avvisa una volta all'80% e una al 100%."""
    r = conn.execute("SELECT nome, tetto_spesa_mese FROM divisioni WHERE id = %s", (divisione_id,)).fetchone()
    if r is None or not r["tetto_spesa_mese"]:
        return None
    tetto = float(r["tetto_spesa_mese"])
    speso = float(conn.execute("""SELECT COALESCE(SUM(c.costo_stimato), 0) AS s FROM costi_api c JOIN agenti a ON a.id = c.agente_id
                                  WHERE a.divisione_id = %s AND c.creato_il >= date_trunc('month', NOW())""", (divisione_id,)).fetchone()["s"])
    marca = datetime.now(timezone.utc).strftime("%Y-%m")
    for livello, soglia in (("100", tetto), ("80", tetto * SOGLIA)):
        if speso >= soglia:
            chiave = f"spesa_reparto_{divisione_id}_{livello}"
            if _imp(conn, chiave) != marca:
                conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (chiave, marca))
                conn.execute("INSERT INTO notifiche (testo, urgente, critica) VALUES (%s, TRUE, %s)",
                             (f"Reparto {r['nome']}: spesa del mese a {speso:.2f} su {tetto:.2f}" + (" - gli agenti del reparto sono fermi fino al mese prossimo o finche' non alzi il tetto." if livello == "100" else "."), livello == "100"))
            break
    if speso >= tetto:
        return f"Tetto di spesa mensile del reparto {r['nome']} raggiunto ({speso:.2f} su {tetto:.2f})"
    return None
