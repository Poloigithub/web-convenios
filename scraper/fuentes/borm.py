"""BORM (Región de Murcia) — API REST pública del portal.

GET /services/boletin/fecha/DD-MM-YYYY/sumario devuelve el boletín del
día con la lista anunciosBoletin (sumario = título, numero = nº de
anuncio, numeroBoletin, anunciante, apartado...).

Como enlace usamos la página del anuncio del propio portal
(#/anuncio/fecha/numero) y no el PDF directo: el endpoint del PDF está
detrás de un gestor anti-bots que a veces desvía a una página de
validación, mientras que la página del anuncio (con su botón de PDF)
funciona siempre.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import date

from ..comun import Recuento, descargar, interesa, limpiar, log, registro

API = "https://www.borm.es/services/boletin/fecha/{dmy}/sumario"


def dia(fecha: date, cuenta: Recuento | None = None) -> list[dict]:
    try:
        crudo = descargar(API.format(dmy=f"{fecha:%d-%m-%Y}"),
                          "application/json").decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (404, 500):
            return []                      # día sin boletín
        raise

    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError:
        log.warning("BORM %s: la respuesta no es JSON", fecha)
        return []

    numero_boletin = str(datos.get("numero") or "")
    anuncios = datos.get("anunciosBoletin") or []
    if cuenta and numero_boletin:
        cuenta.boletines += 1
        cuenta.anuncios += len(anuncios)

    fuera = []
    for an in anuncios:
        titulo = limpiar(str(an.get("sumario") or ""))
        if not titulo or not interesa(titulo):
            continue
        num = an.get("numero")
        fuera.append(registro(
            fuente="BORM",
            ident=f"BORM-{fecha.year}-{num}",
            titulo=titulo,
            numero_diario=numero_boletin,
            fecha_publicacion=fecha,
            url_pdf=f"https://www.borm.es/#/anuncio/{fecha:%d-%m-%Y}/{num}",
        ))
    return fuera


def ultimo() -> dict | None:
    """El BORM tiene endpoint directo del último boletín."""
    from datetime import datetime
    crudo = descargar("https://www.borm.es/services/boletin/ultimo",
                      "application/json").decode("utf-8", "replace")
    datos = json.loads(crudo)
    if not datos.get("numero"):
        return None
    fecha = datetime.strptime(datos["fechaPublicacion"], "%d-%m-%Y").date()
    return {"numero": str(datos["numero"]), "fecha": fecha.isoformat()}
