"""
Módulo de actualización automática para el Launcher de Simulación ROS 2.
Compatible con PySide6 (Qt6).
Soporta actualización tanto de binarios congelados (.exe compilado con PyInstaller)
como de código fuente (modo script Python).
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
from pathlib import Path
from typing import Tuple, Optional, Callable, Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets
from embedded_icon import get_themed_icon

# Configurar logger para este módulo
logger = logging.getLogger("updater")

# Repositorio de GitHub por defecto
DEFAULT_GITHUB_REPO = "javmarina/ros2_docker_sim"

# URL de la API de GitHub para obtener version.json en tiempo real (sin la caché de CDN)
DEFAULT_API_VERSION_URL = f"https://api.github.com/repos/{DEFAULT_GITHUB_REPO}/contents/version.json?ref=main"

# URL directa al version.json en la rama principal (raw.githubusercontent.com)
DEFAULT_VERSION_URL = f"https://raw.githubusercontent.com/{DEFAULT_GITHUB_REPO}/main/version.json"

# URL directa al ejecutable de la release más reciente
DEFAULT_EXE_RELEASE_URL = f"https://github.com/{DEFAULT_GITHUB_REPO}/releases/latest/download/ros2_sim_launcher.exe"

# URL de respaldo para descargar el archivo zip de la rama principal
DEFAULT_ARCHIVE_URL = f"https://github.com/{DEFAULT_GITHUB_REPO}/archive/refs/heads/main.zip"


def is_running_frozen() -> bool:
    """Retorna True si la aplicación se ejecuta como un binario empaquetado (PyInstaller .exe)."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_base_dir() -> Path:
    """Obtiene el directorio base de la aplicación (desarrollo o ejecutable)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()


def get_local_version() -> str:
    """Obtiene la versión instalada localmente leyendo version.json o usando '1.0.0' como base."""
    # 1. En binario congelado, buscar primero dentro del bundle PyInstaller
    if is_running_frozen():
        try:
            ver_file = Path(sys._MEIPASS) / "version.json"
            if ver_file.is_file():
                with open(ver_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    ver = data.get("version")
                    if ver:
                        return str(ver).strip()
        except Exception:
            pass

    # 2. Buscar en la carpeta del ejecutable o script
    for candidate_dir in [get_base_dir(), Path(__file__).parent.resolve()]:
        try:
            ver_file = candidate_dir / "version.json"
            if ver_file.is_file():
                with open(ver_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    ver = data.get("version")
                    if ver:
                        return str(ver).strip()
        except Exception:
            pass

    return "1.0.5"


CURRENT_VERSION = get_local_version()


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Convierte una cadena como 'v1.2.3' o '1.2' en una tupla de enteros (1, 2, 3) para comparar."""
    cleaned = v_str.strip().lstrip('v').lstrip('V')
    parts = []
    for chunk in cleaned.split('.'):
        num_str = ''.join(filter(str.isdigit, chunk))
        parts.append(int(num_str) if num_str else 0)
    result = tuple(parts)
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
    Prioriza la API directa de GitHub para evitar la caché CDN de raw.githubusercontent.com.
    """
    logger.info("fetch_remote_version: Consultando versiones remotas (timeout: %ss)...", timeout)

    if "usuario/repo" in version_url or "usuario/repo" in repo:
        msg = "Repositorio de GitHub pendiente de configurar."
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
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    raw_data = response.read().decode("utf-8")
                    data = json.loads(raw_data)
                    return True, data, "Comprobación exitosa."
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
        except json.JSONDecodeError as e:
            last_error = f"JSONDecodeError: {e}"
        except Exception as e:
            last_error = str(e)

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
    logger.info("Iniciando comprobación de actualizaciones (Versión local: v%s)", active_local_ver)
    ok, data, msg = fetch_remote_version(version_url, timeout=timeout)
    if not ok or not data:
        return False, None, msg

    remote_ver = data.get("version", "")
    if is_newer_version(remote_ver, active_local_ver):
        msg = f"Nueva versión v{remote_ver} disponible (actual: v{active_local_ver})."
        return True, data, msg
    else:
        msg = f"Ya tienes la última versión (v{active_local_ver})."
        return False, data, msg


def _download_file(
    urls: list,
    dest_path: Path,
    progress_cb: Callable[[float, str], None],
    desc_label: str = "archivo"
) -> Tuple[bool, str]:
    """Descarga un archivo con barra de progreso intentando varias URLs alternativas."""
    response = None
    active_url = None
    last_error = None

    for idx, url in enumerate(urls):
        try:
            progress_cb(5.0 + idx * 3.0, f"Conectando al servidor ({url.split('/')[2]})...")
            req = urllib.request.Request(
                url,
                headers={"User-Agent": f"ROS2-Nav-Launcher/{get_local_version()}"}
            )
            resp = urllib.request.urlopen(req, timeout=25.0)
            if resp.status == 200:
                response = resp
                active_url = url
                break
        except Exception as e:
            last_error = e
            logger.warning("Error descargando desde '%s': %s", url, e)

    if not response or not active_url:
        return False, f"No se pudo conectar a los servidores de descarga: {last_error}"

    try:
        with response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 65536  # 64 KB

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                while True:
                    chunk = response.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = min(92.0, (downloaded / total_size) * 85.0 + 5.0)
                        progress_cb(pct, f"Descargando {desc_label}... ({downloaded // (1024*1024):.1f} MB / {total_size // (1024*1024):.1f} MB)")
                    else:
                        progress_cb(-1, f"Descargando {desc_label}... ({downloaded // 1024} KB)")

        return True, "Descarga completada."
    except Exception as e:
        return False, f"Error durante la descarga: {e}"


def download_and_apply_exe_update(
    download_url: str,
    progress_cb: Callable[[float, str], None],
    fallback_repo: str = DEFAULT_GITHUB_REPO
) -> Tuple[bool, str]:
    """
    Descarga el nuevo .exe de la versión y programa su sustitución al cerrar.
    """
    current_exe = Path(sys.executable).resolve()
    temp_new_exe = Path(tempfile.gettempdir()) / f"ros2_sim_launcher_{os.getpid()}_new.exe"

    candidate_urls = []
    if download_url and "usuario/repo" not in download_url:
        candidate_urls.append(download_url)
    candidate_urls.append(f"https://github.com/{fallback_repo}/releases/latest/download/ros2_sim_launcher.exe")

    ok, msg = _download_file(candidate_urls, temp_new_exe, progress_cb, desc_label="nueva versión (.exe)")
    if not ok:
        return False, msg

    progress_cb(95.0, "Preparando reinicio con la nueva versión...")

    # En Windows, un ejecutable en ejecución no puede ser sobreescrito directamente.
    # Lanzamos un proceso en segundo plano (PowerShell) que espera a que este proceso termine,
    # reemplaza el ejecutable actual por el descargado con control de reintentos y vuelve a lanzar la app.
    pid = os.getpid()
    
    if platform.system().lower() == "windows":
        updater_ps1 = Path(tempfile.gettempdir()) / f"ros2_updater_{pid}.ps1"
        ps_current_exe = str(current_exe).replace("'", "''")
        ps_temp_new_exe = str(temp_new_exe).replace("'", "''")
        log_file = Path(tempfile.gettempdir()) / "ros2_updater.log"
        ps_log_file = str(log_file).replace("'", "''")

        ps_content = f"""# Script de actualizacion automatica de ROS 2 Sim Launcher
