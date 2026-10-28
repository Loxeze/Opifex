-- 1.50.0: Ginnasio senza approvazioni (le competenze scritte da Padre Casati entrano da sole, con storico) e task riprese dopo un'ora di attesa
ALTER TABLE task ADD COLUMN IF NOT EXISTS riprese INTEGER NOT NULL DEFAULT 0;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM impostazioni_sistema WHERE chiave = 'migrazione_ginnasio_automatico') THEN
    INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('ginnasio_pausa_studio', '0')
      ON CONFLICT (chiave) DO UPDATE SET valore = '0';
    INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('ginnasio_approva_auto', '1')
      ON CONFLICT (chiave) DO UPDATE SET valore = '1';
    INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('migrazione_ginnasio_automatico', '1');
  END IF;
END $$;
