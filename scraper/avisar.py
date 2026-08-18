"""Detección de problemas y aviso por Telegram.

Por qué hace falta: la pasada diaria NO falla cuando una sola fuente se
rompe, para que la web se siga publicando con el resto. Sin un aviso
explícito, un portal que cambia de forma devolvería cero para siempre y
nadie se enteraría.

Se vigilan cuatro señales:

  · error    — la fuente lanzó una excepción al recoger.
  · canario  — ultimo() no ha podido leer el último boletín publicado.
               No depende de que ese día hubiera convenios, solo de que
               el portal se siga pudiendo leer.
  · anuncios — se han leído boletines pero no se ha extraído ningún
               anuncio de ninguna clase. Cero CONVENIOS es normalísimo y
               no dice nada; cero ANUNCIOS en un boletín que existe es
               imposible, así que delata al parser aunque el portal siga
               respondiendo con normalidad.
  · enlaces  — el enlace del último convenio ya no lleva al documento.
               Se comprueba porque pasó: los del DOGV llevaron meses a
               la portada del diario y nada lo detectaba.

Y, sobre todas ellas, una regla: NO se avisa al primer tropiezo. Los
portales oficiales se caen a ratos y la ventana de diez días recupera
sola lo que se pierda, así que un timeout suelto no es nada que haya que
mirar. Solo se avisa cuando la misma fuente falla en pasadas seguidas,
que es cuando ya no es mala suerte. Una alarma que salta sin motivo
acaba ignorándose, y entonces no sirve para nada.
"""

from __future__ import annotations

import html
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from .comun import TIMEOUT, USER_AGENT, Recuento, log, reintentar

ETIQUETAS = {
    "BOE": "BOE (estatal)",
    "DOGV": "DOGV (País Valencià)",
    "BOP-CS": "BOP Castelló",
    "BOP-V": "BOP València",
    "BOP-A": "BOP Alicante",
    "BORM": "BORM (Múrcia)",
}

AVISAR_TRAS = 2              # pasadas seguidas fallando antes de avisar
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


# ─────────────────────────── Señales ───────────────────────────

def detectar(estado: dict[str, str], ultimos: dict[str, dict],
             recuentos: dict[str, Recuento] | None = None) -> dict[str, str]:
    """Problemas de recogida, uno por fuente (dict vacío si todo va)."""
    problemas: dict[str, str] = {}
    recuentos = recuentos or {}
    for fuente, valor in estado.items():
        if str(valor).startswith("error"):
            problemas[fuente] = f"falló al recoger — {valor[7:]}"
            continue

        if fuente not in ultimos:
            problemas[fuente] = ("no se ha podido leer su último boletín "
                                 "(puede que hayan cambiado el portal)")
            continue

        # Rotura del parser de anuncios. Ojo: NO se miran los convenios,
        # que muy legítimamente pueden ser cero. Se miran los anuncios de
        # cualquier tipo: un boletín que existe siempre trae anuncios, así
        # que sacar cero solo puede significar que ya no sabemos leerlo.
        c = recuentos.get(fuente)
        if not c or not c.boletines:
            continue                      # sin boletines no hay nada que juzgar
        if c.anuncios == 0:
            problemas[fuente] = (f"se han leído {c.boletines} boletines pero "
                                 f"ni un solo anuncio (el parser ha dejado "
                                 f"de funcionar)")
        elif c.declarados and c.anuncios < c.declarados * MINIMO_DECLARADOS:
            problemas[fuente] = (f"solo se han leído {c.anuncios} de los "
                                 f"{c.declarados} anuncios que anuncia el "
                                 f"portal (el parser lee a medias)")
    return problemas


def _primeros_bytes(url: str) -> tuple[int, bytes, str]:
    """Abre el enlace y lee solo el principio: no hace falta el documento
    entero para saber si es lo que dice ser."""
    def hacer():
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(1024), r.geturl()
    return reintentar(hacer, "enlace")


def comprobar_enlaces(enlaces: dict[str, str]) -> dict[str, str]:
    """Comprueba un enlace por diario: que exista y sea lo que toca."""
    problemas: dict[str, str] = {}
    for fuente, url in enlaces.items():
        espera = ENLACE.get(fuente, "pdf")
        try:
            estado, cabeza, final = _primeros_bytes(url)
        except Exception as e:
            problemas[fuente] = ("el enlace del último convenio no responde "
                                 f"— {str(e)[:60]}")
            continue

        if espera == "pdf" and not cabeza.startswith(b"%PDF"):
            pista = ("te deja en una página web en vez del documento"
                     if b"<html" in cabeza[:600].lower()
                     else "no devuelve un PDF")
            problemas[fuente] = (f"el enlace del último convenio {pista} "
                                 f"({final[:70]})")
        elif espera == "web" and estado != 200:
            problemas[fuente] = (f"el enlace del último convenio responde "
                                 f"{estado}")
    return problemas


