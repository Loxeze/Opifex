-- 1.53.0: assistente vocale (tappa 0) - passkey, conferme vocali, note dettate
CREATE TABLE IF NOT EXISTS passkey (
  id SERIAL PRIMARY KEY,
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  credenziale_id TEXT NOT NULL UNIQUE,
  chiave_pubblica TEXT NOT NULL,
  algoritmo INTEGER NOT NULL,
  contatore BIGINT NOT NULL DEFAULT 0,
  nome TEXT NOT NULL DEFAULT 'Telefono',
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ultimo_uso TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS passkey_utente ON passkey (utente_id);

-- sfide monouso (registrazione e accesso): durano pochi minuti e si consumano alla prima verifica
CREATE TABLE IF NOT EXISTS passkey_sfide (
  sfida TEXT PRIMARY KEY,
  scopo TEXT NOT NULL,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE CASCADE,
  scade_il TIMESTAMPTZ NOT NULL
);

-- conferme: ogni azione delicata si prepara, si fa leggere il riepilogo a Lorenzo e solo dopo il suo "si'" si esegue
CREATE TABLE IF NOT EXISTS conferme_vocali (
  id SERIAL PRIMARY KEY,
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  azione TEXT NOT NULL,
  parametri JSONB NOT NULL,
  riepilogo TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  scade_il TIMESTAMPTZ NOT NULL,
  esito TEXT,
  chiusa_il TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS note_vocali (
  id SERIAL PRIMARY KEY,
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  testo TEXT NOT NULL,
  progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL,
  contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE SET NULL,
  origine TEXT NOT NULL DEFAULT 'voce',
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS note_vocali_progetto ON note_vocali (progetto_id, creata_il DESC);
CREATE INDEX IF NOT EXISTS note_vocali_contatto ON note_vocali (contatto_id, creata_il DESC);
