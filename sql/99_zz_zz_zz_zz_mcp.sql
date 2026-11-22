-- 2.77: connettore MCP (OAuth) e inviti del calendario da approvare
CREATE TABLE IF NOT EXISTS mcp_clienti (
  client_id TEXT PRIMARY KEY,
  nome TEXT NOT NULL DEFAULT '',
  redirect_uris TEXT[] NOT NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS mcp_codici (
  codice_hash TEXT PRIMARY KEY,
  client_id TEXT NOT NULL REFERENCES mcp_clienti(client_id) ON DELETE CASCADE,
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  redirect_uri TEXT NOT NULL,
  challenge TEXT NOT NULL,
  scade_il TIMESTAMPTZ NOT NULL,
  usato BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS mcp_token (
  id SERIAL PRIMARY KEY,
  client_id TEXT NOT NULL REFERENCES mcp_clienti(client_id) ON DELETE CASCADE,
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  accesso_hash TEXT NOT NULL UNIQUE,
  rinnovo_hash TEXT NOT NULL UNIQUE,
  scade_il TIMESTAMPTZ NOT NULL,
  rinnovo_scade_il TIMESTAMPTZ NOT NULL,
  revocato BOOLEAN NOT NULL DEFAULT FALSE,
  ultimo_uso TIMESTAMPTZ,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS calendario_proposte (
  id SERIAL PRIMARY KEY,
  titolo TEXT NOT NULL,
  inizio TIMESTAMPTZ NOT NULL,
  fine TIMESTAMPTZ NOT NULL,
  invitati TEXT[] NOT NULL DEFAULT '{}',
  descrizione TEXT NOT NULL DEFAULT '',
  luogo TEXT NOT NULL DEFAULT '',
  account_id INTEGER,
  stato TEXT NOT NULL DEFAULT 'da_approvare' CHECK (stato IN ('da_approvare','creato','scartato')),
  link TEXT,
  da_cliente TEXT NOT NULL DEFAULT '',
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deciso_il TIMESTAMPTZ
);
