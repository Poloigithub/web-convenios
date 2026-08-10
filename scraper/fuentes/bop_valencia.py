"""BOP de València — app PrimeFaces (JSF) en bop.dival.es.

No hay API pública, pero el calendario de la portada permite cargar el
butlletí de cualquier fecha por AJAX. El protocolo, calcado del que usa
el navegador, es:

  1. GET a la portada -> cookies + ViewState.
  2. Un POST "viewChange" con calen_month (0-indexado) y calen_year:
     sin esto el servidor IGNORA en silencio las fechas de otros meses
     y devuelve el último butlletí.
  3. Un POST "dateSelect" con calen_input=dd/mm/yyyy.
  4. Paginación estándar de PrimeFaces sobre el componente "list"
     (25 anuncios por página).

Cada respuesta parcial trae un ViewState nuevo que hay que encadenar.
Comprobamos que la cabecera devuelta corresponde a la fecha pedida:
si un día no tiene butlletí, el servidor deja el que estuviera cargado.
"""

from __future__ import annotations

import http.cookiejar
import re
import time
import urllib.parse
import urllib.request
from datetime import date

from ..comun import (TIMEOUT, USER_AGENT, Recuento, interesa, limpiar, log,
                     registro, reintentar)

BASE = "https://bop.dival.es/bop/"
PORTAL = BASE + "xhtml/portal.xhtml"
MESES_VA = {m: i + 1 for i, m in enumerate(
    "gener febrer març abril maig juny juliol agost "
    "setembre octubre novembre desembre".split())}
RE_ITEM = re.compile(
    r'>([^<>]{15,400})</a></div><span class="info">'
    r'<span class="negrita">N[úu]m\. registre: </span>([\d/]+)')
RE_CABECERA = re.compile(r"(\d{1,2})\s+d[e’']\s*(\w+)\s+de\s+(\d{4})")
RE_NUM_BOLETIN = re.compile(r"Butllet[íi]\s+N[úu]m\.\s*(\d+)")
RE_TOTAL = re.compile(r"Mostrant\s+del?\s+\d+\s+al?\s+\d+\s+de\s+(\d+)")
PAUSA = 0.5          # respiro entre días: el portal corta las ráfagas


