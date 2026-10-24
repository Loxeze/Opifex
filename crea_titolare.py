"""Crea il primo utente titolare (Lorenzo). Si esegue una sola volta, a mano:

    python crea_titolare.py

La password viene chiesta da tastiera e non compare mai a schermo ne' nei file.
"""
import getpass

from app.db import apri_pool, chiudi_pool, connessione
from app.sicurezza import cifra_password

nome = input("Nome: ").strip()
email = input("Email: ").strip().lower()
password = getpass.getpass("Password (minimo 10 caratteri): ")
conferma = getpass.getpass("Ripeti la password: ")

if password != conferma or len(password) < 10:
    raise SystemExit("Le password non coincidono o sono troppo corte.")

apri_pool()
with connessione() as conn:
    conn.execute(
        "INSERT INTO utenti (nome, email, password_hash, ruolo_globale) VALUES (%s, %s, %s, 'titolare')",
        (nome, email, cifra_password(password)),
    )
chiudi_pool()
print("Titolare creato.")
