-- 1.60.0: note di Aurora - Lorenzo detta, Aurora scrive il documento e, su suo comando, lo affida a un manager per l'analisi
CREATE TABLE IF NOT EXISTS note_aurora (
  id SERIAL PRIMARY KEY,
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  titolo TEXT NOT NULL,
  testo TEXT NOT NULL,              -- la dettatura originale, mai modificata da Aurora
  documento TEXT,                   -- la nota scritta da Aurora (ordinata, fedele, senza fatti inventati)
  punti TEXT,                       -- punti d'azione
  stato TEXT NOT NULL DEFAULT 'bozza' CHECK (stato IN ('bozza','proposta','affidata','archiviata')),
  manager_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  analisi TEXT,                     -- che cosa deve analizzare il manager
  motivo TEXT,                      -- perche' Aurora propone proprio quel manager
  consegna_id INTEGER REFERENCES consegne(id) ON DELETE SET NULL,
  task_id INTEGER REFERENCES task(id) ON DELETE SET NULL,
  origine TEXT NOT NULL DEFAULT 'utente',
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  affidata_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS note_aurora_utente ON note_aurora (utente_id, id DESC);
