"""Codici dei messaggi tra agenti: una lettera dopo «#» dice cosa si sta facendo, cosi' bastano pochi token.
Quelli «terminali» non richiedono risposta e chiudono lo scambio senza un'altra chiamata al modello."""
import re

CODICI = {
    "R": "Richiesta (ti chiedo un'azione o un'informazione)",
    "E": "Eseguito (fatto, esito in poche parole)",
    "C": "Chiarito / deciso (la questione e' chiusa)",
    "D": "Dubbio (mi manca un'informazione: la domanda e' dopo il codice)",
    "A": "D'accordo / approvato / ricevuto",
    "N": "Non posso o non sono d'accordo (motivo dopo il codice)",
    "B": "Bloccato: serve una persona (Lorenzo)",
    "P": "In corso (sto lavorando, ti aggiorno)",
    "I": "Informazione (nessuna risposta richiesta)",
}
TERMINALI = ("E", "C", "A", "I")
_RE = re.compile(r"^\s*#([RECDANBPI])(?=$|[\s:.,;\-—–])")
LEGENDA = "Codici (iniziano con #): " + "; ".join(f"#{k} {v}" for k, v in CODICI.items()) + "."


def codice_di(testo: str) -> str | None:
    """Il codice con cui comincia il messaggio, se c'e'. Riconosce anche il vecchio [CHIARITO]."""
    m = _RE.match(testo or "")
    if m:
        return m.group(1)
    if "[CHIARITO]" in (testo or ""):
        return "C"
    return None


def chiude(testo: str) -> bool:
    """True se il messaggio non richiede risposta (eseguito, chiarito, d'accordo, informazione)."""
    c = codice_di(testo)
    return c in TERMINALI and "?" not in (testo or "")


def etichetta(testo: str) -> str | None:
    c = codice_di(testo)
    return f"#{c} {CODICI[c].split(' (')[0]}" if c else None
