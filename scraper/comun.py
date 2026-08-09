"""Utilidades compartidas por todas las fuentes."""

from __future__ import annotations

import html
import logging
import re
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

TIMEOUT = 30
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

log = logging.getLogger("convenios")

# Filtro AMPLIO de relaciones laborales: convenios y su ecosistema
# (revisiones, tablas, calendarios laborales, planes de igualdad, ERTEs,
# acuerdos marco). Regex con límites de palabra para evitar
# falsos positivos; cubre castellano y valencià.
_PATRONES = [
    r"\bconveni[os]?\s+col",              # convenio colectivo / conveni col·lectiu
    r"\bacuerdos?\s+colectiv",            # acuerdo colectivo
    r"\bacords?\s+col",                   # acord col·lectiu
    r"\brevisi[óo]n?\s+salarial",         # revisión / revisió salarial
    r"\bta[bu]l\w*\s+salarial",           # tabla(s) / taula(es) salarial(s)
    r"\bcalendari[os]?\s+laboral",        # calendario / calendari laboral
    r"\bplan(?:es)?\s+de\s+igualdad",     # plan de igualdad
    r"\bplans?\s+d.igualtat",             # pla d'igualtat
    r"\bexpedient[e]?s?\s+de\s+regulaci[óo]",  # expediente de regulación de empleo
    r"\bacuerdos?\s+marco\b",             # acuerdo marco (laboral)
    r"\bacords?\s+marc\b",
    r"\bpact[eo]s?\s+(?:colectiv|col·?lectiu|de\s+empresa|d.empresa)",
    r"\bcomisi[óo]n?\s+paritaria|\bcomissió\s+paritària",
    r"\b(?:comisi[óo]n?|comissió|mesa|taula)\s+negociadora",
]
RE_INTERESA = [re.compile(p, re.IGNORECASE) for p in _PATRONES]
RE_ERTE = re.compile(r"\bERTE\b")        # solo en mayúsculas, si no es ruido

# Anuncios que mencionan términos laborales pero NO son negociación
# colectiva: licitaciones con «acuerdo marco», procesos selectivos de
# personal laboral, bolsas de trabajo...
_EXCLUSIONES = [
    r"licitaci[óo]n?|licitaci[óo]",
    r"contractaci[óo]n?\s+de|contrataci[óo]n?\s+del?\s+(?:servicio|suministro|obra)",
    r"acuerdo\s+marco\s+(?:para|de)\s+(?:la\s+)?(?:contrataci|homologaci|adquisici|prestaci|gesti[óo]|suministr)",
    r"formalizaci[óo]n?\s+de\s+contratos?|acord\s+marc\s+de\s+subministr",
    r"proces[os]{1,2}\s+selectivo|proc[eé]s\s+selectiu|proceso\s+de\s+selecci[óo]n",
    r"admitid[oa]s\s+y\s+excluid[oa]s|admes[oa]s\s+i\s+exclos[oa]s",
    r"bolsa\s+de\s+(?:trabajo|empleo)|borsa\s+de\s+(?:treball|ocupaci[óo])",
    r"oposici[óo]n?\s+libre|concurso[\s-]+oposici[óo]n?|concurs\s+oposici[óo]",
]
RE_EXCLUYE = [re.compile(p, re.IGNORECASE) for p in _EXCLUSIONES]

# Código REGCON («número de convenio»): 14 dígitos modernos
# (p. ej. 12000952011981) o el formato antiguo tipo 030074-5.
RE_CODIGO = re.compile(r"\b(\d{14})\b|\b(\d{6}-\d)\b")


def interesa(titulo: str) -> bool:
    if not (any(r.search(titulo) for r in RE_INTERESA)
            or RE_ERTE.search(titulo)):
        return False
    return not any(r.search(titulo) for r in RE_EXCLUYE)


def extraer_codigo(titulo: str) -> str:
    m = RE_CODIGO.search(titulo)
    return (m.group(1) or m.group(2)) if m else ""


def limpiar(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def descargar(url: str, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": accept})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def hoy_madrid() -> date:
    return datetime.now(ZoneInfo("Europe/Madrid")).date()


def registro(fuente: str, ident: str, titulo: str, numero_diario: str,
             fecha_publicacion: date | str, url_pdf: str) -> dict:
    """Forma canónica de un convenio tal y como lo guarda la BBDD."""
    fecha = (fecha_publicacion.isoformat()
             if isinstance(fecha_publicacion, date) else fecha_publicacion)
    return {
        "id": ident,
        "fuente": fuente,
        "titulo": titulo,
        "codigo_convenio": extraer_codigo(titulo),
        "numero_diario": str(numero_diario or ""),
        "fecha_publicacion": fecha,
        "fecha_captura": hoy_madrid().isoformat(),
        "url_pdf": url_pdf,
    }
