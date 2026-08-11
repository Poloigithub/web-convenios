# Web Convenios

**→ https://poloigithub.github.io/web-convenios/**

Buscador de **convenios colectivos y acuerdos laborales** publicados en seis
diarios oficiales, actualizado a diario con GitHub Actions y servido como web
estática en GitHub Pages.

| Fuente | Ámbito | Cómo se lee |
|---|---|---|
| BOE | Estatal | API pública de datos abiertos (JSON) |
| DOGV | País Valencià | API del portal (JSON) |
| BOP Castelló | Provincia | Portal PrimeFaces: lista de boletines + AJAX |
| BOP València | Provincia | Portal PrimeFaces: calendario (`viewChange` + `dateSelect`) |
| BOP Alicante | Provincia | Webservice JSON de la sede (base completa de convenios) |
| BORM | Región de Murcia | API REST del portal (JSON) |

## Qué recoge

Todo lo que en el **título del sumario** hable de: convenios colectivos,
acuerdos colectivos, revisiones y tablas salariales, calendarios laborales,
planes de igualdad, expedientes de regulación (ERTE) y acuerdos marco
(castellano y valencià). Solo se leen títulos de sumario, nunca se descargan
los documentos.

De cada publicación se guarda: título, código de convenio (REGCON, si el
título lo trae), nº del diario oficial, fecha de publicación, fecha de
captura y URL del PDF/anuncio original.

## Arquitectura

```
scraper/            un módulo por fuente + actualizar.py (orquestador)
datos/convenios.ndjson   el archivo de verdad, versionado (una línea por convenio)
datos/convenios.sqlite   la BBDD, generada desde el ndjson (NO versionada)
datos/convenios.json     exportación que consume la web (NO versionada)
web/                index.html + app.js (vanilla) + tailwind.css
.github/workflows/actualizar.yml   cron diario + build + deploy a Pages
```

### Por qué el archivo es NDJSON y no el sqlite

Un `.sqlite` es binario y git no sabe deltarlo: guardaría una copia
entera en cada pasada diaria (~26 KB al día, ~9 MB al año) aunque solo
cambiasen dos filas. El NDJSON —una línea JSON por convenio, ordenada
por id— se deltea como cualquier texto: **~1 KB al día, ~360 KB al año**.

Así que en el repositorio va el NDJSON, y el sqlite se reconstruye a
partir de él al arrancar (`bd.importar_ndjson`). La BBDD se sigue
publicando en la web para descargarla, en `datos/convenios.sqlite`.
De regalo: en el diff de cada commit se ve qué convenios entraron ese día.

- Solo **biblioteca estándar de Python**: no hay dependencias que instalar.
- La pasada diaria relee una **ventana de 10 días**, así se autorepara si un
  día falla el cron o una fuente. La BBDD ignora duplicados por id.
- La web filtra y busca en cliente sobre el JSON: sin backend.
- Paleta [Catppuccin](https://catppuccin.com/): Latte de día y Mocha en modo oscuro,
  vía variables CSS (sin variantes `dark:` en las clases).

## Los datos

Todo lo recogido está en abierto, en este mismo repositorio:

| Fichero | Dónde | Qué es |
|---|---|---|
| [`datos/convenios.ndjson`](datos/convenios.ndjson) | En el repositorio | **El archivo completo**: una línea JSON por convenio, ordenada por id. Es lo único que se versiona. |
| `datos/convenios.json` | [En la web](https://poloigithub.github.io/web-convenios/datos/convenios.json) | Lo mismo en un único JSON, con metadatos (último boletín de cada diario, estado de la última pasada). Es lo que consume la web. |

El JSON no se versiona porque lleva la marca de tiempo de cada pasada:
dos ejecuciones generan contenido distinto en la misma línea y eso hacía
que cualquier divergencia acabase en conflicto. Al ser un fichero
derivado del ndjson, se genera en cada pasada y se publica, sin más.

La base de datos SQLite no se versiona (ver más abajo), pero se genera en un
segundo desde el NDJSON:

```bash
python3 -c "from pathlib import Path; from scraper import bd; \
  con=bd.abrir(Path('datos/convenios.sqlite')); \
  print(bd.importar_ndjson(con, Path('datos/convenios.ndjson')), 'convenios')"
```

Y para consultarla:

```bash
sqlite3 datos/convenios.sqlite "SELECT fecha_publicacion, titulo FROM convenios WHERE fuente='BOP-CS' ORDER BY fecha_publicacion DESC LIMIT 10;"
```

## Puesta en marcha

1. Crea un repositorio en GitHub y sube este contenido a la rama `main`.
2. En **Settings → Pages**, elige como fuente **GitHub Actions**.
3. En **Actions**, lanza a mano el workflow «Actualizar convenios y publicar
   web» la primera vez (o espera al cron de las 07:30).

Para reconstruir el histórico desde enero (ya viene sembrado):

```bash
python3 -m scraper.actualizar --desde 2026-01-01
```

## Si algo se rompe, avisa

La pasada diaria **no falla** cuando una sola fuente se rompe: la web se
sigue publicando con lo que ya había. Para que un fallo no pase
desapercibido se vigilan dos señales:

- **Error**: la fuente lanzó una excepción al recoger.
- **Canario**: `ultimo()` no ha podido leer el último boletín publicado
  de ese diario. No depende de que ese día hubiera convenios.
- **Anuncios**: se han leído boletines pero no se ha extraído *ningún
  anuncio de ninguna clase*. Cero convenios es normalísimo y no dice
  nada; cero anuncios en un boletín que existe es imposible, así que
  delata al parser aunque el portal siga respondiendo con normalidad.
  Cuando la fuente publica su propio total (el BOP de València dice
  "Mostrant del 1 al 25 de 104") se detecta además la rotura parcial:
  leer menos de la mitad de lo anunciado también avisa.

Cuando hay problemas ocurren dos cosas:

1. **Aviso por Telegram**, con el detalle y el enlace a la ejecución.
   Sale de dos secretos del repositorio (*Settings → Secrets and
   variables → Actions*): `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`.
   Para mandar los avisos a otro chat basta con cambiar el segundo:

   ```bash
   gh secret set TELEGRAM_CHAT_ID    # pide el valor por teclado, no queda en el historial
   ```

   Para averiguar el chat_id de una conversación nueva: escribe algo al
   bot desde ese chat y mira
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
2. **La ejecución se marca en rojo** en la pestaña Actions, *después* de
   haber publicado la web. GitHub manda entonces su correo automático de
   workflow fallido a la cuenta propietaria (esto no requiere configurar
   nada).

Para probar el aviso sin esperar a que se rompa nada:

```bash
TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... python3 -m scraper.actualizar --probar-aviso
```

Y para una pasada normal sin avisar: `--sin-aviso`.

## Límites conocidos

- **BOP Castelló** solo expone los ~30 últimos boletines (unas 10 semanas):
  el histórico anterior a junio de 2026 no existe en su portal.
- El **código de convenio** se extrae del título; si el diario no lo incluye
  ahí, el campo queda vacío.
- Los portales JSF (Castelló, València) son frágiles ante rediseños: si un
  día devuelven 0 crónico o error, tocará ajustar su módulo.
- Si las IPs de los runners de GitHub fueran bloqueadas por algún portal,
  el plan B es ejecutar `python3 -m scraper.actualizar` por cron en cualquier
  máquina y hacer push (el workflow publica igual).
