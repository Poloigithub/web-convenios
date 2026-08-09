"""Detección de problemas y aviso por Telegram.

Por qué hace falta: la pasada diaria NO falla cuando una sola fuente se
rompe, para que la web se siga publicando con el resto. Sin un aviso
explícito, un portal que cambia de forma devolvería cero para siempre y
nadie se enteraría.

Se vigilan dos señales:

  · error   — la fuente lanzó una excepción al recoger.
  · canario — ultimo() no ha podido leer el último boletín publicado.
              Esta es la importante: no depende de que ese día hubiera
              convenios, solo de que el portal se siga pudiendo leer.
              Si rediseñan el portal, salta aquí.
"""

from __future__ import annotations

import html
import os
import urllib.parse
import urllib.request

from .comun import TIMEOUT, log

ETIQUETAS = {
    "BOE": "BOE (estatal)",
    "DOGV": "DOGV (País Valencià)",
    "BOP-CS": "BOP Castelló",
    "BOP-V": "BOP València",
    "BOP-A": "BOP Alicante",
    "BORM": "BORM (Múrcia)",
}


def detectar(estado: dict[str, str], ultimos: dict[str, dict]) -> list[str]:
    """Devuelve una lista de problemas en lenguaje llano (vacía si todo va)."""
    problemas = []
    for fuente, valor in estado.items():
        etiqueta = ETIQUETAS.get(fuente, fuente)
        if str(valor).startswith("error"):
            problemas.append(f"{etiqueta}: falló al recoger — {valor[7:]}")
        elif fuente not in ultimos:
            problemas.append(
                f"{etiqueta}: no se ha podido leer su último boletín "
                f"(puede que hayan cambiado el portal)")
    return problemas


def enviar_telegram(texto: str) -> bool:
    """Manda el aviso al chat de Telegram. Sin credenciales, no hace nada."""
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (token and chat):
        log.info("Sin TELEGRAM_TOKEN/TELEGRAM_CHAT_ID: no se envía aviso")
        return False
    datos = urllib.parse.urlencode({
        "chat_id": chat,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=datos), timeout=TIMEOUT)
        return True
    except Exception as e:
        log.error("No se ha podido avisar por Telegram: %s", e)
        return False


def mensaje(problemas: list[str], total: int, url_run: str = "") -> str:
    L = ["<b>⚠️ Web Convenios: revisar</b>",
         "", "La recogida diaria ha tenido problemas:"]
    L += [f"· {html.escape(p)}" for p in problemas]
    L += ["", f"La web sigue publicada con los {total} convenios que ya había."]
    if url_run:
        L.append(f'<a href="{html.escape(url_run, quote=True)}">Ver el registro de la ejecución</a>')
    return "\n".join(L)


def avisar(estado: dict[str, str], ultimos: dict[str, dict],
           total: int) -> list[str]:
    """Detecta, registra y avisa. Devuelve los problemas encontrados."""
    problemas = detectar(estado, ultimos)
    if not problemas:
        log.info("Salud: las %d fuentes responden correctamente", len(estado))
        return []

    for p in problemas:
        log.warning("SALUD: %s", p)

    url_run = ""
    servidor = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run = os.environ.get("GITHUB_RUN_ID")
    if servidor and repo and run:
        url_run = f"{servidor}/{repo}/actions/runs/{run}"

    enviar_telegram(mensaje(problemas, total, url_run))

    # Para que el workflow pueda marcar la ejecución en rojo (y GitHub
    # mande su correo automático) sin impedir que la web se publique.
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write("hay_problemas=true\n")
            f.write("problemas<<FIN\n" + "\n".join(problemas) + "\nFIN\n")
    return problemas
