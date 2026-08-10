"""BOE — API pública de datos abiertos, sumario diario en JSON.

El sumario viene clasificado por sección → departamento → epígrafe, y el
BOE tiene epígrafes específicamente laborales («Convenios colectivos de
trabajo», «Fiestas laborales», «Planes de igualdad»...). Filtramos por
epígrafe en vez de por título: así se quedan fuera los convenios
administrativos entre administraciones («Comunidad Autónoma de X.
Convenio»), las licitaciones con «acuerdo marco» y los procesos
selectivos de personal laboral, que por título colarían.
"""

from __future__ import annotations

import json
import re
import urllib.error
from datetime import date

from ..comun import Recuento, descargar, limpiar, log, registro

# Epígrafes del BOE que son relaciones laborales colectivas.
RE_EPIGRAFE = re.compile(
    r"convenios?\s+colectivos?|fiestas\s+laborales|"
    r"planes?\s+de\s+igualdad|calendario\s+laboral|revisi[óo]n\s+salarial",
    re.IGNORECASE)


def _lista(x) -> list:
    """La API devuelve lista si hay varios y dict si hay uno solo."""
    if not x:
        return []
    return x if isinstance(x, list) else [x]


def _url_pdf(item: dict) -> str:
    pdf = item.get("url_pdf")
    if isinstance(pdf, dict):
        pdf = pdf.get("texto")
    return (pdf or item.get("url_html")
            or f"https://www.boe.es/diario_boe/txt.php?id={item.get('identificador')}")


def dia(fecha: date, cuenta: Recuento | None = None) -> list[dict]:
    url = f"https://boe.es/datosabiertos/api/boe/sumario/{fecha:%Y%m%d}"
    try:
        datos = json.loads(descargar(url, "application/json"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []                      # domingos y festivos
        raise

    fuera = []
    for diario in _lista(datos.get("data", {}).get("sumario", {}).get("diario")):
        numero = str(diario.get("numero") or "")
        if cuenta:
            cuenta.boletines += 1
        for seccion in _lista(diario.get("seccion")):
            for depto in _lista(seccion.get("departamento")):
                # Los items pueden colgar del epígrafe o directamente del
                # departamento. Se cuentan TODOS (sean laborales o no):
                # es la señal de que el sumario se sigue leyendo bien.
                grupos = [(e.get("nombre"), _lista(e.get("item")))
                          for e in _lista(depto.get("epigrafe"))]
                grupos.append((None, _lista(depto.get("item"))))
                for nombre, items in grupos:
                    if cuenta:
                        cuenta.anuncios += len(items)
                    if not (nombre and RE_EPIGRAFE.search(str(nombre))):
                        continue
                    for item in items:
                        if not item.get("identificador"):
                            continue
                        fuera.append(registro(
                            fuente="BOE",
                            ident=str(item["identificador"]),
                            titulo=limpiar(str(item.get("titulo") or "")),
                            numero_diario=numero,
                            fecha_publicacion=fecha,
                            url_pdf=_url_pdf(item),
                        ))
    return fuera


def ultimo() -> dict | None:
    """Número y fecha del último BOE publicado (retrocede hasta 5 días)."""
    from datetime import timedelta

    from ..comun import hoy_madrid
    for n in range(5):
        f = hoy_madrid() - timedelta(days=n)
        try:
            datos = json.loads(descargar(
                f"https://boe.es/datosabiertos/api/boe/sumario/{f:%Y%m%d}",
                "application/json"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        for diario in _lista(datos.get("data", {}).get("sumario", {}).get("diario")):
            if diario.get("numero"):
                return {"numero": str(diario["numero"]), "fecha": f.isoformat()}
    return None
