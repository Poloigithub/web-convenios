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
  · enlaces — el enlace del último convenio de cada diario ya no lleva
              al documento. Se comprueba porque pasó: los del DOGV
              acabaron meses llevando a la portada del diario.
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

from .comun import TIMEOUT, USER_AGENT, Recuento, log, reintentar

ETIQUETAS = {
    "BOE": "BOE (estatal)",
    "DOGV": "DOGV (País Valencià)",
    "BOP-CS": "BOP Castelló",
    "BOP-V": "BOP València",
    "BOP-A": "BOP Alicante",
    "BORM": "BORM (Múrcia)",
}


MINIMO_DECLARADOS = 0.5      # leer menos de la mitad de lo anunciado es rotura

# Qué debe devolver el enlace de cada diario. Casi todos sirven el PDF
# del anuncio; el BORM es la excepción a propósito, porque su endpoint de
# PDF está detrás de un antibots y enlazamos a la página del anuncio.
#
# Ojo: NO se mira el Content-Type. El BOP de Castelló manda sus PDF como
# application/octet-stream, así que la cabecera miente; lo que no miente
# son los primeros bytes del fichero.
ENLACE = {"BOE": "pdf", "DOGV": "pdf", "BOP-CS": "pdf",
          "BOP-V": "pdf", "BOP-A": "pdf", "BORM": "web"}


def _primeros_bytes(url: str) -> tuple[int, bytes, str]:
    """Abre el enlace y lee solo el principio: no hace falta el documento
    entero para saber si es lo que dice ser."""
    def hacer():
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(1024), r.geturl()
    return reintentar(hacer, "enlace")


def comprobar_enlaces(enlaces: dict[str, str]) -> list[str]:
    """Comprueba un enlace por diario: que exista y sea lo que toca.

    Nace de un fallo real: durante meses los enlaces del DOGV llevaban a
    la portada del diario en vez de al documento, porque a la ruta del
    PDF le faltaba un prefijo. Todo lo demás iba bien —se recogían los
    convenios, no había errores— y ninguna comprobación lo miraba.
    """
    problemas = []
    for fuente, url in enlaces.items():
        etiqueta = ETIQUETAS.get(fuente, fuente)
        espera = ENLACE.get(fuente, "pdf")
        try:
            estado, cabeza, final = _primeros_bytes(url)
        except Exception as e:
            problemas.append(f"{etiqueta}: el enlace del último convenio "
                             f"no responde — {str(e)[:60]}")
            continue

        if espera == "pdf" and not cabeza.startswith(b"%PDF"):
            pista = ("te deja en una página web en vez del documento"
                     if b"<html" in cabeza[:600].lower()
                     else "no devuelve un PDF")
            problemas.append(
                f"{etiqueta}: el enlace del último convenio {pista} "
                f"({final[:70]})")
        elif espera == "web" and estado != 200:
            problemas.append(
                f"{etiqueta}: el enlace del último convenio responde {estado}")
    return problemas


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
           recuentos: dict[str, Recuento] | None = None,
           enlaces: dict[str, str] | None = None) -> list[str]:
    """Detecta, registra y avisa. Devuelve los problemas encontrados."""
    problemas = detectar(estado, ultimos, recuentos)
    if enlaces:
        problemas += comprobar_enlaces(enlaces)
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
