-- Proposte di sviluppo dell'Architetto tecnico (flusso con approvazione obbligatoria di Lorenzo)
-- Da eseguire dopo schema_supervisione.sql
-- stato: 'proposta' -> 'in_discussione' -> 'da_approvare' -> 'approvata' -> 'in_collaudo' -> 'in_produzione'
--        oppure 'respinta' / 'ritirata'
CREATE TABLE IF NOT EXISTS proposte_sviluppo (
  id SERIAL PRIMARY KEY,
  proposta_da_agente INTEGER REFERENCES agenti(id),
  proposta_da_utente INTEGER REFERENCES utenti(id),
  titolo TEXT NOT NULL,
  motivazione TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'miglioramento' CHECK (tipo IN ('falla_sicurezza', 'miglioramento', 'nuova_funzione', 'prestazioni')),
  gravita TEXT NOT NULL DEFAULT 'media' CHECK (gravita IN ('info', 'media', 'alta', 'critica')),
  codice_proposto TEXT,
  piano_collaudo TEXT,
  stato TEXT NOT NULL DEFAULT 'proposta'
    CHECK (stato IN ('proposta', 'in_discussione', 'da_approvare', 'approvata', 'in_collaudo', 'in_produzione', 'respinta', 'ritirata')),
  note_lorenzo TEXT,
  decisa_da INTEGER REFERENCES utenti(id),
  creata_il TIMESTAMPTZ DEFAULT NOW(),
  decisa_il TIMESTAMPTZ
);

-- Discussione tra l'Architetto e i manager su ciascuna proposta
CREATE TABLE IF NOT EXISTS discussioni_proposte (
  id SERIAL PRIMARY KEY,
  proposta_id INTEGER NOT NULL REFERENCES proposte_sviluppo(id) ON DELETE CASCADE,
  agente_id INTEGER REFERENCES agenti(id),
  utente_id INTEGER REFERENCES utenti(id),
  messaggio TEXT NOT NULL,
  creato_il TIMESTAMPTZ DEFAULT NOW()
);
