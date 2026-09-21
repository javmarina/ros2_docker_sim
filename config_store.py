"""
Módulo de gestión de configuración y persistencia para el Launcher de ROS 2.
Guarda las preferencias del usuario (workspace, robot, escenario, etc.) en AppData
para evitar pérdida de configuraciones entre ejecuciones.
"""

import os
import json
import platform
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class ConfigStore:
    """Maneja la carga y almacenamiento seguro de la configuración del usuario en AppData."""

    APP_DIR_NAME = "ros2_nav_launcher"
    CONFIG_FILE_NAME = "config.json"

    # Valores predeterminados seguros
    DEFAULTS: Dict[str, Any] = {
        "workspace_path": "",
        "robot_id": "base",
        "scenario_id": "container_only",
        "world_name": "warehouse",
        "ros_domain_id": "42",
        "web_port": "6080",
        "extra_args": "use_sim_time:=true",
        "force_rebuild": False,
        "auto_open_browser": True
    }

    def __init__(self, fallback_dir: Optional[Path] = None):
        self._fallback_dir = fallback_dir or Path(__file__).parent.resolve()
        self._config_path = self._resolve_config_path()
        self._data: Dict[str, Any] = {}
        self.load()

    def _resolve_config_path(self) -> Path:
        """Determina la ruta óptima para el archivo de configuración según el sistema operativo."""
        system = platform.system().lower()
        try:
            if "windows" in system:
                appdata = os.getenv("APPDATA")
                if appdata:
                    base_dir = Path(appdata) / self.APP_DIR_NAME
                else:
                    base_dir = Path.home() / "AppData" / "Roaming" / self.APP_DIR_NAME
            elif "darwin" in system:
                base_dir = Path.home() / "Library" / "Application Support" / self.APP_DIR_NAME
            else:
                # Linux u otros POSIX
                xdg_config = os.getenv("XDG_CONFIG_HOME")
                if xdg_config:
                    base_dir = Path(xdg_config) / self.APP_DIR_NAME
                else:
                    base_dir = Path.home() / ".config" / self.APP_DIR_NAME

            base_dir.mkdir(parents=True, exist_ok=True)
            return base_dir / self.CONFIG_FILE_NAME
        except Exception:
            # Fallback seguro en la carpeta del script si no hay permisos en AppData
            return self._fallback_dir / f".{self.CONFIG_FILE_NAME}"

    @property
    def config_path(self) -> Path:
        return self._config_path

    def load(self) -> Dict[str, Any]:
        """Carga la configuración desde el archivo JSON o crea una con los valores por defecto."""
        self._data = dict(self.DEFAULTS)
        
        # Si no hay workspace_path configurado, usar por defecto la carpeta del script
        if not self._data["workspace_path"]:
            self._data["workspace_path"] = str(self._fallback_dir)

        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self._data.update(loaded)
            except Exception:
                # Si el archivo está corrupto, usar valores predeterminados
                pass

        return self._data

    def save(self) -> bool:
        """Guarda la configuración actual en disco."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene un valor de la configuración."""
        return self._data.get(key, self.DEFAULTS.get(key, default))

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        """Establece un valor en la configuración y opcionalmente guarda en disco."""
        self._data[key] = value
        if auto_save:
            self.save()

    def update(self, new_data: Dict[str, Any], auto_save: bool = True) -> None:
        """Actualiza múltiples valores."""
        self._data.update(new_data)
        if auto_save:
            self.save()

    @staticmethod
    def validate_workspace(path_str: str) -> Tuple[bool, str]:
        """
        Valida si una ruta de workspace es válida para montaje en Docker y ROS 2.
        Retorna (es_valido, mensaje_descriptivo).
        """
        if not path_str or not path_str.strip():
            return False, "Ruta no especificada."

        p = Path(path_str.strip())
        if not p.exists():
            return False, "La carpeta especificada no existe."

        if not p.is_dir():
            return False, "La ruta indicada no es un directorio."

        # Inspeccionar si tiene estructura de paquetes ROS 2
        try:
            has_src = (p / "src").is_dir()
            has_direct_package = (p / "package.xml").exists()
            has_sub_packages = any(p.glob("*/package.xml")) or (has_src and any((p / "src").glob("*/package.xml")))

            if has_src and any((p / "src").glob("*/package.xml")):
                return True, "Workspace ROS 2 detectado (contiene carpeta src/ con paquetes)."
            elif has_direct_package or has_sub_packages:
                return True, "Paquetes ROS 2 detectados en la carpeta."
            else:
                return True, "Carpeta válida (se montará en /ros2_ws/src)."
        except Exception:
            return True, "Carpeta válida."