$ErrorActionPreference = 'SilentlyContinue'
$targetExe = '{ps_current_exe}'
$newExe = '{ps_temp_new_exe}'
$targetPid = {pid}
$logFile = '{ps_log_file}'

function Log($msg) {{
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Out-File -Append -FilePath $logFile -Encoding utf8
}}

try {{
    Log "Iniciando actualizacion para PID $targetPid..."
    # 1. Esperar a que el proceso anterior muera completamente (hasta 30 segundos)
    try {{
        Wait-Process -Id $targetPid -Timeout 30 -ErrorAction SilentlyContinue
    }} catch {{}}

    # Espera de seguridad para liberar descriptores de archivo del sistema y antivirus
    Start-Sleep -Milliseconds 1200

    # Desbloquear archivo descargado (quitar Zone.Identifier / Mark-of-the-Web)
    Unblock-File -LiteralPath $newExe -ErrorAction SilentlyContinue

    # 2. Reemplazo del archivo con bucle de reintentos
    $replaced = $false
    for ($i = 0; $i -lt 15; $i++) {{
        try {{
            Copy-Item -LiteralPath $newExe -Destination $targetExe -Force -ErrorAction Stop
            $replaced = $true
            Log "Ejecutable reemplazado exitosamente en el intento $i"
            break
        }} catch {{
            Log "Intento $i fallo al sobrescribir, reintentando..."
            Start-Sleep -Milliseconds 500
        }}
    }}

    # 3. Si se reemplazo correctamente, lanzar la nueva version y limpiar
    if ($replaced -and (Test-Path -LiteralPath $targetExe)) {{
        Unblock-File -LiteralPath $targetExe -ErrorAction SilentlyContinue
        $workDir = Split-Path -Path $targetExe -Parent
        Log "Lanzando nueva version en $workDir : $targetExe"
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $targetExe
        $psi.WorkingDirectory = $workDir
        $psi.UseShellExecute = $true
        [System.Diagnostics.Process]::Start($psi)
        Start-Sleep -Milliseconds 600
        Remove-Item -LiteralPath $newExe -Force -ErrorAction SilentlyContinue
        Log "Actualizacion finalizada con exito."
    }} else {{
        Log "ERROR: No se pudo reemplazar el archivo tras varios intentos."
    }}
}} catch {{
    Log "ERROR CRITICO EN UPDATER: $($_.Exception.Message)"
}}

