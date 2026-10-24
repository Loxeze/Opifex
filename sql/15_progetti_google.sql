-- Account Google collegati (piu' di uno) e progetti con cartelle su Google Drive
CREATE TABLE IF NOT EXISTS account_google (
  id SERIAL PRIMARY KEY,
  etichetta TEXT NOT NULL UNIQUE,          -- nome scelto da Lorenzo, es. "Xenia", "Renovatio"
  email TEXT NOT NULL,
  refresh_token_cifrato TEXT NOT NULL,
  servizi TEXT[] NOT NULL DEFAULT '{}',    -- drive, gmail, calendar
  ultimo_errore TEXT,
  creato_il TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS oauth_stati (
  stato_hash TEXT PRIMARY KEY,
  etichetta TEXT NOT NULL,
  servizi TEXT[] NOT NULL,
  creato_il TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS progetti (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL UNIQUE,
  descrizione TEXT,
  archiviato BOOLEAN NOT NULL DEFAULT FALSE,
  drive_cartella_id TEXT,
  drive_agent_id TEXT,
  drive_repository_id TEXT,
  drive_stato TEXT NOT NULL DEFAULT 'da_sincronizzare' CHECK (drive_stato IN ('da_sincronizzare', 'ok', 'errore')),
  drive_errore TEXT,
  creato_il TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS progetti_agenti (
  progetto_id INTEGER NOT NULL REFERENCES progetti(id) ON DELETE CASCADE,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  drive_cartella_id TEXT,
  PRIMARY KEY (progetto_id, agente_id)
);

-- Cartella radice "Opifex" gia' creata su Drive e progetto di prova con la sua struttura
INSERT INTO impostazioni_sistema (chiave, valore) VALUES
  ('drive_radice_id', '1Ca_eWvhoNhRT3L2XU5O-AEBveA2lTgpU'),
  ('drive_account_id', ''),
  ('google_client_id', ''),
  ('google_client_secret_cifrato', ''),
  ('google_redirect', 'http://localhost:8000/gestione/google/callback')
ON CONFLICT (chiave) DO NOTHING;
INSERT INTO progetti (nome, descrizione, drive_cartella_id, drive_agent_id, drive_repository_id, drive_stato)
VALUES ('Progetto Test', 'Progetto di prova per verificare cartelle e flussi', '1AQT--tHtHEPquR7tXHeuSX-lGP04hkIz',
        '1DoFBCJNb1EipYSz7yhlhWj-7nwe0BhMP', '1e_8Q05S9X-l4-ztadMWIi3cbzTTh3Asa', 'da_sincronizzare')
ON CONFLICT (nome) DO NOTHING;
INSERT INTO progetti_agenti (progetto_id, agente_id)
SELECT p.id, a.id FROM progetti p, agenti a WHERE p.nome='Progetto Test' AND a.attivo ON CONFLICT DO NOTHING;
