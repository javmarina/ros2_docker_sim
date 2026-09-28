"""
Launcher de Simulación ROS 2 Jazzy para la Asignatura de Robótica Móvil
Interfaz gráfica moderna, nativa de alta resolución (High-DPI) y modular con PySide6 y Docker.
"""

import os
import shutil
import re
import sys
import logging
import platform
import datetime
import time
import traceback
import urllib.parse
import webbrowser
import subprocess
import threading
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

# --- Configuración del módulo logging estándar ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("launcher")

# --- Habilitar AppUserModelID en Windows para icono en barra de tareas ---
if sys.platform == "win32":
    try:
        import ctypes
        app_id = "lasalle.sistemasdenavegacion.ros2launcher.v107"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

# Módulos del proyecto
from config_store import ConfigStore
from robot_registry import (
    get_all_robots,
    get_robot_by_id,
    get_robot_by_name,
    RobotProfile,
    Scenario
)
from docker_service import (
    DockerService,
    DockerState,
    COURSE_IMAGE_NAME,
    DEFAULT_CONTAINER_NAME,
    DEFAULT_NOVNC_PORT
)
from updater import (
    CURRENT_VERSION,
    check_for_updates,
    UpdateModalDialog,
    DEFAULT_GITHUB_REPO
)
from embedded_icon import get_app_icon_path, get_dropdown_arrow_path, get_themed_icon


def set_window_dark_mode(hwnd: int, dark: bool):
    """Activa o desactiva la barra de título oscura inmersiva de Windows 10/11 vía DWM."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        val = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 en Windows 11 / Win10 20H1+, 19 en builds anteriores
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        if res != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))
    except Exception as e:
        logger.debug("No se pudo configurar DWM immersive dark mode: %s", e)


def is_dark_mode() -> bool:
    """Determina si el sistema operativo está actualmente en Modo Oscuro."""
    app = QtWidgets.QApplication.instance()
    if app:
        hints = app.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == QtCore.Qt.ColorScheme.Dark
    return False


THEME_PALETTES = {
    "light": {
        "bg_window": "#f8fafc",
        "bg_header": "#ffffff",
        "bg_card": "#ffffff",
        "bg_input": "#ffffff",
        "bg_button": "#f1f5f9",
        "bg_button_hover": "#e2e8f0",
        "bg_button_pressed": "#cbd5e1",
        "border": "#e2e8f0",
        "border_input": "#cbd5e1",
        "border_input_hover": "#94a3b8",
        "border_focus": "#2563eb",
        "text_primary": "#0f172a",
        "text_secondary": "#475569",
        "text_muted": "#64748b",
        "text_title": "#1e3a8a",
        "icon_color": "#1e293b",
        "tab_icon_normal": "#475569",
        "tab_icon_selected": "#ffffff",
        "card_desc_bg": "#f8fafc",
        "card_desc_border": "#e2e8f0",
        "tab_bg": "#f1f5f9",
        "tab_text": "#475569",
        "tab_hover": "#e2e8f0",
        "tab_hover_text": "#0f172a",
        "dropdown_bg": "#f8fafc",
        "dropdown_hover": "#e2e8f0",
        "progress_bg": "#ffffff",
        "logs_border": "#cbd5e1",
        "btn_terminal_bg": "#0f172a",
        "btn_terminal_border": "transparent",
        "btn_terminal_hover": "#1e293b",
    },
    "dark": {
        "bg_window": "#0f172a",
        "bg_header": "#1e293b",
        "bg_card": "#1e293b",
        "bg_input": "#0f172a",
        "bg_button": "#334155",
        "bg_button_hover": "#475569",
        "bg_button_pressed": "#1e293b",
        "border": "#334155",
        "border_input": "#475569",
        "border_input_hover": "#64748b",
        "border_focus": "#3b82f6",
        "text_primary": "#f8fafc",
        "text_secondary": "#cbd5e1",
        "text_muted": "#94a3b8",
        "text_title": "#60a5fa",
        "icon_color": "#e2e8f0",
        "tab_icon_normal": "#94a3b8",
        "tab_icon_selected": "#ffffff",
        "card_desc_bg": "#0f172a",
        "card_desc_border": "#334155",
        "tab_bg": "#0f172a",
        "tab_text": "#94a3b8",
        "tab_hover": "#334155",
        "tab_hover_text": "#f8fafc",
        "dropdown_bg": "#0f172a",
        "dropdown_hover": "#334155",
        "progress_bg": "#0f172a",
        "logs_border": "#334155",
        "btn_terminal_bg": "#1e293b",
        "btn_terminal_border": "#475569",
        "btn_terminal_hover": "#334155",
    }
}


# Dockerfile de respaldo en caso de que no exista en el directorio
DOCKERFILE_CONTENT = r"""# Dockerfile for University Course on Navigation and ROS 2 Jazzy
FROM osrf/ros:jazzy-desktop-full

ENV DEBIAN_FRONTEND=noninteractive
ENV RCUTILS_COLORIZED_OUTPUT=1

