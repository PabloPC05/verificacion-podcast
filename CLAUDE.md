# CLAUDE.md

Web estática de verificación de las entrevistas electorales de The Wild Project. Todo el HTML sale de
`web-src/build.py`; la carpeta `web/` es el resultado y se publica tal cual en Vercel.

## Cómo se trabaja

- **No edites `web/` a mano.** Cambia `web-src/build.py` y regenera con `python3 web-src/build.py`. Sin dependencias.
- Regenerar reescribe la fecha `generado` de los JSON de `web/datos/`. Si tu cambio no toca datos, deshazlo antes
  de hacer commit: `git checkout -- web/datos`.
- Cada página es una plantilla en mayúsculas dentro de `build.py` (`PORTADA`, `QUIEN`, `METODOLOGIA`, `VERIFICALO`…)
  con huecos `@@NOMBRE@@`, que rellena `rellenar()`. `@@HEAD_MODO@@` y `@@PIE@@` se rellenan solos.
- Todas las páginas incluyen `@@CSS_MENU@@` al final de su `<style>`. Ahí viven los colores, el contenedor `.ancho`,
  el menú, las esquinas y el retrato. Lo que se repita en dos páginas va en `CSS_MENU`; lo exclusivo de una página, en su plantilla.
- Una página nueva necesita: su plantilla, la escritura en `main()` (junto a `/quien`), su ruta en la lista
  `rutas` de `indexacion()` para el sitemap y, si va en el menú, un enlace en `menu()`.

## Sistema visual

Estética de periódico: blanco y negro, títulos en serif, jerarquía por grosor de borde.

| Elemento | Valor |
|---|---|
| Texto | sistema sans, 16 px, interlineado 1.55–1.6 |
| Títulos | `var(--serif)`; `h1` `clamp(30px,5.2vw,58px)/1.05`, `h2` de sección 24–28 px |
| Separador de sección | `border-top:3px solid var(--tinta)` encima del `h2`, con `padding-top:12px` |
| Cajas y fichas | borde de 2 px de tinta, `border-radius:var(--r-caja)` (14 px) |
| Botones y chips | borde de 1.5–2 px, `var(--r-boton)` (9 px); etiquetas `var(--r-mini)` (5 px) |
| Colores | solo variables: `--fondo`, `--tinta`, `--suave`, `--gris`, `--claro`… y `--tono` para veredictos (clase `tono-<veredicto>`) |
| Etiqueta pequeña | 12 px, mayúsculas, `letter-spacing:.08em`, `color:var(--gris)` |

Nunca pongas un color fijo: el modo oscuro redefine las variables (`_CLARO` / `_OSCURO`) y el botón de la luna
cambia `data-modo` en `<html>`. Comprueba cada cambio en los dos modos.

## Ancho y responsive

La regla principal: **la página usa todo el contenedor y el texto conserva una medida legible.**

- El contenedor es `.ancho` de `CSS_MENU`: 1360 px de máximo y margen lateral `clamp(16px,4vw,48px)`. No lo
  redefinas en una plantilla ni encierres el `main` en 820 px. El ancho se aprovecha con rejillas, no estirando párrafos.
- Los párrafos y listas llevan `max-width:68ch` (entradillas 62ch). Si sobra ancho, pon otra columna al lado.
- Rejillas que se adaptan solas, sin media queries:
  `grid-template-columns:repeat(auto-fit,minmax(min(100%,<mínimo>px),1fr))`. Mínimos que ya se usan: 380 px para
  fichas, 440 px para bloques de texto, 240 px para elementos cortos. El `min(100%, …)` evita el desbordamiento en móvil.
- Cabeceras de página: en móvil, título y entrada apilados; desde 1000 px, rejilla de dos columnas con el `h1`
  a la izquierda y la entrada a la derecha (ver `.cabeza` en `PORTADA` y `QUIEN`).
- Los saltos que existen son 560, 760, 1000 y 1180 px. Usa esos; no inventes otros.
- Tamaños con `clamp()` en vez de saltos bruscos: tipografía, rellenos de caja y huecos de rejilla.
- Dentro de las rejillas, los hijos llevan `min-width:0` para que el texto largo no las rompa.
- Móvil: dianas táctiles de 40–46 px como mínimo, nada de scroll horizontal (las tablas anchas van dentro de
  un contenedor con `overflow-x:auto`) y respeto a `env(safe-area-inset-*)` en lo que vaya fijo.
- Animaciones solo con `transform` y `opacity`, entre 150 y 280 ms, y anuladas con `prefers-reduced-motion`
  (ya lo hace `CSS_MENU`).

## Antes de dar algo por terminado

Regenera, sirve `web/` (`python3 -m http.server -d web`) y mira cada página que hayas tocado a 1440 px y a
390 px de ancho, en claro y en oscuro. Comprueba que `document.documentElement.scrollWidth` no supera el ancho
de la ventana en móvil. Las páginas tienen una animación de entrada: espera un segundo antes de hacer captura.
