# Verificación de las entrevistas electorales de The Wild Project

Web: **https://verificacion-podcast.vercel.app**

Jordi Wild ha entrevistado en The Wild Project a los candidatos a las elecciones generales del 29 de
noviembre de 2026. Este repositorio contiene la transcripción de cada entrevista, las afirmaciones
comprobables que hace cada invitado, el veredicto de cada una con su explicación y sus fuentes, y el código
que genera la web.

Todo está aquí para que cualquiera pueda revisarlo, discutirlo y corregirlo.

## Qué hay

| Carpeta | Contenido |
|---|---|
| `entrevistas/<slug>/transcripcion.txt` | Transcripción automática completa, con marcas de tiempo. |
| `entrevistas/<slug>/segmentos.json` | La misma transcripción por segmentos, con el segundo de inicio y fin. |
| `entrevistas/<slug>/capitulos.json` | Capítulos del vídeo en YouTube. |
| `entrevistas/<slug>/resultados/*.json` | Las afirmaciones verificadas, un fichero por bloque temático: cita literal, veredicto, explicación, confianza y fuentes. |
| `entrevistas/<slug>/resumenes/*.json` | Resumen de una frase de cada explicación (el texto corto que muestra la web). |
| `herramientas/transcribir.py` | Descarga el audio y lo transcribe en local con Whisper. |
| `herramientas/hablantes.py` | Reconoce quién habla en cada segmento (Jordi, el invitado o los verificadores), en local. |
| `entrevistas/<slug>/hablantes.json`, `transcripcion-hablantes.txt` | La voz de cada segmento y la transcripción por intervenciones. |
| `web-src/build.py` | Genera la web estática (`web/`) a partir de los datos. Sin dependencias. |
| `en-directo/` | Experimento: graba el micrófono, transcribe y verifica en directo. Sin terminar de probar. |
| `METODO.md` | El procedimiento exacto, los criterios de cada veredicto y los límites. La web lo publica en `/metodologia`. |

## Entrevistas

| Invitado | Programa | Estado |
|---|---|---|
| Pedro Sánchez | The Wild Project #393 | Verificada |
| Alberto Núñez Feijóo | The Wild Project #392 | Verificada |
| Ada Colau | The Wild Project #391 | Verificada |

## API abierta

Todos los datos se publican también como JSON estático, sin clave y con CORS abierto, para que terceros y
agentes de IA puedan revisar cada veredicto contra sus fuentes. Documentación: https://verificacion-podcast.vercel.app/api

| Qué | Dirección |
|---|---|
| Entrevistas, recuentos y temas | `/api/v1/entrevistas.json` |
| Todas las afirmaciones | `/api/v1/afirmaciones.json` |
| Afirmaciones de una entrevista | `/api/v1/{slug}.json` |
| Transcripción con tiempos | `/api/v1/{slug}/transcripcion.json` y `.txt` |
| Referencia completa y prompt para agentes de IA | `/api` |
| OpenAPI 3.1 | `/api/v1/openapi.json` |
| Guía para modelos de lenguaje | `/llms.txt` |

## Cómo se ha hecho, en corto

1. El audio se transcribe en local con Whisper (`large-v3-turbo`).
2. Se leen la transcripción y los capítulos, y se separan las afirmaciones factuales comprobables del invitado.
3. Un agente de IA (Claude Sonnet con búsqueda web) por bloque temático contrasta cada afirmación con
   fuentes públicas y le asigna un veredicto. El encargo literal está en [METODO.md](METODO.md).
4. La web enlaza cada afirmación con el segundo exacto del vídeo y con sus fuentes.

## Límites

Esto es una verificación asistida por IA, no revisada por un equipo de periodistas. «Falso» significa que
los datos contradicen lo dicho, no que haya intención de mentir. Una parte de las afirmaciones queda como
«no verificable» porque la búsqueda automática se quedó corta. Los detalles están en [METODO.md](METODO.md).

## Quién lo hace

Proyecto independiente de [Pablo Pardo Cotos](https://github.com/PabloPC05) y [Diego Cristóbal Andaluz](https://github.com/2cristo7).
Pablo, estudiante del doble grado de Matemáticas e Ingeniería Informática de la Universidad Complutense de Madrid, es el
autor y mantenedor: transcripción, verificación, método y web. Diego, cofundador de OSIX Tech, ha hecho el rediseño
visual y responsive, la leyenda flotante, las estadísticas de visitas y la referencia interactiva de la API.

Ninguno de los dos milita ni ha militado en ningún partido, ni ha trabajado o colaborado con ningún partido, con Jordi
Wild o con The Wild Project; nadie les ha encargado esto, y The Wild Project y Jordi Wild no participan en la web ni la
respaldan. No hay financiación ni apoyo de nadie: los únicos costes son las suscripciones de IA, que cada uno paga de
su bolsillo, y la web está en el plan gratuito de Vercel, sin publicidad. Las visitas
se cuentan con Umami, que no usa cookies y, según su documentación, no recoge datos personales. Los vídeos se reproducen con el reproductor de YouTube (youtube-nocookie.com), que solo se carga al pulsar un minuto; a partir de ahí se aplica la política de privacidad de Google. Más detalle en https://verificacion-podcast.vercel.app/quien.

## Corregir un error o contribuir

- **Avisar de un error:** en la página de cada afirmación, el botón «Avisar de un error» abre el formulario con la
  afirmación ya rellenada; solo pide una fuente.
- **Pull request:** se abre desde tu propio fork (no se puede subir directamente a este repositorio). Los pasos,
  qué ficheros tocar y qué no, están en [CONTRIBUTING.md](CONTRIBUTING.md). Cada PR pasa una comprobación automática.

## Reproducirlo

```sh
uv venv --python 3.12 && uv pip install mlx-whisper   # solo para transcribir (Mac con Apple Silicon)
python3 web-src/build.py                              # regenera la web a partir de los datos
```