class _Sesion:
    def __init__(self):
        cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj))
        self.op.addheaders = [("User-Agent", USER_AGENT)]
        def abrir():
            with self.op.open(BASE, timeout=TIMEOUT) as r:
                return r.read().decode("utf-8", "replace")
        home = reintentar(abrir, "BOP-V portada")
        m = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', home)
        if not m:
            raise RuntimeError("BOP-V: la portada no trae ViewState")
        self.vs = m.group(1)
        self.mes_visible: tuple[int, int] | None = None

    def _post(self, campos: dict) -> str:
        campos = dict(campos)
        campos["javax.faces.ViewState"] = self.vs
        req = urllib.request.Request(
            PORTAL, data=urllib.parse.urlencode(campos).encode(), headers={
                "User-Agent": USER_AGENT,
                "Faces-Request": "partial/ajax",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept": "application/xml, text/xml, */*; q=0.01",
                "Referer": BASE,
                "Origin": "https://bop.dival.es",
            })
        def pedir():
            with self.op.open(req, timeout=TIMEOUT) as r:
                return r.read().decode("utf-8", "replace")
        frag = reintentar(pedir, "BOP-V")
        nuevo = re.search(r'ViewState[^>]*><!\[CDATA\[([^\]]+)\]\]', frag)
        if nuevo:
            self.vs = nuevo.group(1)
        return frag

    def mes(self, año: int, mes: int) -> None:
        """viewChange al mes (1-12); el widget lo cuenta desde 0."""
        if self.mes_visible == (año, mes):
            return
        self._post({
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "calen",
            "javax.faces.partial.execute": "calen",
            "javax.faces.behavior.event": "viewChange",
            "javax.faces.partial.event": "viewChange",
            "calen_month": str(mes - 1),
            "calen_year": str(año),
            "j_idt128": "j_idt128",
        })
        self.mes_visible = (año, mes)

    def dia(self, fecha: date) -> str:
        self.mes(fecha.year, fecha.month)
        return self._post({
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "calen",
            "javax.faces.partial.execute": "calen",
            "javax.faces.partial.render": "busqueda boletines3 edictos",
            "javax.faces.behavior.event": "dateSelect",
            "javax.faces.partial.event": "dateSelect",
            "j_idt128": "j_idt128",
            "calen_input": f"{fecha:%d/%m/%Y}",
        })

    def pagina(self, primero: int) -> str:
        return self._post({
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "list",
            "javax.faces.partial.execute": "list",
            "javax.faces.partial.render": "list",
            "list": "list",
            "list_pagination": "true",
            "list_first": str(primero),
            "list_rows": "25",
            "list_skipChildren": "true",
            "list_encodeFeature": "true",
        })


def _fecha_cabecera(frag: str) -> date | None:
    m = RE_CABECERA.search(re.sub(r"<[^>]+>", " ", frag))
    if not m:
        return None
    mes = MESES_VA.get(m.group(2).lower())
    if not mes:
        return None
    try:
        return date(int(m.group(3)), mes, int(m.group(1)))
    except ValueError:
        return None


def _dia(ses: _Sesion, fecha: date, vistos: set[str],
         cuenta: Recuento | None) -> list[dict]:
    """Convenios publicados en el butlletí de un día concreto."""
    frag = ses.dia(fecha)
    if _fecha_cabecera(frag) != fecha:
        return []                     # ese día no hubo butlletí

    num = RE_NUM_BOLETIN.search(frag)
    total_m = RE_TOTAL.search(re.sub(r"<[^>]+>", " ", frag))
    total = int(total_m.group(1)) if total_m else 0

    # Se piden TODAS las páginas desde la primera, incluida la 0. El
    # paginador del portal conserva la página en la que se quedó el día
    # anterior, así que el fragmento que llega al seleccionar la fecha no
    # tiene por qué ser la página 1: dar por hecho que lo era hacía
    # perder anuncios a puñados. Como una misma publicación puede
    # repetirse entre páginas, se agrupan por número de registro.
    del_dia: dict[str, str] = {}
    primero = 0
    while primero < total:
        for bruto, numreg in RE_ITEM.findall(ses.pagina(primero)):
            del_dia.setdefault(numreg, bruto)
        primero += 25
    if not total:
        # Sin total declarado no hay a dónde paginar; nos quedamos con
        # lo que trajera el fragmento inicial.
        for bruto, numreg in RE_ITEM.findall(frag):
            del_dia.setdefault(numreg, bruto)

    if cuenta:
        cuenta.boletines += 1
        cuenta.anuncios += len(del_dia)
        cuenta.declarados += total

    fuera = []
    for numreg, bruto in del_dia.items():
        titulo = limpiar(bruto)
        if numreg in vistos or not titulo or not interesa(titulo):
            continue
        vistos.add(numreg)
        fuera.append(registro(
            fuente="BOP-V",
            ident=f"BOP-V-{numreg.replace('/', '-')}",
            titulo=titulo,
            numero_diario=num.group(1) if num else "",
            fecha_publicacion=fecha,
            url_pdf=(f"{BASE}downloads?anuncioNumReg="
                     f"{urllib.parse.quote(numreg, safe='')}&lang=va"),
        ))
    return fuera


def rango(inicio: date, fin: date,
          cuenta: Recuento | None = None) -> list[dict]:
    ses = _Sesion()
    fuera: list[dict] = []
    vistos: set[str] = set()
    fallidos: list[date] = []

    fecha = fin                       # de nuevo a viejo, como el calendario
    while fecha >= inicio:
        if fecha.weekday() < 5:       # no hay butlletí en fin de semana
            try:
                time.sleep(PAUSA)
                fuera += _dia(ses, fecha, vistos, cuenta)
            except Exception as e:
                # Un día que se atraganta no puede costar meses de
                # trabajo: se anota, se abre sesión nueva (la anterior
                # puede haber quedado inservible) y se sigue.
                log.warning("BOP-V %s: %s", fecha, e)
                fallidos.append(fecha)
                try:
                    ses = _Sesion()
                except Exception as e2:
                    log.error("BOP-V: no se puede reabrir sesión: %s", e2)
                    break
        fecha = fecha.fromordinal(fecha.toordinal() - 1)

    if fallidos:
        log.warning("BOP-V: %d días sin leer (%s%s)", len(fallidos),
                    ", ".join(str(f) for f in fallidos[:5]),
                    "…" if len(fallidos) > 5 else "")
    return fuera


def ultimo() -> dict | None:
    """La portada llega con el últim butlletí ya renderizado."""
    import urllib.request as _ur
    req = _ur.Request(BASE, headers={"User-Agent": USER_AGENT})
    with _ur.urlopen(req, timeout=TIMEOUT) as r:
        home = r.read().decode("utf-8", "replace")
    num = RE_NUM_BOLETIN.search(home)
    fecha = _fecha_cabecera(home)
    if not (num and fecha):
        return None
    return {"numero": num.group(1), "fecha": fecha.isoformat()}
