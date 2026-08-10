"""DOGV — API pública del portal, sumario diario en JSON.

La fecha va en ISO y el idioma como es_es. Cada elemento de
"disposiciones" trae titulo, id y urlPdf (ruta relativa).
"""

from __future__ import annotations

import json
import urllib.error
from datetime import date

from ..comun import Recuento, descargar, interesa, limpiar, log, registro

API = "https://dogv.gva.es/dogv-portal/dogv?date={iso}&lang=es_es"


def dia(fecha: date, cuenta: Recuento | None = None) -> list[dict]:
    try:
        crudo = descargar(API.format(iso=fecha.isoformat()),
                          "application/json").decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise

    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError:
        log.warning("DOGV %s: la respuesta no es JSON", fecha)
        return []

    numero = str((datos.get("cabecera") or {}).get("numeroDogv") or "")
    disposiciones = datos.get("disposiciones") or []
    if cuenta and numero:
        cuenta.boletines += 1
        cuenta.anuncios += len(disposiciones)

    fuera = []
    for disp in disposiciones:
        if not isinstance(disp, dict):
            continue
        titulo = limpiar(str(disp.get("titulo") or ""))
        if not titulo or not interesa(titulo):
            continue
        ruta = str(disp.get("urlPdf") or "")
        if ruta.startswith("/"):
            enlace = "https://dogv.gva.es" + ruta
        elif ruta:
            enlace = ruta
        else:
            enlace = f"https://dogv.gva.es/es/sumari?data={fecha:%d.%m.%Y}"
        ident = "DOGV-" + (str(disp["id"]) if disp.get("id")
                           else f"{fecha:%Y%m%d}-{len(fuera)}")
        fuera.append(registro(
            fuente="DOGV", ident=ident, titulo=titulo, numero_diario=numero,
            fecha_publicacion=fecha, url_pdf=enlace))
    return fuera


def ultimo() -> dict | None:
    """Número y fecha del último DOGV publicado (retrocede hasta 5 días)."""
    from datetime import timedelta
    from ..comun import hoy_madrid
    for n in range(5):
        f = hoy_madrid() - timedelta(days=n)
        try:
            crudo = descargar(API.format(iso=f.isoformat()),
                              "application/json").decode("utf-8", "replace")
            datos = json.loads(crudo)
        except (urllib.error.HTTPError, json.JSONDecodeError):
            continue
        numero = (datos.get("cabecera") or {}).get("numeroDogv")
        if numero:
            return {"numero": str(numero), "fecha": f.isoformat()}
    return None
