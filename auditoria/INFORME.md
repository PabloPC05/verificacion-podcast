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
| Pedro Sánchez | 147 | 7 → 4 | 23 → 24 | 53 → 50 | 29 → 38 | 35 → 31 | 23 |
| Alberto Núñez Feijóo | 153 | 4 → 4 | 27 → 26 | 52 → 54 | 41 → 43 | 29 → 26 | 22 |
| Ada Colau | 153 | 5 → 4 | 24 → 24 | 73 → 73 | 36 → 37 | 15 → 15 | 16 |

En total cambian 61 veredictos de afirmaciones publicadas; el resto de los 65 cambios son de afirmaciones excluidas.

## Veredictos cambiados

| Afirmación | Minuto | Antes | Después | Motivo |
|---|---|---|---|---|
| [`sanchez-m710`](https://verificacion-podcast.vercel.app/sanchez#m710) | 0:11:50 | No verificable | Casi cierto | La afirmación estaba mal reformulada: los «intentos de asalto» los plantea Jordi Wild y Sánchez solo responde «nosotros las hemos condenado». Cargos socialistas condenaron los disturbios de A Coruña, pero no consta una condena expresa de Sánchez. |
| [`sanchez-m1087-2`](https://verificacion-podcast.vercel.app/sanchez#m1087-2) | 0:18:07 | No verificable | Engañoso | Merca2 y Mundiario atribuyen a Transportes un marco de 19.000 millones hasta 2030 para Adif, pero incluye obra nueva y los convenios de febrero fijan el mantenimiento en unos 8.150 millones. |
| [`sanchez-m1358`](https://verificacion-podcast.vercel.app/sanchez#m1358) | 0:22:38 | No verificable | Casi cierto | La serie oficial de plantilla de Adif muestra un +11 % sobre 2018 y un +19 % sobre el mínimo de 2021; de los controladores no hay serie y hay denuncias de falta de personal. |
| [`sanchez-m1556`](https://verificacion-podcast.vercel.app/sanchez#m1556) | 0:25:56 | Casi cierto | Verdadero | El Diario de Sesiones del Congreso de 2013 muestra que, en la comparecencia de Pastor, el portavoz socialista pidió explicaciones, medidas y una comisión, pero no su dimisión. |
| [`sanchez-m1846`](https://verificacion-podcast.vercel.app/sanchez#m1846) | 0:30:46 | No verificable | Casi cierto | Un informe de la Guardia Civil cuenta 605 entradas a nado en 24 horas y la Presidencia de Ceuta cifraba unas 200 al día, lo que hace plausible la cifra, aunque falta el recuento exacto de los cinco días. |
| [`sanchez-m1911`](https://verificacion-podcast.vercel.app/sanchez#m1911) | 0:31:51 | Casi cierto | Verdadero | El informe de la Policía Nacional para la Audiencia Nacional confirma que la lectura distorsionada de la sentencia circuló antes de la entrada y se usó en la convocatoria. |
| [`sanchez-m2012`](https://verificacion-podcast.vercel.app/sanchez#m2012) | 0:33:32 | Falso | Engañoso | No hay censo por edades de quienes entraron y la Policía describe un «alto porcentaje de menores» en dos de las tres oleadas, así que los datos no contradicen directamente la afirmación, solo no la respaldan para el conjunto. |
| [`sanchez-m3378`](https://verificacion-podcast.vercel.app/sanchez#m3378) | 0:56:18 | Casi cierto | No verificable | El Banco de España estima que la inmigración aportó en torno a la mitad del crecimiento del PIB en 2022-2025 y cerca del 19 % del per cápita; ninguna estimación publicada coincide con el 25 %. |
| [`sanchez-m3602`](https://verificacion-podcast.vercel.app/sanchez#m3602) | 1:00:02 | Casi cierto | Verdadero | La afirmación estaba mal reformulada: Sánchez dice que «muchos» vienen en avión y en coche, no que sean la mayoría de los irregulares, y los datos del INE y ACNUR de 2024 respaldan lo dicho. |
| [`sanchez-m3929-2`](https://verificacion-podcast.vercel.app/sanchez#m3929-2) | 1:05:29 | Casi cierto | Verdadero | La tabla del INE de paro por nacionalidad, que antes no se había obtenido, muestra que la tasa de los españoles bajó del 13,70 % (tercer trimestre de 2018) al 9,26 % (tercero de 2026). |
| [`sanchez-m4377`](https://verificacion-podcast.vercel.app/sanchez#m4377) | 1:12:57 | Casi cierto | Verdadero | Dos agencias recogen literalmente su petición de perdón, EFE el 12/6/2025 y Europa Press/RTVE el 17/6/2025; la frase de la entrevista es ambigua, pero la petición pública consta. |
| [`sanchez-m4623`](https://verificacion-podcast.vercel.app/sanchez#m4623) | 1:17:03 | Engañoso | Casi cierto | La afirmación estaba mal reformulada: Sánchez comparó (no conocía a Koldo como a Ábalos y Cerdán) y precisó que no era un desconocido; Valencia Plaza, El Debate y EFE respaldan esa relación menor. |
| [`sanchez-m5104`](https://verificacion-podcast.vercel.app/sanchez#m5104) | 1:25:04 | Engañoso | No verificable | Lo que Sánchez ha oído no se puede comprobar y no aparece la frase literal de Colau, aunque el 3 de noviembre de 2026 dijo, según Europa Press, que el Ministerio de Vivienda «no ha hecho nada» en esta legislatura. |
| [`sanchez-m5164`](https://verificacion-podcast.vercel.app/sanchez#m5164) | 1:26:04 | Engañoso | No verificable | Hay indicios, pero ni el Banco de España ni la Universidad de Málaga miden la brecha con Manresa y sus estudios tratan de alquileres, no de precios de venta, así que la causa no se puede confirmar ni descartar. |
| [`sanchez-m5188`](https://verificacion-podcast.vercel.app/sanchez#m5188) | 1:26:28 | Falso | Engañoso | Según las tablas oficiales, el millón y el 13 % encajan con las viviendas iniciadas desde 2018 (947.600 y 13,1 %), no con las terminadas (726.100), y los «más de 150.000» protegidas no cuadran (unas 124.000 iniciadas). |
| [`sanchez-m5287`](https://verificacion-podcast.vercel.app/sanchez#m5287) | 1:28:07 | No verificable | Engañoso | El «ocho» sale del preámbulo del Real Decreto 326/2026, que cuenta 20.988 millones movilizados con financiación y fondos europeos, mientras que en los Presupuestos el crédito nacional solo se duplicó de 2018 a 2023, de 481 a 997 millones. |
| [`sanchez-m5365`](https://verificacion-podcast.vercel.app/sanchez#m5365) | 1:29:25 | No verificable | Casi cierto | La izquierda se ha opuesto a las reformas de la ley del suelo (Sumar y Podemos en 2025, Podemos en 2026), pero no consta posición de Colau y Sumar aceptó incluirla en el borrador de julio de 2026. |
| [`sanchez-m5392`](https://verificacion-podcast.vercel.app/sanchez#m5392) | 1:29:52 | No verificable | Verdadero | Los dos reales decretos-ley estaban pendientes de convalidación y se votaron el 12 de noviembre de 2026, aunque el resultado fue mixto: uno salió adelante y el otro decayó. |
| [`sanchez-m5838`](https://verificacion-podcast.vercel.app/sanchez#m5838) | 1:37:18 | Engañoso | Casi cierto | La visita a los hospitales Sagrat Cor y Sant Pau el 21-10-2019 y los gritos del personal sanitario encajan con su relato; lo único que no se puede comprobar es su motivación personal. |
| [`sanchez-m5951`](https://verificacion-podcast.vercel.app/sanchez#m5951) | 1:39:11 | Casi cierto | Verdadero | Bildu no tiene ministros ni forma parte del Gobierno, y Maldita recoge que PSOE y EH Bildu no compartieron gobierno en ninguna institución entre 2019 y 2023; el apoyo parlamentario es otra cosa que Sánchez no niega. |
| [`sanchez-m5970`](https://verificacion-podcast.vercel.app/sanchez#m5970) | 1:39:30 | Casi cierto | Verdadero | Ni en Euskadi (coalición PNV-PSE-EE) ni en Navarra (PSN, Geroa Bai y Contigo) gobierna EH Bildu, que en Navarra solo se abstuvo en la investidura de 2023. |
| [`sanchez-m6028`](https://verificacion-podcast.vercel.app/sanchez#m6028) | 1:40:28 | Falso | Engañoso | Sánchez sí dijo en laSexta, el 19-9-2019, que «no dormiría por la noche» si ciertos ministerios iban a personas del círculo de Iglesias, y Maldita considera manipulada la versión viral, que omite esa condición. |
| [`sanchez-m6204`](https://verificacion-podcast.vercel.app/sanchez#m6204) | 1:43:24 | Casi cierto | Verdadero | NacióDigital recoge que el PSC fue la fuerza más votada de Cataluña en las municipales de 2023, por primera vez desde 2007, lo que cubre lo de «muchos municipios» que antes no se pudo comprobar. |
| [`feijoo-m434`](https://verificacion-podcast.vercel.app/feijoo#m434) | 0:07:14 | Verdadero | Casi cierto | La fuente anterior no era válida; los programas de Vox de 2019 y 2023 y la reacción de Abascal en 2024 confirman su posición, aunque Vox la ha presentado como objetivo a largo plazo. |
| [`feijoo-m971`](https://verificacion-podcast.vercel.app/feijoo#m971) | 0:16:11 | Engañoso | Casi cierto | El PP apoyó la renovación del pacto, aprobada en el Pleno el 26 de febrero de 2025, y sigue vigente. Pero fue hace casi dos años, no «unos meses», y por dictamen parlamentario, no por pacto personal. |
| [`feijoo-m1131`](https://verificacion-podcast.vercel.app/feijoo#m1131) | 0:18:51 | No verificable | Verdadero | El Decreto 325/2009 (DOG de 2009) fija la dependencia de la Presidencia y el Decreto 215/2020 recoge la fusión con empleo, algo que antes no se había podido comprobar. |
| [`feijoo-m1219-2`](https://verificacion-podcast.vercel.app/feijoo#m1219-2) | 0:20:19 | Engañoso | Falso | Según el INE, la población creció entre 2,9 y 3,1 millones desde 2018, no más de 4 millones; la dirección de lo dicho (inmigración y saldo vegetativo negativo) sí es correcta. |
| [`feijoo-m1346`](https://verificacion-podcast.vercel.app/feijoo#m1346) | 0:22:26 | No verificable | Casi cierto | Sumando los Consejos de Ministros del 27 de octubre y del 3 y 10 de noviembre salen unos 18.200 millones en Defensa, compatibles con su cifra, aunque «adjudicado» es impreciso. |
| [`feijoo-m1413`](https://verificacion-podcast.vercel.app/feijoo#m1413) | 0:23:33 | Casi cierto | Verdadero | Las cifras oficiales de transferencias de 2025 (52.990 millones en total, 47.815 del Estado y organismos autónomos, según el Ministerio de Inclusión) hacen correcto «unos 50.000 millones». |
| [`feijoo-m1452`](https://verificacion-podcast.vercel.app/feijoo#m1452) | 0:24:12 | Casi cierto | Verdadero | La Seguridad Social fija 67 años como regla general (66 años y 10 meses en 2026), por lo que el redondeo de dos meses es admisible. |
| [`feijoo-m1552`](https://verificacion-podcast.vercel.app/feijoo#m1552) | 0:25:52 | No verificable | Casi cierto | La serie de la asociación de mutuas AMAT cifra el coste de las bajas en 14.561 millones en 2018 y 33.280 en 2025, lo que encaja con lo dicho, aunque es una fuente interesada y no oficial. |
| [`feijoo-m1620`](https://verificacion-podcast.vercel.app/feijoo#m1620) | 0:27:00 | Casi cierto | No verificable | Los datos de bajas iniciadas de las mutuas (AMAT) respaldan el lunes como día con más bajas nuevas, pero no el viernes, y no hay estadística oficial de ausentes por día de la semana. |
| [`feijoo-m1661`](https://verificacion-podcast.vercel.app/feijoo#m1661) | 0:27:41 | Casi cierto | Verdadero | Existen actividades con esas tasas (Correos, 13,0 % en 2025; servicios a edificios, 12,5 %, según Adecco con datos del INE) y Feijóo no dice que sea la media nacional, que es del 7,6 %. |
| [`feijoo-m2075`](https://verificacion-podcast.vercel.app/feijoo#m2075) | 0:34:35 | Casi cierto | No verificable | El Decreto 83/2009 solo documenta un 17 % menos de direcciones y secretarías generales y un 25 % menos de consellerías, no un 50 %, y no hay recuento oficial de altos cargos que lo confirme o desmienta. |
| [`feijoo-m2260`](https://verificacion-podcast.vercel.app/feijoo#m2260) | 0:37:40 | No verificable | Casi cierto | La AIReF (15-4-2026) recoge seis comunidades con superávit previsto en 2026 y Newtral, cinco con superávit en 2023; son previsiones, y falta el desglose autonómico del último cierre. |
| [`feijoo-m2340`](https://verificacion-podcast.vercel.app/feijoo#m2340) | 0:39:00 | No verificable | Casi cierto | Las tablas de la OTAN de junio de 2024 dan a España un 1,19 % del PIB en 2023 y un 1,28 % estimado en 2024, lo que encaja con su cifra, aunque luego se revisó 2024 al 1,43 %. |
| [`feijoo-m2417`](https://verificacion-podcast.vercel.app/feijoo#m2417) | 0:40:17 | No verificable | Casi cierto | Tres Consejos de Ministros (27-10, 3-11 y 10-11) suman unos 18.700 millones en Defensa, pero son autorizaciones de gasto y no adjudicaciones, y el tramo del 10-11 solo lo recoge un medio que cita a La Moncloa. |
| [`feijoo-m2526`](https://verificacion-podcast.vercel.app/feijoo#m2526) | 0:42:06 | Verdadero | Casi cierto | La nota del CENIF del 28 de julio era más matizada de lo que se decía: no apreciaba indicadores de un salto masivo a la valla y calificaba de incipientes las señales; el aviso inequívoco es del 29 de julio. |
| [`feijoo-m2894`](https://verificacion-podcast.vercel.app/feijoo#m2894) | 0:48:14 | Casi cierto | Verdadero | La web de la Comisión Europea confirma los acuerdos comerciales vigentes con Marruecos y el Parlamento Europeo lo llama «socio clave», lo que resuelve el reparo anterior sobre su situación en 2026. |
| [`feijoo-m3123-2`](https://verificacion-podcast.vercel.app/feijoo#m3123-2) | 0:52:03 | Falso | Engañoso | Los datos oficiales no publican los beneficiarios por nacionalidad, por lo que «medio millón» podría ser el total de miembros de hogares con titular extranjero; lo que las cifras ministeriales sí contradicen es que no hayan trabajado. |
| [`feijoo-m3334`](https://verificacion-podcast.vercel.app/feijoo#m3334) | 0:55:34 | Engañoso | Casi cierto | Idescat, con datos del INE, da un 27,8 % de nacidos en el extranjero en Lleida a 1 de enero de 2025; una desviación de unos dos puntos en una cifra dada como «aproximadamente» es una imprecisión menor. |
| [`feijoo-m3665`](https://verificacion-podcast.vercel.app/feijoo#m3665) | 1:01:05 | Verdadero | No verificable | La absolución de 1999 solo la recoge El Salto: Público no la menciona, las crónicas de El País y La Voz de Galicia no se pudieron abrir y no se accedió a la sentencia. |
| [`feijoo-m3973-2`](https://verificacion-podcast.vercel.app/feijoo#m3973-2) | 1:06:13 | Casi cierto | Engañoso | Dos medios fechan la licitación de forma distinta (25/6/2018 y 4/6/2018, esta última anterior a la llegada de Ábalos), la obra se adjudicó el 31/1/2019 y la sospecha procede solo de la UCO. |
| [`feijoo-m4174`](https://verificacion-podcast.vercel.app/feijoo#m4174) | 1:09:34 | No verificable | Casi cierto | Gamarra es vicesecretaria de Regeneración Institucional del PP, según la ficha del partido, y tres medios sitúan Justicia en su área, aunque el PP no publica el reparto interno. |
| [`feijoo-m4185`](https://verificacion-podcast.vercel.app/feijoo#m4185) | 1:09:45 | Casi cierto | No verificable | El 9/11/2026 Gamarra reconoció la reunión entre Durán y Koldo García, pero ninguna fuente muestra que Durán hablara con otros abogados de las partes ni que Gamarra lo supiera. |
| [`colau-m355`](https://verificacion-podcast.vercel.app/colau#m355) | 0:05:55 | No verificable | Casi cierto | El Tribunal de Cuentas da el gasto real de PP, PSOE y Sumar en 2023 y Frente Amplio declara 1,6 millones para 2026, aunque faltan cifras de 2026 de PP y PSOE y la suya viene de un solo medio. |
| [`colau-m1719`](https://verificacion-podcast.vercel.app/colau#m1719) | 0:28:39 | Casi cierto | Verdadero | Público y elDiario.es confirman que la jueza atribuyó la querella a la discrepancia con las políticas de vivienda de Colau y al «efecto mediático»; antes la cita se apoyaba en Deia, que no se pudo abrir. |
| [`colau-m2221`](https://verificacion-podcast.vercel.app/colau#m2221) | 0:37:01 | Falso | Engañoso | Puente fue nombrado ministro el 20 de noviembre de 2023, unos 26 meses antes del accidente, lo que contradice la idea de recién llegado; pero «poco tiempo» es una valoración subjetiva, no un dato que pueda desmentirse. |
| [`colau-m2236`](https://verificacion-podcast.vercel.app/colau#m2236) | 0:37:16 | Casi cierto | Engañoso | La inversión ferroviaria cayó de 8.772 millones en 2009 a 1.652 en 2016, pero el mantenimiento de Adif subió desde 2017 y la causa de los accidentes sigue en investigación, así que el nexo con la desinversión no está demostrado. |
| [`colau-m2245`](https://verificacion-podcast.vercel.app/colau#m2245) | 0:37:25 | Verdadero | Casi cierto | La cronología muestra que Colau exigió «responsabilidades» el 28 de octubre, pero la petición explícita de dimisión llegó el 30, dos días después del accidente de Urda, y no «inmediatamente». |
| [`colau-m3058`](https://verificacion-podcast.vercel.app/colau#m3058) | 0:50:58 | Engañoso | Casi cierto | La afirmación estaba mal reformulada: Colau no dice que la crisis fuera en agosto ni que Sánchez no fuera a Ceuta, sino que critica sus vacaciones y la primera respuesta, algo documentado salvo la visita del 31 de julio. |
| [`colau-m5132`](https://verificacion-podcast.vercel.app/colau#m5132) | 1:25:32 | Casi cierto | Engañoso | El CES habla de un impacto fiscal «neutro o ligeramente positivo», no de «mucho más»; según The Conversation, el 1% es gasto en prestaciones y no todo el gasto público, y las cifras no figuran en el informe del CES. |
| [`colau-m5730`](https://verificacion-podcast.vercel.app/colau#m5730) | 1:35:30 | No verificable | Casi cierto | La web del Ayuntamiento y Betevé confirman que el alcalde preside la Junta Local de Seguridad y que reúne a todos los cuerpos, pero la Junta se reúne dos veces al año, no cada trimestre. |
| [`colau-m5744`](https://verificacion-podcast.vercel.app/colau#m5744) | 1:35:44 | Engañoso | No verificable | No existen datos públicos de la nacionalidad de los autores de delitos en Barcelona durante el mandato, y las únicas cifras disponibles, las de detenciones, miden otra cosa. |
| [`colau-m5782`](https://verificacion-podcast.vercel.app/colau#m5782) | 1:36:22 | Engañoso | No verificable | No hay una serie de Barcelona sobre la nacionalidad de los autores: a escala catalana hay apoyo (55 % de delitos de autores españoles en 2023, según los Mossos), pero en la ciudad las detenciones apuntan en sentido contrario. |
| [`colau-m5982`](https://verificacion-podcast.vercel.app/colau#m5982) | 1:39:42 | Falso | No verificable | Ninguna fuente respalda la cifra, pero tampoco la contradice: no hay un registro público de las viviendas de los fondos y las cifras de Civio y Atlas miden viviendas alquiladas, no el parque total en propiedad. |
| [`colau-m6059`](https://verificacion-podcast.vercel.app/colau#m6059) | 1:40:59 | Engañoso | Falso | La memoria económica oficial de la ordenanza dice que el Ayuntamiento paga el mismo precio y condiciones que se ofrecen, no una tasación inferior al mercado; solo es cierto que la norma del área la hizo el Ayuntamiento. |
| [`colau-m6758`](https://verificacion-podcast.vercel.app/colau#m6758) | 1:52:38 | No verificable | Engañoso | Según Eurostat, la relación precio-renta de 2025 sigue por debajo de la de 2007 y la sobrecarga de los inquilinos era mayor en 2014, aunque los precios nominales están en máximos. |
| [`colau-m7382-2`](https://verificacion-podcast.vercel.app/colau#m7382-2) | 2:03:02 | Engañoso | Casi cierto | La historiografía sitúa las víctimas de la represión franquista entre 130.000 y 200.000, de modo que «cientos de miles» es un redondeo al alza dentro de ese rango. |
| [`colau-m7459`](https://verificacion-podcast.vercel.app/colau#m7459) | 2:04:19 | Casi cierto | Engañoso | La detención de la cúpula de Núcleo Nacional es cierta, pero los cargos conocidos (odio, asociación ilícita y armas) no incluyen palizas y los detenidos están investigados, no condenados. |
| [`colau-m7593`](https://verificacion-podcast.vercel.app/colau#m7593) | 2:06:33 | Casi cierto | Verdadero | La cita de Ara coincide literalmente con lo que Colau cuenta («amigos pijos»), y «crujir» y «ricachones» son palabras de Jordi Wild; solo hay cobertura de Ara, una fuente independiente. |

## Fuentes descartadas

Se descartaron 374 fuentes. Los dominios más afectados:

| Dominio | Descartadas |
|---|---|
| es.wikipedia.org | 70 |
| lamoncloa.gob.es | 32 |
| moncloa.com | 29 |
| maldita.es | 14 |
| en.wikipedia.org | 12 |
| deia.eus | 9 |
| infobae.com | 8 |
| noticiasdenavarra.com | 7 |
| eldebate.com | 7 |
| eldiario.es | 7 |
| vozpopuli.com | 7 |
| theobjective.com | 7 |

Wikipedia se descarta como base única (se usa para llegar a la fuente primaria que cita) y moncloa.com por ser un medio privado. Las de lamoncloa.gob.es se descartan cuando la página no abre o no dice lo que se le atribuía; en ese caso se sustituyen por la fuente oficial que sí lo dice o por agencias y prensa de referencia.

## Fuentes primarias en lo más grave

Antes de la auditoría, 15 de las 90 afirmaciones falsas o engañosas publicadas citaban una fuente oficial o primaria. Ahora son 45 de 86 (cálculo aproximado por dominio: organismos públicos, BOE, INE, Eurostat, tribunales, Congreso…). Las demás se apoyan en agencias, verificadores o prensa de distintas líneas editoriales, como permite la política cuando no hay fuente oficial abierta.

## La misma vara para los tres

- **Pedro Sánchez**: 35 → 31 no verificables; entre las verificables, 13 pasan a un veredicto más favorable y 0 a uno más desfavorable.
- **Alberto Núñez Feijóo**: 29 → 26 no verificables; entre las verificables, 7 pasan a un veredicto más favorable y 4 a uno más desfavorable.
- **Ada Colau**: 15 → 15 no verificables; entre las verificables, 5 pasan a un veredicto más favorable y 5 a uno más desfavorable.

La diferencia de «no verificables» entre candidatos se ha reducido, pero no desaparece: depende también de cuántas anécdotas y datos sin registro público da cada uno.

## Pendiente

- `python3 web-src/acceso.py` para que las fuentes nuevas se puedan leer en el visor (si no, abren en pestaña nueva).
- `herramientas/archivar_fuentes.py` para guardar en la Wayback Machine las fuentes nuevas.
- Revisión humana de las falsas y engañosas: la auditoría también es de IA.
