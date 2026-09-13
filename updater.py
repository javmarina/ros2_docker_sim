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
import logging
import platform
import subprocess
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Tuple, Optional, Callable, Dict, Any

# Configurar logger para este módulo
logger = logging.getLogger("updater")

# Repositorio de GitHub por defecto (el profesor puede cambiarlo por el suyo)
# Ejemplo: "tu_usuario/tu_repositorio"
DEFAULT_GITHUB_REPO = "javmarina/ros2_docker_sim"

# URL de la API de GitHub para obtener version.json en tiempo real (sin la caché de 5 minutos de Fastly CDN)
DEFAULT_API_VERSION_URL = f"https://api.github.com/repos/{DEFAULT_GITHUB_REPO}/contents/version.json?ref=main"

# URL directa al version.json en la rama principal (raw.githubusercontent.com - caché CDN de ~5 min)
DEFAULT_VERSION_URL = f"https://raw.githubusercontent.com/{DEFAULT_GITHUB_REPO}/main/version.json"

# URL de respaldo automático para descargar el archivo zip de la rama principal de GitHub
DEFAULT_ARCHIVE_URL = f"https://github.com/{DEFAULT_GITHUB_REPO}/archive/refs/heads/main.zip"


def get_local_version() -> str:
    """Obtiene la versión instalada localmente leyendo version.json o usando '1.0.0' como base."""
    try:
        ver_file = Path(__file__).parent.resolve() / "version.json"
        if ver_file.is_file():
            with open(ver_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                ver = data.get("version")
                if ver:
                    return str(ver).strip()
    except Exception as e:
        logger.debug("get_local_version error al leer version.json: %s", e)
    return "1.0.0"


# Versión actual de este cliente (se lee dinámicamente de version.json)
CURRENT_VERSION = get_local_version()


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Convierte una cadena como 'v1.2.3' o '1.2' en una tupla de enteros (1, 2, 3) para comparar."""
    cleaned = v_str.strip().lstrip('v').lstrip('V')
    parts = []
    for chunk in cleaned.split('.'):
        num_str = ''.join(filter(str.isdigit, chunk))
        parts.append(int(num_str) if num_str else 0)
    result = tuple(parts)
    logger.debug("parse_version('%s') -> %s", v_str, result)
    return result


def is_newer_version(remote_ver: str, local_ver: str = CURRENT_VERSION) -> bool:
    """Retorna True si remote_ver es estrictamente superior a local_ver."""
    try:
        remote_tuple = parse_version(remote_ver)
        local_tuple = parse_version(local_ver)
        newer = remote_tuple > local_tuple
        logger.debug("is_newer_version: remote %s > local %s -> %s", remote_tuple, local_tuple, newer)
        return newer
    except Exception as e:
        logger.error("is_newer_version error: %s", e, exc_info=True)
        return False


def fetch_remote_version(
    version_url: str = DEFAULT_VERSION_URL,
    timeout: float = 3.0,
    repo: str = DEFAULT_GITHUB_REPO
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Comprueba si hay una nueva versión en GitHub mediante HTTP GET.
    Prioriza la API directa de GitHub para evitar la caché de 5 minutos de Fastly CDN (raw.githubusercontent.com).
    Retorna: (hay_conexion_exitosa, dict_version, mensaje)
    """
    logger.info("fetch_remote_version: Consultando versiones remotas (timeout: %ss)...", timeout)

    # Si aún no se ha configurado el repositorio real, omitir silenciosamente
    if "usuario/repo" in version_url or "usuario/repo" in repo:
        msg = "Repositorio de GitHub pendiente de configurar por el profesor (se mantiene 'usuario/repo')."
        logger.warning("fetch_remote_version: %s", msg)
        return False, None, msg

    api_url = f"https://api.github.com/repos/{repo}/contents/version.json?ref=main"
    urls_to_try = [
        (api_url, {"Accept": "application/vnd.github.v3.raw", "User-Agent": f"ROS2-Nav-Launcher/{get_local_version()}"}, "API de GitHub (en vivo)"),
        (version_url, {"User-Agent": f"ROS2-Nav-Launcher/{get_local_version()}", "Cache-Control": "no-cache", "Pragma": "no-cache"}, "raw.githubusercontent.com (CDN)")
    ]

    last_error = None
    for url, headers, source_name in urls_to_try:
        try:
            logger.debug("fetch_remote_version: Enviando petición a %s: '%s'", source_name, url)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                logger.debug("fetch_remote_version: Respuesta %s código HTTP %s", source_name, response.status)
                if response.status == 200:
                    raw_data = response.read().decode("utf-8")
                    logger.debug("fetch_remote_version: Contenido recibido de %s:\n%s", source_name, raw_data.strip())
                    data = json.loads(raw_data)
                    return True, data, "Comprobación exitosa."
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
            logger.debug("fetch_remote_version: %s devolvió %s", source_name, last_error)
        except json.JSONDecodeError as e:
            last_error = f"JSONDecodeError: {e}"
            logger.warning("fetch_remote_version: %s no devolvió JSON válido: %s", source_name, e)
        except Exception as e:
            last_error = str(e)
            logger.debug("fetch_remote_version: Error conectando con %s: %s", source_name, e)

    err_msg = f"No se pudo comprobar la versión remota ({last_error})."
    logger.warning("fetch_remote_version: %s", err_msg)
    return False, None, err_msg


def check_for_updates(
    version_url: str = DEFAULT_VERSION_URL,
    timeout: float = 2.0,
    local_ver: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Función principal de comprobación:
    Retorna (hay_actualizacion_disponible, info_dict, mensaje)
    """
    active_local_ver = local_ver or get_local_version()
    logger.info("Iniciando comprobación de actualizaciones (Versión local instalada: v%s)", active_local_ver)
    ok, data, msg = fetch_remote_version(version_url, timeout=timeout)
    if not ok or not data:
        logger.warning("check_for_updates: No se pudo obtener versión remota (%s)", msg)
        return False, None, msg

    remote_ver = data.get("version", "")
    logger.info("Versión remota encontrada: v%s", remote_ver)
    if is_newer_version(remote_ver, active_local_ver):
        msg = f"Nueva versión {remote_ver} disponible (actual: {active_local_ver})."
        logger.info("check_for_updates: ¡HAY ACTUALIZACIÓN DISPONIBLE! -> %s", msg)
        return True, data, msg
    else:
        msg = f"Ya tienes la última versión ({active_local_ver})."
        logger.info("check_for_updates: El sistema está al día -> %s", msg)
        return False, data, msg


def download_and_extract_update(
    download_url: str,
    target_dir: Path,
    progress_cb: Callable[[float, str], None],
    fallback_repo: str = DEFAULT_GITHUB_REPO
) -> Tuple[bool, str]:
    """
    Descarga el paquete .zip de la nueva versión con reporte de progreso
    y extrae los archivos sobreescribiendo los ficheros locales.
    Soporta fallback automático a la descarga directa del repositorio de GitHub
    en caso de que download_url retorne 404 o no esté disponible.
    """
    fallback_url = f"https://github.com/{fallback_repo}/archive/refs/heads/main.zip"
    logger.info(
        "Iniciando descarga de actualización. URL principal: '%s' | URL de respaldo: '%s' (Destino: %s)",
        download_url, fallback_url, target_dir
    )

    candidate_urls = []
    if download_url and "usuario/repo" not in download_url:
        candidate_urls.append(download_url)
    if fallback_url and fallback_url not in candidate_urls and "usuario/repo" not in fallback_url:
        candidate_urls.append(fallback_url)

    if not candidate_urls:
        err_msg = "No se configuró ninguna URL de descarga válida."
        logger.error("download_and_extract_update: %s", err_msg)
        return False, err_msg

    temp_zip = None
    try:
        response = None
        active_url = None
        last_error = None

        for idx, url in enumerate(candidate_urls):
            try:
                if idx == 0:
                    progress_cb(5.0, "Conectando con el servidor de descargas...")
                else:
                    progress_cb(10.0, "Conectando con el servidor de respaldo de GitHub...")
                logger.debug("Intentando conectar con URL de descarga: %s", url)
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": f"ROS2-Nav-Launcher/{get_local_version()}"}
                )
                resp = urllib.request.urlopen(req, timeout=15.0)
                if resp.status == 200:
                    response = resp
                    active_url = url
                    logger.info("Conexión de descarga exitosa con: %s", url)
                    break
                else:
                    logger.warning("Respuesta HTTP no esperada (%s) desde: %s", resp.status, url)
            except urllib.error.HTTPError as e:
                last_error = e
                logger.warning("Error HTTP %s (%s) al intentar descargar desde '%s'", e.code, e.reason, url)
                if idx + 1 < len(candidate_urls):
                    logger.info("Intentando descarga alternativa usando el archivo zip del repositorio de GitHub...")
                    progress_cb(8.0, "Probando servidor de respaldo de GitHub...")
            except Exception as e:
                last_error = e
                logger.warning("Error de conexión al intentar descargar desde '%s': %s", url, e)
                if idx + 1 < len(candidate_urls):
                    logger.info("Intentando descarga alternativa usando el archivo zip del repositorio de GitHub...")
                    progress_cb(8.0, "Probando servidor de respaldo de GitHub...")

        if not response or not active_url:
            err_msg = f"No se pudo descargar el archivo de actualización: {last_error}"
            logger.error("download_and_extract_update: %s", err_msg)
            return False, err_msg

        with response:
            total_size = int(response.headers.get("Content-Length", 0))
            logger.debug("Tamaño de descarga reportado: %s bytes", total_size)
            downloaded = 0
            block_size = 16384  # 16 KB

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            temp_zip = Path(temp_file.name)
            logger.debug("Guardando temporalmente en '%s'", temp_zip)

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

            logger.debug("Descarga de archivo temporal completada (%s bytes)", downloaded)

        progress_cb(92.0, "Extrayendo archivos y aplicando cambios...")

        # Descomprimir en el directorio de destino
        extracted_files = []
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            namelist = zip_ref.namelist()
            # Detectar si todos los archivos están contenidos en una carpeta raíz común
            # (típico de los archivos zip de GitHub como 'ros2_docker_sim-main/')
            non_empty_items = [m.rstrip('/') for m in namelist if m.strip('/')]
            top_parts = [p.split('/')[0] for p in non_empty_items if '/' in p]
            has_single_root = bool(top_parts and all(p == top_parts[0] for p in [m.split('/')[0] for m in non_empty_items]))
            root_prefix = f"{top_parts[0]}/" if has_single_root else ""
            if has_single_root:
                logger.debug("Prefijo de directorio raíz detectado en el ZIP: '%s'", root_prefix)

            for member in namelist:
                # Omitir directorios
                if member.endswith('/'):
                    continue

                # Quitar el prefijo de carpeta raíz si existe
                rel_path_str = member[len(root_prefix):] if (has_single_root and member.startswith(root_prefix)) else member
                if not rel_path_str:
                    continue

                # Normalizar ruta para evitar path traversal
                rel_path = Path(rel_path_str)
                if rel_path.is_absolute() or ".." in rel_path.parts:
                    logger.warning("Omitiendo ruta insegura en zip: %s", member)
                    continue

                # Omitir archivos ocultos (.git, .gitignore, .github, etc.) y __pycache__
                if any(part.startswith('.') for part in rel_path.parts) or "__pycache__" in rel_path.parts:
                    continue

                filename = rel_path.name
                allowed_extensions = (
                    ".py", ".json", ".ico", ".png", ".jpg", ".jpeg", ".svg",
                    ".md", ".sh", ".bash", ".yaml", ".yml", ".txt"
                )
                if filename.endswith(allowed_extensions) or filename in ("Dockerfile", "docker-compose.yml"):
                    dest_file = target_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    with zip_ref.open(member) as source, open(dest_file, "wb") as target:
                        target.write(source.read())
                    extracted_files.append(str(rel_path))
                    logger.debug("Archivo extraído y actualizado: '%s' -> %s", member, dest_file)

        logger.info("Actualización completada con éxito. Archivos actualizados: %s", extracted_files)
        progress_cb(100.0, "¡Actualización completada!")
        return True, f"Actualizados {len(extracted_files)} archivos correctamente."

    except Exception as e:
        err_msg = f"Error durante la actualización: {str(e)}"
        logger.error("download_and_extract_update error: %s", err_msg, exc_info=True)
        return False, err_msg
    finally:
        if temp_zip and temp_zip.exists():
            try:
                temp_zip.unlink()
                logger.debug("Archivo temporal '%s' eliminado.", temp_zip)
            except Exception:
                pass


def restart_application():
    """Reinicia la aplicación lanzando un nuevo proceso Python y cerrando el actual."""
    python_bin = sys.executable
    script_path = str(Path(sys.argv[0]).resolve())
    app_dir = str(Path(script_path).parent.resolve())
    args = [python_bin, script_path] + sys.argv[1:]
    logger.info("restart_application: Reiniciando con comando: %s (cwd: %s)", ' '.join(args), app_dir)
    
    try:
        subprocess.Popen(args, cwd=app_dir)
    except Exception as e:
        logger.error("restart_application error al relanzar proceso: %s", e, exc_info=True)
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
        self.geometry("560x440")
        self.minsize(480, 380)
        self.resizable(True, True)
        self.configure(bg="#f8fafc")
        self.transient(parent)
        self.grab_set()

        # Configurar icono en la ventana modal si está disponible
        try:
            from embedded_icon import get_app_icon_path
            ico_p = get_app_icon_path()
            if ico_p and ico_p.is_file():
                self.iconbitmap(str(ico_p))
        except Exception:
            pass

        self._build_ui()
        # Centrar en la ventana padre tras construir la interfaz
        self._center_window(parent)

    def _center_window(self, parent):
        self.update_idletasks()
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            if w <= 1:
                w = 560
            if h <= 1:
                h = 440
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _build_ui(self):
        # 1. Cabecera superior
        head_frame = tk.Frame(self, bg="#ffffff", padx=16, pady=12, relief="solid", bd=1)
        head_frame.pack(side=tk.TOP, fill=tk.X)

        badge_frame = tk.Frame(head_frame, bg="#ffffff")
        badge_frame.pack(fill=tk.X)

        lbl_badge = tk.Label(
            badge_frame,
            text=f"✨ Nueva versión: v{self.remote_version}",
            bg="#dcfce7",
            fg="#15803d",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=4
        )
        lbl_badge.pack(side=tk.LEFT)

        lbl_current = tk.Label(
            badge_frame,
            text=f"(Versión instalada: v{CURRENT_VERSION})",
            bg="#ffffff",
            fg="#64748b",
            font=("Segoe UI", 9)
        )
        lbl_current.pack(side=tk.LEFT, padx=10)

        if self.release_date:
            lbl_date = tk.Label(
                badge_frame,
                text=f"Fecha: {self.release_date}",
                bg="#ffffff",
                fg="#94a3b8",
                font=("Segoe UI", 8)
            )
            lbl_date.pack(side=tk.RIGHT)

        # 2. Barra inferior de botones (CRÍTICO: side=tk.BOTTOM ANTES del cuerpo para que NUNCA se recorte)
        btn_frame = tk.Frame(self, bg="#f1f5f9", padx=16, pady=12, relief="solid", bd=1)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Botón de actualizar (Primario - Verde moderno con hover)
        self.btn_update = tk.Button(
            btn_frame,
            text="⬇ Actualizar y Reiniciar",
            bg="#16a34a",
            activebackground="#15803d",
            fg="#ffffff",
            activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._on_start_update
        )
        self.btn_update.pack(side=tk.RIGHT, padx=(10, 0))
        self.btn_update.bind("<Enter>", lambda e: self.btn_update.configure(bg="#15803d") if str(self.btn_update["state"]) != "disabled" else None)
        self.btn_update.bind("<Leave>", lambda e: self.btn_update.configure(bg="#16a34a") if str(self.btn_update["state"]) != "disabled" else None)

        self.btn_later = tk.Button(
            btn_frame,
            text="Recordar más tarde",
            bg="#e2e8f0",
            activebackground="#cbd5e1",
            fg="#334155",
            activeforeground="#1e293b",
            font=("Segoe UI", 9),
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self.destroy
        )
        self.btn_later.pack(side=tk.RIGHT)
        self.btn_later.bind("<Enter>", lambda e: self.btn_later.configure(bg="#cbd5e1") if str(self.btn_later["state"]) != "disabled" else None)
        self.btn_later.bind("<Leave>", lambda e: self.btn_later.configure(bg="#e2e8f0") if str(self.btn_later["state"]) != "disabled" else None)

        # 3. Cuerpo central con Changelog y barra de progreso (EXPANDIBLE)
        body_frame = tk.Frame(self, bg="#f8fafc", padx=16, pady=12)
        body_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        tk.Label(
            body_frame,
            text="Novedades y notas de la versión:",
            bg="#f8fafc",
            fg="#0f172a",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 6))

        # Contenedor para el changelog con scrollbar
        txt_box_frame = tk.Frame(body_frame, bg="#f8fafc")
        txt_box_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        scroll = ttk.Scrollbar(txt_box_frame, orient="vertical")
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        txt_changelog = tk.Text(
            txt_box_frame,
            height=5,
            bg="#ffffff",
            fg="#334155",
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
            wrap=tk.WORD,
            padx=8,
            pady=8,
            yscrollcommand=scroll.set
        )
        scroll.configure(command=txt_changelog.yview)
        txt_changelog.insert(tk.END, self.changelog)
        txt_changelog.configure(state="disabled")
        txt_changelog.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Barra de progreso
        self.prog_bar = ttk.Progressbar(body_frame, orient="horizontal", mode="determinate")
        self.prog_bar.pack(fill=tk.X, pady=(4, 4))

        self.lbl_status = tk.Label(
            body_frame,
            text="¿Deseas descargar e instalar esta actualización ahora?",
            bg="#f8fafc",
            fg="#475569",
            font=("Segoe UI", 9)
        )
        self.lbl_status.pack(anchor="w")

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
        self.btn_update.configure(state="disabled", bg="#94a3b8", cursor="watch", text="⏳ Actualizando...")
        self.btn_later.configure(state="disabled", cursor="arrow")

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
                self.after(0, lambda: self.btn_update.configure(
                    state="normal",
                    bg="#16a34a",
                    cursor="hand2",
                    text="⬇ Reintentar actualización"
                ))
                self.after(0, lambda: self.btn_later.configure(state="normal", cursor="hand2"))

        threading.Thread(target=_worker, daemon=True).start()
