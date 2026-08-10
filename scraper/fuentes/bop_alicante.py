"""BOP de Alicante — webservice JSON de la sede de la Diputación.

La consulta BOP_COV devuelve LA BASE ENTERA de convenios colectivos
(desde el año 2000) con extracto, fecha, nº de edicto, denominación del
convenio y URL del PDF. Cada pasada re-lee todo y el INSERT OR IGNORE
de la BBDD se queda solo con lo nuevo.

Ojo: la URL funciona con la ruta LITERAL (con ../) tal y como la usa el
JS de la sede; normalizada devuelve "File not found".

Al ser la sección oficial de convenios colectivos, se incluye todo lo
que devuelve sin pasar el filtro de palabras: si está ahí, es laboral.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime

from ..comun import TIMEOUT, USER_AGENT, Recuento, log, registro

WS = ("https://sede.diputacionalicante.es/wp-content/themes/generatepress/"
      "../Desarrollo-Diputacion/webservices/wseConsultaAjax.php")
RE_NUM_BOLETIN = re.compile(r"/\d{4}/\d{2}/\d{2}_(\d+)/")


def _campo(reg: dict, clave: str) -> str:
    v = reg.get(clave) or [""]
    return str(v[0]).strip() if isinstance(v, list) else str(v).strip()


def rango(inicio: date, fin: date,
          cuenta: Recuento | None = None) -> list[dict]:
    q = urllib.parse.urlencode({
        "nemo": "BOP_COV",
        "param": "<parametros><tipo></tipo><entidad></entidad></parametros>",
        "usuario": "-",
    })
    req = urllib.request.Request(f"{WS}?{q}", headers={"User-Agent": USER_AGENT})
    datos = json.loads(urllib.request.urlopen(req, timeout=60)
                       .read().decode("utf-8", "replace"))
    if "convenios" not in datos:
        raise RuntimeError(f"BOP-A: respuesta inesperada: {str(datos)[:120]}")

    todos = datos["convenios"]["registro"]
    # Aquí no hay boletines: el webservice devuelve la base entera de
    # convenios. Que conteste con cero registros ya es la señal de rotura.
    if cuenta:
        cuenta.boletines += 1
        cuenta.anuncios += len(todos)

    fuera = []
    for reg in todos:
        pub = _campo(reg, "publicacion")           # dd/mm/yyyy
        try:
            fecha = datetime.strptime(pub, "%d/%m/%Y").date()
        except ValueError:
            continue
        if not (inicio <= fecha <= fin):
            continue
        extracto = _campo(reg, "extracto")
        denominacion = _campo(reg, "denominacion")
        # El extracto a veces no dice de qué convenio va; la denominación
        # de la BBDD de la Diputación sí. La anteponemos si falta.
        titulo = extracto
        if denominacion and denominacion.lower() not in extracto.lower():
            titulo = f"{denominacion}: {extracto}"
        url = _campo(reg, "ubicacion")
        m = RE_NUM_BOLETIN.search(url)
        edicto = _campo(reg, "edicto")
        fuera.append(registro(
            fuente="BOP-A",
            ident=f"BOP-A-{fecha.year}-{edicto}",
            titulo=titulo,
            numero_diario=m.group(1) if m else "",
            fecha_publicacion=fecha,
            url_pdf=url,
        ))
    return fuera


def ultimo() -> dict | None:
    """Consulta BOP_CON retrocediendo hasta dar con el último boletín."""
    from datetime import timedelta
    from ..comun import hoy_madrid
    for n in range(6):
        f = hoy_madrid() - timedelta(days=n)
        q = urllib.parse.urlencode({
            "nemo": "BOP_CON",
            "param": (f"<raiz><entrada><registro><fechaPub>{f:%d/%m/%Y}"
                      "</fechaPub><tipoorganismo></tipoorganismo>"
                      "</registro></entrada></raiz>"),
            "usuario": "-",
        })
        req = urllib.request.Request(f"{WS}?{q}",
                                     headers={"User-Agent": USER_AGENT})
        try:
            datos = json.loads(urllib.request.urlopen(req, timeout=30)
                               .read().decode("utf-8", "replace"))
        except Exception:
            continue
        for reg in ((datos.get("boletin") or {}).get("boletin") or [{}])[0].get("registro", []):
            m = re.search(r"N[ºo°]\s*(\d+)\s+del?\s+(\d{2})-(\d{2})-(\d{4})",
                          _campo(reg, "sumario"))
            if m:
                return {"numero": m.group(1),
                        "fecha": f"{m.group(4)}-{m.group(3)}-{m.group(2)}"}
    return None
