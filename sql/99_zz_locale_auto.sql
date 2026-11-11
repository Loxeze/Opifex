-- modello «automatico»: il modello principale del primo computer locale acceso
INSERT INTO modelli_ai (fornitore_id, nome, costo_input_per_milione, costo_output_per_milione, fascia, importato, usa_per_dialoghi)
SELECT f.id, 'locale-auto', 0, 0, 'economico', TRUE, FALSE FROM fornitori_ai f
WHERE f.nome = 'locale' AND NOT EXISTS (SELECT 1 FROM modelli_ai WHERE nome = 'locale-auto');
