-- Memoria di lavoro: decisioni, fatti, preferenze e lezioni che gli agenti ritrovano in futuro. Le voci nascono come proposte
-- e diventano memoria solo quando le approva una persona autorizzata.
CREATE TABLE IF NOT EXISTS memorie_lavoro (
  id SERIAL PRIMARY KEY,
  testo TEXT NOT NULL CHECK (length(testo) BETWEEN 3 AND 1200),
  tipo TEXT NOT NULL DEFAULT 'decisione' CHECK (tipo IN ('decisione', 'fatto', 'preferenza', 'lezione', 'sintesi')),
  stato TEXT NOT NULL DEFAULT 'proposta' CHECK (stato IN ('proposta', 'approvata', 'scartata', 'superata')),
  fascia_dati TEXT NOT NULL DEFAULT 'interno' CHECK (fascia_dati IN ('pubblico', 'interno', 'riservato')),
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL,
  divisione_id INTEGER REFERENCES divisioni(id) ON DELETE SET NULL,
  fonte TEXT,
  sostituisce_id INTEGER REFERENCES memorie_lavoro(id) ON DELETE SET NULL,
  proposta_da_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  proposta_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  decisa_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  decisa_il TIMESTAMPTZ,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ricerca TSVECTOR GENERATED ALWAYS AS (to_tsvector('italian', testo)) STORED
);
CREATE INDEX IF NOT EXISTS idx_memorie_ricerca ON memorie_lavoro USING GIN (ricerca);
CREATE INDEX IF NOT EXISTS idx_memorie_stato ON memorie_lavoro (stato, divisione_id);
