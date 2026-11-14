# Informe de la auditoría de fuentes y veredictos

Revisión completa de las tres entrevistas con la misma política de fuentes para todos los candidatos: atribución contra la transcripción, cada enlace abierto, al menos una fuente primaria u oficial para cifras, leyes y hechos judiciales o institucionales, dos fuentes válidas independientes en lo demás, y «no verificable» cuando las fuentes fidedignas no bastan. Wikipedia y los medios de opinión solo valen como apoyo; moncloa.com (medio privado) no vale.

- Bloques 01 a 05 de cada entrevista (15 ficheros, 298 afirmaciones): auditoría lanzada el 13-11-2026, una sesión de Claude con un subagente Sonnet por bloque.
- Bloques 06 a 08 (9 ficheros, 192 afirmaciones): auditoría de Diego Cristóbal con el mismo encargo, PR #14.
- El detalle de cada afirmación (veredicto y confianza antes y después, fuentes descartadas y nuevas, nota) está en `auditoria/<slug>/<NN-tema>.json`.
- Cada veredicto cambiado lleva en su afirmación `correcciones: [{fecha: 2026-11-14, antes, motivo}]`, así que la web lo marca como «Corregido» y enseña el historial.

## Recuento publicado, antes y después

Solo afirmaciones publicadas (sin las excluidas por falta de interés público).

| Candidato | Total | Falso | Engañoso | Casi cierto | Verdadero | No verificable | Cambios |
|---|---|---|---|---|---|---|---|
| Pedro Sánchez | 147 | 7 → 5 | 23 → 23 | 53 → 52 | 29 → 36 | 35 → 31 | 20 |
| Alberto Núñez Feijóo | 153 | 4 → 4 | 27 → 26 | 52 → 54 | 41 → 43 | 29 → 26 | 22 |
| Ada Colau | 153 | 5 → 4 | 24 → 24 | 73 → 73 | 36 → 37 | 15 → 15 | 16 |
