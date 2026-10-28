-- 1.48.0: segmenti del CRM (liste intelligenti): filtri salvati che si aggiornano da soli
CREATE TABLE IF NOT EXISTS crm_segmenti (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL CHECK (char_length(nome) BETWEEN 2 AND 80),
  filtri JSONB NOT NULL DEFAULT '{}'::jsonb,
  creato_da INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (nome)
);