# ──────────────────── Insistencia entre pasadas ────────────────────

def _cargar(ruta: Path) -> dict[str, dict]:
    try:
        return json.loads(ruta.read_text("utf-8"))
    except Exception:
        return {}


def racha(problemas: dict[str, str], ruta: Path,
          hoy: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """Lleva la cuenta de fallos seguidos y decide de qué hay que avisar.

    Devuelve (estado nuevo, lo que merece aviso). Una fuente que vuelve a
    funcionar se le borra la cuenta: solo preocupa lo que persiste.
    """
    previo = _cargar(ruta)
    nuevo: dict[str, dict] = {}
    for fuente, motivo in problemas.items():
        antes = previo.get(fuente, {})
        nuevo[fuente] = {
            "fallos": int(antes.get("fallos", 0)) + 1,
            "desde": antes.get("desde", hoy),
            "motivo": motivo,
        }
    avisables = {f: d for f, d in nuevo.items() if d["fallos"] >= AVISAR_TRAS}
    return nuevo, avisables


# ─────────────────────────── Aviso ───────────────────────────

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


def mensaje(lineas: list[str], total: int, url_run: str = "") -> str:
    L = ["<b>⚠️ Web Convenios: revisar</b>", "",
         "Estas fuentes llevan varias pasadas fallando:"]
    L += [f"· {html.escape(t)}" for t in lineas]
    L += ["", f"La web sigue publicada con los {total} convenios que ya había."]
    if url_run:
        L.append(f'<a href="{html.escape(url_run, quote=True)}">'
                 "Ver el registro de la ejecución</a>")
    return "\n".join(L)


def avisar(estado: dict[str, str], ultimos: dict[str, dict], total: int,
           recuentos: dict[str, Recuento] | None = None,
           enlaces: dict[str, str] | None = None,
           salud: Path | None = None, hoy: str = "") -> list[str]:
    """Detecta, lleva la cuenta y avisa de lo que persiste."""
    problemas = detectar(estado, ultimos, recuentos)
    if enlaces:
        for fuente, motivo in comprobar_enlaces(enlaces).items():
            problemas.setdefault(fuente, motivo)

    salud = salud or Path("datos/salud.json")
    nuevo, avisables = racha(problemas, salud, hoy)

    try:
        salud.parent.mkdir(parents=True, exist_ok=True)
        salud.write_text(json.dumps(nuevo, ensure_ascii=False, indent=1,
                                    sort_keys=True) + "\n", "utf-8")
    except Exception as e:
        log.warning("No se ha podido guardar %s: %s", salud, e)

    if not problemas:
        log.info("Salud: las %d fuentes responden correctamente", len(estado))
        return []

    for fuente, dato in nuevo.items():
        cuantos = dato["fallos"]
        aguanta = "" if cuantos >= AVISAR_TRAS else "  (aún sin avisar)"
        log.warning("SALUD: %s: %s [%d seguidas]%s",
                    ETIQUETAS.get(fuente, fuente), dato["motivo"],
                    cuantos, aguanta)

    if not avisables:
        log.info("Nada que avisar: ningún fallo llega a %d pasadas seguidas",
                 AVISAR_TRAS)
        return []

    lineas = [f"{ETIQUETAS.get(f, f)}: {d['motivo']} "
              f"({d['fallos']} pasadas seguidas, desde el {d['desde']})"
              for f, d in avisables.items()]

    url_run = ""
    servidor = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run = os.environ.get("GITHUB_RUN_ID")
    if servidor and repo and run:
        url_run = f"{servidor}/{repo}/actions/runs/{run}"

    enviar_telegram(mensaje(lineas, total, url_run))

    # Para que el workflow pueda marcar la ejecución en rojo (y GitHub
    # mande su correo automático) sin impedir que la web se publique.
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write("hay_problemas=true\n")
            f.write("problemas<<FIN\n" + "\n".join(lineas) + "\nFIN\n")
    return lineas
