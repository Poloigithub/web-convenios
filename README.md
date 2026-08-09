# Web Convenios

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
datos/convenios.sqlite   la BBDD canónica (la actualiza el workflow y la commitea)
datos/convenios.json     exportación que consume la web
web/                index.html + app.js (vanilla) + tailwind.css
.github/workflows/actualizar.yml   cron diario + build + deploy a Pages
```

- Solo **biblioteca estándar de Python**: no hay dependencias que instalar.
- La pasada diaria relee una **ventana de 10 días**, así se autorepara si un
  día falla el cron o una fuente. La BBDD ignora duplicados por id.
- La web filtra y busca en cliente sobre el JSON: sin backend.
- Paleta [Catppuccin](https://catppuccin.com/): Latte de día y Mocha en modo oscuro,
  vía variables CSS (sin variantes `dark:` en las clases).

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
  de ese diario. Es la señal importante, porque no depende de que ese
  día hubiera convenios: si rediseñan el portal, salta aquí aunque el
  scraper devuelva cero en silencio.

Cuando hay problemas ocurren dos cosas:

1. **Aviso por Telegram** (opcional), con el detalle y el enlace a la
   ejecución. Se activa añadiendo dos secretos en el repositorio, en
   *Settings → Secrets and variables → Actions*:
   `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`.
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
