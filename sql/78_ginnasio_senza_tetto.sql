-- 1.48.0: la formazione di Padre Casati non ha piu' un tetto giornaliero di token (0 = senza limite); una sola volta
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM impostazioni_sistema WHERE chiave = 'migrazione_ginnasio_senza_tetto') THEN
    INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('ginnasio_budget_giornaliero', '0')
      ON CONFLICT (chiave) DO UPDATE SET valore = '0';
    INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('migrazione_ginnasio_senza_tetto', '1');
  END IF;
END $$;
