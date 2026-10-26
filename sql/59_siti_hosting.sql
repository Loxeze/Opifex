-- 1.28.0: siti e hosting con credenziali cifrate; gli agenti li usano tramite strumenti, senza mai vedere il segreto
CREATE TABLE IF NOT EXISTS siti_hosting (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL UNIQUE CHECK (length(nome) BETWEEN 2 AND 80),
  tipo TEXT NOT NULL CHECK (tipo IN ('sftp', 'ftp', 'wordpress', 'pannello', 'api')),
  url TEXT,
  host TEXT,
  porta INTEGER,
  utente TEXT,
  segreto_cifrato TEXT,
  impronta_host TEXT,                       -- impronta della chiave SSH del server, fissata alla prima prova riuscita
  percorso_base TEXT NOT NULL DEFAULT '/',
  produzione BOOLEAN NOT NULL DEFAULT TRUE,  -- in produzione ogni scrittura aspetta il via libera
  note TEXT,
  attivo BOOLEAN NOT NULL DEFAULT TRUE,
  ultima_prova TIMESTAMPTZ,
  esito_prova TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS siti_agenti (
  sito_id INTEGER NOT NULL REFERENCES siti_hosting(id) ON DELETE CASCADE,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  PRIMARY KEY (sito_id, agente_id)
);

CREATE TABLE IF NOT EXISTS siti_scritture (
  id SERIAL PRIMARY KEY,
  sito_id INTEGER NOT NULL REFERENCES siti_hosting(id) ON DELETE CASCADE,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  percorso TEXT NOT NULL,
  contenuto TEXT NOT NULL,
  motivo TEXT,
  precedente TEXT,                           -- copia di sicurezza del contenuto prima della modifica
  stato TEXT NOT NULL DEFAULT 'in_attesa' CHECK (stato IN ('in_attesa', 'applicata', 'respinta', 'errore')),
  errore TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  decisa_il TIMESTAMPTZ,
  decisa_da INTEGER REFERENCES utenti(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_scritture_stato ON siti_scritture (stato, creata_il DESC);
