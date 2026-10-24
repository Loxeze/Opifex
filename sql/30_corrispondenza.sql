-- Dipartimento Corrispondenza: le caselle di posta sono affidate in esclusiva a un solo agente;
-- solo gli agenti dei dipartimenti con "gestisce_posta" possono riceverne (uno o piu' caselle).
ALTER TABLE divisioni ADD COLUMN IF NOT EXISTS gestisce_posta BOOLEAN NOT NULL DEFAULT FALSE;
-- una casella ha al massimo un agente (in caso di duplicati resta il primo)
DELETE FROM agenti_caselle_posta x USING agenti_caselle_posta y WHERE x.casella_id = y.casella_id AND x.agente_id > y.agente_id;
ALTER TABLE agenti_caselle_posta DROP CONSTRAINT IF EXISTS agenti_caselle_posta_pkey;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agenti_caselle_posta_casella_pkey') THEN
    ALTER TABLE agenti_caselle_posta ADD CONSTRAINT agenti_caselle_posta_casella_pkey PRIMARY KEY (casella_id);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_agenti_caselle_agente ON agenti_caselle_posta (agente_id);
-- i dipartimenti che gia' hanno agenti con una casella restano abilitati
UPDATE divisioni SET gestisce_posta = TRUE WHERE id IN
  (SELECT a.divisione_id FROM agenti a JOIN agenti_caselle_posta x ON x.agente_id = a.id WHERE a.divisione_id IS NOT NULL);
INSERT INTO divisioni (nome, descrizione, gestisce_posta)
SELECT 'Corrispondenza', 'Gestione delle caselle di posta e delle comunicazioni da e verso l''esterno', TRUE
WHERE NOT EXISTS (SELECT 1 FROM divisioni WHERE lower(nome) = 'corrispondenza');
