-- 1.52.0: ogni contatto del CRM e' associato a una o piu' imprese del gruppo (si puo' contattare solo a nome di quelle) e indica i reparti di Opifex a cui puo' servire
CREATE TABLE IF NOT EXISTS crm_contatto_imprese (
  id SERIAL PRIMARY KEY,
  contatto_id INTEGER NOT NULL REFERENCES crm_contatti(id) ON DELETE CASCADE,
  azienda_id INTEGER NOT NULL REFERENCES aziende(id) ON DELETE CASCADE,
  motivo TEXT NOT NULL,
  dal DATE NOT NULL DEFAULT CURRENT_DATE,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (contatto_id, azienda_id)
);
CREATE INDEX IF NOT EXISTS crm_contatto_imprese_azienda ON crm_contatto_imprese (azienda_id);

CREATE TABLE IF NOT EXISTS crm_contatto_reparti (
  id SERIAL PRIMARY KEY,
  contatto_id INTEGER NOT NULL REFERENCES crm_contatti(id) ON DELETE CASCADE,
  divisione_id INTEGER NOT NULL REFERENCES divisioni(id) ON DELETE CASCADE,
  nota TEXT NOT NULL,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (contatto_id, divisione_id)
);
CREATE INDEX IF NOT EXISTS crm_contatto_reparti_div ON crm_contatto_reparti (divisione_id);
