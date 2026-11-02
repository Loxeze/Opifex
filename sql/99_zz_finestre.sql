-- 2.18.0: finestre (browser nella plancia); gli agenti abilitati leggono le schede condivise
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS finestre_attivo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS finestre_siti TEXT[] NOT NULL DEFAULT '{}';
