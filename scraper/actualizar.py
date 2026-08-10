#!/usr/bin/env python3
"""Pasada diaria: recoge las 6 fuentes, actualiza sqlite y exporta JSON.

    python3 -m scraper.actualizar                    # últimos 10 días
    python3 -m scraper.actualizar --desde 2026-01-01 # backfill
    python3 -m scraper.actualizar --solo BOP-V       # una fuente

La ventana por defecto de 10 días hace la pasada autoreparable: si un
día el cron no corre (o una fuente falla), la siguiente pasada lo
recupera. La BBDD ignora los duplicados.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from . import avisar, bd
from .comun import Recuento, hoy_madrid, log
from .fuentes import boe, bop_alicante, bop_castellon, bop_valencia, borm, dogv

RAIZ = Path(__file__).resolve().parent.parent
VENTANA_DIAS = 10


def _por_dias(modulo):
    """Adapta las fuentes con función dia(fecha) a la firma rango()."""
    def rango(inicio: date, fin: date,
              cuenta: Recuento | None = None) -> list[dict]:
        fuera = []
        f = inicio
        while f <= fin:
            fuera += modulo.dia(f, cuenta)
            f += timedelta(days=1)
        return fuera
    return rango


FUENTES = {
    "BOE": _por_dias(boe),
    "DOGV": _por_dias(dogv),
    "BOP-CS": bop_castellon.rango,
    "BOP-V": bop_valencia.rango,
    "BOP-A": bop_alicante.rango,
    "BORM": _por_dias(borm),
}

MODULOS = {"BOE": boe, "DOGV": dogv, "BOP-CS": bop_castellon,
           "BOP-V": bop_valencia, "BOP-A": bop_alicante, "BORM": borm}


def ultimos_boletines() -> dict[str, dict]:
    """Número y fecha del último diario publicado por cada fuente,
    para el pie de la web. Cualquier fallo deja la fuente fuera."""
    fuera = {}
    for nombre, modulo in MODULOS.items():
        try:
            dato = modulo.ultimo()
            if dato:
                fuera[nombre] = dato
        except Exception as e:
            log.warning("ultimo() de %s: %s", nombre, e)
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser(description="Actualiza la BBDD de convenios")
    ap.add_argument("--desde", type=date.fromisoformat)
    ap.add_argument("--hasta", type=date.fromisoformat)
    ap.add_argument("--solo", choices=sorted(FUENTES))
    ap.add_argument("--bd", type=Path, default=RAIZ / "datos" / "convenios.sqlite")
    ap.add_argument("--json", type=Path, default=RAIZ / "datos" / "convenios.json")
    ap.add_argument("--ndjson", type=Path,
                    default=RAIZ / "datos" / "convenios.ndjson")
    ap.add_argument("--sin-aviso", action="store_true",
                    help="no enviar aviso aunque haya problemas")
    ap.add_argument("--probar-aviso", action="store_true",
                    help="manda un aviso de prueba y sale")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    if args.probar_aviso:
        ok = avisar.enviar_telegram(avisar.mensaje(
            ["(prueba) BOP Castelló: no se ha podido leer su último boletín"],
            0, ""))
        log.info("Aviso de prueba %s", "enviado" if ok else "NO enviado")
        return 0 if ok else 1

    hoy = hoy_madrid()
    fin = args.hasta or hoy
    inicio = args.desde or fin - timedelta(days=VENTANA_DIAS)
    log.info("Ventana %s … %s", inicio, fin)

    con = bd.abrir(args.bd)
    # El sqlite no se versiona: en un runner recién clonado no existe y
    # se reconstruye desde el NDJSON, que sí está en el repositorio.
    recuperados = bd.importar_ndjson(con, args.ndjson)
    if recuperados:
        log.info("BBDD reconstruida desde %s (%d convenios)",
                 args.ndjson.name, recuperados)

    estado: dict[str, str] = {}
    recuentos: dict[str, Recuento] = {}
    for nombre, tarea in FUENTES.items():
        if args.solo and nombre != args.solo:
            continue
        cuenta = Recuento()
        recuentos[nombre] = cuenta
        try:
            registros = tarea(inicio, fin, cuenta)
            nuevos = bd.guardar(con, registros)
            estado[nombre] = str(nuevos)
            log.info("%s → %d encontrados, %d nuevos (%s)",
                     nombre, len(registros), nuevos, cuenta)
        except Exception as e:
            estado[nombre] = f"error: {str(e)[:80]}"
            log.warning("%s FALLÓ: %s", nombre, e)

    ultimos = ultimos_boletines()
    total = bd.exportar_json(con, args.json, estado, ultimos)
    bd.exportar_ndjson(con, args.ndjson)
    log.info("BBDD: %d convenios en total; JSON exportado "
             "(últimos boletines de %d fuentes)", total, len(ultimos))

    # Aviso de problemas. No cambia el código de salida: la web debe
    # publicarse igual aunque una fuente se haya roto; de marcar la
    # ejecución en rojo se encarga el workflow con la salida que deja
    # avisar() en GITHUB_OUTPUT.
    if not args.sin_aviso:
        avisar.avisar(estado, ultimos, total, recuentos)

    # La pasada solo se considera fallida si TODAS las fuentes fallaron.
    if estado and all(v.startswith("error") for v in estado.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
