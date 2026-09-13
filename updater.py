"""
Módulo de actualización automática para el Launcher de Simulación ROS 2.
Comprueba versiones en GitHub, descarga actualizaciones en segundo plano
y permite al alumno actualizar el código con un solo clic.
"""

import os
import sys
import json
import zipfile
import tempfile
import platform
import subprocess
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Tuple, Optional, Callable, Dict, Any

# Versión actual de este cliente
CURRENT_VERSION = "1.0.0"

# Repositorio de GitHub por defecto (el profesor puede cambiarlo por el suyo)
# Ejemplo: "tu_usuario/tu_repositorio"
DEFAULT_GITHUB_REPO = "usuario/repo"

# URL directa al version.json en la rama principal (raw.githubusercontent.com)
DEFAULT_VERSION_URL = f"https://raw.githubusercontent.com/{DEFAULT_GITHUB_REPO}/main/version.json"


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Convierte una cadena como 'v1.2.3' o '1.2' en una tupla de enteros (1, 2, 3) para comparar."""
    cleaned = v_str.strip().lstrip('v').lstrip('V')
    parts = []
    for chunk in cleaned.split('.'):
        num_str = ''.join(filter(str.isdigit, chunk))
        parts.append(int(num_str) if num_str else 0)
    return tuple(parts)


def is_newer_version(remote_ver: str, local_ver: str = CURRENT_VERSION) -> bool:
    """Retorna True si remote_ver es estrictamente superior a local_ver."""
    try:
        return parse_version(remote_ver) > parse_version(local_ver)
    except Exception:
        return False


def fetch_remote_version(version_url: str = DEFAULT_VERSION_URL, timeout: float = 2.0) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Comprueba si hay una nueva versión en GitHub mediante HTTP GET con timeout corto.
    Retorna: (hay_conexion_exitosa, dict_version, mensaje)
    """
    # Si aún no se ha configurado el repositorio real, omitir silenciosamente
    if "usuario/repo" in version_url:
        return False, None, "Repositorio de GitHub pendiente de configurar por el profesor."

    try:
        req = urllib.request.Request(
            version_url,
            headers={"User-Agent": f"ROS2-Nav-Launcher/{CURRENT_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                raw_data = response.read().decode("utf-8")
                data = json.loads(raw_data)
                return True, data, "Comprobación exitosa."
            return False, None, f"Respuesta HTTP {response.status}."
    except urllib.error.URLError as e:
        return False, None, f"Error de red o sin conexión a internet: {e.reason}"
    except json.JSONDecodeError:
        return False, None, "El archivo de versión remoto no tiene formato JSON válido."
    except Exception as e:
        return False, None, f"No se pudo comprobar la versión: {str(e)}"


def check_for_updates(
    version_url: str = DEFAULT_VERSION_URL,
    timeout: float = 2.0
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Función principal de comprobación:
    Retorna (hay_actualizacion_disponible, info_dict, mensaje)
    """
    ok, data, msg = fetch_remote_version(version_url, timeout=timeout)
    if not ok or not data:
        return False, None, msg

    remote_ver = data.get("version", "")
    if is_newer_version(remote_ver, CURRENT_VERSION):
        return True, data, f"Nueva versión {remote_ver} disponible (actual: {CURRENT_VERSION})."
    else:
        return False, data, f"Ya tienes la última versión ({CURRENT_VERSION})."


def download_and_extract_update(
    download_url: str,
    target_dir: Path,
    progress_cb: Callable[[float, str], None]
) -> Tuple[bool, str]:
    """
    Descarga el paquete .zip de la nueva versión con reporte de progreso
    y extrae los archivos sobreescribiendo los ficheros locales.
    """
    if not download_url:
        return False, "La URL de descarga de la actualización está vacía."

    temp_zip = None
    try:
        progress_cb(5.0, "Conectando con el servidor de descargas...")
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": f"ROS2-Nav-Launcher/{CURRENT_VERSION}"}
        )

        with urllib.request.urlopen(req, timeout=15.0) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 16384  # 16 KB

            # Guardar en archivo temporal
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            temp_zip = Path(temp_file.name)

            with open(temp_zip, "wb") as f:
                while True:
                    chunk = response.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = min(90.0, (downloaded / total_size) * 85.0 + 5.0)
                        progress_cb(pct, f"Descargando actualización... ({downloaded // 1024} KB)")
                    else:
                        progress_cb(-1, f"Descargando... ({downloaded // 1024} KB)")

        progress_cb(92.0, "Extrayendo archivos y aplicando cambios...")

        # Descomprimir en el directorio de destino
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            # Lista de archivos a extraer
            for member in zip_ref.namelist():
                # Evitar extraer carpetas de sistema o rutas relativas peligrosas
                filename = os.path.basename(member)
                if not filename:
                    continue
                # Si el archivo está dentro de un subdirectorio del zip (ej: repo-main/launch_simulation.py),
                # extraer los archivos principales en target_dir
                if filename.endswith(".py") or filename == "version.json":
                    source = zip_ref.open(member)
                    dest_file = target_dir / filename
                    with open(dest_file, "wb") as target:
                        target.write(source.read())

        progress_cb(100.0, "¡Actualización completada!")
        return True, "Archivos actualizados correctamente."

    except Exception as e:
        return False, f"Error durante la actualización: {str(e)}"
    finally:
        if temp_zip and temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass


def restart_application():
    """Reinicia la aplicación lanzando un nuevo proceso Python y cerrando el actual."""
    python_bin = sys.executable
    script_path = sys.argv[0]
    args = [python_bin, script_path] + sys.argv[1:]
    
    try:
        subprocess.Popen(args)
    except Exception:
        pass
    sys.exit(0)


class UpdateModalDialog(tk.Toplevel):
    """Ventana modal moderna que informa de la nueva versión y muestra la barra de descarga."""

    def __init__(self, parent: tk.Tk, update_info: Dict[str, Any], target_dir: Path):
        super().__init__(parent)
        self.target_dir = target_dir
        self.update_info = update_info
        self.download_url = update_info.get("download_url", "")
        self.remote_version = update_info.get("version", "desconocida")
        self.changelog = update_info.get("changelog", "Mejoras generales y corrección de errores.")
        self.release_date = update_info.get("release_date", "")

        self.title("Actualización disponible - ROS 2 Launcher")
        self.geometry("500x340")
        self.resizable(False, False)
        self.configure(bg="#f8fafc")
        self.transient(parent)
        self.grab_set()

        # Centrar en la ventana padre
        self._center_window(parent)
        self._build_ui()

    def _center_window(self, parent):
        self.update_idletasks()
        try:
            x = parent.winfo_x() + (parent.winfo_width() // 2) - 250
            y = parent.winfo_y() + (parent.winfo_height() // 2) - 170
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _build_ui(self):
        # Cabecera
        head_frame = tk.Frame(self, bg="#ffffff", padx=16, pady=12, relief="solid", bd=1)
        head_frame.pack(fill=tk.X)

        lbl_badge = tk.Label(
            head_frame,
            text=f"Nueva versión: v{self.remote_version}",
            bg="#dcfce7",
            fg="#15803d",
            font=("Segoe UI", 10, "bold"),
            padx=8,
            pady=3
        )
        lbl_badge.pack(side=tk.LEFT)

        lbl_current = tk.Label(
            head_frame,
            text=f"(Versión instalada: v{CURRENT_VERSION})",
            bg="#ffffff",
            fg="#64748b",
            font=("Segoe UI", 9)
        )
        lbl_current.pack(side=tk.LEFT, padx=8)

        # Cuerpo con Changelog
        body_frame = tk.Frame(self, bg="#f8fafc", padx=16, pady=12)
        body_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            body_frame,
            text="Novedades y notas de la versión:",
            bg="#f8fafc",
            fg="#0f172a",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 4))

        # Caja de texto para el changelog
        txt_changelog = tk.Text(
            body_frame,
            height=5,
            bg="#ffffff",
            fg="#334155",
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
            wrap=tk.WORD,
            padx=8,
            pady=8
        )
        txt_changelog.insert(tk.END, self.changelog)
        txt_changelog.configure(state="disabled")
        txt_changelog.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # Barra de progreso (inicialmente oculta o en 0)
        self.prog_bar = ttk.Progressbar(body_frame, orient="horizontal", mode="determinate")
        self.prog_bar.pack(fill=tk.X, pady=(4, 2))

        self.lbl_status = tk.Label(
            body_frame,
            text="¿Deseas descargar e instalar esta actualización ahora?",
            bg="#f8fafc",
            fg="#475569",
            font=("Segoe UI", 8)
        )
        self.lbl_status.pack(anchor="w")

        # Barra inferior de botones
        btn_frame = tk.Frame(self, bg="#f8fafc", padx=16, pady=12)
        btn_frame.pack(fill=tk.X)

        self.btn_update = ttk.Button(
            btn_frame,
            text="⬇ Actualizar y Reiniciar",
            style="Primary.TButton",
            command=self._on_start_update
        )
        self.btn_update.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_later = ttk.Button(
            btn_frame,
            text="Recordar más tarde",
            style="Secondary.TButton",
            command=self.destroy
        )
        self.btn_later.pack(side=tk.RIGHT)

    def _set_progress(self, pct: float, status_text: str):
        def _update():
            if pct < 0:
                self.prog_bar.configure(mode="indeterminate")
                self.prog_bar.start(10)
            else:
                self.prog_bar.configure(mode="determinate")
                self.prog_bar.stop()
                self.prog_bar["value"] = pct
            self.lbl_status.configure(text=status_text)
        self.after(0, _update)

    def _on_start_update(self):
        """Inicia la descarga de la actualización en un hilo secundario."""
        self.btn_update.configure(state="disabled")
        self.btn_later.configure(state="disabled")

        def _worker():
            ok, msg = download_and_extract_update(
                self.download_url,
                self.target_dir,
                self._set_progress
            )
            if ok:
                self._set_progress(100.0, "¡Actualización completada! Reiniciando launcher...")
                self.after(1500, restart_application)
            else:
                self.after(0, lambda: messagebox.showerror(
                    "Error de actualización",
                    f"No se pudo completar la actualización:\n{msg}",
                    parent=self
                ))
                self.after(0, self.destroy)

        threading.Thread(target=_worker, daemon=True).start()
