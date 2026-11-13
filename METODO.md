# Método de verificación

Este es el procedimiento exacto con el que se ha verificado cada entrevista. Está escrito para que
cualquiera (una persona o una sesión de Claude Code) lo repita con otra entrevista y obtenga un resultado
comparable. La regla principal: **la misma vara de medir para todos los invitados, sea cual sea su partido.**

## 1. Descargar y transcribir

```sh
.venv/bin/python herramientas/transcribir.py <slug> <url-de-youtube> "<Nombre del invitado>" "<glosario opcional>"
```

Crea `entrevistas/<slug>/` con la transcripción (`transcripcion.txt`, párrafos de ~1 minuto con marca
`[h:mm:ss]`), los segmentos con tiempos (`segmentos.json`), los capítulos del vídeo (`capitulos.json`) y
`meta.json`. Revisa `meta.json` (nombre del invitado, programa, fecha, duración). El audio no se sube al repo.

Si el entorno `.venv` no existe: `uv venv --python 3.12 && uv pip install mlx-whisper`.

## 2. Repartir por temas

Lee la transcripción entera y `capitulos.json`. Agrupa los capítulos en bloques temáticos (en la entrevista
de Sánchez fueron 8 bloques para 12 capítulos: los capítulos sin datos comprobables se juntan). Para cada
bloque, anota el tramo de tiempo, las líneas del fichero y la lista de afirmaciones comprobables que haces
a primera lectura.

## 3. Verificar: un subagente Sonnet por bloque

Lanza en paralelo un subagente (modelo Sonnet, con WebSearch y WebFetch) por bloque, con este encargo
(sustituye lo que va entre `<>`):

> Eres verificador de datos (fact-checker) riguroso e imparcial. Hoy es `<fecha>`. `<Contexto: programa,
> invitado, fecha de publicación, elecciones>`. Tengo la transcripción automática (Whisper, sin etiquetas de
> hablante y con algún error de reconocimiento) en `<ruta>/transcripcion.txt`, con marcas [h:mm:ss] al inicio
> de cada párrafo.
>
> TU PARTE: el capítulo `<título>` (`<tramo>`, líneas `<a–b>` del fichero). Lee esas líneas enteras.
>
> TAREA: comprueba con búsqueda web cada afirmación FACTUAL COMPROBABLE que haga `<INVITADO>` (no las de
> Jordi Wild; deduce quién habla por el contexto). No evalúes opiniones, valoraciones, promesas ni anécdotas
> privadas imposibles de comprobar.
>
> Afirmaciones que ya he localizado (comprueba estas y añade cualquier otra comprobable que veas en tu
> tramo): `<lista numerada>`
>
> MÉTODO: usa WebSearch y WebFetch. Muchos hechos son recientes: NO te fíes de tu memoria, búscalo. Prioriza
> fuentes primarias y oficiales (INE, Eurostat, BOE, Banco de España, Congreso, ministerios, resoluciones
> judiciales) y prensa de distintas líneas editoriales; verificadores (Newtral, Maldita, EFE Verifica) como
> apoyo. Aplica la misma vara de medir que a cualquier político de cualquier partido. Admite el redondeo
> razonable del lenguaje oral. Respeta la presunción de inocencia de los no condenados. Cita solo URLs que
> hayas visto de verdad; nunca inventes una URL ni un dato. Si no encuentras prueba suficiente, el veredicto
> es «no_verificable»: no fuerces ni «falso» ni «verdadero».
>
> VEREDICTOS: verdadero | mayormente_verdadero | enganoso (dato real pero sin contexto, mezcla de periodos o
> conclusión que no se sigue) | falso | no_verificable.
>
> ENTREGA: escribe el fichero `entrevistas/<slug>/resultados/<NN-tema>.json` con un array JSON de objetos:
> `{"minuto": "h:mm:ss", "cita": "literal de la transcripción", "afirmacion": "reformulada y autocontenida",
> "veredicto": "...", "explicacion": "2-4 frases con el dato real, su fecha y de dónde sale",
> "confianza": "alta|media|baja", "fuentes": [{"titulo": "...", "url": "https://..."}]}`. Todo en español.
> Como respuesta final dame solo el recuento por veredicto y una línea por cada «falso» o «enganoso».

