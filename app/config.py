"""Configurazione letta dalle variabili d'ambiente (file .env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Impostazioni(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str
    token_durata_ore: int = 12
    origini_consentite: str = "http://localhost:8080"
    # Chiavi dei fornitori AI: solo nel file .env del server
    chiave_anthropic: str = ""
    chiave_openai: str = ""
    chiave_xai: str = ""
    # Chiave che cifra le credenziali dei siti (cassaforte). Solo nel file .env del server
    chiave_cassaforte: str = ""
    # Solo per i collaudi: consente siti su localhost
    consenti_localhost_prova: bool = False
    # Opifex 3.0: "3" = installazione nuova che parte vuota (Aurora e Posta); importa_da = database della 2 da cui copiare; codice per creare il primo accesso
    opifex_edizione: str = "2"
    opifex_importa_da: str = ""
    opifex_codice_avvio: str = ""
    opifex_indirizzo: str = ""

    @property
    def origini(self) -> list[str]:
        return [o.strip() for o in self.origini_consentite.split(",") if o.strip()]


impostazioni = Impostazioni()
