"""BOP de Castelló — app PrimeFaces (JSF) detrás de un WAF F5.

No hay API por fecha: la home trae la lista de los ~30 últimos boletines
(fila 0 = el más reciente) y cada fila es un botón AJAX que recarga el
formulario con los anuncios de ESE boletín. El título de cada anuncio
vive en un <span class="titulo4"> detrás del enlace de descarga.

Límite honesto: el portal solo expone ~30 boletines (unas 10 semanas).
No se puede hacer backfill más atrás.
"""

from __future__ import annotations

import http.cookiejar
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from ..comun import (TIMEOUT, USER_AGENT, Recuento, interesa, limpiar, log,
                     registro)

PAUSA = 1.5          # segundos entre boletines: el WAF corta las ráfagas
REINTENTOS = 3

PORTAL = "https://bop.dipcas.es/PortalBOP/"
MESES = {m: i + 1 for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto "
    "septiembre octubre noviembre diciembre".split())}
RE_TITULO4 = re.compile(
    r'descargarAnuncio\?idAnuncio=(\d+).*?<span class="titulo4">(.*?)</span>',
    re.S)


def _opener():
    op = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", USER_AGENT)]
    return op


def _navega(op, vs: str, list_id: str, item_id: str, row: int) -> str:
    src = f"busquedaBoletinesForm:{list_id}:{row}:{item_id}"
    data = urllib.parse.urlencode({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": src,
        "javax.faces.partial.execute": src,
        "javax.faces.partial.render": "busquedaBoletinesForm",
        src: src,
        "busquedaBoletinesForm": "busquedaBoletinesForm",
        "javax.faces.ViewState": vs,
    }).encode()
    req = urllib.request.Request(PORTAL, data=data, headers={
        "User-Agent": USER_AGENT,
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        # El WAF exige Referer/Origin del propio portal en los POST.
        "Referer": PORTAL,
        "Origin": "https://bop.dipcas.es",
    })
    for intento in range(REINTENTOS):
        try:
            with op.open(req, timeout=TIMEOUT) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code < 500 or intento == REINTENTOS - 1:
                raise
            log.info("BOP-CS: %s en la fila %d, reintento en %ds",
                     e.code, row, 10 * (intento + 1))
            time.sleep(10 * (intento + 1))
    raise RuntimeError("inalcanzable")


def rango(inicio: date, fin: date,
          cuenta: Recuento | None = None) -> list[dict]:
    op = _opener()
    with op.open(PORTAL, timeout=TIMEOUT) as r:
        home = r.read().decode("utf-8", "replace")

    m_vs = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', home)
    m_id = re.search(r'busquedaBoletinesForm:(j_idt\d+):\d+:(j_idt\d+)', home)
    if not (m_vs and m_id):
        raise RuntimeError("el portal del BOP-CS no tiene la forma esperada")
    vs = m_vs.group(1)
    list_id, item_id = m_id.group(1), m_id.group(2)

    # fila -> (nº boletín, fecha), del texto "Nº 94 jueves 06 Agosto 2026"
    filas: list[tuple[int, str, date]] = []
    patron = rf'<a id="busquedaBoletinesForm:{list_id}:(\d+):{item_id}"[^>]*>(.*?)</a>'
    for m in re.finditer(patron, home, re.S):
        txt = limpiar(m.group(2))
        dnum = re.search(r'N[ºo°]?\s*(\d+)', txt)
        dm = re.search(r'(\d{1,2})\s+([A-Za-zñÑáéíóúÁÉÍÓÚ]+)\s+(\d{4})', txt)
        mes = MESES.get(dm.group(2).lower()) if dm else None
        if not (dm and mes):
            continue
        try:
            filas.append((int(m.group(1)),
                          dnum.group(1) if dnum else "",
                          date(int(dm.group(3)), mes, int(dm.group(1)))))
        except ValueError:
            continue

    if filas and min(f[2] for f in filas) > inicio:
        log.warning("BOP-CS: el portal solo llega hasta %s; "
                    "no se puede rellenar más atrás",
                    min(f[2] for f in filas))

    fuera = []
    for row, num, fecha in sorted(filas):
        if fecha > fin:
            continue
        if fecha < inicio:
            break
        time.sleep(PAUSA)
        frag = _navega(op, vs, list_id, item_id, row)
        anuncios = RE_TITULO4.findall(frag)
        if cuenta:
            cuenta.boletines += 1
            cuenta.anuncios += len(anuncios)
        for ident, bruto in anuncios:
            titulo = limpiar(bruto)
            if titulo and interesa(titulo):
                fuera.append(registro(
                    fuente="BOP-CS", ident=f"BOP-CS-{ident}", titulo=titulo,
                    numero_diario=num, fecha_publicacion=fecha,
                    url_pdf=f"{PORTAL}api/descargarAnuncio?idAnuncio={ident}&idioma=es"))
    return fuera


def ultimo() -> dict | None:
    """Fila 0 de la lista de la portada: el boletín más reciente."""
    op = _opener()
    with op.open(PORTAL, timeout=TIMEOUT) as r:
        home = r.read().decode("utf-8", "replace")
    m_id = re.search(r'busquedaBoletinesForm:(j_idt\d+):\d+:(j_idt\d+)', home)
    if not m_id:
        return None
    patron = (rf'<a id="busquedaBoletinesForm:{m_id.group(1)}:0:'
              rf'{m_id.group(2)}"[^>]*>(.*?)</a>')
    m = re.search(patron, home, re.S)
    if not m:
        return None
    txt = limpiar(m.group(1))
    dnum = re.search(r'N[ºo°]?\s*(\d+)', txt)
    dm = re.search(r'(\d{1,2})\s+([A-Za-zñÑáéíóúÁÉÍÓÚ]+)\s+(\d{4})', txt)
    mes = MESES.get(dm.group(2).lower()) if dm else None
    if not (dnum and dm and mes):
        return None
    return {"numero": dnum.group(1),
            "fecha": date(int(dm.group(3)), mes, int(dm.group(1))).isoformat()}
