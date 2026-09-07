import os
import shutil
from datetime import datetime
from pathlib import Path

from ..db import DB_PATH


def crear_backup(dest_dir: str | None = None) -> list[Path]:
    """Copia la base de datos a las carpetas de backup y devuelve las rutas creadas.

    Si `dest_dir` se indica, se usa solo esa carpeta; si no, se leen las rutas de
    `CONTA_BACKUP_DIRS` (separadas por ':'), con ~/repos/conta/backups por defecto.
    """
    src_path = Path(DB_PATH)
    if not src_path.exists():
        raise FileNotFoundError(f"No se encontró la base de datos en {DB_PATH}")

    if dest_dir:
        dest_dirs = [Path(dest_dir).expanduser()]
    else:
        raw = os.getenv("CONTA_BACKUP_DIRS", "~/repos/conta/backups")
        dest_dirs = [Path(p.strip()).expanduser() for p in raw.split(":") if p.strip()]

    filename = f"conta-{datetime.now().strftime('%d-%m-%Y-%H%M')}.db"

    dest_paths = []
    for dir_path in dest_dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
        dest_path = dir_path / filename
        shutil.copy2(src_path, dest_path)
        dest_paths.append(dest_path)
    return dest_paths