# Install Navigation2, SLAM Toolbox, TurtleBot4 dependencies, and Gazebo (ros_gz)
RUN echo "=== [1/3] Actualizando repositorios APT ===" && \
    apt-get update && \
    echo "=== [2/3] Instalando dependencias de ROS 2 y utilidades del sistema ===" && \
    apt-get install -y --no-install-recommends \
        --verbose-versions \
        -o Dpkg::Use-Pty=0 \
        ros-jazzy-navigation2 \
        ros-jazzy-nav2-bringup \
        ros-jazzy-slam-toolbox \
        ros-jazzy-robot-localization \
        ros-jazzy-turtlebot4-simulator \
        ros-jazzy-turtlebot4-gz-bringup \
        ros-jazzy-turtlebot4-gz-gui-plugins \
        ros-jazzy-turtlebot4-gz-toolbox \
        ros-jazzy-turtlebot4-navigation \
        ros-jazzy-turtlebot4-description \
        ros-jazzy-turtlebot4-viz \
        ros-jazzy-irobot-create-nodes \
        ros-jazzy-ros-gz \
        ros-jazzy-ros-gz-bridge \
        ros-jazzy-ros-gz-sim \
        ros-jazzy-ros-gz-interfaces \
        ros-jazzy-teleop-twist-keyboard \
        ros-jazzy-joint-state-publisher-gui \
        ros-jazzy-xacro \
        ros-jazzy-twist-mux \
        ros-jazzy-controller-manager \
        ros-jazzy-ros2-control \
        ros-jazzy-ros2-controllers \
        python3-colcon-common-extensions \
        python3-rosdep \
        x11-apps \
        mesa-utils \
        libgl1 \
        libglx-mesa0 \
        libgl1-mesa-dri \
        novnc \
        websockify \
        xvfb \
        x11vnc \
        openbox \
        nano \
        gedit \
        git \
        wget \
        curl \
        net-tools \
    && echo "=== [3/3] Limpiando cache de APT ===" \
    && rm -rf /var/lib/apt/lists/*

ENV ROBOT_MODEL=turtlebot4

# Pre-descarga de modelos 3D de Gazebo Fuel para mundos de simulacion (Warehouse, Depot)
RUN /bin/bash -c "source /opt/ros/jazzy/setup.bash && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Warehouse' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Depot' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/MovAi/models/pallet_box_mobile' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/MovAi/models/shelf' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/MovAi/models/shelf_big' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Chair' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/CoffeeTable' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/FemaleVisitorSit' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Jersey Barrier' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/MaleVisitorOnPhone' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/foldable_chair' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/plateau/models/Casual female' || true"

EXPOSE 6080
WORKDIR /ros2_ws

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc \
    && echo "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi" >> /root/.bashrc

CMD ["/bin/bash"]
"""

def ensure_dockerfile_sync(workspace_dir: Path) -> Path:
    """
    Garantiza que el Dockerfile en disco esté exactamente sincronizado con DOCKERFILE_CONTENT.
    Si existe 'Dockerfile' en la raíz del workspace (modo desarrollo/git), lo actualiza si difiere.
    Si no existe (modo ejecutable empaquetado), lo crea dentro de '.docker_build/Dockerfile'.
    Inserta la etiqueta LABEL con el hash calculado antes de CMD para persistencia nativa en la imagen.
    Devuelve la ruta al directorio de construcción (build_dir).
    """
    dockerfile_root = workspace_dir / "Dockerfile"
    if dockerfile_root.exists():
        build_dir = workspace_dir
        target_file = dockerfile_root
    else:
        build_dir = workspace_dir / ".docker_build"
        build_dir.mkdir(parents=True, exist_ok=True)
        target_file = build_dir / "Dockerfile"

    content_hash = DockerService.compute_dockerfile_hash(DOCKERFILE_CONTENT)
    effective_content = DOCKERFILE_CONTENT
    label_line = f'LABEL {DockerService.DOCKERFILE_HASH_LABEL}="{content_hash}"'
    if label_line not in effective_content:
        cmd_marker = 'CMD ["/bin/bash"]'
        if cmd_marker in effective_content:
            effective_content = effective_content.replace(cmd_marker, f'{label_line}\n\n{cmd_marker}')
        else:
            effective_content += f'\n{label_line}\n'

    try:
        current_content = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        if current_content.strip() != effective_content.strip():
            target_file.write_text(effective_content, encoding="utf-8")
    except Exception as e:
        logger.warning("No se pudo sincronizar Dockerfile en %s: %s", target_file, e)

    return build_dir

GUIDE_MARKDOWN = """# Guía de Simulación y Navegación ROS 2 Jazzy

Este entorno ejecuta **ROS 2 Jazzy**, **Gazebo Sim** y **Navigation2 (Nav2)** dentro de un contenedor Docker con interfaz gráfica accesible directamente desde el navegador web (noVNC).

---

### 1. Interfaz Gráfica Web (Gazebo y RViz2)
- No necesitas instalar servidores X11 (XQuartz o VcXsrv) en tu ordenador.
- Al iniciar la simulación, el navegador se abrirá automáticamente en:
  **`http://localhost:6080/vnc.html`**
- En esa pestaña interactuarás con el escritorio virtual con Gazebo Sim y RViz2.

---

### 2. Terminal Docker Nativo (Windows Terminal / PowerShell)
- Pulsa el botón **"Abrir Terminal Docker"** en la barra de acciones superior.
- Se abrirá automáticamente una ventana de terminal conectada al contenedor.
- El entorno de ROS 2 ya está cargado con los paquetes del sistema y tu workspace:
  - `ros2 topic list`
  - `ros2 run teleop_twist_keyboard teleop_twist_keyboard`
  - `ros2 topic echo /odom`

---

### 3. Espacio de Trabajo (Workspace en Windows)
- La carpeta seleccionada en "Espacio de Trabajo" se monta automáticamente en:
  **`/ros2_ws/src`**
- Puedes editar tus paquetes y nodos de ROS 2 en Windows usando tu editor preferido (VS Code, etc.).
- Cualquier cambio en Windows se sincroniza instantáneamente con Docker.
- Para compilar tus paquetes, pulsa **"Compilar Workspace"** o escribe `colcon build` en la terminal. Para limpiar una compilación anterior y reconstruir desde cero, pulsa **"Limpiar compilación"** en la pestaña de Comandos rápidos.

---

### 4. Modo Solo Contenedor (Modo Libre / Sin Simulación)
- Si deseas desarrollar, compilar o ejecutar tus propios launch files y nodos sin la sobrecarga de una simulación completa de Gazebo o Nav2:
  - Selecciona el escenario: **"Solo contenedor (sin procesos / modo libre)"**.
  - Pulsa el botón **"Iniciar contenedor"**.
  - El contenedor arrancará con el workspace montado en `/ros2_ws/src` y abrirá automáticamente una terminal interactiva nativa.
  - El servidor gráfico noVNC permanece disponible en segundo plano: si ejecutas `rviz2` o cualquier herramienta GUI desde la consola, podrás interactuar con ella pulsando **"Interfaz web (noVNC)"**.

---

### 5. Guía Rápida de Prácticas

#### A. Mapeo con SLAM Toolbox
1. Selecciona el escenario: **"Gazebo Sim + SLAM Toolbox (Modo mapeo)"**.
2. Pulsa **"Iniciar Simulación"**.
3. Abre una terminal con **"Abrir Terminal Docker"** y pilota el robot:
   `ros2 run teleop_twist_keyboard teleop_twist_keyboard`
4. Una vez completado el mapa, guárdalo desde el plugin de SLAM en RViz2 o desde la terminal.

#### B. Navegación Autónoma con Nav2
1. Selecciona el escenario: **"Gazebo Sim + Nav2 (Navegación completa y RViz2)"**.
2. Pulsa **"Iniciar Simulación"**.
3. En RViz2, fija la posición inicial estimada con la herramienta **"2D Pose Estimate"**.
4. Envía metas de navegación pulsando **"Nav2 Goal"** en el mapa.
"""



# --- Señales y Hilos de Soporte Qt ---

class ProcessRunnerSignals(QtCore.QObject):
    line_received = QtCore.Signal(str)
    progress_changed = QtCore.Signal(float, str)
    finished = QtCore.Signal(int)
    error = QtCore.Signal(str)


class ProcessRunnerThread(QtCore.QThread):
    def __init__(self, cmd: List[str], cwd: Optional[str] = None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.signals = ProcessRunnerSignals()
        self.proc: Optional[subprocess.Popen] = None

    def run(self):
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.proc = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True,
                creationflags=creationflags
            )
            for line in iter(self.proc.stdout.readline, ''):
                self.signals.line_received.emit(line)
            self.proc.stdout.close()
            rc = self.proc.wait()
            self.signals.finished.emit(rc)
        except Exception as e:
            self.signals.error.emit(str(e))

    def terminate_process(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass


# --- Parser de Códigos de Escape ANSI para QTextEdit ---

class AnsiColorParser:
    ANSI_MAP = {
        30: QtGui.QColor("#4f5666"), 31: QtGui.QColor("#e06c75"), 32: QtGui.QColor("#98c379"),
        33: QtGui.QColor("#e5c07b"), 34: QtGui.QColor("#61afef"), 35: QtGui.QColor("#c678dd"),
        36: QtGui.QColor("#56b6c2"), 37: QtGui.QColor("#abb2bf"),
        90: QtGui.QColor("#5c6370"), 91: QtGui.QColor("#ff6c6b"), 92: QtGui.QColor("#98be65"),
        93: QtGui.QColor("#da8548"), 94: QtGui.QColor("#51afef"), 95: QtGui.QColor("#a9a1e1"),
        96: QtGui.QColor("#46d9ff"), 97: QtGui.QColor("#ffffff"),
    }
    REGEX = re.compile(r'(\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\))')

    def __init__(self, default_color: QtGui.QColor = QtGui.QColor("#e4e4e7")):
        self.default_color = default_color
        self.current_format = QtGui.QTextCharFormat()
        self.current_format.setForeground(self.default_color)

    def parse_to_cursor(self, text: str, cursor: QtGui.QTextCursor):
        tokens = self.REGEX.split(text)
        for token in tokens:
            if not token:
                continue
            if token.startswith('\x1b['):
                if token.endswith('m'):
                    params_str = token[2:-1]
                    params = [int(p) for p in params_str.split(';') if p] if params_str else [0]
                    for code in params:
                        if code == 0:
                            self.current_format = QtGui.QTextCharFormat()
                            self.current_format.setForeground(self.default_color)
                        elif code == 1:
                            self.current_format.setFontWeight(QtGui.QFont.Weight.Bold)
                        elif code == 4:
                            self.current_format.setFontUnderline(True)
                        elif code in self.ANSI_MAP:
                            self.current_format.setForeground(self.ANSI_MAP[code])
                        elif code == 39:
                            self.current_format.setForeground(self.default_color)
            elif token.startswith('\x1b'):
                pass
            else:
                clean_text = token.replace('\x07', '')
                if clean_text:
                    cursor.insertText(clean_text, self.current_format)



# --- Utilidades de Red y Detección del Robot TurtleBot 4 ---

DEFAULT_TURTLEBOT4_MAC = "e4:5f:01:bd:05:1a"

def get_connected_ssid() -> Optional[str]:
    """
    Retorna el SSID de la red Wi-Fi actualmente conectada, o None si no está conectado o no disponible.
    Soporta Windows (netsh wlan / Get-NetConnectionProfile), Linux (iwgetid / nmcli) y macOS (airport).
    """
    try:
        if sys.platform == "win32":
            # 1. Intento ultrarrápido con netsh wlan show interfaces
            try:
                flags = subprocess.CREATE_NO_WINDOW
                out = subprocess.check_output(
                    ["netsh", "wlan", "show", "interfaces"],
                    text=True, stderr=subprocess.DEVNULL,
                    creationflags=flags
                )
                for line in out.splitlines():
                    if "SSID" in line and "BSSID" not in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            ssid = parts[1].strip()
                            if ssid:
                                return ssid
            except Exception:
                pass

            # 2. Fallback a PowerShell Get-NetConnectionProfile
            try:
                flags = subprocess.CREATE_NO_WINDOW
                output = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", "Get-NetConnectionProfile"],
                    text=True, stderr=subprocess.DEVNULL,
                    creationflags=flags
                )
                for line in output.splitlines():
                    if ":" in line:
                        key, _, value = line.partition(":")
                        if key.strip().lower() == "name":
                            name = value.strip()
                            if name:
                                return name
            except Exception:
                pass
        elif sys.platform == "darwin":
            cmd = ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"]
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if "SSID:" in line and "BSSID" not in line:
                    return line.split(":", 1)[1].strip()
        else:
            for cmd in [["iwgetid", "-r"], ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"]]:
                try:
                    out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
                    lines = [l.strip() for l in out.splitlines() if l.strip()]
                    if lines:
                        if cmd[0] == "nmcli":
                            for l in lines:
                                if l.startswith("yes:"):
                                    return l.split(":", 1)[1]
                        else:
                            return lines[0]
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Error al consultar SSID Wi-Fi: %s", e)
    return None


def get_local_ip() -> str:
    """Determina la IP local de la interfaz de red activa."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def get_ip_from_mac(target_mac: str) -> Optional[str]:
    """
    Escanea la tabla ARP local para encontrar la IP asociada a una dirección MAC específica.
    Lógica adaptada de proxy.py.
    """
    target_mac = target_mac.lower().replace("-", ":").strip()
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        output = subprocess.check_output(["arp", "-a"], text=True, stderr=subprocess.DEVNULL, creationflags=flags)
        for line in output.splitlines():
            clean_line = line.lower().replace("-", ":")
            if target_mac in clean_line:
                match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
                if match:
                    return match.group(1)
    except Exception as e:
        logger.debug("Error al escanear tabla ARP: %s", e)
    return None


def ping_device(ip_address: str, timeout: float = 1.0) -> bool:
    """Comprueba mediante ping si un host es alcanzable en la red."""
    if not ip_address:
        return False
    try:
        param = "-n" if sys.platform == "win32" else "-c"
        w_param = "-w" if sys.platform == "win32" else "-W"
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        ms = str(int(timeout * 1000)) if sys.platform == "win32" else str(max(1, int(timeout)))
        subprocess.check_output(
            ["ping", param, "1", w_param, ms, ip_address],
            stderr=subprocess.DEVNULL,
            creationflags=flags
        )
        return True
    except Exception:
        return False


def subnet_sweep(local_ip: str, timeout: float = 0.35) -> None:
    """
    Realiza un barrido ICMP rápido sobre toda la subred local /24 para poblar la tabla ARP.
    Lógica adaptada de proxy.py.
    """
    try:
        parts = local_ip.split(".")
        if len(parts) != 4:
            return
        subnet_prefix = ".".join(parts[:-1])
        own_last = int(parts[-1])
        ips = [f"{subnet_prefix}.{i}" for i in range(1, 255) if i != own_last]

        param = "-n" if sys.platform == "win32" else "-c"
        w_param = "-w" if sys.platform == "win32" else "-W"
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        ms = str(int(timeout * 1000)) if sys.platform == "win32" else str(max(1, int(timeout)))

        def _ping(ip: str):
            try:
                subprocess.run(
                    ["ping", param, "1", w_param, ms, ip],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=flags
                )
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=32) as executor:
            list(executor.map(_ping, ips))
    except Exception as e:
        logger.debug("Error en subnet_sweep: %s", e)


def sftp_upload_dir(sftp, local_dir: Path, remote_dir: str, log_cb=None) -> int:
    """
    Sube recursivamente un directorio local a un directorio remoto vía SFTP.
    Omite artefactos de compilación, carpetas de control de versiones y temporales.
    """
    ignore_dirs = {".git", ".svn", "build", "install", "log", "__pycache__", ".vscode", ".idea", ".DS_Store"}

    def _remote_mkdir_p(path: str):
        clean = path.replace("\\", "/")
        parts = clean.strip("/").split("/")
        cur = "/" if clean.startswith("/") else ""
        for p in parts:
            cur = f"{cur.rstrip('/')}/{p}"
            try:
                sftp.stat(cur)
            except IOError:
                try:
                    sftp.mkdir(cur)
                except IOError:
                    pass

    _remote_mkdir_p(remote_dir)
    file_count = 0
    local_p = Path(local_dir).resolve()

    for root, dirs, files in os.walk(local_p):
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
        rel = os.path.relpath(root, local_p).replace("\\", "/")
        dest_sub = remote_dir if rel == "." else f"{remote_dir}/{rel}"
        _remote_mkdir_p(dest_sub)

        for f in files:
            if f.endswith((".pyc", ".swp", "~")) or f in ignore_dirs:
                continue
            src_file = os.path.join(root, f)
            dest_file = f"{dest_sub}/{f}"
            if log_cb:
                disp = f if rel == "." else f"{rel}/{f}"
                log_cb(f"  -> [SCP] {disp}\n")
            sftp.put(src_file, dest_file)
            file_count += 1

    return file_count


# --- Ventana Principal del Launcher ---

class ModernSimulationLauncher(QtWidgets.QMainWindow):
    """Ventana principal del launcher con PySide6, High-DPI y estilo profesional moderno."""

    sig_manual_update_result = QtCore.Signal(bool, object, str)
    sig_docker_status = QtCore.Signal(bool, bool, str)  # (installed, running, daemon_msg)
    sig_docker_state_changed = QtCore.Signal(object)  # (DockerState)
    sig_docker_ready = QtCore.Signal()
    sig_docker_failed = QtCore.Signal(str)
    sig_docker_poll_progress = QtCore.Signal(int, int)  # (elapsed_seconds, max_seconds)
    sig_container_status = QtCore.Signal(bool)  # (is_running)
    sig_log_received = QtCore.Signal(str)
    sig_robot_scan_finished = QtCore.Signal(bool, str, bool, str, str)  # (wifi_ok, ssid, robot_found, robot_ip, msg)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ROS 2 Jazzy - Launcher de simulación (v{CURRENT_VERSION}) | Sistemas de Navegación")
        self.resize(1020, 680)
        self.setMinimumSize(880, 520)

        # Gestor de configuración persistente (guarda en AppData)
        self.config_store = ConfigStore(fallback_dir=Path(__file__).parent.resolve())
        self.active_sim_thread: Optional[ProcessRunnerThread] = None
        self.active_cmd_thread: Optional[ProcessRunnerThread] = None
        self.compile_runner: Optional[ProcessRunnerThread] = None
        self.autoscroll_enabled = True
        self.ansi_parser = AnsiColorParser()
        self.latest_update_info: Optional[Dict] = None

        # Control de estado de Docker Desktop con Enum de tres estados (NOT_RUNNING, STARTING, RUNNING)
        self._docker_state: DockerState = DockerState.NOT_RUNNING
        self._docker_poll_timer: Optional[QtCore.QTimer] = None
        self._docker_poll_count = 0
        self._is_loading_preferences = True

        # Control de estado del contenedor y ciclo de vida de la simulación
        self._is_container_running: bool = False
        self._is_launching_sim: bool = False
        self._is_stopping_sim: bool = False
        self._is_checking_container: bool = False
        self._container_poll_timer: Optional[QtCore.QTimer] = None

        # Control de estado del robot TurtleBot 4
        self._last_robot_scan_data: Optional[Tuple[bool, str, bool, str, str]] = None
        self._is_scanning_robot: bool = False
        self._has_checked_robot_once: bool = False

        # Conexiones de señales Qt entre hilos
        self.sig_manual_update_result.connect(self._on_manual_update_result)
        self.sig_docker_status.connect(self._apply_docker_status)
        self.sig_docker_ready.connect(self._on_docker_ready)
        self.sig_docker_failed.connect(self._on_docker_start_failed)
        self.sig_docker_poll_progress.connect(self._on_docker_poll_progress)
        self.sig_container_status.connect(self._on_container_status_changed)
        self.sig_log_received.connect(self._append_log_main_thread)
        self.sig_robot_scan_finished.connect(self._on_robot_scan_finished)

        self._is_dark = self.is_dark_mode()
        self._setup_window_icon()
        self._build_ui()
        self._apply_theme(self._is_dark)
        self._load_saved_preferences()
        self._update_action_buttons_state()
        self._start_container_poll_timer()
        self._check_docker_live_status()

        # Escuchar cambios de tema en Windows en tiempo real
        hints = QtWidgets.QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_color_scheme_changed)

        # Comprobar actualizaciones en segundo plano o forzadas al arrancar
        if "--force-update" in sys.argv:
            QtCore.QTimer.singleShot(1000, lambda: self._on_manual_check_updates(force=True))
        else:
            QtCore.QTimer.singleShot(1500, self._check_for_updates_background)

    @property
    def docker_state(self) -> DockerState:
        """Devuelve el estado actual de Docker (DockerState enum)."""
        return self._docker_state

    def _set_docker_state(self, new_state: DockerState):
        """Actualiza el estado de Docker y emite la señal de cambio de estado."""
        if self._docker_state != new_state:
            self._docker_state = new_state
            self.sig_docker_state_changed.emit(new_state)
            self._update_action_buttons_state()

    @property
    def _docker_running(self) -> bool:
        return self._docker_state == DockerState.RUNNING

    @property
    def _is_starting_docker(self) -> bool:
        return self._docker_state == DockerState.STARTING

    def _setup_window_icon(self):
        try:
            ico_path = get_app_icon_path()
            if ico_path and ico_path.is_file():
                app_icon = QtGui.QIcon(str(ico_path))
                self.setWindowIcon(app_icon)
                QtWidgets.QApplication.setWindowIcon(app_icon)
        except Exception as e:
            logger.warning("No se pudo configurar el icono de la ventana: %s", e)

    def is_dark_mode(self) -> bool:
        """Determina si el sistema operativo está actualmente en Modo Oscuro."""
        return is_dark_mode()

    @QtCore.Slot(QtCore.Qt.ColorScheme)
    def _on_color_scheme_changed(self, scheme: QtCore.Qt.ColorScheme):
        """Manejador del evento de cambio de tema nativo de Windows (Win10 / Win11)."""
        is_dark = (scheme == QtCore.Qt.ColorScheme.Dark)
        logger.info("Cambio de tema nativo del sistema detectado: %s", "Oscuro" if is_dark else "Claro")
        self._apply_theme(is_dark)

    def _apply_theme(self, is_dark: Optional[bool] = None):
        """Aplica el tema visual (colores, estilos, barra de título e iconos)."""
        if is_dark is None:
            is_dark = self.is_dark_mode()
        self._is_dark = is_dark
        self._apply_global_styles(is_dark)
        if sys.platform == "win32":
            set_window_dark_mode(int(self.winId()), is_dark)
        self._refresh_icons(is_dark)
        self._update_workspace_validation()
        self._refresh_docker_badge_style()
        self._refresh_robot_status_styles()

    def _style_badge(self, label: QtWidgets.QLabel, text: str, kind: str):
        """Aplica estilo consistente a los badges según el tema activo (light/dark)."""
        label.setText(text)
        is_dark = getattr(self, "_is_dark", False)
        if kind == "success":
            bg = "rgba(34, 197, 94, 0.2)" if is_dark else "#dcfce7"
            fg = "#4ade80" if is_dark else "#15803d"
        elif kind == "warning":
            bg = "rgba(245, 158, 11, 0.2)" if is_dark else "#fef3c7"
            fg = "#fbbf24" if is_dark else "#b45309"
        elif kind == "error":
            bg = "rgba(239, 68, 68, 0.2)" if is_dark else "#fee2e2"
            fg = "#f87171" if is_dark else "#b91c1c"
        else:
            bg = "rgba(148, 163, 184, 0.2)" if is_dark else "#f1f5f9"
            fg = "#cbd5e1" if is_dark else "#475569"

        label.setStyleSheet(f"""
            background-color: {bg};
            color: {fg};
            font-size: 11px;
            font-weight: 700;
            padding: 0 12px;
            border-radius: 6px;
        """)

    def _style_status_label(self, label: QtWidgets.QLabel, text: str, kind: str):
        """Aplica color accesible a las etiquetas de estado según el tema activo."""
        label.setText(text)
        is_dark = getattr(self, "_is_dark", False)
        if kind == "success":
            fg = "#4ade80" if is_dark else "#15803d"
            weight = "600"
        elif kind == "warning":
            fg = "#fbbf24" if is_dark else "#b45309"
            weight = "600"
        elif kind == "error":
            fg = "#f87171" if is_dark else "#dc2626"
            weight = "600"
        else:
            fg = "#94a3b8" if is_dark else "#64748b"
            weight = "normal"
        label.setStyleSheet(f"font-size: 11px; color: {fg}; font-weight: {weight};")

    def _refresh_docker_badge_style(self):
        """Refresca el estado actual del badge de docker con los colores del tema activo."""
        if hasattr(self, "_last_docker_status"):
            installed, running, daemon_msg = self._last_docker_status
            self._apply_docker_status(installed, running, daemon_msg)

    def _refresh_icons(self, is_dark: bool):
        """Actualiza los iconos vectoriales de la interfaz con el tinte del tema activo."""
        p = THEME_PALETTES["dark" if is_dark else "light"]
        col = p["icon_color"]

        # Botones de cabecera
        if hasattr(self, "btn_header_update") and not self.latest_update_info:
            self.btn_header_update.setIcon(get_themed_icon("system-software-update", color=col, fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_ArrowUp))
        if hasattr(self, "btn_docker"):
            if self._docker_state == DockerState.RUNNING:
                self.btn_docker.setIcon(get_themed_icon("view-refresh", color=col, fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload))

        # Botones de herramientas en pestañas
        btn_icon_map = [
            ("btn_browse", "document-open", QtWidgets.QStyle.StandardPixmap.SP_DialogOpenButton),
            ("btn_scroll_bottom", "go-down", QtWidgets.QStyle.StandardPixmap.SP_ArrowDown),
            ("btn_clear", "edit-clear", QtWidgets.QStyle.StandardPixmap.SP_DialogResetButton),
            ("btn_topics", "emblem-documents", QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ("btn_nodes", "network-wired", QtWidgets.QStyle.StandardPixmap.SP_FileDialogContentsView),
            ("btn_compile", "applications-development", QtWidgets.QStyle.StandardPixmap.SP_CommandLink),
            ("btn_clean_compile", "edit-clear", QtWidgets.QStyle.StandardPixmap.SP_DialogResetButton),
            ("btn_prep_image", "view-refresh", QtWidgets.QStyle.StandardPixmap.SP_BrowserReload),
            ("btn_clean_cache", "user-trash", QtWidgets.QStyle.StandardPixmap.SP_TrashIcon),
            ("btn_check_updates", "system-software-update", QtWidgets.QStyle.StandardPixmap.SP_BrowserReload),
            ("btn_scan_robot", "view-refresh", QtWidgets.QStyle.StandardPixmap.SP_BrowserReload),
            ("btn_robot_scp", "document-open", QtWidgets.QStyle.StandardPixmap.SP_ArrowUp),
            ("btn_robot_compile", "applications-development", QtWidgets.QStyle.StandardPixmap.SP_CommandLink),
            ("btn_robot_terminal", "utilities-terminal", QtWidgets.QStyle.StandardPixmap.SP_DesktopIcon),
        ]
        for attr, key, fallback in btn_icon_map:
            if hasattr(self, attr):
                btn = getattr(self, attr)
                btn.setIcon(get_themed_icon(key, color=col, fallback_sp=fallback))

        # Pestañas
        if hasattr(self, "tab_widget"):
            self._on_tab_changed(self.tab_widget.currentIndex())

        # Guía
        if hasattr(self, "txt_guide"):
            self._update_guide_styles()

    def _apply_global_styles(self, is_dark: bool = False):
        palette_key = "dark" if is_dark else "light"
        p = THEME_PALETTES[palette_key]
        arrow_path = get_dropdown_arrow_path(dark_mode=is_dark)
        arrow_url = arrow_path.as_posix() if arrow_path else ""

        css = f"""
            QMainWindow {{
                background-color: {p['bg_window']};
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif;
            }}
            QWidget {{
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif;
                color: {p['text_primary']};
            }}
            /* Header */
            #headerFrame {{
                background-color: {p['bg_header']};
                border-bottom: 1px solid {p['border']};
                padding: 10px 18px;
            }}
            #titleLabel {{
                font-size: 15px;
                font-weight: 700;
                color: {p['text_title']};
            }}
            #subtitleLabel {{
                font-size: 11px;
                color: {p['text_muted']};
            }}
            /* Cards semánticas */
            QFrame[card="true"] {{
                background-color: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 8px;
            }}
            /* Títulos y textos semánticos dentro de tarjetas */
            QLabel[heading="true"] {{
                font-size: 15px;
                font-weight: 700;
                color: {p['text_title']};
            }}
            QLabel[heading_small="true"] {{
                font-size: 12px;
                font-weight: 600;
                color: {p['text_primary']};
            }}
            QLabel[secondary="true"] {{
                font-size: 11px;
                color: {p['text_secondary']};
            }}
            QLabel[note="true"] {{
                font-size: 11px;
                font-style: italic;
                color: {p['text_muted']};
            }}
            /* Tab Widget */
            QTabWidget::pane {{
                border: 1px solid {p['border']};
                border-radius: 8px;
                background-color: {p['bg_window']};
                top: -1px;
            }}
            QTabBar::tab {{
                background: {p['tab_bg']};
                color: {p['tab_text']};
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
                border: 1px solid {p['border']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background: #2563eb;
                color: #ffffff;
                border-color: #2563eb;
            }}
            QTabBar::tab:hover:!selected {{
                background: {p['tab_hover']};
                color: {p['tab_hover_text']};
            }}
            /* Inputs */
            QLineEdit {{
                background-color: {p['bg_input']};
                border: 1px solid {p['border_input']};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                color: {p['text_primary']};
            }}
            QLineEdit:hover {{
                border-color: {p['border_input_hover']};
            }}
            QLineEdit:focus {{
                border: 1px solid {p['border_focus']};
            }}
            /* Dropdowns (QComboBox) */
            QComboBox {{
                background-color: {p['bg_input']};
                border: 1px solid {p['border_input']};
                border-radius: 6px;
                padding: 6px 30px 6px 10px;
                font-size: 12px;
                color: {p['text_primary']};
                min-height: 20px;
            }}
            QComboBox:hover {{
                border-color: {p['border_input_hover']};
            }}
            QComboBox:focus, QComboBox:on {{
                border: 1px solid {p['border_focus']};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 26px;
                border-left: 1px solid {p['border']};
                border-top-right-radius: 5px;
                border-bottom-right-radius: 5px;
                background-color: {p['dropdown_bg']};
            }}
            QComboBox::drop-down:hover {{
                background-color: {p['dropdown_hover']};
            }}
            QComboBox::down-arrow {{
                image: url("{arrow_url}");
                width: 12px;
                height: 12px;
            }}
            QComboBox::down-arrow:disabled {{
                opacity: 0.3;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid {p['border_input']};
                border-radius: 6px;
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                outline: 0;
                padding: 4px;
            }}
            /* Buttons */
            QPushButton {{
                background-color: {p['bg_button']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: 600;
                color: {p['text_primary']};
            }}
            QPushButton:hover {{
                background-color: {p['bg_button_hover']};
            }}
            QPushButton:pressed {{
                background-color: {p['bg_button_pressed']};
            }}
            QPushButton:disabled {{
                background-color: {p['bg_button']};
                color: {p['text_muted']};
                border-color: {p['border']};
            }}
            /* Header buttons */
            #btnHeaderUpdate, #btnDocker {{
                background-color: {p['bg_button']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                font-weight: 600;
                font-size: 11px;
                border-radius: 6px;
                padding: 0 10px;
            }}
            #btnHeaderUpdate:hover, #btnDocker:hover {{
                background-color: {p['bg_button_hover']};
            }}
            /* Action Buttons Specific */
            #btnLaunch {{
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                font-weight: 700;
                padding: 9px 12px;
            }}
            #btnLaunch:hover {{
                background-color: #1d4ed8;
            }}
            #btnLaunch:disabled {{
                background-color: {p['bg_button']};
                color: {p['text_muted']};
                border: 1px solid {p['border']};
            }}
            #btnTerminal {{
                background-color: {p['btn_terminal_bg']};
                color: #ffffff;
                border: 1px solid {p['btn_terminal_border']};
                font-weight: 700;
                padding: 9px 12px;
            }}
            #btnTerminal:hover {{
                background-color: {p['btn_terminal_hover']};
            }}
            #btnWeb {{
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                font-weight: 700;
                padding: 9px 12px;
            }}
            #btnWeb:hover {{
                background-color: #0369a1;
            }}
            #btnStop {{
                background-color: #dc2626;
                color: #ffffff;
                border: none;
                font-weight: 700;
                padding: 9px 12px;
            }}
            #btnStop:hover {{
                background-color: #b91c1c;
            }}
            #btnStop:disabled {{
                background-color: {p['bg_button']};
                color: {p['text_muted']};
                border: 1px solid {p['border']};
            }}
            /* Progress Bar */
            QProgressBar {{
                border: 1px solid {p['border_input']};
                border-radius: 6px;
                text-align: center;
                background-color: {p['progress_bg']};
                color: {p['text_primary']};
                height: 16px;
                font-size: 10px;
                font-weight: 600;
            }}
            QProgressBar::chunk {{
                background-color: #2563eb;
                border-radius: 5px;
            }}
            /* Scenario description box */
            #scenarioDescFrame {{
                background-color: {p['card_desc_bg']};
                border: 1px solid {p['card_desc_border']};
                border-radius: 6px;
                padding: 8px 12px;
            }}
            #lblScenarioDesc {{
                font-size: 11px;
                font-style: italic;
                color: {p['text_secondary']};
            }}
            /* Log box & Guide */
            #txtLogs {{
                background-color: #0f172a;
                color: #e2e8f0;
                font-family: 'Cascadia Code', 'Consolas', 'DejaVu Sans Mono', monospace;
                font-size: 11px;
                border: 1px solid {p['logs_border']};
                border-radius: 6px;
                padding: 8px;
            }}
            #txtGuide {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 6px;
                padding: 16px;
                font-size: 13px;
                line-height: 1.5;
            }}
        """
        self.setStyleSheet(css)


    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Cabecera superior
        self._build_header(main_layout)

        # Contenedor interior con márgenes
        content_container = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_container)
        content_layout.setContentsMargins(18, 12, 18, 14)
        content_layout.setSpacing(10)

        # 2. Barra de acciones rápidas fijas
        self._build_action_bar(content_layout)

        # 3. Pestañas de la aplicación
        self._build_tabs(content_layout)

        main_layout.addWidget(content_container, 1)

    def _build_header(self, parent_layout: QtWidgets.QVBoxLayout):
        header = QtWidgets.QFrame()
        header.setObjectName("headerFrame")
        h_layout = QtWidgets.QHBoxLayout(header)
        h_layout.setContentsMargins(18, 8, 18, 8)
        h_layout.setSpacing(10)

        left_box = QtWidgets.QVBoxLayout()
        left_box.setSpacing(1)

        title = QtWidgets.QLabel(f"ROS 2 - Launcher de simulación  (v{CURRENT_VERSION})")
        title.setObjectName("titleLabel")
        left_box.addWidget(title)

        sub = QtWidgets.QLabel("Sistemas de Navegación")
        sub.setObjectName("subtitleLabel")
        left_box.addWidget(sub)
        h_layout.addLayout(left_box)

        h_layout.addStretch()

        style = self.style()

        # Botón de versión / actualización (mismo tamaño y altura que el de Docker)
        self.btn_header_update = QtWidgets.QPushButton(f"v{CURRENT_VERSION}")
        self.btn_header_update.setObjectName("btnHeaderUpdate")
        self.btn_header_update.setIconSize(QtCore.QSize(16, 16))
        self.btn_header_update.clicked.connect(self._on_header_update_clicked)
        self.btn_header_update.setFixedHeight(30)
        self.btn_header_update.setMinimumWidth(115)
        self.btn_header_update.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        h_layout.addWidget(self.btn_header_update)

        # Badge de estado de Docker (misma altura y padding uniforme, sin emojis)
        self.lbl_docker_badge = QtWidgets.QLabel("● Comprobando Docker...")
        self.lbl_docker_badge.setFixedHeight(30)
        self.lbl_docker_badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._style_badge(self.lbl_docker_badge, "● Comprobando Docker...", "warning")
        h_layout.addWidget(self.lbl_docker_badge)

        # Botón de Docker (mismo tamaño y altura que el de actualización, icono nativo moderno)
        self.btn_docker = QtWidgets.QPushButton("Docker")
        self.btn_docker.setObjectName("btnDocker")
        self.btn_docker.setIconSize(QtCore.QSize(16, 16))
        self.btn_docker.clicked.connect(self._on_docker_button_clicked)
        self.btn_docker.setFixedHeight(30)
        self.btn_docker.setMinimumWidth(115)
        self.btn_docker.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        h_layout.addWidget(self.btn_docker)

        parent_layout.addWidget(header)

    def _build_action_bar(self, parent_layout: QtWidgets.QVBoxLayout):
        card = QtWidgets.QFrame()
        card.setProperty("card", True)
        card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        c_layout = QtWidgets.QVBoxLayout(card)
        c_layout.setContentsMargins(14, 10, 14, 10)
        c_layout.setSpacing(8)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(10)

        style = self.style()

        # Los 4 botones de acción tienen exactamente el mismo tamaño (proporción 1:1:1:1 y altura 40px)
        self.btn_launch = QtWidgets.QPushButton("Iniciar simulación")
        self.btn_launch.setObjectName("btnLaunch")
        self.btn_launch.setIcon(get_themed_icon("media-playback-start", color="#ffffff", disabled_color="#94a3b8", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_launch.setIconSize(QtCore.QSize(20, 20))
        self.btn_launch.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_launch.clicked.connect(self._on_launch_simulation)
        self.btn_launch.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.btn_launch.setFixedHeight(40)
        btn_row.addWidget(self.btn_launch, 1)

        self.btn_terminal = QtWidgets.QPushButton("Abrir terminal Docker")
        self.btn_terminal.setObjectName("btnTerminal")
        self.btn_terminal.setIcon(get_themed_icon("utilities-terminal", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon))
        self.btn_terminal.setIconSize(QtCore.QSize(20, 20))
        self.btn_terminal.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_terminal.clicked.connect(self._on_open_terminal)
        self.btn_terminal.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.btn_terminal.setFixedHeight(40)
        btn_row.addWidget(self.btn_terminal, 1)

        self.btn_web = QtWidgets.QPushButton("Interfaz web (noVNC)")
        self.btn_web.setObjectName("btnWeb")
        self.btn_web.setIcon(get_themed_icon("applications-internet", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_DesktopIcon))
        self.btn_web.setIconSize(QtCore.QSize(20, 20))
        self.btn_web.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_web.clicked.connect(self._open_web_gui)
        self.btn_web.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.btn_web.setFixedHeight(40)
        btn_row.addWidget(self.btn_web, 1)

        self.btn_stop = QtWidgets.QPushButton("Detener contenedor")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setIcon(get_themed_icon("media-playback-stop", color="#ffffff", disabled_color="#94a3b8", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_MediaStop))
        self.btn_stop.setIconSize(QtCore.QSize(20, 20))
        self.btn_stop.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.btn_stop.clicked.connect(self._on_stop_simulation)
        self.btn_stop.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.btn_stop.setFixedHeight(40)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setToolTip("El contenedor no está en ejecución.")
        btn_row.addWidget(self.btn_stop, 1)

        c_layout.addLayout(btn_row)

        # Fila de progreso
        prog_row = QtWidgets.QHBoxLayout()
        prog_row.setSpacing(8)

        self.prog_bar = QtWidgets.QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        prog_row.addWidget(self.prog_bar, 1)

        self.lbl_progress = QtWidgets.QLabel("Listo")
        self.lbl_progress.setObjectName("lblProgress")
        self.lbl_progress.setProperty("secondary", True)
        prog_row.addWidget(self.lbl_progress)

        c_layout.addLayout(prog_row)
        parent_layout.addWidget(card)

    def _build_tabs(self, parent_layout: QtWidgets.QVBoxLayout):
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setIconSize(QtCore.QSize(18, 18))
        style = self.style()

        self.tab_icon_keys = [
            "document-properties",
            "utilities-terminal",
            "applications-development",
            "network-wired",
            "applications-system",
            "help-browser"
        ]

        # 1. Configuración
        self.tab_config = QtWidgets.QWidget()
        self._build_config_tab(self.tab_config)
        self.tab_widget.addTab(self.tab_config, QtGui.QIcon(), "Configuración de simulación")

        # 2. Logs
        self.tab_logs = QtWidgets.QWidget()
        self._build_logs_tab(self.tab_logs)
        self.tab_widget.addTab(self.tab_logs, QtGui.QIcon(), "Salida y logs")

        # 3. Comandos Rápidos
        self.tab_quick = QtWidgets.QWidget()
        self._build_quick_tab(self.tab_quick)
        self.tab_widget.addTab(self.tab_quick, QtGui.QIcon(), "Comandos rápidos")

        # 4. TurtleBot 4
        self.tab_physical = QtWidgets.QWidget()
        self._build_physical_tab(self.tab_physical)
        self.tab_widget.addTab(self.tab_physical, QtGui.QIcon(), "TurtleBot 4")

        # 5. Ajustes Avanzados
        self.tab_advanced = QtWidgets.QWidget()
        self._build_advanced_tab(self.tab_advanced)
        self.tab_widget.addTab(self.tab_advanced, QtGui.QIcon(), "Ajustes avanzados")

        # 6. Guía del Estudiante
        self.tab_guide = QtWidgets.QWidget()
        self._build_guide_tab(self.tab_guide)
        self.tab_widget.addTab(self.tab_guide, QtGui.QIcon(), "Guía del estudiante")

        # Asegurar que la pestaña seleccionada (fondo azul) tenga icono blanco puro
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self._on_tab_changed(self.tab_widget.currentIndex())

        parent_layout.addWidget(self.tab_widget, 1)

    def _on_tab_changed(self, current_index: int):
        """Tiñe de blanco el icono de la pestaña seleccionada y de color accesible las inactivas."""
        is_dark = getattr(self, "_is_dark", False)
        p = THEME_PALETTES["dark" if is_dark else "light"]
        for i, key in enumerate(self.tab_icon_keys):
            if i < self.tab_widget.count():
                if i == current_index:
                    self.tab_widget.setTabIcon(i, get_themed_icon(key, color=p["tab_icon_selected"]))
                else:
                    self.tab_widget.setTabIcon(i, get_themed_icon(key, color=p["tab_icon_normal"]))

        # Al acceder a la pestaña Avanzada, refrescar estado de imagen Docker
        if hasattr(self, "tab_advanced") and self.tab_widget.currentWidget() == self.tab_advanced:
            self._update_docker_image_ui_state()

        # Al acceder a la pestaña Física, refrescar estado inicial si no se ha comprobado aún
        if hasattr(self, "tab_physical") and self.tab_widget.currentWidget() == self.tab_physical:
            self._on_physical_tab_opened()

    def _build_config_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # Tarjeta de Workspace
        ws_card = QtWidgets.QFrame()
        ws_card.setProperty("card", True)
        ws_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        ws_layout = QtWidgets.QVBoxLayout(ws_card)
        ws_layout.setContentsMargins(16, 14, 16, 14)
        ws_layout.setSpacing(10)

        ws_head = QtWidgets.QHBoxLayout()
        lbl_ws_title = QtWidgets.QLabel("Espacio de trabajo en Windows (workspace)")
        lbl_ws_title.setProperty("heading", True)
        ws_head.addWidget(lbl_ws_title)
        ws_head.addStretch()
        ws_layout.addLayout(ws_head)

        ws_input_row = QtWidgets.QHBoxLayout()
        self.ent_ws_path = QtWidgets.QLineEdit()
        self.ent_ws_path.textChanged.connect(self._on_workspace_path_edited)
        ws_input_row.addWidget(self.ent_ws_path, 1)

        self.btn_browse = QtWidgets.QPushButton("Explorar...")
        self.btn_browse.setIconSize(QtCore.QSize(16, 16))
        self.btn_browse.clicked.connect(self._on_browse_workspace)
        ws_input_row.addWidget(self.btn_browse)
        ws_layout.addLayout(ws_input_row)

        ws_feedback = QtWidgets.QHBoxLayout()
        self.lbl_ws_status = QtWidgets.QLabel("Validando ruta...")
        ws_feedback.addWidget(self.lbl_ws_status)
        ws_feedback.addStretch()

        lbl_ws_note = QtWidgets.QLabel("Se monta como volumen en /ros2_ws/src en el contenedor.")
        lbl_ws_note.setProperty("note", True)
        ws_feedback.addWidget(lbl_ws_note)
        ws_layout.addLayout(ws_feedback)

        layout.addWidget(ws_card)

        # Tarjeta de Parámetros de Simulación
        param_card = QtWidgets.QFrame()
        param_card.setProperty("card", True)
        param_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        p_layout = QtWidgets.QVBoxLayout(param_card)
        p_layout.setContentsMargins(16, 14, 16, 14)
        p_layout.setSpacing(10)

        lbl_param_title = QtWidgets.QLabel("Parámetros de simulación")
        lbl_param_title.setProperty("heading", True)
        p_layout.addWidget(lbl_param_title)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        # Fila 0: Robot y Mundo
        grid.addWidget(QtWidgets.QLabel("Modelo de robot:"), 0, 0)
        self.cbo_robot = QtWidgets.QComboBox()
        self.cbo_robot.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        for r in get_all_robots():
            self.cbo_robot.addItem(r.name, userData=r.id)
        self.cbo_robot.currentIndexChanged.connect(self._on_robot_changed)
        grid.addWidget(self.cbo_robot, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Mundo Gazebo:"), 0, 2)
        self.cbo_world = QtWidgets.QComboBox()
        self.cbo_world.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.cbo_world.currentIndexChanged.connect(self._save_current_settings)
        grid.addWidget(self.cbo_world, 0, 3)

        # Fila 1: Escenario y ROS_DOMAIN_ID
        grid.addWidget(QtWidgets.QLabel("Escenario:"), 1, 0)
        self.cbo_scenario = QtWidgets.QComboBox()
        self.cbo_scenario.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.cbo_scenario.currentIndexChanged.connect(self._on_scenario_changed)
        grid.addWidget(self.cbo_scenario, 1, 1)

        grid.addWidget(QtWidgets.QLabel("ROS_DOMAIN_ID:"), 1, 2)
        self.ent_domain_id = QtWidgets.QLineEdit()
        self.ent_domain_id.setMaximumWidth(90)
        self.ent_domain_id.textChanged.connect(self._save_current_settings)
        grid.addWidget(self.ent_domain_id, 1, 3)

        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(3, 1)
        p_layout.addLayout(grid)

        # Descripción del escenario
        self.scenario_desc_frame = QtWidgets.QFrame()
        self.scenario_desc_frame.setObjectName("scenarioDescFrame")
        desc_layout = QtWidgets.QHBoxLayout(self.scenario_desc_frame)
        desc_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_scenario_desc = QtWidgets.QLabel("")
        self.lbl_scenario_desc.setObjectName("lblScenarioDesc")
        desc_layout.addWidget(self.lbl_scenario_desc)
        p_layout.addWidget(self.scenario_desc_frame)

        layout.addWidget(param_card)
        layout.addStretch()

    def _build_logs_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # Barra de control de logs
        ctrl_bar = QtWidgets.QHBoxLayout()
        self.lbl_autoscroll = QtWidgets.QLabel("● Auto-scroll: Activo")
        self.lbl_autoscroll.setStyleSheet("font-size: 11px; font-weight: 700; color: #16a34a;")
        ctrl_bar.addWidget(self.lbl_autoscroll)

        ctrl_bar.addStretch()

        self.btn_scroll_bottom = QtWidgets.QPushButton("Ir al final")
        self.btn_scroll_bottom.setIconSize(QtCore.QSize(16, 16))
        self.btn_scroll_bottom.clicked.connect(self._scroll_to_bottom)
        ctrl_bar.addWidget(self.btn_scroll_bottom)

        self.btn_clear = QtWidgets.QPushButton("Limpiar logs")
        self.btn_clear.setIconSize(QtCore.QSize(16, 16))
        self.btn_clear.clicked.connect(self._clear_logs)
        ctrl_bar.addWidget(self.btn_clear)

        layout.addLayout(ctrl_bar)

        # Consola de texto oscura (adaptada al tema global con Cascadia Code / Consolas)
        self.txt_logs = QtWidgets.QPlainTextEdit()
        self.txt_logs.setObjectName("txtLogs")
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setMaximumBlockCount(10000)
        layout.addWidget(self.txt_logs, 1)

    def _build_quick_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        style = self.style()

        # Tarjeta de Comandos de Inspección
        cmd_card = QtWidgets.QFrame()
        cmd_card.setProperty("card", True)
        cmd_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        cmd_layout = QtWidgets.QVBoxLayout(cmd_card)
        cmd_layout.setContentsMargins(16, 14, 16, 14)
        cmd_layout.setSpacing(12)

        lbl_intro = QtWidgets.QLabel("Comandos de inspección y control")
        lbl_intro.setProperty("heading", True)
        cmd_layout.addWidget(lbl_intro)

        # Grid de botones rápidos
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)

        self.btn_topics = QtWidgets.QPushButton("Listar topics (ros2 topic list)")
        self.btn_topics.setIconSize(QtCore.QSize(16, 16))
        self.btn_topics.clicked.connect(lambda: self._execute_quick_command("ros2 topic list"))
        grid.addWidget(self.btn_topics, 0, 0)

        self.btn_nodes = QtWidgets.QPushButton("Listar nodos (ros2 node list)")
        self.btn_nodes.setIconSize(QtCore.QSize(16, 16))
        self.btn_nodes.clicked.connect(lambda: self._execute_quick_command("ros2 node list"))
        grid.addWidget(self.btn_nodes, 0, 1)

        self.btn_compile = QtWidgets.QPushButton("Compilar workspace (colcon build)")
        self.btn_compile.setIconSize(QtCore.QSize(16, 16))
        self.btn_compile.clicked.connect(self._on_compile_workspace)
        grid.addWidget(self.btn_compile, 1, 0)

        self.btn_clean_compile = QtWidgets.QPushButton("Limpiar compilación (clean build)")
        self.btn_clean_compile.setIconSize(QtCore.QSize(16, 16))
        self.btn_clean_compile.clicked.connect(self._on_clean_compilation)
        grid.addWidget(self.btn_clean_compile, 1, 1)

        cmd_layout.addLayout(grid)
        layout.addWidget(cmd_card)

        # Tarjeta para comando personalizado
        custom_card = QtWidgets.QFrame()
        custom_card.setProperty("card", True)
        custom_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        c_layout = QtWidgets.QVBoxLayout(custom_card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(10)

        lbl_custom = QtWidgets.QLabel("Comando ROS 2 personalizado")
        lbl_custom.setProperty("heading", True)
        c_layout.addWidget(lbl_custom)

        custom_row = QtWidgets.QHBoxLayout()
        self.ent_custom_cmd = QtWidgets.QLineEdit("ros2 topic list")
        self.ent_custom_cmd.returnPressed.connect(self._on_run_custom_command)
        custom_row.addWidget(self.ent_custom_cmd, 1)

        btn_run_custom = QtWidgets.QPushButton("Ejecutar")
        btn_run_custom.setIcon(get_themed_icon("media-playback-start", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))
        btn_run_custom.setIconSize(QtCore.QSize(16, 16))
        btn_run_custom.setStyleSheet("background-color: #2563eb; color: #ffffff; font-weight: 700; padding: 7px 14px;")
        btn_run_custom.clicked.connect(self._on_run_custom_command)
        custom_row.addWidget(btn_run_custom)
        c_layout.addLayout(custom_row)

        lbl_custom_note = QtWidgets.QLabel("La salida del comando se imprimirá en directo en la pestaña 'Salida y logs'.")
        lbl_custom_note.setProperty("note", True)
        c_layout.addWidget(lbl_custom_note)

        layout.addWidget(custom_card)
        layout.addStretch()

    def _build_physical_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # ----------------------------------------------------
        # Tarjeta 1: Estado de Red y Detección del Robot
        # ----------------------------------------------------
        status_card = QtWidgets.QFrame()
        status_card.setProperty("card", True)
        status_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        s_layout = QtWidgets.QVBoxLayout(status_card)
        s_layout.setContentsMargins(16, 14, 16, 14)
        s_layout.setSpacing(12)

        lbl_status_title = QtWidgets.QLabel("Estado de conexión del TurtleBot 4")
        lbl_status_title.setProperty("heading", True)
        s_layout.addWidget(lbl_status_title)

        # Fila 1: Wi-Fi
        wifi_row = QtWidgets.QHBoxLayout()
        wifi_row.setSpacing(10)
        lbl_wifi_title = QtWidgets.QLabel("Red Wi-Fi:")
        lbl_wifi_title.setFixedWidth(150)
        lbl_wifi_title.setProperty("heading_small", True)
        wifi_row.addWidget(lbl_wifi_title)

        self.lbl_wifi_badge = QtWidgets.QLabel("Sin comprobar")
        self.lbl_wifi_badge.setFixedHeight(24)
        self._style_badge(self.lbl_wifi_badge, "Sin comprobar", "neutral")
        wifi_row.addWidget(self.lbl_wifi_badge)

        self.lbl_wifi_desc = QtWidgets.QLabel("Verificando si el PC está conectado a la red Wi-Fi 'dd-wrt' del laboratorio.")
        self.lbl_wifi_desc.setProperty("secondary", True)
        wifi_row.addWidget(self.lbl_wifi_desc, 1)
        s_layout.addLayout(wifi_row)

        # Fila 2: Robot Status & MAC
        robot_row = QtWidgets.QHBoxLayout()
        robot_row.setSpacing(10)
        lbl_robot_title = QtWidgets.QLabel("TurtleBot 4 (MAC):")
        lbl_robot_title.setFixedWidth(150)
        lbl_robot_title.setProperty("heading_small", True)
        robot_row.addWidget(lbl_robot_title)

        self.lbl_robot_badge = QtWidgets.QLabel("No escaneado")
        self.lbl_robot_badge.setFixedHeight(24)
        self._style_badge(self.lbl_robot_badge, "No escaneado", "neutral")
        robot_row.addWidget(self.lbl_robot_badge)

        self.lbl_robot_desc = QtWidgets.QLabel("MAC objetivo: e4:5f:01:bd:05:1a")
        self.lbl_robot_desc.setProperty("secondary", True)
        robot_row.addWidget(self.lbl_robot_desc, 1)
        s_layout.addLayout(robot_row)

        # Fila 3: Dirección IP y Botón Escanear
        ip_row = QtWidgets.QHBoxLayout()
        ip_row.setSpacing(10)
        lbl_ip_title = QtWidgets.QLabel("Dirección IP del robot:")
        lbl_ip_title.setFixedWidth(150)
        lbl_ip_title.setProperty("heading_small", True)
        ip_row.addWidget(lbl_ip_title)

        self.ent_robot_ip = QtWidgets.QLineEdit()
        self.ent_robot_ip.setPlaceholderText("ej. 192.168.1.142")
        self.ent_robot_ip.setFixedWidth(160)
        self.ent_robot_ip.textChanged.connect(self._save_current_settings)
        ip_row.addWidget(self.ent_robot_ip)

        self.btn_scan_robot = QtWidgets.QPushButton("Buscar / Escanear robot")
        self.btn_scan_robot.setIconSize(QtCore.QSize(16, 16))
        self.btn_scan_robot.clicked.connect(lambda: self._start_robot_scan(deep_sweep=True))
        ip_row.addWidget(self.btn_scan_robot)

        lbl_ip_hint = QtWidgets.QLabel("(Se autocompleta al detectar el robot en la red o puede introducirse manualmente)")
        lbl_ip_hint.setProperty("note", True)
        ip_row.addWidget(lbl_ip_hint, 1)
        s_layout.addLayout(ip_row)

        layout.addWidget(status_card)

        # ----------------------------------------------------
        # Tarjeta 2: Parámetros de Acceso SSH
        # ----------------------------------------------------
        ssh_card = QtWidgets.QFrame()
        ssh_card.setProperty("card", True)
        ssh_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        ssh_layout = QtWidgets.QVBoxLayout(ssh_card)
        ssh_layout.setContentsMargins(16, 14, 16, 14)
        ssh_layout.setSpacing(10)

        lbl_ssh_head = QtWidgets.QLabel("Parámetros de acceso y workspace remoto")
        lbl_ssh_head.setProperty("heading", True)
        ssh_layout.addWidget(lbl_ssh_head)

        ssh_grid = QtWidgets.QGridLayout()
        ssh_grid.setHorizontalSpacing(14)
        ssh_grid.setVerticalSpacing(8)

        # Usuario SSH
        lbl_user = QtWidgets.QLabel("Usuario SSH:")
        lbl_user.setProperty("heading_small", True)
        ssh_grid.addWidget(lbl_user, 0, 0)
        self.ent_robot_user = QtWidgets.QLineEdit("ubuntu")
        self.ent_robot_user.textChanged.connect(self._save_current_settings)
        ssh_grid.addWidget(self.ent_robot_user, 0, 1)

        # Contraseña SSH
        lbl_pwd = QtWidgets.QLabel("Contraseña SSH:")
        lbl_pwd.setProperty("heading_small", True)
        ssh_grid.addWidget(lbl_pwd, 0, 2)
        self.ent_robot_password = QtWidgets.QLineEdit("turtlebot4")
        self.ent_robot_password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.ent_robot_password.textChanged.connect(self._save_current_settings)
        ssh_grid.addWidget(self.ent_robot_password, 0, 3)

        # Puerto SSH
        lbl_port = QtWidgets.QLabel("Puerto SSH:")
        lbl_port.setProperty("heading_small", True)
        ssh_grid.addWidget(lbl_port, 1, 0)
        self.ent_robot_port = QtWidgets.QLineEdit("22")
        self.ent_robot_port.setFixedWidth(80)
        self.ent_robot_port.textChanged.connect(self._save_current_settings)
        ssh_grid.addWidget(self.ent_robot_port, 1, 1)

        # Workspace remoto
        lbl_ws = QtWidgets.QLabel("Workspace remoto:")
        lbl_ws.setProperty("heading_small", True)
        ssh_grid.addWidget(lbl_ws, 1, 2)
        self.ent_robot_ws = QtWidgets.QLineEdit("~/ros2_ws")
        self.ent_robot_ws.textChanged.connect(self._save_current_settings)
        ssh_grid.addWidget(self.ent_robot_ws, 1, 3)

        ssh_layout.addLayout(ssh_grid)

        lbl_ssh_note = QtWidgets.QLabel("Valores predeterminados para TurtleBot 4: usuario 'ubuntu', contraseña 'turtlebot4', workspace '~/ros2_ws'.")
        lbl_ssh_note.setProperty("note", True)
        ssh_layout.addWidget(lbl_ssh_note)

        layout.addWidget(ssh_card)

        # ----------------------------------------------------
        # Tarjeta 3: Acciones con el Robot
        # ----------------------------------------------------
        ops_card = QtWidgets.QFrame()
        ops_card.setProperty("card", True)
        ops_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        ops_layout = QtWidgets.QVBoxLayout(ops_card)
        ops_layout.setContentsMargins(16, 14, 16, 14)
        ops_layout.setSpacing(12)

        lbl_ops_head = QtWidgets.QLabel("Operaciones en el Robot Real")
        lbl_ops_head.setProperty("heading", True)
        ops_layout.addWidget(lbl_ops_head)

        # Botones de acción
        btn_grid = QtWidgets.QGridLayout()
        btn_grid.setSpacing(10)

        # 1. Enviar código (SCP)
        self.btn_robot_scp = QtWidgets.QPushButton("Enviar código al robot (SCP)")
        self.btn_robot_scp.setIconSize(QtCore.QSize(16, 16))
        self.btn_robot_scp.clicked.connect(self._on_robot_send_code)
        btn_grid.addWidget(self.btn_robot_scp, 0, 0)

        # 2. Compilar en robot
        self.btn_robot_compile = QtWidgets.QPushButton("Compilar en el robot (colcon build)")
        self.btn_robot_compile.setIconSize(QtCore.QSize(16, 16))
        self.btn_robot_compile.clicked.connect(self._on_robot_compile)
        btn_grid.addWidget(self.btn_robot_compile, 0, 1)

        # 3. Abrir terminal
        self.btn_robot_terminal = QtWidgets.QPushButton("Abrir terminal en el robot (SSH)")
        self.btn_robot_terminal.setIconSize(QtCore.QSize(16, 16))
        self.btn_robot_terminal.setStyleSheet("background-color: #2563eb; color: #ffffff; font-weight: 700; padding: 7px 14px;")
        self.btn_robot_terminal.clicked.connect(self._on_robot_open_terminal)
        btn_grid.addWidget(self.btn_robot_terminal, 1, 0, 1, 2)

        ops_layout.addLayout(btn_grid)

        lbl_ops_info = QtWidgets.QLabel(
            "• 'Enviar código (SCP)': Sincroniza la carpeta 'src' del workspace local con el workspace remoto en el TurtleBot 4.\n"
            "• 'Compilar en el robot': Ejecuta 'colcon build --symlink-install' en el robot; la salida se muestra en directo en la pestaña 'Salida y logs'.\n"
            "• 'Abrir terminal en el robot': Lanza una sesión interactiva SSH en una ventana de consola independiente."
        )
        lbl_ops_info.setProperty("secondary", True)
        ops_layout.addWidget(lbl_ops_info)

        layout.addWidget(ops_card)
        layout.addStretch()

    def _build_advanced_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        style = self.style()

        # Tarjeta Ajustes de Red y Entorno
        net_card = QtWidgets.QFrame()
        net_card.setProperty("card", True)
        net_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        n_layout = QtWidgets.QVBoxLayout(net_card)
        n_layout.setContentsMargins(16, 14, 16, 14)
        n_layout.setSpacing(10)

        lbl_net_title = QtWidgets.QLabel("Ajustes de red y entorno")
        lbl_net_title.setProperty("heading", True)
        n_layout.addWidget(lbl_net_title)

        # Fila Puerto Web noVNC
        row_port = QtWidgets.QHBoxLayout()
        lbl_port = QtWidgets.QLabel("Puerto servidor noVNC:")
        lbl_port.setFixedWidth(210)
        row_port.addWidget(lbl_port)
        self.ent_web_port = QtWidgets.QLineEdit()
        self.ent_web_port.setFixedWidth(90)
        self.ent_web_port.textChanged.connect(self._save_current_settings)
        row_port.addWidget(self.ent_web_port)
        lbl_port_note = QtWidgets.QLabel("(Por defecto: 6080 -> http://localhost:6080/vnc.html)")
        lbl_port_note.setProperty("note", True)
        row_port.addWidget(lbl_port_note)
        row_port.addStretch()
        n_layout.addLayout(row_port)

        # Fila Argumentos Extra
        row_args = QtWidgets.QHBoxLayout()
        lbl_args = QtWidgets.QLabel("Argumentos extra para ROS 2:")
        lbl_args.setFixedWidth(210)
        row_args.addWidget(lbl_args)
        self.ent_extra_args = QtWidgets.QLineEdit()
        self.ent_extra_args.textChanged.connect(self._save_current_settings)
        row_args.addWidget(self.ent_extra_args, 1)
        n_layout.addLayout(row_args)

        # Checkbox recompilación
        self.chk_force_rebuild = QtWidgets.QCheckBox("Forzar recompilación completa con colcon en cada inicio de simulación")
        self.chk_force_rebuild.stateChanged.connect(self._save_current_settings)
        n_layout.addWidget(self.chk_force_rebuild)

        layout.addWidget(net_card)

        # Tarjeta Mantenimiento Docker
        maint_card = QtWidgets.QFrame()
        maint_card.setProperty("card", True)
        maint_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        m_layout = QtWidgets.QVBoxLayout(maint_card)
        m_layout.setContentsMargins(16, 14, 16, 14)
        m_layout.setSpacing(10)

        lbl_maint = QtWidgets.QLabel("Mantenimiento de Docker y caché")
        lbl_maint.setProperty("heading", True)
        m_layout.addWidget(lbl_maint)

        maint_row = QtWidgets.QHBoxLayout()
        self.btn_prep_image = QtWidgets.QPushButton("Reconstruir / preparar imagen Docker")
        self.btn_prep_image.setIconSize(QtCore.QSize(16, 16))
        self.btn_prep_image.clicked.connect(self._on_pull_or_build_image)
        maint_row.addWidget(self.btn_prep_image)

        self.lbl_image_status = QtWidgets.QLabel("")
        self.lbl_image_status.setProperty("note", True)
        maint_row.addWidget(self.lbl_image_status)

        self.btn_clean_cache = QtWidgets.QPushButton("Limpiar volúmenes de caché")
        self.btn_clean_cache.setIconSize(QtCore.QSize(16, 16))
        self.btn_clean_cache.clicked.connect(self._on_clean_build_cache)
        maint_row.addWidget(self.btn_clean_cache)
        maint_row.addStretch()
        m_layout.addLayout(maint_row)

        layout.addWidget(maint_card)

        # Tarjeta Actualizaciones GitHub
        upd_card = QtWidgets.QFrame()
        upd_card.setProperty("card", True)
        upd_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        u_layout = QtWidgets.QVBoxLayout(upd_card)
        u_layout.setContentsMargins(16, 14, 16, 14)
        u_layout.setSpacing(10)

        lbl_upd = QtWidgets.QLabel("Actualizaciones del software")
        lbl_upd.setProperty("heading", True)
        u_layout.addWidget(lbl_upd)

        upd_row = QtWidgets.QHBoxLayout()
        lbl_inst = QtWidgets.QLabel(f"Versión instalada: v{CURRENT_VERSION}")
        lbl_inst.setProperty("heading_small", True)
        upd_row.addWidget(lbl_inst)

        self.btn_check_updates = QtWidgets.QPushButton("Comprobar actualizaciones")
        self.btn_check_updates.setIconSize(QtCore.QSize(16, 16))
        self.btn_check_updates.clicked.connect(self._on_manual_check_updates)
        upd_row.addWidget(self.btn_check_updates)

        self.lbl_update_status = QtWidgets.QLabel("Comprobando al iniciar...")
        self.lbl_update_status.setProperty("note", True)
        upd_row.addWidget(self.lbl_update_status)
        upd_row.addStretch()
        u_layout.addLayout(upd_row)

        layout.addWidget(upd_card)

        # Ruta en AppData
        lbl_appdata = QtWidgets.QLabel(f"Archivo de configuración: {self.config_store.config_path}")
        lbl_appdata.setProperty("secondary", True)
        layout.addWidget(lbl_appdata)
        layout.addStretch()

    def _build_guide_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(14, 12, 14, 12)

        self.txt_guide = QtWidgets.QTextBrowser()
        self.txt_guide.setObjectName("txtGuide")
        self._update_guide_styles()
        layout.addWidget(self.txt_guide)

    def _update_guide_styles(self):
        """Actualiza el estilo visual del Markdown de la guía según el tema activo."""
        if not hasattr(self, "txt_guide"):
            return
        is_dark = getattr(self, "_is_dark", False)
        p = THEME_PALETTES["dark" if is_dark else "light"]
        h_color = p["text_title"]
        text_color = p["text_primary"]
        code_bg = "#0f172a" if is_dark else "#f1f5f9"
        border_col = p["border"]
        doc_css = f"""
            body {{ color: {text_color}; }}
            h1, h2, h3, h4 {{ color: {h_color}; font-weight: 700; }}
            code {{ background-color: {code_bg}; color: {text_color}; font-family: monospace; padding: 2px 4px; border-radius: 4px; }}
            hr {{ border: 1px solid {border_col}; }}
        """
        self.txt_guide.document().setDefaultStyleSheet(doc_css)
        self.txt_guide.setMarkdown(GUIDE_MARKDOWN)

    # --- Persistencia y Carga de Configuraciones ---

    def _load_saved_preferences(self):
        self._is_loading_preferences = True
        try:
            # 1. Workspace
            saved_ws = self.config_store.get("workspace_path")
            self.ent_ws_path.setText(saved_ws)
            self._update_workspace_validation()

            # 2. Robot
            saved_robot_id = self.config_store.get("robot_id", "base")
            robot_profile = get_robot_by_id(saved_robot_id) or get_robot_by_name(saved_robot_id) or get_all_robots()[0]
            self.cbo_robot.blockSignals(True)
            idx_r = self.cbo_robot.findData(robot_profile.id)
            if idx_r < 0:
                idx_r = self.cbo_robot.findText(robot_profile.name)
            if idx_r >= 0:
                self.cbo_robot.setCurrentIndex(idx_r)
            else:
                self.cbo_robot.setCurrentText(robot_profile.name)
            self.cbo_robot.blockSignals(False)

            self._update_worlds_and_scenarios(robot_profile)

            # 3. Mundo
            saved_world = self.config_store.get("world_name", "warehouse")
            idx_w = self.cbo_world.findText(saved_world)
            if idx_w >= 0:
                self.cbo_world.blockSignals(True)
                self.cbo_world.setCurrentIndex(idx_w)
                self.cbo_world.blockSignals(False)

            # 4. Escenario
            saved_sc = self.config_store.get("scenario_id", "container_only")
            if saved_sc == "bash":
                saved_sc = "container_only"
            sc_obj = robot_profile.get_scenario_by_id(saved_sc)
            if sc_obj:
                idx_s = self.cbo_scenario.findText(sc_obj.name)
                if idx_s >= 0:
                    self.cbo_scenario.blockSignals(True)
                    self.cbo_scenario.setCurrentIndex(idx_s)
                    self.cbo_scenario.blockSignals(False)
            self._on_scenario_changed()

            # 5. Domain ID, Puerto, Args
            self.ent_domain_id.setText(str(self.config_store.get("ros_domain_id", "42")))
            self.ent_web_port.setText(str(self.config_store.get("web_port", str(DEFAULT_NOVNC_PORT))))
            self.ent_extra_args.setText(str(self.config_store.get("extra_args", "use_sim_time:=true")))
            self.chk_force_rebuild.setChecked(bool(self.config_store.get("force_rebuild", False)))

            # 6. TurtleBot 4
            saved_robot_ip = self.config_store.get("robot_ip", "")
            if hasattr(self, "ent_robot_ip"):
                self.ent_robot_ip.setText(str(saved_robot_ip))
            if hasattr(self, "ent_robot_user"):
                self.ent_robot_user.setText(str(self.config_store.get("robot_user", "ubuntu")))
            if hasattr(self, "ent_robot_password"):
                self.ent_robot_password.setText(str(self.config_store.get("robot_password", "turtlebot4")))
            if hasattr(self, "ent_robot_port"):
                self.ent_robot_port.setText(str(self.config_store.get("robot_port", "22")))
            if hasattr(self, "ent_robot_ws"):
                self.ent_robot_ws.setText(str(self.config_store.get("robot_remote_ws", "~/ros2_ws")))
        finally:
            self._is_loading_preferences = False

    def _save_current_settings(self):
        if getattr(self, "_is_loading_preferences", False):
            return

        robot_id = self.cbo_robot.currentData()
        if not robot_id:
            selected_robot_name = self.cbo_robot.currentText()
            robot_profile = get_robot_by_name(selected_robot_name)
            robot_id = robot_profile.id if robot_profile else "turtlebot4"
        else:
            robot_profile = get_robot_by_id(robot_id)

        selected_scenario_name = self.cbo_scenario.currentText()
        scenario_id = "container_only" if (robot_profile and robot_profile.id == "base") else "nav2"
        if robot_profile:
            sc_obj = robot_profile.get_scenario_by_name(selected_scenario_name)
            if sc_obj:
                scenario_id = sc_obj.id
            elif "solo contenedor" in selected_scenario_name.lower():
                scenario_id = "container_only"

        data = {
            "workspace_path": self.ent_ws_path.text().strip(),
            "robot_id": robot_id,
            "scenario_id": scenario_id,
            "world_name": self.cbo_world.currentText().strip() or "warehouse",
            "ros_domain_id": self.ent_domain_id.text().strip() or "42",
            "web_port": self.ent_web_port.text().strip() or str(DEFAULT_NOVNC_PORT),
            "extra_args": self.ent_extra_args.text().strip(),
            "force_rebuild": self.chk_force_rebuild.isChecked()
        }
        if hasattr(self, "ent_robot_ip"):
            data["robot_ip"] = self.ent_robot_ip.text().strip()
        if hasattr(self, "ent_robot_user"):
            data["robot_user"] = self.ent_robot_user.text().strip() or "ubuntu"
        if hasattr(self, "ent_robot_password"):
            data["robot_password"] = self.ent_robot_password.text().strip() or "turtlebot4"
        if hasattr(self, "ent_robot_port"):
            data["robot_port"] = self.ent_robot_port.text().strip() or "22"
        if hasattr(self, "ent_robot_ws"):
            data["robot_remote_ws"] = self.ent_robot_ws.text().strip() or "~/ros2_ws"
        self.config_store.update(data, auto_save=True)

    # --- Manejadores de Eventos de la Interfaz ---

    def _on_workspace_path_edited(self):
        self._update_workspace_validation()
        self._save_current_settings()

    def _on_browse_workspace(self):
        current_dir = self.ent_ws_path.text().strip()
        if not os.path.exists(current_dir):
            current_dir = str(Path.home())
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta de desarrollo (Workspace)",
            current_dir
        )
        if chosen:
            self.ent_ws_path.setText(chosen)
            self._update_workspace_validation()
            self._save_current_settings()

    def _update_workspace_validation(self):
        if not hasattr(self, "ent_ws_path") or not hasattr(self, "lbl_ws_status"):
            return
        path_str = self.ent_ws_path.text().strip()
        is_valid, msg = ConfigStore.validate_workspace(path_str)
        if is_valid:
            if "detectado" in msg:
                self._style_status_label(self.lbl_ws_status, f"[OK] {msg}", "success")
            else:
                self._style_status_label(self.lbl_ws_status, f"[OK] {msg}", "info")
        else:
            self._style_status_label(self.lbl_ws_status, f"[Aviso] {msg}", "error")

    def _on_robot_changed(self):
        if getattr(self, "_is_loading_preferences", False):
            return
        robot_id = self.cbo_robot.currentData()
        robot_profile = get_robot_by_id(robot_id) if robot_id else None
        if not robot_profile:
            selected_name = self.cbo_robot.currentText()
            robot_profile = get_robot_by_name(selected_name)
        if robot_profile:
            self._update_worlds_and_scenarios(robot_profile)
            self._on_scenario_changed()
            self._save_current_settings()

    def _update_worlds_and_scenarios(self, robot_profile: RobotProfile):
        self.cbo_world.blockSignals(True)
        self.cbo_scenario.blockSignals(True)

        self.cbo_world.clear()
        for w in robot_profile.supported_worlds:
            self.cbo_world.addItem(w)

        self.cbo_scenario.clear()
        for sc in robot_profile.scenarios:
            self.cbo_scenario.addItem(sc.name)

        self.cbo_world.blockSignals(False)
        self.cbo_scenario.blockSignals(False)

    def _on_scenario_changed(self):
        robot_id = self.cbo_robot.currentData()
        robot_profile = get_robot_by_id(robot_id) if robot_id else None
        if not robot_profile:
            selected_robot_name = self.cbo_robot.currentText()
            robot_profile = get_robot_by_name(selected_robot_name)
        scenario_id = "nav2"
        if robot_profile:
            scenario_name = self.cbo_scenario.currentText()
            sc_obj = robot_profile.get_scenario_by_name(scenario_name)
            if sc_obj:
                scenario_id = sc_obj.id
                self.lbl_scenario_desc.setText(sc_obj.description)
            else:
                self.lbl_scenario_desc.setText("")

        is_container_only = (
            scenario_id in ("container_only", "bash")
            or "solo contenedor" in self.cbo_scenario.currentText().lower()
            or "modo libre" in self.cbo_scenario.currentText().lower()
        )
        is_base_robot = (robot_profile and robot_profile.id == "base")

        if is_container_only:
            self.btn_launch.setText("Iniciar contenedor")
            self.btn_launch.setToolTip("Inicia el contenedor Docker con el workspace montado en modo libre (sin simulación ni roslaunch)")
            self.cbo_world.setEnabled(False)
            self.cbo_world.setToolTip("El mundo de simulación Gazebo no aplica en modo solo contenedor")
            self.ent_extra_args.setEnabled(False)
            self.ent_extra_args.setToolTip("Los argumentos extra no aplican en modo solo contenedor")
        else:
            self.btn_launch.setText("Iniciar simulación")
            self.btn_launch.setToolTip("Inicia la simulación ROS 2 seleccionada")
            self.cbo_world.setEnabled(not is_base_robot)
            self.cbo_world.setToolTip("" if not is_base_robot else "No aplica para entorno base sin robot")
            self.ent_extra_args.setEnabled(True)
            self.ent_extra_args.setToolTip("")

        self._save_current_settings()
        self._update_action_buttons_state()

    def _start_container_poll_timer(self):
        """Inicia temporizador de sondeo periódico para detectar el estado real del contenedor."""
        if self._container_poll_timer is None:
            self._container_poll_timer = QtCore.QTimer(self)
            self._container_poll_timer.setInterval(2000)
            self._container_poll_timer.timeout.connect(self._check_container_live_status)
        if not self._container_poll_timer.isActive():
            self._container_poll_timer.start()

    def _check_container_live_status(self):
        """Comprueba en segundo plano si el contenedor de simulación está corriendo."""
        if self._docker_state != DockerState.RUNNING:
            if self._is_container_running:
                self.sig_container_status.emit(False)
            return
        if self._is_launching_sim or self._is_stopping_sim:
            return
        if self._is_checking_container:
            return
        self._is_checking_container = True

        def _worker():
            try:
                running = DockerService.is_container_running(DEFAULT_CONTAINER_NAME, timeout=2.0)
                self.sig_container_status.emit(running)
            except Exception:
                pass
            finally:
                self._is_checking_container = False

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(bool)
    def _on_container_status_changed(self, running: bool):
        """Manejador ejecutado en el hilo principal de Qt cuando cambia el estado del contenedor."""
        changed = (self._is_container_running != running)
        self._is_container_running = running
        if changed:
            if running:
                self.lbl_progress.setText("Simulación en ejecución")
            elif not self._is_launching_sim and not self._is_stopping_sim:
                self.lbl_progress.setText("Listo")
        self._update_action_buttons_state()

    @QtCore.Slot()
    def _update_action_buttons_state(self):
        """
        Garantiza que 'Iniciar simulación' esté deshabilitado si ya está en ejecución
        o arrancando, y que 'Detener contenedor' esté habilitado únicamente cuando
        el contenedor está en ejecución.
        """
        is_running = self._is_container_running
        is_launching = self._is_launching_sim
        is_stopping = self._is_stopping_sim
        docker_starting = (self._docker_state == DockerState.STARTING)

        # 'Iniciar simulación': deshabilitado si ya está en ejecución, iniciándose o si Docker está arrancando
        can_launch = (not is_running) and (not is_launching) and (not docker_starting)
        self.btn_launch.setEnabled(can_launch)
        self.btn_launch.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor if can_launch else QtCore.Qt.CursorShape.ArrowCursor
        )

        # 'Detener contenedor': habilitado ÚNICAMENTE si el contenedor está en ejecución
        can_stop = is_running and (not is_stopping)
        self.btn_stop.setEnabled(can_stop)
        self.btn_stop.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor if can_stop else QtCore.Qt.CursorShape.ArrowCursor
        )

        # Textos y tooltips contextuales
        selected_sc_name = self.cbo_scenario.currentText()
        is_container_only = (
            "solo contenedor" in selected_sc_name.lower()
            or "modo libre" in selected_sc_name.lower()
        )

        if is_running:
            self.btn_launch.setToolTip("La simulación o contenedor ya se encuentra en ejecución.")
            self.btn_stop.setToolTip("Detiene y elimina el contenedor Docker en ejecución.")
        elif is_launching:
            self.btn_launch.setToolTip("Iniciando contenedor o simulación...")
            self.btn_stop.setToolTip("El contenedor se está iniciando...")
        elif is_stopping:
            self.btn_launch.setToolTip("Deteniendo contenedor...")
            self.btn_stop.setToolTip("Deteniendo contenedor en ejecución...")
        elif docker_starting:
            self.btn_launch.setToolTip("Esperando a que Docker Desktop termine de arrancar...")
            self.btn_stop.setToolTip("Docker Desktop se está iniciando...")
        else:
            self.btn_stop.setToolTip("El contenedor no está en ejecución.")
            if is_container_only:
                self.btn_launch.setToolTip(
                    "Inicia el contenedor Docker con el workspace montado en modo libre (sin simulación ni roslaunch)"
                )
            else:
                self.btn_launch.setToolTip("Inicia la simulación ROS 2 seleccionada")

    def _check_docker_live_status(self):
        if self._docker_state == DockerState.STARTING:
            return

        self._style_badge(self.lbl_docker_badge, "● Comprobando Docker...", "warning")

        def _worker():
            installed, _ = DockerService.check_docker_installed()
            if not installed:
                self.sig_docker_status.emit(False, False, "")
                return
            running, daemon_msg = DockerService.check_docker_running()
            self.sig_docker_status.emit(True, running, daemon_msg)

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(bool, bool, str)
    def _apply_docker_status(self, installed: bool, running: bool, daemon_msg: str):
        if self._docker_state == DockerState.STARTING:
            return

        self._set_docker_state(DockerState.RUNNING if running else DockerState.NOT_RUNNING)
        self._last_docker_status = (installed, running, daemon_msg)
        is_dark = getattr(self, "_is_dark", False)
        p = THEME_PALETTES["dark" if is_dark else "light"]

        if not installed:
            self._style_badge(self.lbl_docker_badge, "● Docker no encontrado", "error")
            self.btn_docker.setText("Instalar Docker")
            self.btn_docker.setIcon(get_themed_icon("help-browser", color="#f87171" if is_dark else "#b91c1c", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_DialogHelpButton))
            self.btn_docker.setToolTip("Docker no está instalado en este sistema. Clic para ver opciones de descarga.")
            btn_bg = "rgba(239, 68, 68, 0.15)" if is_dark else "#fef2f2"
            btn_fg = "#f87171" if is_dark else "#b91c1c"
            btn_border = "#7f1d1d" if is_dark else "#fecaca"
            self.btn_docker.setStyleSheet(f"""
                QPushButton {{
                    background-color: {btn_bg}; color: {btn_fg}; border: 1px solid {btn_border};
                    font-weight: 600; font-size: 11px; border-radius: 6px; padding: 0 10px;
                }}
                QPushButton:hover {{ background-color: {btn_border}; }}
            """)
            self.btn_docker.setEnabled(True)
            self.sig_container_status.emit(False)
        elif running:
            self._style_badge(self.lbl_docker_badge, f"● {daemon_msg}", "success")
            self.btn_docker.setText("Docker")
            self.btn_docker.setIcon(get_themed_icon("view-refresh", color=p["icon_color"], fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload))
            self.btn_docker.setToolTip("Docker activo y funcionando. Clic para volver a comprobar el estado.")
            self.btn_docker.setStyleSheet("")  # Regla QSS global #btnDocker
            self.btn_docker.setEnabled(True)
            self._check_container_live_status()
            self._update_docker_image_ui_state()
        else:
            self._style_badge(self.lbl_docker_badge, "● Docker detenido", "warning")
            self.btn_docker.setText("Iniciar Docker")
            self.btn_docker.setIcon(get_themed_icon("media-playback-start", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))
            self.btn_docker.setToolTip("Docker no está corriendo. Clic para arrancar Docker Desktop en Windows.")
            self.btn_docker.setStyleSheet("""
                QPushButton {
                    background-color: #2563eb; color: #ffffff; border: 1px solid #1d4ed8;
                    font-weight: 700; font-size: 11px; border-radius: 6px; padding: 0 10px;
                }
                QPushButton:hover { background-color: #1d4ed8; }
            """)
            self.btn_docker.setEnabled(True)
            self.sig_container_status.emit(False)

    def _on_docker_button_clicked(self):
        if self._docker_state == DockerState.STARTING:
            return

        installed, _ = DockerService.check_docker_installed()
        if not installed:
            ans = QtWidgets.QMessageBox.question(
                self,
                "Docker no encontrado",
                "Docker no se encuentra instalado en tu sistema.\n\n"
                "¿Deseas abrir el navegador para descargar e instalar Docker Desktop?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if ans == QtWidgets.QMessageBox.StandardButton.Yes:
                webbrowser.open("https://www.docker.com/products/docker-desktop/")
            return

        if self._docker_state == DockerState.RUNNING:
            self._check_docker_live_status()
        else:
            self._start_docker_desktop()

    def _start_docker_desktop(self):
        if self._docker_state == DockerState.STARTING:
            return

        self._set_docker_state(DockerState.STARTING)
        is_dark = getattr(self, "_is_dark", False)
        self._style_badge(self.lbl_docker_badge, "● Arrancando Docker...", "info")
        self.btn_docker.setText("Arrancando...")
        self.btn_docker.setIcon(get_themed_icon("process-working", color="#94a3b8" if is_dark else "#64748b", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload))
        self.btn_docker.setEnabled(False)
        self.btn_docker.setStyleSheet("")

        self._append_log("\n[Docker] Iniciando Docker Desktop en segundo plano...\nPor favor espera mientras el motor se inicializa.\n")
        self.lbl_progress.setText("Arrancando Docker Desktop...")

        def _worker():
            ok, msg = DockerService.start_docker_desktop()
            if not ok:
                self.sig_docker_failed.emit(msg)
                return

            max_seconds = 90
            poll_interval = 2.0
            elapsed = 0.0

            # Pausa breve inicial antes de comenzar las consultas al daemon
            time.sleep(3.0)
            elapsed += 3.0

            while elapsed < max_seconds:
                if self._docker_state != DockerState.STARTING:
                    return

                # Sondeo en segundo plano con timeout controlado para mantener la app fluida
                running, _ = DockerService.check_docker_running(timeout=2.5)
                if running:
                    self.sig_docker_ready.emit()
                    return

                self.sig_docker_poll_progress.emit(int(elapsed), max_seconds)
                time.sleep(poll_interval)
                elapsed += poll_interval

            self.sig_docker_failed.emit(
                f"Tiempo de espera agotado al arrancar Docker Desktop ({max_seconds}s).\n"
                "Por favor comprueba si Docker Desktop se abrió en tu sistema y revisa su estado."
            )

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(int, int)
    def _on_docker_poll_progress(self, elapsed: int, max_s: int):
        self._style_badge(self.lbl_docker_badge, f"● Arrancando Docker ({elapsed}s)...", "info")
        self.lbl_progress.setText(f"Arrancando Docker Desktop ({elapsed}s / {max_s}s)...")

    @QtCore.Slot()
    def _on_docker_ready(self):
        self._set_docker_state(DockerState.RUNNING)
        self._append_log("[Docker] Docker Desktop ha arrancado correctamente.\n")
        self.lbl_progress.setText("Docker listo")
        self._check_docker_live_status()

    @QtCore.Slot(str)
    def _on_docker_start_failed(self, err_msg: str):
        self._set_docker_state(DockerState.NOT_RUNNING)
        self._append_log(f"[Error Docker] No se pudo arrancar Docker Desktop: {err_msg}\n")
        self.lbl_progress.setText("Error al arrancar Docker")
        self._check_docker_live_status()
        self._show_warning_box("Docker", f"No se pudo arrancar Docker Desktop automáticamente:\n\n{err_msg}")

    # --- Actualizaciones Automáticas ---

    def _on_header_update_clicked(self):
        if self.latest_update_info:
            self._prompt_update_available(self.latest_update_info)
        else:
            self._on_manual_check_updates()

    def _check_for_updates_background(self, force: bool = False):
        def _worker():
            has_update, info, _ = check_for_updates(timeout=3.0, force=force)
            if has_update and info:
                ver = info.get("version", "")
                self.latest_update_info = info
                QtCore.QMetaObject.invokeMethod(
                    self, "_on_update_found_bg", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, ver)
                )
            else:
                self.latest_update_info = None

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(str)
    def _on_update_found_bg(self, ver: str):
        self.btn_header_update.setText(f"Actualizar v{ver}")
        self.btn_header_update.setIcon(get_themed_icon("system-software-update", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_ArrowUp))
        self.btn_header_update.setStyleSheet("""
            QPushButton {
                background-color: #16a34a; color: #ffffff; font-weight: 700;
                font-size: 11px; border-radius: 6px; padding: 0 10px; border: none;
            }
            QPushButton:hover { background-color: #15803d; }
        """)
        self._style_status_label(self.lbl_update_status, f"Nueva versión v{ver} disponible", "success")
        if self.latest_update_info:
            self._prompt_update_available(self.latest_update_info)

    def _prompt_update_available(self, update_info: dict, is_forced: bool = False):
        target_dir = Path(__file__).parent.resolve()
        dialog = UpdateModalDialog(self, update_info, target_dir, is_forced=is_forced)
        dialog.exec()

    def _on_manual_check_updates(self, force: bool = False):
        self.btn_check_updates.setEnabled(False)
        self._style_status_label(self.lbl_update_status, "Buscando nueva versión en GitHub...", "info")

        def _worker():
            has_update, info, msg = check_for_updates(timeout=3.5, force=force)
            self.sig_manual_update_result.emit(has_update, info, msg)

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(bool, object, str)
    def _on_manual_update_result(self, has_update: bool, info: Optional[Dict], msg: str):
        self.btn_check_updates.setEnabled(True)
        if has_update and info:
            ver = info.get("version", "")
            self.latest_update_info = info
            is_forced = ("--force-update" in sys.argv)
            self.btn_header_update.setText(f"Actualizar v{ver}")
            self.btn_header_update.setIcon(get_themed_icon("system-software-update", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_ArrowUp))
            self.btn_header_update.setStyleSheet("""
                QPushButton {
                    background-color: #16a34a; color: #ffffff; font-weight: 700;
                    padding: 0 10px; font-size: 11px; border-radius: 6px; border: none;
                }
                QPushButton:hover { background-color: #15803d; }
            """)
            self._style_status_label(self.lbl_update_status, f"Nueva versión v{ver} disponible", "success")
            self._prompt_update_available(info, is_forced=is_forced)
        elif info:
            self.latest_update_info = None
            self._style_status_label(self.lbl_update_status, f"Al día (v{CURRENT_VERSION})", "success")
            QtWidgets.QMessageBox.information(
                self,
                "Actualizaciones",
                f"¡Ya tienes instalada la versión más reciente (v{CURRENT_VERSION})!"
            )
        else:
            self.latest_update_info = None
            self._style_status_label(self.lbl_update_status, msg, "error")
            QtWidgets.QMessageBox.warning(self, "Actualizaciones", msg)

    # --- Acciones Principales: Terminal Docker, Simulación, Web ---

    def _open_web_gui(self):
        port = self.ent_web_port.text().strip() or str(DEFAULT_NOVNC_PORT)
        url = f"http://localhost:{port}/vnc.html?autoconnect=true&resize=scale"
        webbrowser.open(url)

    def _on_open_terminal(self):
        if self._docker_state == DockerState.STARTING:
            self._show_warning_box("Docker", "Docker Desktop se está iniciando en este momento.\nPor favor espera a que el servicio esté listo.")
            return

        def _worker():
            if not DockerService.is_container_running(DEFAULT_CONTAINER_NAME, timeout=3.0):
                QtCore.QMetaObject.invokeMethod(
                    self, "_prompt_start_terminal_container", QtCore.Qt.ConnectionType.QueuedConnection
                )
                return

            ok, msg = DockerService.open_container_terminal(DEFAULT_CONTAINER_NAME)
            if ok:
                self._append_log(f"\n[Terminal] {msg}\n")
            else:
                self._append_log(f"\n[Error Terminal] {msg}\n")
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_warning_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Terminal"),
                    QtCore.Q_ARG(str, msg)
                )

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot()
    def _prompt_start_terminal_container(self):
        answer = QtWidgets.QMessageBox.question(
            self,
            "Contenedor no iniciado",
            "El contenedor de simulación no está activo.\n\n"
            "¿Deseas iniciar el contenedor en modo libre ahora para abrir la terminal?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self._launch_interactive_shell_container()

    def _launch_interactive_shell_container(self):
        idx = self.cbo_scenario.findText("Solo contenedor", QtCore.Qt.MatchFlag.MatchContains)
        if idx >= 0:
            self.cbo_scenario.setCurrentIndex(idx)
        self._on_launch_simulation()

    @QtCore.Slot()
    def _prompt_initial_image_build(self):
        QtWidgets.QMessageBox.information(
            self,
            "Preparación de Imagen Docker",
            f"La imagen '{COURSE_IMAGE_NAME}' no existe localmente.\n\n"
            "Se procederá a compilarla. Este proceso puede tardar unos minutos la primera vez.\n"
            "Al finalizar, la simulación se iniciará automáticamente."
        )
        self._on_pull_or_build_image(
            on_success_callback=lambda: self._on_launch_simulation(skip_update_check=True)
        )

    @QtCore.Slot()
    def _prompt_update_and_rebuild_image(self):
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("Actualización del Entorno Docker")
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        msg_box.setText(
            "Se han detectado actualizaciones en la configuración del contenedor (DOCKERFILE_CONTENT).\n\n"
            "¿Deseas actualizar la imagen Docker ahora?\n\n"
            "• Utilizará la caché local de Docker (solo descargará/compilará las capas nuevas).\n"
            "• La simulación se iniciará automáticamente al completar la actualización."
        )
        btn_update = msg_box.addButton("Actualizar ahora (Recomendado)", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        btn_skip = msg_box.addButton("Iniciar sin actualizar", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        btn_cancel = msg_box.addButton("Cancelar", QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        msg_box.setDefaultButton(btn_update)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == btn_update:
            self._append_log("[INFO] Iniciando actualización de capas Docker...\n")
            self._on_pull_or_build_image(
                on_success_callback=lambda: self._on_launch_simulation(skip_update_check=True)
            )
        elif clicked == btn_skip:
            self._append_log("[AVISO] Continuando con la imagen actual sin actualizar capas.\n")
            self._on_launch_simulation(skip_update_check=True)
        else:
            self._append_log("[INFO] Inicio cancelado por el usuario.\n")
            self._set_progress(0.0, "Cancelado")

    def _on_launch_simulation(self, skip_update_check: bool = False):
        if self._docker_state == DockerState.STARTING:
            self._show_warning_box("Docker", "Docker Desktop se está iniciando en este momento.\nPor favor espera a que finalice el arranque.")
            return

        if self._is_container_running:
            self._show_warning_box("Simulación", "La simulación o contenedor ya se encuentra en ejecución.\nDetén el contenedor actual antes de iniciar una nueva simulación.")
            return

        if self._is_launching_sim:
            return

        image_name = COURSE_IMAGE_NAME
        running, err = DockerService.check_docker_running(timeout=3.0)
        if not running:
            ans = QtWidgets.QMessageBox.question(
                self,
                "Docker no está en ejecución",
                f"Docker no está en ejecución:\n\n{err}\n\n¿Deseas arrancar Docker Desktop ahora?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if ans == QtWidgets.QMessageBox.StandardButton.Yes:
                self._start_docker_desktop()
            return

        self._save_current_settings()

        selected_scenario_name = self.cbo_scenario.currentText()
        is_container_only = (
            "solo contenedor" in selected_scenario_name.lower()
            or "modo libre" in selected_scenario_name.lower()
        )

        title_msg = (
            "Iniciando contenedor ROS 2 (Modo Libre / Sin simulación)..."
            if is_container_only else "Iniciando simulación de ROS 2..."
        )
        self.tab_widget.setCurrentIndex(1)  # Tab Logs
        self._append_log("\n" + "="*50 + f"\n{title_msg}\n" + "="*50 + "\n")

        self._is_launching_sim = True
        self.lbl_progress.setText("Iniciando contenedor..." if is_container_only else "Iniciando simulación...")
        self._update_action_buttons_state()

        def _worker():
            try:
                if not DockerService.is_image_available(image_name):
                    self._append_log(f"Imagen '{image_name}' no encontrada localmente. Iniciando preparación...\n")
                    self._is_launching_sim = False
                    QtCore.QMetaObject.invokeMethod(self, "_update_action_buttons_state", QtCore.Qt.ConnectionType.QueuedConnection)
                    QtCore.QMetaObject.invokeMethod(self, "_prompt_initial_image_build", QtCore.Qt.ConnectionType.QueuedConnection)
                    return

                # Comprobar si la imagen existente requiere actualización incremental de capas
                expected_hash = DockerService.compute_dockerfile_hash(DOCKERFILE_CONTENT)
                stored_hash = self.config_store.get("dockerfile_content_hash")
                is_up_to_date = DockerService.is_image_up_to_date(
                    image_name, expected_hash, fallback_hash=stored_hash
                )
                if not is_up_to_date and not skip_update_check:
                    self._append_log(
                        f"[AVISO] Se detectaron modificaciones en DOCKERFILE_CONTENT pendientes de aplicar a la imagen '{image_name}'.\n"
                    )
                    self._is_launching_sim = False
                    QtCore.QMetaObject.invokeMethod(self, "_update_action_buttons_state", QtCore.Qt.ConnectionType.QueuedConnection)
                    QtCore.QMetaObject.invokeMethod(self, "_prompt_update_and_rebuild_image", QtCore.Qt.ConnectionType.QueuedConnection)
                    return

                DockerService.stop_container(DEFAULT_CONTAINER_NAME)

                robot_id = self.cbo_robot.currentData()
                robot_profile = get_robot_by_id(robot_id) if robot_id else None
                if not robot_profile:
                    selected_robot_name = self.cbo_robot.currentText()
                    robot_profile = get_robot_by_name(selected_robot_name) or get_all_robots()[0]

                selected_sc_name = self.cbo_scenario.currentText()
                scenario_obj = robot_profile.get_scenario_by_name(selected_sc_name)
                scenario_id = scenario_obj.id if scenario_obj else ("container_only" if is_container_only else "nav2")

                world_name = self.cbo_world.currentText().strip() or "warehouse"
                extra_args = self.ent_extra_args.text().strip()
                force_rebuild = self.chk_force_rebuild.isChecked()
                domain_id = self.ent_domain_id.text().strip() or "42"
                ws_path = self.ent_ws_path.text().strip()
                web_port = self.ent_web_port.text().strip() or str(DEFAULT_NOVNC_PORT)

                ros_cmd = robot_profile.build_command(
                    scenario_id=scenario_id,
                    world_name=world_name,
                    extra_args=extra_args,
                    force_rebuild=force_rebuild
                )

                docker_cmd = DockerService.build_docker_run_args(
                    image_name=image_name,
                    container_name=DEFAULT_CONTAINER_NAME,
                    ros_cmd=ros_cmd,
                    domain_id=domain_id,
                    robot_model=robot_profile.id,
                    ws_path=ws_path,
                    web_port=web_port
                )

                self._append_log(f"Comando Docker generado:\n{' '.join(docker_cmd)}\n\n")

                if scenario_id in ("container_only", "bash"):
                    self._append_log("Abriendo terminal nativa conectada al contenedor...\n")
                    QtCore.QTimer.singleShot(1500, self._on_open_terminal)
                else:
                    QtCore.QTimer.singleShot(2500, self._open_web_gui)

                def _on_sim_finished(rc):
                    self._append_log(f"\n[El proceso finalizó con código de salida {rc}]\n")
                    self.sig_container_status.emit(False)

                def _on_sim_error(err):
                    self._append_log(f"\n[Error durante la ejecución: {err}]\n")
                    self.sig_container_status.emit(False)

                self.active_sim_thread = ProcessRunnerThread(docker_cmd)
                self.active_sim_thread.signals.line_received.connect(self._append_log)
                self.active_sim_thread.signals.finished.connect(_on_sim_finished)
                self.active_sim_thread.signals.error.connect(_on_sim_error)
                self.active_sim_thread.start()

                self._is_launching_sim = False
                self.sig_container_status.emit(True)
            except Exception as e:
                self._append_log(f"\n[Error durante el arranque: {e}]\n")
                self._is_launching_sim = False
                self.sig_container_status.emit(False)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stop_simulation(self):
        if not self._is_container_running and not (self.active_sim_thread and self.active_sim_thread.isRunning()):
            return
        if self._is_stopping_sim:
            return

        self.tab_widget.setCurrentIndex(1)  # Logs
        self._is_stopping_sim = True
        self.lbl_progress.setText("Deteniendo contenedor...")
        self._update_action_buttons_state()

        def _worker():
            try:
                self._append_log("\nDeteniendo contenedor de simulación...\n")
                ok, msg = DockerService.stop_container(DEFAULT_CONTAINER_NAME)
                self._append_log(f"{msg}\n")
                if self.active_sim_thread and self.active_sim_thread.isRunning():
                    self.active_sim_thread.terminate_process()
                    self.active_sim_thread.wait(1000)
                if ok:
                    QtCore.QMetaObject.invokeMethod(
                        self, "_show_info_box", QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, "Simulación"),
                        QtCore.Q_ARG(str, "Contenedor detenido correctamente.")
                    )
            except Exception as e:
                self._append_log(f"[Error al detener contenedor: {e}]\n")
            finally:
                self._is_stopping_sim = False
                self.sig_container_status.emit(False)

        threading.Thread(target=_worker, daemon=True).start()

    # --- Comandos Rápidos y Compilación ---

    def _execute_quick_command(self, cmd_str: str):
        if not DockerService.is_container_running(DEFAULT_CONTAINER_NAME):
            QtWidgets.QMessageBox.warning(
                self,
                "Contenedor inactivo",
                "El contenedor no está en ejecución. Inicia la simulación primero para ejecutar comandos."
            )
            return

        self.tab_widget.setCurrentIndex(1)  # Tab Logs
        self._append_log(f"\n>>> Ejecutando comando en contenedor: {cmd_str}\n")

        docker_cmd = DockerService.get_container_exec_args(DEFAULT_CONTAINER_NAME, cmd_str)

        # Detener comando previo si aún está corriendo
        if self.active_cmd_thread and self.active_cmd_thread.isRunning():
            self.active_cmd_thread.terminate_process()
            self.active_cmd_thread.wait(500)

        self.active_cmd_thread = ProcessRunnerThread(docker_cmd)
        self.active_cmd_thread.signals.line_received.connect(self._append_log)
        self.active_cmd_thread.signals.finished.connect(
            lambda rc: self._append_log(f"\n[Comando finalizado con código {rc}]\n")
        )
        self.active_cmd_thread.signals.error.connect(
            lambda err: self._append_log(f"\n[Error al ejecutar comando: {err}]\n")
        )
        self.active_cmd_thread.start()

    def _on_run_custom_command(self):
        cmd = self.ent_custom_cmd.text().strip()
        if cmd:
            self._execute_quick_command(cmd)

    def _on_compile_workspace(self):
        if self._docker_state == DockerState.STARTING:
            self._show_warning_box("Docker", "Docker Desktop se está iniciando en este momento.\nPor favor espera a que el servicio esté listo.")
            return

        image_name = COURSE_IMAGE_NAME
        running, err = DockerService.check_docker_running(timeout=3.0)
        if not running:
            QtWidgets.QMessageBox.critical(self, "Docker", f"Docker no está en ejecución:\n\n{err}")
            return

        ws_path = self.ent_ws_path.text().strip()
        self.tab_widget.setCurrentIndex(1)  # Logs
        self._append_log("\n=== Compilando paquetes del workspace con colcon... ===\n")

        def _worker():
            build_cmd = [
                "docker", "run", "--rm",
                "-v", "ros2_jazzy_build_cache:/ros2_ws/build",
                "-v", "ros2_jazzy_install_cache:/ros2_ws/install",
                "-v", "ros2_jazzy_log_cache:/ros2_ws/log",
            ]
            if ws_path and os.path.exists(ws_path):
                norm_path = Path(ws_path).resolve().as_posix()
                build_cmd.extend(["-v", f"{norm_path}:/ros2_ws/src:rw"])

            build_cmd.append(image_name)
            build_cmd.extend([
                "/bin/bash", "-c",
                "source /opt/ros/jazzy/setup.bash && cd /ros2_ws && colcon build --symlink-install"
            ])

            self.compile_runner = ProcessRunnerThread(build_cmd)
            self.compile_runner.signals.line_received.connect(self._append_log)
            self.compile_runner.signals.finished.connect(self._on_compile_finished)
            self.compile_runner.start()

        threading.Thread(target=_worker, daemon=True).start()

    def _on_compile_finished(self, rc: int):
        if rc == 0:
            self._append_log("\n[Compilación exitosa]\n")
            QtWidgets.QMessageBox.information(self, "Compilación", "Workspace compilado correctamente.")
        else:
            self._append_log(f"\n[Compilación con errores (código {rc})]\n")
            QtWidgets.QMessageBox.critical(self, "Compilación", f"La compilación terminó con código de error {rc}.")

    def _on_clean_compilation(self):
        if self._docker_state == DockerState.STARTING:
            self._show_warning_box("Docker", "Docker Desktop se está iniciando en este momento.\nPor favor espera a que el servicio esté listo.")
            return

        running, err = DockerService.check_docker_running(timeout=3.0)
        if not running:
            QtWidgets.QMessageBox.critical(self, "Docker", f"Docker no está en ejecución:\n\n{err}")
            return

        answer = QtWidgets.QMessageBox.question(
            self,
            "Limpiar compilación",
            "¿Deseas limpiar todos los archivos y caché de compilación del workspace?\n\n"
            "Se eliminarán los directorios 'build', 'install' y 'log' para compilar desde cero.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        ws_path = self.ent_ws_path.text().strip()
        self.tab_widget.setCurrentIndex(1)  # Tab Logs
        self._append_log("\n=== Limpiando archivos y caché de compilación del workspace... ===\n")

        def _worker():
            try:
                # 1. Detener compilación activa si existiese
                if self.compile_runner and self.compile_runner.isRunning():
                    self._append_log("[Aviso] Deteniendo compilador colcon en curso...\n")
                    self.compile_runner.terminate_process()
                    self.compile_runner.wait(1000)

                # 2. Si el contenedor de simulación está activo, limpiar directorios internos
                is_running = DockerService.is_container_running(DEFAULT_CONTAINER_NAME)
                if is_running:
                    self._append_log("[Docker] Contenedor de simulación activo detectado. Vaciando directorios /ros2_ws/{build,install,log}...\n")
                    clean_script = (
                        "find /ros2_ws/build -mindepth 1 -delete 2>/dev/null || rm -rf /ros2_ws/build/*; "
                        "find /ros2_ws/install -mindepth 1 -delete 2>/dev/null || rm -rf /ros2_ws/install/*; "
                        "find /ros2_ws/log -mindepth 1 -delete 2>/dev/null || rm -rf /ros2_ws/log/*"
                    )
                    exec_cmd = [
                        "docker", "exec", DEFAULT_CONTAINER_NAME,
                        "/bin/bash", "-c", clean_script
                    ]
                    res = subprocess.run(
                        exec_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                        timeout=15.0,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    )
                    if res.returncode == 0:
                        self._append_log("[Docker] Directorios de compilación internos vaciados correctamente.\n")
                    else:
                        self._append_log(f"[Docker Aviso] docker exec terminó con código {res.returncode}: {res.stderr}\n")
                else:
                    # Contenedor detenido: eliminar volúmenes persistentes de Docker directamente
                    self._append_log("[Docker] Eliminando volúmenes de caché persistentes de colcon (ros2_jazzy_*)...\n")
                    ok, msg = DockerService.clean_build_volumes()
                    self._append_log(f"[Docker] {msg}\n")

                # 3. Limpiar carpetas locales de build/install/log en el workspace anfitrión si existen
                if ws_path and os.path.exists(ws_path):
                    p = Path(ws_path)
                    for sub in ("build", "install", "log"):
                        host_sub = p / sub
                        if host_sub.exists() and host_sub.is_dir():
                            try:
                                shutil.rmtree(host_sub, ignore_errors=True)
                                self._append_log(f"[Workspace local] Carpeta '{sub}' eliminada en {p}.\n")
                            except Exception as e:
                                self._append_log(f"[Aviso] No se pudo eliminar '{sub}' local: {e}\n")

                self._append_log("\n[Compilación limpia] Limpieza finalizada. El workspace está listo para compilar desde cero.\n")
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_info_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Limpiar compilación"),
                    QtCore.Q_ARG(str, "Compilación limpia finalizada.\nTodos los archivos y cachés de compilación han sido eliminados.")
                )
            except Exception as ex:
                err_msg = f"Error al limpiar la compilación: {ex}"
                logger.error(err_msg, exc_info=True)
                self._append_log(f"\n[Error] {err_msg}\n")
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_warning_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Error"),
                    QtCore.Q_ARG(str, err_msg)
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _on_clean_build_cache(self):
        if self._docker_state == DockerState.STARTING:
            self._show_warning_box("Docker", "Docker Desktop se está iniciando en este momento.\nPor favor espera a que el servicio esté listo.")
            return

        answer = QtWidgets.QMessageBox.question(
            self,
            "Limpiar Caché",
            "¿Deseas eliminar la caché de compilación de Docker?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        self._append_log("\nLimpiando volúmenes de caché en segundo plano...\n")

        def _worker():
            ok, msg = DockerService.clean_build_volumes()
            self._append_log(f"{msg}\n")
            if ok:
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_info_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Caché"),
                    QtCore.Q_ARG(str, msg)
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _on_pull_or_build_image(self, on_success_callback: Optional[Callable[[], None]] = None):
        image_name = COURSE_IMAGE_NAME
        self.tab_widget.setCurrentIndex(1)  # Logs
        self._append_log(f"\n--- Preparando / actualizando imagen Docker: {image_name} ---\n")

        self.btn_prep_image.setEnabled(False)
        self._set_progress(-1, "Comprobando imagen y capas...")

        workspace_dir = Path(__file__).parent.resolve()
        build_dir = ensure_dockerfile_sync(workspace_dir)

        expected_hash = DockerService.compute_dockerfile_hash(DOCKERFILE_CONTENT)
        labels = {DockerService.DOCKERFILE_HASH_LABEL: expected_hash}

        self._pending_post_build_callback = on_success_callback

        def _worker():
            self._append_log(f"Construyendo imagen desde: {build_dir}\n")
            self._append_log("Utilizando caché local de Docker (solo se compilarán las capas modificadas)...\n")
            success, msg = DockerService.build_image_stream(
                str(build_dir),
                image_name,
                lambda pct, txt: QtCore.QMetaObject.invokeMethod(
                    self, "_set_progress", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(float, pct),
                    QtCore.Q_ARG(str, txt)
                ),
                self._append_log,
                labels=labels
            )
            QtCore.QMetaObject.invokeMethod(
                self, "_on_build_image_finished", QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(bool, success),
                QtCore.Q_ARG(str, msg)
            )

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(bool, str)
    def _on_build_image_finished(self, success: bool, msg: str):
        self.btn_prep_image.setEnabled(True)
        self._set_progress(100.0 if success else 0.0, "Listo" if success else "Error")
        cb = getattr(self, "_pending_post_build_callback", None)
        self._pending_post_build_callback = None

        if success:
            expected_hash = DockerService.compute_dockerfile_hash(DOCKERFILE_CONTENT)
            self.config_store.set("dockerfile_content_hash", expected_hash)
            self._append_log(f"\n[ÉXITO] {msg}\n")
            self._update_docker_image_ui_state()

            if cb:
                self._append_log("[INFO] Reanudando lanzamiento tras actualizar la imagen...\n")
                QtCore.QTimer.singleShot(300, cb)
            else:
                QtWidgets.QMessageBox.information(
                    self, "Imagen Docker",
                    f"Imagen '{COURSE_IMAGE_NAME}' lista y actualizada con éxito."
                )
        else:
            self._append_log(f"\n[ERROR] {msg}\n")
            self._update_docker_image_ui_state()
            QtWidgets.QMessageBox.critical(self, "Error", f"Error al preparar imagen:\n{msg}")

    def _update_docker_image_ui_state(self):
        """Actualiza el texto y estado del botón y etiqueta de la imagen Docker en la pestaña Avanzada."""
        if not hasattr(self, "lbl_image_status"):
            return

        def _check_worker():
            installed, _ = DockerService.check_docker_installed()
            running, _ = DockerService.check_docker_running()
            if not installed or not running:
                QtCore.QMetaObject.invokeMethod(
                    self, "_apply_docker_image_ui_state", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "docker_down"),
                    QtCore.Q_ARG(str, "Docker no disponible")
                )
                return

            if not DockerService.is_image_available(COURSE_IMAGE_NAME):
                QtCore.QMetaObject.invokeMethod(
                    self, "_apply_docker_image_ui_state", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "not_installed"),
                    QtCore.Q_ARG(str, "Imagen no encontrada localmente")
                )
                return

            expected_hash = DockerService.compute_dockerfile_hash(DOCKERFILE_CONTENT)
            up_to_date = DockerService.is_image_up_to_date(
                COURSE_IMAGE_NAME,
                expected_hash,
                fallback_hash=self.config_store.get("dockerfile_content_hash")
            )
            if up_to_date:
                QtCore.QMetaObject.invokeMethod(
                    self, "_apply_docker_image_ui_state", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "up_to_date"),
                    QtCore.Q_ARG(str, "Imagen al día (capas sincronizadas)")
                )
            else:
                QtCore.QMetaObject.invokeMethod(
                    self, "_apply_docker_image_ui_state", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "update_available"),
                    QtCore.Q_ARG(str, "Actualización disponible (capas modificadas)")
                )

        threading.Thread(target=_check_worker, daemon=True).start()

    @QtCore.Slot(str, str)
    def _apply_docker_image_ui_state(self, state_key: str, status_text: str):
        if not hasattr(self, "lbl_image_status"):
            return
        self.lbl_image_status.setText(status_text)
        if state_key == "up_to_date":
            self.lbl_image_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.btn_prep_image.setText("Reconstruir imagen Docker")
        elif state_key == "update_available":
            self.lbl_image_status.setStyleSheet("color: #FF9800; font-weight: bold;")
            self.btn_prep_image.setText("Actualizar imagen Docker (Caché)")
        elif state_key == "not_installed":
            self.lbl_image_status.setStyleSheet("color: #F44336; font-weight: bold;")
            self.btn_prep_image.setText("Construir imagen Docker")
        else:
            self.lbl_image_status.setStyleSheet("")
            self.btn_prep_image.setText("Reconstruir / preparar imagen Docker")

    # --- Consola de Logs y Control de Auto-Scroll ---

    @QtCore.Slot(str)
    def _append_log(self, text: str):
        # Si se invoca desde un hilo en segundo plano, encolar mediante la señal Qt
        # para garantizar que toda modificación de widgets de texto se ejecute en el hilo principal GUI.
        if QtCore.QThread.currentThread() != self.thread():
            self.sig_log_received.emit(text)
            return
        self._append_log_main_thread(text)

    def _append_log_main_thread(self, text: str):
        cursor = self.txt_logs.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        self.ansi_parser.parse_to_cursor(text, cursor)

        if self.autoscroll_enabled:
            self._scroll_to_bottom()

    def _clear_logs(self):
        self.txt_logs.clear()
        self.autoscroll_enabled = True
        self._update_autoscroll_ui()

    def _scroll_to_bottom(self):
        scrollbar = self.txt_logs.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.autoscroll_enabled = True
        self._update_autoscroll_ui()

    def _update_autoscroll_ui(self):
        if self.autoscroll_enabled:
            self.lbl_autoscroll.setText("● Auto-scroll: Activo")
            self.lbl_autoscroll.setStyleSheet("font-size: 11px; font-weight: 700; color: #16a34a;")
        else:
            self.lbl_autoscroll.setText("○ Auto-scroll: Pausado")
            self.lbl_autoscroll.setStyleSheet("font-size: 11px; font-weight: 700; color: #dc2626;")

    @QtCore.Slot(float, str)
    def _set_progress(self, pct: float, status_str: str):
        if pct < 0:
            self.prog_bar.setRange(0, 0)
        else:
            self.prog_bar.setRange(0, 100)
            self.prog_bar.setValue(int(pct))
        self.lbl_progress.setText(status_str)

    @QtCore.Slot(str, str)
    def _show_info_box(self, title: str, text: str):
        QtWidgets.QMessageBox.information(self, title, text)

    @QtCore.Slot(str, str)
    def _show_warning_box(self, title: str, text: str):
        QtWidgets.QMessageBox.warning(self, title, text)

    # --- Manejadores de Interacción con el TurtleBot 4 ---

    def _on_physical_tab_opened(self):
        """Al abrir la pestaña del robot por primera vez, realiza una comprobación inicial rápida."""
        if not getattr(self, "_has_checked_robot_once", False):
            self._has_checked_robot_once = True
            self._start_robot_scan(deep_sweep=False)

    def _start_robot_scan(self, deep_sweep: bool = True):
        if getattr(self, "_is_scanning_robot", False):
            return
        self._is_scanning_robot = True
        if hasattr(self, "btn_scan_robot"):
            self.btn_scan_robot.setEnabled(False)
            self.btn_scan_robot.setText("Buscando en la red...")
        if hasattr(self, "lbl_wifi_badge"):
            self._style_badge(self.lbl_wifi_badge, "Verificando...", "neutral")
        if hasattr(self, "lbl_robot_badge"):
            self._style_badge(self.lbl_robot_badge, "Escaneando...", "neutral")
            self.lbl_robot_desc.setText("Consultando tabla ARP y barriendo la subred local...")

        def _worker():
            try:
                target_mac = self.config_store.get("robot_mac", DEFAULT_TURTLEBOT4_MAC)
                ssid = get_connected_ssid()
                wifi_ok = bool(ssid and "dd-wrt" in ssid.lower())

                local_ip = get_local_ip()
                robot_ip = get_ip_from_mac(target_mac)

                if not robot_ip and deep_sweep and local_ip and local_ip != "127.0.0.1":
                    subnet_sweep(local_ip, timeout=0.35)
                    robot_ip = get_ip_from_mac(target_mac)

                robot_found = bool(robot_ip)
                msg = f"SSID: {ssid or 'N/A'} | Robot IP: {robot_ip or 'No encontrado'}"
                self.sig_robot_scan_finished.emit(wifi_ok, ssid or "", robot_found, robot_ip or "", msg)
            except Exception as e:
                logger.exception("Error durante el escaneo del robot: %s", e)
                self.sig_robot_scan_finished.emit(False, "", False, "", str(e))
            finally:
                self._is_scanning_robot = False

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(bool, str, bool, str, str)
    def _on_robot_scan_finished(self, wifi_ok: bool, ssid: str, robot_found: bool, robot_ip: str, msg: str):
        self._last_robot_scan_data = (wifi_ok, ssid, robot_found, robot_ip, msg)
        self._update_robot_ui_status(wifi_ok, ssid, robot_found, robot_ip, msg)
        if hasattr(self, "btn_scan_robot"):
            self.btn_scan_robot.setEnabled(True)
            self.btn_scan_robot.setText("Buscar / Escanear robot")

    def _update_robot_ui_status(self, wifi_ok: bool, ssid: str, robot_found: bool, robot_ip: str, msg: str):
        if not hasattr(self, "lbl_wifi_badge") or not hasattr(self, "lbl_robot_badge"):
            return

        # 1. Estado de la red Wi-Fi
        if not ssid:
            self._style_badge(self.lbl_wifi_badge, "Desconectado", "error")
            self.lbl_wifi_desc.setText("No se detecta conexión Wi-Fi activa. Conéctate a 'dd-wrt'.")
        elif wifi_ok:
            self._style_badge(self.lbl_wifi_badge, f"Conectado: {ssid}", "success")
            self.lbl_wifi_desc.setText(f"Conexión activa a la red Wi-Fi del laboratorio ('{ssid}').")
        else:
            self._style_badge(self.lbl_wifi_badge, f"Red: {ssid}", "warning")
            self.lbl_wifi_desc.setText(f"Conectado a '{ssid}'. En el laboratorio se requiere la red 'dd-wrt'.")

        # 2. Estado del Robot y MAC
        target_mac = self.config_store.get("robot_mac", DEFAULT_TURTLEBOT4_MAC)
        if robot_found and robot_ip:
            self._style_badge(self.lbl_robot_badge, "Localizado", "success")
            self.lbl_robot_desc.setText(f"TurtleBot 4 detectado en la IP {robot_ip} (MAC: {target_mac}).")
            if hasattr(self, "ent_robot_ip"):
                current_ip = self.ent_robot_ip.text().strip()
                if not current_ip or current_ip != robot_ip:
                    self.ent_robot_ip.setText(robot_ip)
                    self._save_current_settings()
        else:
            self._style_badge(self.lbl_robot_badge, "No detectado", "error")
            self.lbl_robot_desc.setText(f"Robot no encontrado en la subred (MAC: {target_mac}). Pulsa 'Buscar / Escanear robot'.")

    def _refresh_robot_status_styles(self):
        if hasattr(self, "_last_robot_scan_data") and self._last_robot_scan_data:
            wifi_ok, ssid, robot_found, robot_ip, msg = self._last_robot_scan_data
            self._update_robot_ui_status(wifi_ok, ssid, robot_found, robot_ip, msg)

    def _on_robot_send_code(self):
        robot_ip = self.ent_robot_ip.text().strip() if hasattr(self, "ent_robot_ip") else ""
        if not robot_ip:
            self._show_warning_box("TurtleBot 4", "Por favor introduce o escanea la dirección IP del TurtleBot 4 antes de transferir.")
            return

        ws_path = self.ent_ws_path.text().strip() if hasattr(self, "ent_ws_path") else ""
        if not ws_path or not os.path.exists(ws_path):
            self._show_warning_box("TurtleBot 4", "La carpeta local del espacio de trabajo (workspace) no existe o no es válida.")
            return

        user = self.ent_robot_user.text().strip() if hasattr(self, "ent_robot_user") else "ubuntu"
        user = user or "ubuntu"
        password = self.ent_robot_password.text().strip() if hasattr(self, "ent_robot_password") else "turtlebot4"
        port = int(self.ent_robot_port.text().strip() or "22") if hasattr(self, "ent_robot_port") else 22
        remote_ws = self.ent_robot_ws.text().strip() if hasattr(self, "ent_robot_ws") else "~/ros2_ws"
        remote_ws = remote_ws or "~/ros2_ws"

        self.tab_widget.setCurrentIndex(1)  # Tab Logs
        self._append_log(f"\n=== [SCP] Enviando código fuente al TurtleBot 4 ({user}@{robot_ip}:{remote_ws}) ===\n")

        def _worker():
            try:
                import paramiko
            except ImportError:
                self.sig_log_received.emit("\n[Error SCP] La librería 'paramiko' no está instalada en el entorno Python.\n")
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_warning_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Dependencia faltante"),
                    QtCore.Q_ARG(str, "Se requiere la librería 'paramiko' para transferir archivos vía SCP/SFTP.\nInstálala con: pip install paramiko")
                )
                return

            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.sig_log_received.emit(f"[SCP] Estableciendo conexión SFTP con {user}@{robot_ip}:{port}...\n")
                client.connect(robot_ip, port=port, username=user, password=password, timeout=10.0)

                # Si el workspace remoto inicia con ~, expandir home
                target_base = remote_ws
                if target_base.startswith("~"):
                    _, stdout_h, _ = client.exec_command("echo $HOME")
                    r_home = stdout_h.read().decode("utf-8").strip() or f"/home/{user}"
                    target_base = r_home + target_base[1:]

                local_p = Path(ws_path).resolve()
                if (local_p / "src").is_dir():
                    src_dir = local_p / "src"
                    dest_dir = f"{target_base.rstrip('/')}/src"
                else:
                    src_dir = local_p
                    dest_dir = f"{target_base.rstrip('/')}/src/{local_p.name}"

                self.sig_log_received.emit(f"[SCP] Directorio origen local: {src_dir}\n")
                self.sig_log_received.emit(f"[SCP] Directorio destino remoto: {dest_dir}\n")

                sftp = client.open_sftp()
                t0 = time.time()
                file_count = sftp_upload_dir(sftp, src_dir, dest_dir, log_cb=lambda msg: self.sig_log_received.emit(msg))
                elapsed = time.time() - t0

                sftp.close()
                client.close()

                self.sig_log_received.emit(f"\n[SCP] Transferencia completada con éxito: {file_count} archivos transferidos en {elapsed:.1f}s.\n")
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_info_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Transferencia SCP"),
                    QtCore.Q_ARG(str, f"Se han transferido con éxito {file_count} archivos al robot en {elapsed:.1f} segundos.")
                )
            except Exception as e:
                logger.exception("Error al transferir archivos vía SCP: %s", e)
                self.sig_log_received.emit(f"\n[Error SCP] Fallo en la transferencia: {e}\n")
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_warning_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Error SCP"),
                    QtCore.Q_ARG(str, f"Error al enviar código al TurtleBot 4:\n\n{e}")
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _on_robot_compile(self):
        robot_ip = self.ent_robot_ip.text().strip() if hasattr(self, "ent_robot_ip") else ""
        if not robot_ip:
            self._show_warning_box("TurtleBot 4", "Por favor introduce o escanea la dirección IP del TurtleBot 4 antes de compilar.")
            return

        user = self.ent_robot_user.text().strip() if hasattr(self, "ent_robot_user") else "ubuntu"
        user = user or "ubuntu"
        password = self.ent_robot_password.text().strip() if hasattr(self, "ent_robot_password") else "turtlebot4"
        port = int(self.ent_robot_port.text().strip() or "22") if hasattr(self, "ent_robot_port") else 22
        remote_ws = self.ent_robot_ws.text().strip() if hasattr(self, "ent_robot_ws") else "~/ros2_ws"
        remote_ws = remote_ws or "~/ros2_ws"

        self.tab_widget.setCurrentIndex(1)  # Tab Logs
        self._append_log(f"\n=== [SSH] Iniciando compilación remota (colcon build) en TurtleBot 4 ({user}@{robot_ip}) ===\n")

        def _worker():
            try:
                import paramiko
            except ImportError:
                self.sig_log_received.emit("\n[Error SSH] La librería 'paramiko' no está instalada en el entorno Python.\n")
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_warning_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Dependencia faltante"),
                    QtCore.Q_ARG(str, "Se requiere la librería 'paramiko' para compilar remotamente vía SSH.\nInstálala con: pip install paramiko")
                )
                return

            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.sig_log_received.emit(f"[SSH] Conectando a {user}@{robot_ip}:{port}...\n")
                client.connect(robot_ip, port=port, username=user, password=password, timeout=10.0)

                build_cmd = (
                    f"bash -lc '"
                    f"if [ -f /opt/ros/humble/setup.bash ]; then source /opt/ros/humble/setup.bash; "
                    f"elif [ -f /opt/ros/jazzy/setup.bash ]; then source /opt/ros/jazzy/setup.bash; fi; "
                    f"cd {remote_ws} && colcon build --symlink-install"
                    f"'"
                )
                self.sig_log_received.emit(f"[SSH Ejecutando] {build_cmd}\n\n")

                stdin, stdout, stderr = client.exec_command(build_cmd, get_pty=True)
                for line in iter(stdout.readline, ""):
                    self.sig_log_received.emit(line)

                rc = stdout.channel.recv_exit_status()
                client.close()

                if rc == 0:
                    self.sig_log_received.emit("\n[Robot Compilación] Compilación completada con ÉXITO.\n")
                    QtCore.QMetaObject.invokeMethod(
                        self, "_show_info_box", QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, "Compilación en Robot"),
                        QtCore.Q_ARG(str, "El espacio de trabajo en el TurtleBot 4 se ha compilado correctamente.")
                    )
                else:
                    self.sig_log_received.emit(f"\n[Robot Compilación Error] La compilación terminó con código de error {rc}.\n")
                    QtCore.QMetaObject.invokeMethod(
                        self, "_show_warning_box", QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, "Error de Compilación"),
                        QtCore.Q_ARG(str, f"La compilación en el robot terminó con errores (código {rc}). Revisa los logs.")
                    )
            except Exception as e:
                logger.exception("Error al compilar remotamente en el robot: %s", e)
                self.sig_log_received.emit(f"\n[SSH Error] Excepción al conectar/compilar en el robot: {e}\n")
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_warning_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Error SSH"),
                    QtCore.Q_ARG(str, f"Error al ejecutar la compilación en el TurtleBot 4:\n\n{e}")
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _on_robot_open_terminal(self):
        robot_ip = self.ent_robot_ip.text().strip() if hasattr(self, "ent_robot_ip") else ""
        if not robot_ip:
            self._show_warning_box("TurtleBot 4", "Por favor introduce o escanea la dirección IP del TurtleBot 4 antes de abrir la terminal.")
            return

        user = self.ent_robot_user.text().strip() if hasattr(self, "ent_robot_user") else "ubuntu"
        user = user or "ubuntu"
        port = self.ent_robot_port.text().strip() if hasattr(self, "ent_robot_port") else "22"
        port_opt = f"-p {port}" if port and port != "22" else ""

        try:
            if sys.platform == "win32":
                cmd = f'cmd.exe /c start "TurtleBot 4 SSH ({user}@{robot_ip})" ssh -o StrictHostKeyChecking=no {port_opt} {user}@{robot_ip}'
                subprocess.Popen(cmd)
                self._append_log(f"\n[Terminal Robot] Ventana SSH iniciada en nueva consola para {user}@{robot_ip}\n")
            elif sys.platform == "darwin":
                script = f'tell application "Terminal" to do script "ssh -o StrictHostKeyChecking=no {port_opt} {user}@{robot_ip}"'
                subprocess.Popen(["osascript", "-e", script])
                self._append_log(f"\n[Terminal Robot] Terminal SSH lanzada para {user}@{robot_ip} (macOS)\n")
            else:
                launched = False
                for term in ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"]:
                    if shutil.which(term):
                        subprocess.Popen([term, "-e", f"ssh -o StrictHostKeyChecking=no {port_opt} {user}@{robot_ip}"])
                        launched = True
                        break
                if launched:
                    self._append_log(f"\n[Terminal Robot] Terminal SSH lanzada para {user}@{robot_ip} (Linux)\n")
                else:
                    self._show_warning_box("Terminal Robot", "No se encontró ningún emulador de terminal compatible en el sistema.")
        except Exception as e:
            logger.exception("Error al abrir terminal SSH: %s", e)
            self._show_warning_box("Terminal Robot", f"No se pudo iniciar la terminal SSH:\n\n{e}")

    def closeEvent(self, event: QtGui.QCloseEvent):
        # Cancelar cualquier sondeo activo de Docker en segundo plano
        self._set_docker_state(DockerState.NOT_RUNNING)

        # Guardar configuración actual antes de salir
        self._save_current_settings()

        # Detener temporizadores activos para evitar advertencias de Qt al cerrar
        if self._docker_poll_timer and self._docker_poll_timer.isActive():
            self._docker_poll_timer.stop()
        if self._container_poll_timer and self._container_poll_timer.isActive():
            self._container_poll_timer.stop()

        # Detener comandos secundarios si continúan activos
        if self.active_cmd_thread and self.active_cmd_thread.isRunning():
            self.active_cmd_thread.terminate_process()
            self.active_cmd_thread.wait(500)

        # Si hay una simulación en curso, advertir al usuario
        if DockerService.is_container_running(DEFAULT_CONTAINER_NAME):
            answer = QtWidgets.QMessageBox.question(
                self,
                "Simulación activa",
                "El contenedor de simulación sigue en ejecución.\n\n¿Deseas detenerlo antes de salir?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No | QtWidgets.QMessageBox.StandardButton.Cancel
            )
            if answer == QtWidgets.QMessageBox.StandardButton.Yes:
                DockerService.stop_container(DEFAULT_CONTAINER_NAME)
                event.accept()
            elif answer == QtWidgets.QMessageBox.StandardButton.No:
                event.accept()
            else:
                event.ignore()
                return
        event.accept()


SUPPORT_EMAIL = "javier.marina@salle.url.edu"


class ExceptionModalDialog(QtWidgets.QDialog):
    """
    Ventana modal moderna construida con PySide6 para capturar y mostrar cualquier
    excepción no controlada, permitiendo copiar el informe técnico detallado
    o enviárselo directamente por correo electrónico a soporte.
    """

    def __init__(self, exc_type, exc_value, exc_tb, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.exc_type = exc_type
        self.exc_value = exc_value
        self.exc_tb = exc_tb

        self.setWindowTitle("Error inesperado - ROS 2 Simulation Launcher")
        self.setMinimumSize(620, 460)
        self.resize(680, 500)
        self.setModal(True)

        # Configurar icono nativo
        try:
            ico_p = get_app_icon_path()
            if ico_p and ico_p.is_file():
                self.setWindowIcon(QtGui.QIcon(str(ico_p)))
        except Exception:
            pass

        self.report_text = self._build_report()
        self._build_ui()
        self._apply_styles()

    def _build_report(self) -> str:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tb_lines = "".join(traceback.format_exception(self.exc_type, self.exc_value, self.exc_tb))

        try:
            docker_inst = "Sí" if DockerService.is_docker_installed() else "No"
            docker_run = "Sí" if DockerService.is_docker_running() else "No"
            docker_info = f"Instalado: {docker_inst} | En ejecución: {docker_run}"
        except Exception:
            docker_info = "No disponible"

        err_type_name = getattr(self.exc_type, "__name__", str(self.exc_type))

        report = (
            "============================================================\n"
            "INFORME DE ERROR - ROS 2 SIMULATION LAUNCHER\n"
            "============================================================\n"
            f"Fecha y hora: {now_str}\n"
            f"Versión Launcher: v{CURRENT_VERSION}\n"
            f"Destinatario soporte: {SUPPORT_EMAIL}\n"
            "\n"
            "--- ENTORNO DEL SISTEMA ---\n"
            f"Sistema Operativo: {platform.system()} {platform.release()} (Build {platform.version()})\n"
            f"Arquitectura: {platform.machine()}\n"
            f"Python: {platform.python_version()} ({platform.architecture()[0]})\n"
            f"PySide6: {QtCore.qVersion()}\n"
            f"Docker Desktop: {docker_info}\n"
            "\n"
            "--- EXCEPCIÓN DETECTADA ---\n"
            f"Tipo: {err_type_name}\n"
            f"Mensaje: {self.exc_value}\n"
            "\n"
            "--- TRAZA DE LA PILA (TRACEBACK) ---\n"
            f"{tb_lines}\n"
            "============================================================\n"
        )
        return report

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # 1. Cabecera con alerta
        header_card = QtWidgets.QFrame()
        header_card.setObjectName("headerCard")
        head_layout = QtWidgets.QHBoxLayout(header_card)
        head_layout.setContentsMargins(14, 12, 14, 12)

        badge_lbl = QtWidgets.QLabel("Error Inesperado")
        badge_lbl.setObjectName("badgeError")
        head_layout.addWidget(badge_lbl)

        err_name = getattr(self.exc_type, "__name__", "Excepción")
        summary_msg = str(self.exc_value).strip().replace("\n", " ")
        if len(summary_msg) > 75:
            summary_msg = summary_msg[:72] + "..."
        title_lbl = QtWidgets.QLabel(f"<b>{err_name}</b>: {summary_msg}")
        title_lbl.setObjectName("titleLabel")
        head_layout.addWidget(title_lbl, 1)

        main_layout.addWidget(header_card)

        # 2. Texto informativo con destinatario
        self.lbl_info = QtWidgets.QLabel()
        self.lbl_info.setObjectName("lblInfo")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setOpenExternalLinks(True)
        main_layout.addWidget(self.lbl_info)

        # 3. Visor de la traza de error
        self.txt_report = QtWidgets.QPlainTextEdit()
        self.txt_report.setObjectName("reportBox")
        self.txt_report.setReadOnly(True)
        self.txt_report.setPlainText(self.report_text)
        main_layout.addWidget(self.txt_report, 1)

        # 4. Etiqueta de feedback para copia
        self.lbl_feedback = QtWidgets.QLabel("")
        self.lbl_feedback.setObjectName("feedbackLabel")
        main_layout.addWidget(self.lbl_feedback)

        # 5. Barra de botones
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_copy = QtWidgets.QPushButton("Copiar informe de error")
        self.btn_copy.setObjectName("btnCopy")
        self.btn_copy.setIconSize(QtCore.QSize(18, 18))
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(self.btn_copy)

        self.btn_email = QtWidgets.QPushButton("Enviar por correo")
        self.btn_email.setObjectName("btnEmail")
        self.btn_email.setIconSize(QtCore.QSize(18, 18))
        self.btn_email.clicked.connect(self._open_email_client)
        btn_layout.addWidget(self.btn_email)

        btn_layout.addStretch()

        self.btn_close = QtWidgets.QPushButton("Cerrar aplicación")
        self.btn_close.setObjectName("btnClose")
        self.btn_close.setIconSize(QtCore.QSize(18, 18))
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        main_layout.addLayout(btn_layout)

    def _apply_styles(self):
        is_dark = is_dark_mode()
        set_window_dark_mode(int(self.winId()), is_dark)

        link_col = "#60a5fa" if is_dark else "#2563eb"
        self.lbl_info.setText(
            f"Se ha producido una excepción no controlada durante la ejecución. "
            f"Puedes copiar el informe técnico con la traza completa y enviarlo por correo "
            f"a <b><a style='color: {link_col}; text-decoration: none;' href='mailto:{SUPPORT_EMAIL}'>{SUPPORT_EMAIL}</a></b>"
        )

        self.btn_copy.setIcon(get_themed_icon("emblem-documents", color="#ffffff"))
        btn_email_icon_col = "#f8fafc" if is_dark else "#1e293b"
        self.btn_email.setIcon(get_themed_icon("applications-internet", color=btn_email_icon_col))
        btn_close_icon_col = "#94a3b8" if is_dark else "#475569"
        self.btn_close.setIcon(get_themed_icon("window-close", color=btn_close_icon_col))

        if is_dark:
            self.setStyleSheet("""
                QDialog {
                    background-color: #0f172a;
                    font-family: 'Segoe UI', system-ui, sans-serif;
                }
                #headerCard {
                    background-color: #1e293b;
                    border: 1px solid #7f1d1d;
                    border-radius: 8px;
                }
                #badgeError {
                    background-color: rgba(239, 68, 68, 0.2);
                    color: #f87171;
                    font-weight: 700;
                    font-size: 12px;
                    padding: 4px 10px;
                    border-radius: 6px;
                }
                #titleLabel {
                    color: #f8fafc;
                    font-size: 13px;
                    margin-left: 8px;
                }
                #lblInfo {
                    font-size: 13px;
                    color: #cbd5e1;
                    line-height: 1.4;
                }
                #reportBox {
                    background-color: #020617;
                    color: #f1f5f9;
                    font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace;
                    font-size: 11px;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 8px;
                }
                #feedbackLabel {
                    font-size: 12px;
                    color: #4ade80;
                    font-weight: 600;
                    min-height: 16px;
                }
                #btnCopy {
                    background-color: #2563eb;
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 13px;
                    padding: 7px 16px;
                    border-radius: 6px;
                    border: none;
                }
                #btnCopy:hover {
                    background-color: #1d4ed8;
                }
                #btnEmail {
                    background-color: #1e293b;
                    color: #f8fafc;
                    font-weight: 600;
                    font-size: 13px;
                    padding: 7px 16px;
                    border-radius: 6px;
                    border: 1px solid #334155;
                }
                #btnEmail:hover {
                    background-color: #334155;
                }
                #btnClose {
                    background-color: transparent;
                    color: #94a3b8;
                    font-weight: 600;
                    font-size: 13px;
                    padding: 7px 16px;
                    border-radius: 6px;
                    border: 1px solid #334155;
                }
                #btnClose:hover {
                    background-color: rgba(239, 68, 68, 0.2);
                    color: #f87171;
                    border-color: #ef4444;
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
                    border: 1px solid #fee2e2;
                    border-radius: 8px;
                }
                #badgeError {
                    background-color: #fee2e2;
                    color: #b91c1c;
                    font-weight: 700;
                    font-size: 12px;
                    padding: 4px 10px;
                    border-radius: 6px;
                }
                #titleLabel {
                    color: #0f172a;
                    font-size: 13px;
                    margin-left: 8px;
                }
                #lblInfo {
                    font-size: 13px;
                    color: #334155;
                    line-height: 1.4;
                }
                #reportBox {
                    background-color: #0f172a;
                    color: #f1f5f9;
                    font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace;
                    font-size: 11px;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 8px;
                }
                #feedbackLabel {
                    font-size: 12px;
                    color: #16a34a;
                    font-weight: 600;
                    min-height: 16px;
                }
                #btnCopy {
                    background-color: #2563eb;
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 13px;
                    padding: 7px 16px;
                    border-radius: 6px;
                    border: none;
                }
                #btnCopy:hover {
                    background-color: #1d4ed8;
                }
                #btnEmail {
                    background-color: #ffffff;
                    color: #0f172a;
                    font-weight: 600;
                    font-size: 13px;
                    padding: 7px 16px;
                    border-radius: 6px;
                    border: 1px solid #cbd5e1;
                }
                #btnEmail:hover {
                    background-color: #f1f5f9;
                }
                #btnClose {
                    background-color: transparent;
                    color: #475569;
                    font-weight: 600;
                    font-size: 13px;
                    padding: 7px 16px;
                    border-radius: 6px;
                    border: 1px solid #cbd5e1;
                }
                #btnClose:hover {
                    background-color: #fee2e2;
                    color: #b91c1c;
                    border-color: #fca5a5;
                }
            """)

    def _copy_to_clipboard(self):
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.report_text)
        self.btn_copy.setText("✓ ¡Informe copiado!")
        self.lbl_feedback.setText(f"✓ ¡Informe copiado al portapapeles! Puedes pegarlo (Ctrl+V) en un correo a {SUPPORT_EMAIL}")
        QtCore.QTimer.singleShot(3000, self._reset_copy_btn)

    def _reset_copy_btn(self):
        self.btn_copy.setText("Copiar informe de error")

    def _open_email_client(self):
        self._copy_to_clipboard()
        err_name = getattr(self.exc_type, "__name__", "Excepción")
        subject = f"[Error ROS 2 Launcher] {err_name}: {str(self.exc_value)[:50]}"
        body = (
            "Hola Javier,\n\n"
            "Se ha producido la siguiente excepción en el Launcher de Simulación ROS 2:\n\n"
            f"- Tipo: {err_name}\n"
            f"- Mensaje: {self.exc_value}\n\n"
            "(Nota: El informe técnico completo con la traza de la pila y entorno ya se ha copiado "
            "automáticamente al portapapeles. Pégalo a continuación con Ctrl+V):\n\n"
        )
        mailto_url = f"mailto:{SUPPORT_EMAIL}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(mailto_url))
        self.lbl_feedback.setText(f"Abriendo cliente de correo... Recuerda pegar el informe (Ctrl+V) antes de enviar.")


class GlobalExceptionDispatcher(QtCore.QObject):
    """
    Despachador central de excepciones. Conecta excepciones procedentes de
    cualquier hilo (hilo principal o hilos secundarios) con el hilo de la GUI
    mediante una conexión de señales encolada segura (QueuedConnection).
    """
    sig_exception = QtCore.Signal(object, object, object)

    def __init__(self):
        super().__init__()
        self._active = False
        self.sig_exception.connect(self._on_exception, QtCore.Qt.ConnectionType.QueuedConnection)

    @QtCore.Slot(object, object, object)
    def _on_exception(self, exc_type, exc_value, exc_tb):
        if self._active:
            return  # Evitar ventanas recursivas o apiladas si hay un bucle de excepciones
        self._active = True
        try:
            parent = QtWidgets.QApplication.activeWindow()
            dlg = ExceptionModalDialog(exc_type, exc_value, exc_tb, parent=parent)
            dlg.exec()
        except Exception as err:
            logger.critical("Error al mostrar la ventana modal de excepción: %s", err)
        finally:
            self._active = False
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.closeAllWindows()
                app.quit()


_global_dispatcher: Optional[GlobalExceptionDispatcher] = None


def _global_excepthook(exc_type, exc_value, exc_tb):
    """Manejador global para sys.excepthook."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    logger.critical("Excepción no controlada capturada:", exc_info=(exc_type, exc_value, exc_tb))

    if _global_dispatcher is not None:
        _global_dispatcher.sig_exception.emit(exc_type, exc_value, exc_tb)
    else:
        # Fallback previo a la inicialización del despachador
        app = QtWidgets.QApplication.instance()
        if app is None:
            try:
                app = QtWidgets.QApplication(sys.argv)
            except Exception:
                app = None
        if app is not None:
            try:
                dlg = ExceptionModalDialog(exc_type, exc_value, exc_tb)
                dlg.exec()
                app.closeAllWindows()
                app.quit()
                return
            except Exception:
                pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)


