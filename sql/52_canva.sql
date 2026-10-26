-- 1.24.0: connettore Canva (Connect API); gli agenti abilitati creano e esportano design
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS canva_attivo BOOLEAN NOT NULL DEFAULT FALSE;
