"""Detección de problemas y aviso por Telegram.

Por qué hace falta: la pasada diaria NO falla cuando una sola fuente se
rompe, para que la web se siga publicando con el resto. Sin un aviso
explícito, un portal que cambia de forma devolvería cero para siempre y
nadie se enteraría.

Se vigilan tres señales:

  · error   — la fuente lanzó una excepción al recoger.
  · canario — ultimo() no ha podido leer el último boletín publicado.
              No depende de que ese día hubiera convenios, solo de que
              el portal se siga pudiendo leer.
  · anuncios — se han leído boletines pero no se ha extraído ningún
              anuncio de ninguna clase. Cero CONVENIOS es normalísimo y
              no dice nada; cero ANUNCIOS en un boletín que existe es
              imposible, así que delata al parser aunque el portal
              siga respondiendo con normalidad.
"""

from __future__ import annotations

import html
import os
import urllib.parse
import urllib.request

from .comun import TIMEOUT, Recuento, log

ETIQUETAS = {
    "BOE": "BOE (estatal)",
    "DOGV": "DOGV (País Valencià)",
    "BOP-CS": "BOP Castelló",
    "BOP-V": "BOP València",
    "BOP-A": "BOP Alicante",
    "BORM": "BORM (Múrcia)",
}


MINIMO_DECLARADOS = 0.5      # leer menos de la mitad de lo anunciado es rotura


def detectar(estado: dict[str, str], ultimos: dict[str, dict],
             recuentos: dict[str, Recuento] | None = None) -> list[str]:
    """Devuelve una lista de problemas en lenguaje llano (vacía si todo va)."""
    problemas = []
    recuentos = recuentos or {}
    for fuente, valor in estado.items():
        etiqueta = ETIQUETAS.get(fuente, fuente)

        if str(valor).startswith("error"):
            problemas.append(f"{etiqueta}: falló al recoger — {valor[7:]}")
            continue

        if fuente not in ultimos:
            problemas.append(
                f"{etiqueta}: no se ha podido leer su último boletín "
                f"(puede que hayan cambiado el portal)")
            continue

        # Rotura del parser de anuncios. Ojo: NO se miran los convenios,
        # que muy legítimamente pueden ser cero. Se miran los anuncios de
        # cualquier tipo: un boletín que existe siempre trae anuncios, así
        # que sacar cero solo puede significar que ya no sabemos leerlo.
        c = recuentos.get(fuente)
        if not c or not c.boletines:
            continue                      # sin boletines no hay nada que juzgar
        if c.anuncios == 0:
            problemas.append(
                f"{etiqueta}: se han leído {c.boletines} boletines pero "
                f"ni un solo anuncio (el parser ha dejado de funcionar)")
        elif c.declarados and c.anuncios < c.declarados * MINIMO_DECLARADOS:
            problemas.append(
                f"{etiqueta}: solo se han leído {c.anuncios} de los "
                f"{c.declarados} anuncios que anuncia el portal "
                f"(el parser lee a medias)")
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


def avisar(estado: dict[str, str], ultimos: dict[str, dict], total: int,
           recuentos: dict[str, Recuento] | None = None) -> list[str]:
    """Detecta, registra y avisa. Devuelve los problemas encontrados."""
    problemas = detectar(estado, ultimos, recuentos)
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