def _thread_excepthook(args):
    """Manejador global para threading.excepthook (hilos secundarios en segundo plano)."""
    _global_excepthook(args.exc_type, args.exc_value, args.exc_traceback)


def main():
    global _global_dispatcher

    # Inicializar aplicación Qt
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("ROS 2 Simulation Launcher")
    app.setOrganizationName("La Salle URL")

    # Registrar despachador y capturadores globales de excepciones
    _global_dispatcher = GlobalExceptionDispatcher()
    sys.excepthook = _global_excepthook
    threading.excepthook = _thread_excepthook

    # Configurar icono nativo de aplicación
    try:
        ico_path = get_app_icon_path()
        if ico_path and ico_path.is_file():
            app.setWindowIcon(QtGui.QIcon(str(ico_path)))
    except Exception:
        pass

    try:
        window = ModernSimulationLauncher()
        window.show()

        # Garantizar que Windows Taskbar y Alt+Tab reciban el icono nativo (32x32)
        if sys.platform == "win32" and ico_path and ico_path.is_file():
            try:
                import ctypes
                hwnd = int(window.winId())
                ico_str = str(ico_path)
                # IMAGE_ICON = 1, LR_LOADFROMFILE = 0x10
                hicon_big = ctypes.windll.user32.LoadImageW(None, ico_str, 1, 32, 32, 0x00000010)
                hicon_small = ctypes.windll.user32.LoadImageW(None, ico_str, 1, 16, 16, 0x00000010)
                if hicon_big:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon_big)
                if hicon_small:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon_small)
            except Exception as e:
                logger.debug("No se pudo forzar WM_SETICON nativo: %s", e)

        sys.exit(app.exec())
    except Exception:
        _global_excepthook(*sys.exc_info())


if __name__ == "__main__":
    main()
