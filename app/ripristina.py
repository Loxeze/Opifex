"""Ripristino da un backup: python -m app.ripristina FILE.enc CHIAVE CARTELLA_DESTINAZIONE
Scrive database.sql e env.txt nella cartella indicata. Poi: psql "$DATABASE_URL" < database.sql  (vedi guida nella pagina Backup)."""
import os
import sys

from .backup import ErroreBackup, apri

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("uso: python -m app.ripristina FILE.enc CHIAVE CARTELLA")
    try:
        contenuti = apri(sys.argv[1], sys.argv[2])
    except ErroreBackup as e:
        sys.exit(str(e))
    os.makedirs(sys.argv[3], mode=0o700, exist_ok=True)
    for nome, dati in contenuti.items():
        p = os.path.join(sys.argv[3], nome)
        with open(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
            f.write(dati)
        print("scritto", p)