# Auto-eliminacion del script temporal
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
        try:
            updater_ps1.write_text(ps_content, encoding="utf-8")
            progress_cb(100.0, "¡Actualización lista! Reiniciando launcher...")

            # Buscar ejecutable powershell nativo
            sys_root = os.environ.get("WINDIR", "C:\\Windows")
            ps_native = Path(sys_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            ps_cmd = str(ps_native) if ps_native.is_file() else "powershell.exe"

            creationflags = subprocess.CREATE_NO_WINDOW if platform.system().lower() == "windows" else 0

            subprocess.Popen(
                [
                    ps_cmd,
                    "-ExecutionPolicy", "Bypass",
                    "-WindowStyle", "Hidden",
                    "-NoProfile",
                    "-NonInteractive",
                    "-File", str(updater_ps1)
                ],
                creationflags=creationflags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True
            )
            return True, "Reiniciando..."
        except Exception as e_ps:
            logger.warning("No se pudo iniciar updater con PowerShell (%s), usando fallback .bat...", e_ps)
            updater_bat = Path(tempfile.gettempdir()) / f"ros2_updater_{pid}.bat"
            bat_content = f"""@echo off
set PID={pid}
set NEW_EXE="{temp_new_exe}"
set TARGET_EXE="{current_exe}"

:wait_loop
ping 127.0.0.1 -n 2 > nul
tasklist /fi "PID eq %PID%" 2>nul | findstr /i "%PID%" > nul
if "%ERRORLEVEL%"=="0" goto wait_loop

ping 127.0.0.1 -n 2 > nul
copy /y %NEW_EXE% %TARGET_EXE% > nul
if exist %TARGET_EXE% (
    del /f /q %NEW_EXE% > nul
    start "" %TARGET_EXE%
)
del "%~f0" > nul
"""
            try:
                updater_bat.write_text(bat_content, encoding="utf-8")
                creationflags = subprocess.CREATE_NO_WINDOW if platform.system().lower() == "windows" else 0
                subprocess.Popen(
                    ["cmd.exe", "/c", str(updater_bat)],
                    creationflags=creationflags,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True
                )
                return True, "Reiniciando..."
            except Exception as e_bat:
                logger.error("Error al programar sustitución de ejecutable: %s", e_bat)
                return False, f"No se pudo programar el reinicio: {e_bat}"
    else:
        updater_sh = Path(tempfile.gettempdir()) / f"ros2_updater_{pid}.sh"
        sh_content = f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do
    sleep 0.5
done
sleep 0.5
cp -f "{temp_new_exe}" "{current_exe}"
chmod +x "{current_exe}"
rm -f "{temp_new_exe}"
"{current_exe}" &
rm -f "$0"
"""
        try:
            updater_sh.write_text(sh_content, encoding="utf-8")
            updater_sh.chmod(0o755)
            progress_cb(100.0, "¡Actualización lista! Reiniciando launcher...")
            subprocess.Popen(
                ["/bin/sh", str(updater_sh)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True
            )
            return True, "Reiniciando..."
        except Exception as e:
            logger.error("Error al programar script de actualización Unix: %s", e)
            return False, f"No se pudo programar el reinicio: {e}"


def download_and_extract_zip_update(
    download_url: str,
    target_dir: Path,
    progress_cb: Callable[[float, str], None],
    fallback_repo: str = DEFAULT_GITHUB_REPO
) -> Tuple[bool, str]:
    """
    Modo Script / Desarrollo: Descarga y extrae archivos del repositorio sobrescribiendo los locales.
    """
    temp_zip = Path(tempfile.gettempdir()) / f"ros2_sim_update_{os.getpid()}.zip"
    candidate_urls = []
    if download_url and download_url.endswith(".zip"):
        candidate_urls.append(download_url)
    candidate_urls.append(f"https://github.com/{fallback_repo}/archive/refs/heads/main.zip")

    ok, msg = _download_file(candidate_urls, temp_zip, progress_cb, desc_label="código fuente (.zip)")
    if not ok:
        return False, msg

    try:
        progress_cb(92.0, "Extrayendo archivos y aplicando cambios...")
        extracted_files = []
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            namelist = zip_ref.namelist()
            non_empty_items = [m.rstrip('/') for m in namelist if m.strip('/')]
            top_parts = [p.split('/')[0] for p in non_empty_items if '/' in p]
            has_single_root = bool(top_parts and all(p == top_parts[0] for p in [m.split('/')[0] for m in non_empty_items]))
            root_prefix = f"{top_parts[0]}/" if has_single_root else ""

            for member in namelist:
                if member.endswith('/'):
                    continue

                rel_path_str = member[len(root_prefix):] if (has_single_root and member.startswith(root_prefix)) else member
                if not rel_path_str:
                    continue

                rel_path = Path(rel_path_str)
                if rel_path.is_absolute() or ".." in rel_path.parts:
                    continue
                if any(part.startswith('.') for part in rel_path.parts) or "__pycache__" in rel_path.parts:
                    continue

                filename = rel_path.name
                allowed_extensions = (
                    ".py", ".json", ".ico", ".png", ".jpg", ".jpeg", ".svg",
                    ".md", ".sh", ".bash", ".yaml", ".yml", ".txt", ".spec"
                )
                if filename.endswith(allowed_extensions) or filename in ("Dockerfile", "docker-compose.yml"):
                    dest_file = target_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    with zip_ref.open(member) as source, open(dest_file, "wb") as target:
                        target.write(source.read())
                    extracted_files.append(str(rel_path))

        progress_cb(100.0, "¡Actualización completada!")
        return True, f"Actualizados {len(extracted_files)} archivos correctamente."
    except Exception as e:
        return False, f"Error extrayendo archivos: {e}"
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass


def restart_application():
    """Reinicia la aplicación según si se ejecuta como ejecutable congelado o como script."""
    app = QtWidgets.QApplication.instance()
    if is_running_frozen():
        # Para binarios congelados, el proceso auxiliar en segundo plano se encarga
        # de esperar a que este proceso muera, reemplazar el .exe y relanzarlo.
        # Es fundamental cerrar todas las ventanas y forzar os._exit(0) para liberar
        # el descriptor del archivo ejecutable de inmediato sin bloqueos de hilos o bucle Qt.
        try:
            if app:
                app.closeAllWindows()
                app.quit()
        except Exception:
            pass
        os._exit(0)
    else:
        python_bin = sys.executable
        script_path = str(Path(sys.argv[0]).resolve())
        app_dir = str(Path(script_path).parent.resolve())
        args = [python_bin, script_path] + sys.argv[1:]
        try:
            subprocess.Popen(args, cwd=app_dir)
        except Exception as e:
            logger.error("restart_application error: %s", e)
        try:
            if app:
                app.closeAllWindows()
                app.quit()
        except Exception:
            pass
        os._exit(0)


class UpdateWorkerSignals(QtCore.QObject):
    progress = QtCore.Signal(float, str)
    finished = QtCore.Signal(bool, str)


class UpdateModalDialog(QtWidgets.QDialog):
    """Ventana modal moderna construida con PySide6 para informar y descargar actualizaciones."""

    def __init__(self, parent: Optional[QtWidgets.QWidget], update_info: Dict[str, Any], target_dir: Path):
        super().__init__(parent)
        self.update_info = update_info
        self.target_dir = target_dir
        self.download_url = update_info.get("download_url", "")
        self.remote_version = update_info.get("version", "desconocida")
        self.changelog = update_info.get("changelog", "Mejoras generales y corrección de errores.")
        self.release_date = update_info.get("release_date", "")

        self.setWindowTitle("Actualización disponible - ROS 2 Launcher")
        self.setMinimumSize(560, 420)
        self.resize(580, 440)
        self.setModal(True)

        # Configurar icono nativo
        try:
            from embedded_icon import get_app_icon_path
            ico_p = get_app_icon_path()
            if ico_p and ico_p.is_file():
                self.setWindowIcon(QtGui.QIcon(str(ico_p)))
        except Exception:
            pass

        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # 1. Cabecera con Badge de Versión
        header_card = QtWidgets.QFrame()
        header_card.setObjectName("headerCard")
        head_layout = QtWidgets.QHBoxLayout(header_card)
        head_layout.setContentsMargins(14, 12, 14, 12)

        badge_lbl = QtWidgets.QLabel(f"Nueva versión disponible: v{self.remote_version}")
        badge_lbl.setObjectName("badgeLabel")
        head_layout.addWidget(badge_lbl)

        curr_lbl = QtWidgets.QLabel(f"(Instalada: v{CURRENT_VERSION})")
        curr_lbl.setObjectName("currentLabel")
        head_layout.addWidget(curr_lbl)

        head_layout.addStretch()

        if self.release_date:
            date_lbl = QtWidgets.QLabel(f"Fecha: {self.release_date}")
            date_lbl.setObjectName("dateLabel")
            head_layout.addWidget(date_lbl)

        main_layout.addWidget(header_card)

        # 2. Notas de la versión (Changelog)
        lbl_notes = QtWidgets.QLabel("Novedades y notas de la versión:")
        lbl_notes.setObjectName("lblNotes")
        main_layout.addWidget(lbl_notes)

        self.txt_changelog = QtWidgets.QTextBrowser()
        self.txt_changelog.setObjectName("changelogBox")
        self.txt_changelog.setPlainText(self.changelog)
        main_layout.addWidget(self.txt_changelog, 1)

        # 3. Barra de progreso y estado
        self.prog_bar = QtWidgets.QProgressBar()
        self.prog_bar.setObjectName("progressBar")
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setTextVisible(True)
        main_layout.addWidget(self.prog_bar)

        self.lbl_status = QtWidgets.QLabel("¿Deseas descargar e instalar esta actualización ahora?")
        self.lbl_status.setObjectName("statusLabel")
        main_layout.addWidget(self.lbl_status)

        # 4. Fila de botones de acción
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_later = QtWidgets.QPushButton("Recordar más tarde")
        self.btn_later.setObjectName("btnLater")
        self.btn_later.setIconSize(QtCore.QSize(18, 18))
        self.btn_later.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_later)

        self.btn_update = QtWidgets.QPushButton("Actualizar y reiniciar")
        self.btn_update.setObjectName("btnUpdate")
        self.btn_update.setIcon(get_themed_icon("system-software-update", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_ArrowDown))
        self.btn_update.setIconSize(QtCore.QSize(18, 18))
        self.btn_update.clicked.connect(self._start_update)
        btn_layout.addWidget(self.btn_update)

        main_layout.addLayout(btn_layout)

    def _apply_styles(self):
        app = QtWidgets.QApplication.instance()
        is_dark = False
        if app:
            hints = app.styleHints()
            if hasattr(hints, "colorScheme"):
                is_dark = (hints.colorScheme() == QtCore.Qt.ColorScheme.Dark)

        if sys.platform == "win32":
            try:
                import ctypes
                val = ctypes.c_int(1 if is_dark else 0)
                res = ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(val), ctypes.sizeof(val))
                if res != 0:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 19, ctypes.byref(val), ctypes.sizeof(val))
            except Exception:
                pass

        btn_later_icon_col = "#cbd5e1" if is_dark else "#475569"
        self.btn_later.setIcon(get_themed_icon("window-close", color=btn_later_icon_col))

        if is_dark:
            self.setStyleSheet("""
                QDialog {
                    background-color: #0f172a;
                    font-family: 'Segoe UI', system-ui, sans-serif;
                }
                #headerCard {
                    background-color: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                }
                #badgeLabel {
                    background-color: rgba(34, 197, 94, 0.2);
                    color: #4ade80;
                    font-weight: 700;
                    font-size: 13px;
                    padding: 4px 10px;
                    border-radius: 6px;
                }
                #currentLabel {
                    color: #cbd5e1;
                    font-size: 12px;
                    margin-left: 6px;
                }
                #dateLabel {
                    color: #94a3b8;
                    font-size: 11px;
                }
                #lblNotes {
                    font-size: 13px;
                    font-weight: 600;
                    color: #f8fafc;
                }
                #changelogBox {
                    background-color: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 10px;
                    color: #f8fafc;
                    font-size: 12px;
                    line-height: 1.4;
                }
                #progressBar {
                    border: 1px solid #334155;
                    border-radius: 6px;
                    text-align: center;
                    background-color: #0f172a;
                    height: 20px;
                    font-size: 11px;
                    font-weight: 600;
                    color: #f8fafc;
                }
                #progressBar::chunk {
                    background-color: #16a34a;
                    border-radius: 5px;
                }
                #statusLabel {
                    color: #cbd5e1;
                    font-size: 12px;
                }
                #btnLater {
                    background-color: #334155;
                    color: #f8fafc;
                    border: 1px solid #475569;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: 600;
                }
                #btnLater:hover {
                    background-color: #475569;
                }
                #btnUpdate {
                    background-color: #16a34a;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 18px;
                    font-size: 12px;
                    font-weight: 700;
                }
                #btnUpdate:hover {
                    background-color: #15803d;
                }
                #btnUpdate:disabled {
                    background-color: #94a3b8;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f8fafc;
                    font-family: 'Segoe UI', system-ui, sans-serif;
                }
                #headerCard {
                    background-color: #ffffff;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                }
                #badgeLabel {
                    background-color: #dcfce7;
                    color: #15803d;
                    font-weight: 700;
                    font-size: 13px;
                    padding: 4px 10px;
                    border-radius: 6px;
                }
                #currentLabel {
                    color: #64748b;
                    font-size: 12px;
                    margin-left: 6px;
                }
                #dateLabel {
                    color: #94a3b8;
                    font-size: 11px;
                }
                #lblNotes {
                    font-size: 13px;
                    font-weight: 600;
                    color: #0f172a;
                }
                #changelogBox {
                    background-color: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 10px;
                    color: #334155;
                    font-size: 12px;
                    line-height: 1.4;
                }
                #progressBar {
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    text-align: center;
                    background-color: #ffffff;
                    height: 20px;
                    font-size: 11px;
                    font-weight: 600;
                    color: #0f172a;
                }
                #progressBar::chunk {
                    background-color: #16a34a;
                    border-radius: 5px;
                }
                #statusLabel {
                    color: #475569;
                    font-size: 12px;
                }
                #btnLater {
                    background-color: #e2e8f0;
                    color: #334155;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: 600;
                }
                #btnLater:hover {
                    background-color: #cbd5e1;
                    color: #0f172a;
                }
                #btnUpdate {
                    background-color: #16a34a;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 18px;
                    font-size: 12px;
                    font-weight: 700;
                }
                #btnUpdate:hover {
                    background-color: #15803d;
                }
                #btnUpdate:disabled {
                    background-color: #94a3b8;
                }
            """)

    def _on_progress(self, pct: float, status_text: str):
        if pct < 0:
            self.prog_bar.setRange(0, 0)
        else:
            self.prog_bar.setRange(0, 100)
            self.prog_bar.setValue(int(pct))
        self.lbl_status.setText(status_text)

    def _on_finished(self, success: bool, msg: str):
        if success:
            self.prog_bar.setValue(100)
            self.lbl_status.setText("¡Actualización completada! Reiniciando launcher...")
            QtCore.QTimer.singleShot(1200, restart_application)
        else:
            self.btn_update.setEnabled(True)
            self.btn_update.setText("Reintentar actualización")
            self.btn_update.setIcon(get_themed_icon("view-refresh", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload))
            self.btn_later.setEnabled(True)
            QtWidgets.QMessageBox.critical(
                self,
                "Error de actualización",
                f"No se pudo completar la actualización:\n\n{msg}"
            )

    def _start_update(self):
        self.btn_update.setEnabled(False)
        self.btn_update.setText("Actualizando...")
        self.btn_update.setIcon(get_themed_icon("view-refresh", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload))
        self.btn_later.setEnabled(False)

        signals = UpdateWorkerSignals()
        signals.progress.connect(self._on_progress)
        signals.finished.connect(self._on_finished)

        def _worker():
            if is_running_frozen():
                # En modo .exe congelado, descargar el nuevo ejecutable
                ok, msg = download_and_apply_exe_update(
                    self.download_url,
                    lambda pct, txt: signals.progress.emit(pct, txt)
                )
            else:
                # En modo script, extraer archivos al directorio de destino
                ok, msg = download_and_extract_zip_update(
                    self.download_url,
                    self.target_dir,
                    lambda pct, txt: signals.progress.emit(pct, txt)
                )
            signals.finished.emit(ok, msg)

        threading.Thread(target=_worker, daemon=True).start()
