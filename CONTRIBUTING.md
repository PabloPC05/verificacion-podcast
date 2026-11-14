# Cómo contribuir

Gracias por querer mejorar la verificación. Las correcciones con fuente son lo más valioso que puedes aportar.

## La forma más rápida: avisar de un error

Si has visto un veredicto que crees que está mal, una fuente rota o una cita mal transcrita, no hace falta que
toques código: en la página de la afirmación, pulsa **«Avisar de un error»**. Se abre el formulario con la afirmación
ya rellenada y solo hay que pegar una fuente que respalde la corrección. También se puede abrir
[directamente](https://github.com/PabloPC05/verificacion-podcast/issues/new?template=correccion.yml) indicando quién
lo dijo y el minuto.

## Abrir una pull request

No tienes permiso para subir ramas directamente a este repositorio (nadie lo tiene salvo el mantenedor). Por eso
`git push` a este repositorio da error. Hay que hacerlo desde una copia tuya (un *fork*):

1. Pulsa **Fork** arriba a la derecha en GitHub para crear tu copia.
2. Clónala y crea una rama:
   ```sh
   git clone https://github.com/<tu-usuario>/verificacion-podcast.git
   cd verificacion-podcast
   git checkout -b corrige-sanchez-m6003
   ```
3. Haz el cambio (ver abajo qué tocar), y súbelo **a tu fork**:
   ```sh
   git commit -am "Corrige el veredicto de sanchez-m6003"
   git push -u origin corrige-sanchez-m6003
   ```
4. GitHub te mostrará el botón **Compare & pull request**. Ábrela contra la rama `main` de este repositorio.

Para un cambio pequeño también puedes editar el fichero desde la web de GitHub (icono del lápiz): GitHub crea el
fork y la rama por ti y te ofrece abrir la PR al guardar.

## Qué ficheros tocar

| Quiero… | Fichero |
|---|---|
| Corregir un veredicto, una explicación o una fuente | `entrevistas/<slug>/resultados/<NN-tema>.json` |
| Corregir el resumen corto que muestra la web | `entrevistas/<slug>/resumenes/<NN-tema>.json` (misma posición que en `resultados`) |
| Proponer quitar o recuperar una afirmación irrelevante | `entrevistas/<slug>/excluidas.json` (criterio en [METODO.md](METODO.md)) |
| Proponer otra afirmación para «Lo esencial» | `entrevistas/<slug>/esencial.json` (de 3 a 5, criterio en el propio fichero) |
| Enlazar lo que publicó otro verificador sobre la misma frase | `entrevistas/<slug>/otros_verificadores.json` |
| Mover un capítulo a otro tema de la comparativa | `entrevistas/temas.json` |
| Cambiar el diseño o el generador de la web | `web-src/` |

**No incluyas cambios en `web/`.** Es la web generada: se regenera al aceptar la PR y, si la incluyes, casi
seguro dará conflictos con otras PR.

Si cambias un veredicto, explica en la PR por qué y enlaza la fuente, y deja constancia en la propia afirmación con
un campo `correcciones`. La web la marcará como «Corregido» y enseñará el historial:

```json
"correcciones": [{"fecha": "2026-11-20", "antes": "enganoso", "motivo": "El INE publicó el dato definitivo, que confirma la cifra."}]
```

`antes` es el veredicto anterior (si solo cambia la explicación o una fuente, déjalo fuera). La fecha de la
verificación original sale de `meta.json` (`verificado`); si vuelves a verificar una afirmación entera, añádele
`"verificado": "AAAA-MM-DD"`.

Se aplica la misma vara de medir a todos los
invitados: una corrección se acepta por la fuente, no por el partido.

## Comprobar tu cambio en local (opcional)

Solo hace falta Python 3, sin dependencias:

```sh
python3 web-src/build.py          # genera web/ a partir de los datos
python3 -m http.server -d web 8000  # y abre http://localhost:8000
```

En local, los datos de la API están en `/datos/v1/` (en la web publicada, Vercel los sirve en `/api/v1/`).

Cada PR pasa además una comprobación automática que valida los JSON y genera la web. Si falla, el detalle está
en la pestaña **Checks** de la PR.

## Normas

- Sé respetuoso. Esto va de datos, no de partidos.
- Una PR por corrección o por tema facilita la revisión.
- No inventes fuentes ni enlaces; si no hay prueba suficiente, el veredicto es «no verificable».
