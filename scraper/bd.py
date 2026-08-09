"""Base de datos sqlite y exportación a JSON para la web."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ESQUEMA = """
CREATE TABLE IF NOT EXISTS convenios (
    id                TEXT PRIMARY KEY,
    fuente            TEXT NOT NULL,
    titulo            TEXT NOT NULL,
    codigo_convenio   TEXT,
    numero_diario     TEXT,
    fecha_publicacion TEXT NOT NULL,
    fecha_captura     TEXT NOT NULL,
    url_pdf           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fecha  ON convenios (fecha_publicacion);
CREATE INDEX IF NOT EXISTS idx_fuente ON convenios (fuente);
"""

CAMPOS = ("id", "fuente", "titulo", "codigo_convenio", "numero_diario",
          "fecha_publicacion", "fecha_captura", "url_pdf")


def abrir(ruta: Path) -> sqlite3.Connection:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.executescript(ESQUEMA)
    return con


def guardar(con: sqlite3.Connection, registros: list[dict]) -> int:
    """INSERT OR IGNORE: si ya existe el id, se conserva la fila original
    (y con ella la fecha_captura del día que se vio por primera vez).
    Devuelve cuántos registros eran nuevos de verdad."""
    antes = con.execute("SELECT COUNT(*) FROM convenios").fetchone()[0]
    con.executemany(
        f"INSERT OR IGNORE INTO convenios ({','.join(CAMPOS)}) "
        f"VALUES ({','.join('?' * len(CAMPOS))})",
        [tuple(r[c] for c in CAMPOS) for r in registros])
    con.commit()
    return con.execute("SELECT COUNT(*) FROM convenios").fetchone()[0] - antes


def exportar_json(con: sqlite3.Connection, ruta: Path,
                  estado: dict[str, str],
                  ultimos: dict[str, dict] | None = None) -> int:
    filas = con.execute(
        f"SELECT {','.join(CAMPOS)} FROM convenios "
        "ORDER BY fecha_publicacion DESC, fuente").fetchall()
    items = [dict(zip(CAMPOS, f)) for f in filas]
    recuento: dict[str, int] = {}
    for it in items:
        recuento[it["fuente"]] = recuento.get(it["fuente"], 0) + 1
    datos = {
        "generado": datetime.now(ZoneInfo("Europe/Madrid")).isoformat(timespec="seconds"),
        "total": len(items),
        "recuento": recuento,
        "estado": estado,          # nº de altas (o error) por fuente en esta pasada
        "ultimos": ultimos or {},  # último boletín publicado por cada diario
        "items": items,
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
                    "utf-8")
    return len(items)