La `cita` debe ser literal: la web la usa para encontrar el segundo exacto del vídeo.

## 4. Resumir las justificaciones

Un subagente Sonnet por fichero de resultados. Para cada afirmación, en el mismo orden, un resumen de la
explicación: una frase (dos como mucho), máximo 30 palabras, que empiece por el dato real y no añada nada
que no esté en la explicación. Se guarda como array de cadenas en
`entrevistas/<slug>/resumenes/<NN-tema>.json` (misma longitud y orden que el fichero de resultados).

## 4 bis. Excluir lo que no aporta al debate público

Algunas afirmaciones se pueden comprobar pero no tienen interés público. Se quitan de la web y de los recuentos,
y se listan en `entrevistas/<slug>/excluidas.json` con su veredicto original y el motivo. La API las publica
aparte, en el campo `excluidas`. Solo hay cinco motivos posibles:

| Motivo | Ejemplos |
|---|---|
| Dato biográfico o familiar del invitado | Edad, edad de los padres, hijos, estudios, idiomas, a quién votó en su juventud |
| Anécdota personal o privada | Qué coche usaba en las primarias, qué redes sociales usa, ofertas de cargos que rechazó |
| Duración de un cargo o de una trayectoria | «Lleva ocho años en el Gobierno», «llevo 30 años en política» |
| Detalle logístico de la campaña o de la entrevista | Cuándo empieza la campaña, a qué medios ha ido |
| Curiosidad sin relación con el debate público | Que el Papa votó, en qué año se construyó un edificio |

El criterio se aplica igual a todos los invitados y **sin mirar el veredicto**. Nunca se excluye una
afirmación sobre políticas, cifras públicas, instituciones, leyes o la actuación de un cargo o de un partido,
aunque parezca menor. Los identificadores (`m<segundo>`) se asignan antes de excluir, así que no cambian.

## 5. Generar la web y publicar

Cuando todos los bloques y resúmenes estén completos, añade `"publicar": true` a `entrevistas/<slug>/meta.json`
(el generador ignora las entrevistas que no lo tienen, para no publicar verificaciones a medias).

Antes de generar la web, crea las imágenes que se ven al compartir los enlaces (vista previa en WhatsApp, X,
Telegram, LinkedIn, Bluesky): una por entrevista publicada, con el nombre, el partido y el número del programa
(sin recuentos, para que no se queden viejas al corregir veredictos). Necesita Pillow, que no es dependencia del
proyecto, así que se ejecuta con `uv`. Escribe en `web-src/compartir/` (también el favicon); hay que subir esos
ficheros al repositorio. Si falta la imagen de una entrevista, `build.py` avisa y usa la general.

```sh
uv run --with pillow python herramientas/imagenes_compartir.py   # web-src/compartir/<slug>.png, 1200×630
python3 web-src/build.py                                  # genera web/index.html y web/<slug>/index.html
git add entrevistas/<slug> web web-src/compartir && git commit -m "Verificación de la entrevista a <invitado>" && git push
cd web && npx vercel deploy --prod --yes --scope pablopc05s-projects
```

## Qué significa cada veredicto

| Veredicto | Criterio |
|---|---|
| Verdadero | Los datos lo confirman. |
| Casi cierto | Cierto en lo esencial, con una imprecisión menor. |
| Engañoso | Se apoya en algo real pero omite contexto, mezcla periodos o lleva a una conclusión que no se sigue. |
| Falso | Los datos lo contradicen. No implica intención de mentir: incluye errores y lapsus. |
| No verificable | No hay prueba pública suficiente, o la búsqueda se quedó corta. |

## Límites conocidos

- La verificación la hacen modelos de IA y no la revisa un equipo de periodistas.
- Los subagentes tienen un cupo de búsquedas; cuando se agota, lo que queda sin contrastar se marca «no
  verificable», no «verdadero».
- Algunas páginas oficiales no se dejan abrir de forma automática y se citan a través de prensa.
- La transcripción automática no distingue hablantes y a veces confunde nombres.
- El número de afirmaciones falsas depende de cuánto habla cada invitado y de cuántos datos da: no es un ranking.
