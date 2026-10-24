-- Altri modelli GPT (registrabili anche dall'app; costi per milione di token modificabili da Impostazioni)
INSERT INTO modelli_ai (fornitore_id, nome, costo_input_per_milione, costo_output_per_milione, fascia)
SELECT f.id, v.nome, NULL, NULL, v.fascia FROM fornitori_ai f,
  (VALUES ('gpt-4o-mini', 'economico'), ('gpt-4.1', 'standard'), ('gpt-4.1-mini', 'economico')) AS v(nome, fascia)
WHERE f.nome = 'openai' AND NOT EXISTS (SELECT 1 FROM modelli_ai m WHERE m.nome = v.nome);
