-- 1.68.0: nelle riunioni vocali i manager non propongono argomenti propri; le loro richieste restano in coda (coda=1) e si consegnano a richiesta (le copie consegnate hanno coda=0, gli originali passano a 2)
ALTER TABLE tavoli_interventi ADD COLUMN IF NOT EXISTS coda SMALLINT NOT NULL DEFAULT 0;
