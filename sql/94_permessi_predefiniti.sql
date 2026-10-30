-- 1.71.0: permessi di base per tutti gli agenti: scrivere e modificare documenti su Drive (mai cancellare);
-- i manager vedono cio' che fanno tutti gli agenti (vede_attivita), gli altri cio' che fa il proprio reparto
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS vede_attivita BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE agenti SET drive_attivo = TRUE WHERE NOT COALESCE(sentinella, FALSE);
UPDATE agenti SET vede_attivita = TRUE WHERE (livello IN ('manager', 'referente') OR vede_tutto) AND NOT COALESCE(sentinella, FALSE);
ALTER TABLE agenti ALTER COLUMN drive_attivo SET DEFAULT TRUE;
