"""Solo per i collaudi: completa il login dei collaboratori (secondo fattore obbligatorio)."""
import os
import psycopg
from app import totp
SEGRETI = {}
def accedi(c, email, password):
    r = c.post("/login", json={"email": email, "password": password}).json()
    while r.get("passo") != "ok":
        if r["passo"] == "configura_2fa":
            a = c.post("/login/2fa/avvia", json={"sfida": r["sfida"]}).json()
            SEGRETI[email] = a["segreto"]
            r = c.post("/login/2fa/conferma", json={"sfida": r["sfida"], "codice": totp.codice_adesso(a["segreto"])}).json()
        elif r["passo"] == "codice":
            with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as k:
                k.execute("UPDATE utenti SET totp_ultimo_passo=0 WHERE email=%s", (email,))
            r = c.post("/login/2fa", json={"sfida": r["sfida"], "codice": totp.codice_adesso(SEGRETI[email])}).json()
        else:
            raise RuntimeError(r)
    return r["token"]
