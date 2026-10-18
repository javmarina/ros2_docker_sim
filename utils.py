"""
Non-UI utilities: process runner, ANSI color parser, network helpers,
SFTP upload, Dockerfile management, SSH terminal launcher, and guide content.
"""

import hashlib
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6 import QtCore, QtGui

logger = logging.getLogger("launcher")

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# ---------------------------------------------------------------------------
# Process Runner (QThread wrapper for streaming subprocess output)
# ---------------------------------------------------------------------------


class ProcessRunnerSignals(QtCore.QObject):
    line_received = QtCore.Signal(str)
    progress_changed = QtCore.Signal(float, str)
    finished = QtCore.Signal(int)
    error = QtCore.Signal(str)


class ProcessRunnerThread(QtCore.QThread):
    def __init__(self, cmd: list[str], cwd: str | None = None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.signals = ProcessRunnerSignals()
        self.proc: subprocess.Popen | None = None

    def run(self):
        try:
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
                creationflags=_NO_WINDOW,
            )
            for line in iter(self.proc.stdout.readline, ""):
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


# ---------------------------------------------------------------------------
# ANSI escape code parser for QTextEdit (renders colors in log console)
# ---------------------------------------------------------------------------


class AnsiColorParser:
    ANSI_MAP = {
        30: QtGui.QColor("#4f5666"),
        31: QtGui.QColor("#e06c75"),
        32: QtGui.QColor("#98c379"),
        33: QtGui.QColor("#e5c07b"),
        34: QtGui.QColor("#61afef"),
        35: QtGui.QColor("#c678dd"),
        36: QtGui.QColor("#56b6c2"),
        37: QtGui.QColor("#abb2bf"),
        90: QtGui.QColor("#5c6370"),
        91: QtGui.QColor("#ff6c6b"),
        92: QtGui.QColor("#98be65"),
        93: QtGui.QColor("#da8548"),
        94: QtGui.QColor("#51afef"),
        95: QtGui.QColor("#a9a1e1"),
        96: QtGui.QColor("#46d9ff"),
        97: QtGui.QColor("#ffffff"),
    }
    REGEX = re.compile(r"(\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\))")

    def __init__(self, default_color: QtGui.QColor = QtGui.QColor("#e4e4e7")):
        self.default_color = default_color
        self.current_format = QtGui.QTextCharFormat()
        self.current_format.setForeground(self.default_color)

    def parse_to_cursor(self, text: str, cursor: QtGui.QTextCursor):
        for token in self.REGEX.split(text):
            if not token:
                continue
            if token.startswith("\x1b["):
                if token.endswith("m"):
                    params = [int(p) for p in token[2:-1].split(";") if p] if token[2:-1] else [0]
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
            elif token.startswith("\x1b"):
                pass  # Ignore other escape sequences (e.g. OSC)
            else:
                clean = token.replace("\x07", "")
                if clean:
                    cursor.insertText(clean, self.current_format)


# ---------------------------------------------------------------------------
# Network utilities & TurtleBot 4 detection
# ---------------------------------------------------------------------------

DEFAULT_TURTLEBOT4_MAC = "e4:5f:01:bd:05:1a"


def get_connected_ssid() -> str | None:
    """Returns the currently connected Wi-Fi SSID, or None."""
    try:
        if sys.platform == "win32":
            # Try netsh first (fast)
            try:
                out = subprocess.check_output(
                    ["netsh", "wlan", "show", "interfaces"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    creationflags=_NO_WINDOW,
                )
                for line in out.splitlines():
                    if "SSID" in line and "BSSID" not in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2 and parts[1].strip():
                            return parts[1].strip()
            except Exception:
                pass
            # Fallback to PowerShell
            try:
                output = subprocess.check_output(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Get-NetConnectionProfile",
                    ],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    creationflags=_NO_WINDOW,
                )
                for line in output.splitlines():
                    if ":" in line:
                        key, _, value = line.partition(":")
                        if key.strip().lower() == "name" and value.strip():
                            return value.strip()
            except Exception:
                pass
        elif sys.platform == "darwin":
            cmd = [
                "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport",
                "-I",
            ]
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if "SSID:" in line and "BSSID" not in line:
                    return line.split(":", 1)[1].strip()
        else:
            for cmd in [
                ["iwgetid", "-r"],
                ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            ]:
                try:
                    out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
                    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
                    if lines:
                        if cmd[0] == "nmcli":
                            for ln in lines:
                                if ln.startswith("yes:"):
                                    return ln.split(":", 1)[1]
                        else:
                            return lines[0]
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Error al consultar SSID Wi-Fi: %s", e)
    return None


def get_local_ip() -> str:
    """Returns the local IP of the active network interface."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def get_ip_from_mac(target_mac: str) -> str | None:
    """Scans the local ARP table for an IP associated with the given MAC address."""
    target_mac = target_mac.lower().replace("-", ":").strip()
    try:
        output = subprocess.check_output(
            ["arp", "-a"],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
        for line in output.splitlines():
            if target_mac in line.lower().replace("-", ":"):
                match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
                if match:
                    return match.group(1)
    except Exception as e:
        logger.debug("Error al escanear tabla ARP: %s", e)
    return None


def _ping_cmd(ip: str, timeout: float) -> list[str]:
    """Builds a single-packet ping command for the current platform."""
    if sys.platform == "win32":
        return ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
    return ["ping", "-c", "1", "-W", str(max(1, int(timeout))), ip]


def ping_device(ip_address: str, timeout: float = 1.0) -> bool:
    """Checks whether a host is reachable via ICMP ping."""
    if not ip_address:
        return False
    try:
        subprocess.check_output(
            _ping_cmd(ip_address, timeout),
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
        return True
    except Exception:
        return False


def subnet_sweep(local_ip: str, timeout: float = 0.35) -> None:
    """Fast ICMP sweep over the local /24 subnet to populate the ARP table."""
    try:
        parts = local_ip.split(".")
        if len(parts) != 4:
            return
        prefix = ".".join(parts[:-1])
        own = int(parts[-1])
        ips = [f"{prefix}.{i}" for i in range(1, 255) if i != own]

        def _ping(ip):
            try:
                subprocess.run(
                    _ping_cmd(ip, timeout),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=_NO_WINDOW,
                )
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=32) as executor:
            list(executor.map(_ping, ips))
    except Exception as e:
        logger.debug("Error en subnet_sweep: %s", e)


# ---------------------------------------------------------------------------
# SFTP recursive upload
# ---------------------------------------------------------------------------

_SFTP_IGNORE_DIRS = {
    ".git",
    ".svn",
    "build",
    "install",
    "log",
    "__pycache__",
    ".vscode",
    ".idea",
    ".DS_Store",
}


def sftp_upload_dir(sftp, local_dir: Path, remote_dir: str, log_cb=None) -> int:
    """Recursively uploads a local directory to a remote directory via SFTP."""

    def _remote_mkdir_p(path: str):
        clean = path.replace("\\", "/")
        parts = clean.strip("/").split("/")
        cur = "/" if clean.startswith("/") else ""
        for p in parts:
            cur = f"{cur.rstrip('/')}/{p}"
            try:
                sftp.stat(cur)
            except OSError:
                try:
                    sftp.mkdir(cur)
                except OSError:
                    pass

    _remote_mkdir_p(remote_dir)
    file_count = 0
    local_p = Path(local_dir).resolve()

    for root, dirs, files in os.walk(local_p):
        dirs[:] = [d for d in dirs if d not in _SFTP_IGNORE_DIRS and not d.startswith(".")]
        rel = os.path.relpath(root, local_p).replace("\\", "/")
        dest_sub = remote_dir if rel == "." else f"{remote_dir}/{rel}"
        _remote_mkdir_p(dest_sub)

        for f in files:
            if f.endswith((".pyc", ".swp", "~")) or f in _SFTP_IGNORE_DIRS:
                continue
            src_file = os.path.join(root, f)
            dest_file = f"{dest_sub}/{f}"
            if log_cb:
                disp = f if rel == "." else f"{rel}/{f}"
                log_cb(f"  -> [SCP] {disp}\n")
            sftp.put(src_file, dest_file)
            file_count += 1

    return file_count


# ---------------------------------------------------------------------------
# Robot SSH terminal launcher (platform-specific, no Qt dependency)
# ---------------------------------------------------------------------------


def _cleanup_temp_file(fpath: str, delay: float = 15.0):
    """Deletes a temp file after a delay, in a background thread."""

    def _worker():
        time.sleep(delay)
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def _clean_stale_askpass_files():
    """Removes orphaned askpass temp files from previous sessions."""
    try:
        for old in Path(tempfile.gettempdir()).glob("tb4_askpass_*"):
            try:
                if old.is_file():
                    old.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass


def _write_askpass(content: str, suffix: str) -> str:
    """Writes a self-deleting SSH_ASKPASS helper script and returns its path."""
    path = os.path.join(
        tempfile.gettempdir(),
        f"tb4_askpass_{os.getpid()}_{int(time.time() * 1000)}.{suffix}",
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if suffix == "sh":
        os.chmod(path, 0o700)
    _cleanup_temp_file(path)
    return path


def open_robot_ssh_terminal(
    ip: str, user: str, password: str, port: str, remote_ws: str
) -> tuple[bool, str]:
    """
    Opens a native SSH terminal window to the robot.
    Returns (success, message).
    """
    port_opt = f"-p {port}" if port and port != "22" else ""

    remote_init_cmd = (
        "if [ -f /opt/ros/humble/setup.bash ]; then source /opt/ros/humble/setup.bash; "
        "elif [ -f /opt/ros/jazzy/setup.bash ]; then source /opt/ros/jazzy/setup.bash; fi; "
        "if [ -f ~/turtlebot4_ws/install/setup.bash ]; then "
        "source ~/turtlebot4_ws/install/setup.bash; echo '[ROS 2] Entorno cargado: ~/turtlebot4_ws/install/setup.bash'; "
        f"elif [ -f {remote_ws}/install/setup.bash ]; then "
        f"source {remote_ws}/install/setup.bash; echo '[ROS 2] Entorno cargado: {remote_ws}/install/setup.bash'; "
        "fi; exec bash"
    )

    _clean_stale_askpass_files()
    auth_mode = "con autenticación automática" if password else "solicitando contraseña"
    ssh = f"ssh -o StrictHostKeyChecking=no {port_opt} -t {user}@{ip}"
    sh_askpass = f"#!/bin/sh\necho '{password}'\n"

    if sys.platform == "win32":
        title = f'cmd.exe /c start "TurtleBot 4 SSH ({user}@{ip})" '
        if password:
            askpass_path = _write_askpass(
                f"@echo off\r\necho {password.replace('%', '%%')}\r\n", "cmd"
            )
            cmd = (
                f'{title}cmd.exe /c "set "SSH_ASKPASS={askpass_path}" && '
                f'set "SSH_ASKPASS_REQUIRE=force" && '
                f'{ssh} "{remote_init_cmd}" || pause"'
            )
        else:
            cmd = f'{title}{ssh} "{remote_init_cmd}"'
        subprocess.Popen(cmd, shell=True)
        return True, f"Ventana SSH iniciada para {user}@{ip} ({auth_mode})"

    elif sys.platform == "darwin":
        env = ""
        if password:
            askpass_path = _write_askpass(sh_askpass, "sh")
            env = f'export SSH_ASKPASS=\\"{askpass_path}\\" SSH_ASKPASS_REQUIRE=force; '
        script = f'tell application "Terminal" to do script "{env}{ssh} \\"{remote_init_cmd}\\""'
        subprocess.Popen(["osascript", "-e", script])
        return True, f"Terminal SSH lanzada para {user}@{ip} (macOS, {auth_mode})"

    else:  # Linux
        ssh_cmd = f"{ssh} '{remote_init_cmd}'"
        if password and shutil.which("sshpass"):
            ssh_cmd = f"sshpass -p '{password}' {ssh_cmd}"
        elif password:
            askpass_path = _write_askpass(sh_askpass, "sh")
            ssh_cmd = f"env SSH_ASKPASS='{askpass_path}' SSH_ASKPASS_REQUIRE=force {ssh_cmd}"

        for term in [
            "x-terminal-emulator",
            "gnome-terminal",
            "konsole",
            "xfce4-terminal",
            "xterm",
        ]:
            if shutil.which(term):
                subprocess.Popen([term, "-e", f'bash -c "{ssh_cmd}"'])
                return (
                    True,
                    f"Terminal SSH lanzada para {user}@{ip} (Linux, {auth_mode})",
                )

        return (
            False,
            "No se encontró ningún emulador de terminal compatible en el sistema.",
        )


# ---------------------------------------------------------------------------
# Dockerfile content and sync
# ---------------------------------------------------------------------------

def _assets_digest() -> str:
    """Digest of the files COPY'd into the image, so editing them changes the Dockerfile hash."""
    root = Path(__file__).parent
    files = [
        root / "turtlebot4_nodock.launch.py",
        *root.joinpath("worlds").rglob("*"),
        *root.joinpath("maps").rglob("*"),
    ]
    h = hashlib.sha256()
    for f in sorted(p for p in files if p.is_file()):
        h.update(f.relative_to(root).as_posix().encode() + f.read_bytes())
    return h.hexdigest()[:16]


DOCKERFILE_CONTENT = r"""# Dockerfile for University Course on Navigation and ROS 2 Humble
FROM osrf/ros:humble-desktop-full

ENV DEBIAN_FRONTEND=noninteractive
ENV RCUTILS_COLORIZED_OUTPUT=1

# Install Navigation2, SLAM Toolbox, TurtleBot4 dependencies, and Ignition Gazebo
RUN echo "=== [1/3] Actualizando repositorios APT ===" && \
    apt-get update && \
    echo "=== [2/3] Instalando dependencias de ROS 2 y utilidades del sistema ===" && \
    apt-get install -y --no-install-recommends \
        --verbose-versions \
        -o Dpkg::Use-Pty=0 \
        ros-humble-navigation2 \
        ros-humble-nav2-bringup \
        ros-humble-slam-toolbox \
        ros-humble-robot-localization \
        ros-humble-turtlebot4-simulator \
        ros-humble-turtlebot4-desktop \
        ros-humble-turtlebot4-navigation \
        ros-humble-turtlebot4-description \
        ros-humble-turtlebot4-viz \
        ros-humble-irobot-create-nodes \
        ros-humble-teleop-twist-keyboard \
        ros-humble-joint-state-publisher-gui \
        ros-humble-xacro \
        ros-humble-twist-mux \
        ros-humble-controller-manager \
        ros-humble-ros2-control \
        ros-humble-ros2-controllers \
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

# Launch file sin dock, mundos (SDF) y mapas (YAML/PNG) de la asignatura
COPY turtlebot4_nodock.launch.py /opt/ros/humble/share/turtlebot4_ignition_bringup/launch/
COPY worlds/ /opt/ros/humble/share/turtlebot4_ignition_bringup/worlds/
COPY maps/ /opt/ros/humble/share/turtlebot4_navigation/maps/
# Eliminar panel HMI innecesario en la GUI de Gazebo
RUN sed -i '/<plugin filename=.*Hmi/,/<\/plugin>/d' /opt/ros/humble/share/turtlebot4_ignition_bringup/gui/*/gui.config
LABEL org.nav_course.assets_digest="@ASSETS_DIGEST@"

EXPOSE 6080
WORKDIR /ros2_ws

RUN echo "source /opt/ros/humble/setup.bash" >> /root/.bashrc \
    && echo "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi" >> /root/.bashrc

CMD ["/bin/bash"]
""".replace("@ASSETS_DIGEST@", _assets_digest())


def ensure_dockerfile_sync(workspace_dir: Path) -> Path:
    """
    Ensures the on-disk Dockerfile is in sync with DOCKERFILE_CONTENT.
    Returns the build directory path.
    """
    from docker_service import DockerService  # deferred to avoid circular imports

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
            effective_content = effective_content.replace(
                cmd_marker, f"{label_line}\n\n{cmd_marker}"
            )
        else:
            effective_content += f"\n{label_line}\n"

    try:
        current = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        if current.strip() != effective_content.strip():
            target_file.write_text(effective_content, encoding="utf-8")
        if build_dir != workspace_dir:
            src_root = Path(__file__).parent
            for item in ["turtlebot4_nodock.launch.py", "worlds", "maps"]:
                src = src_root / item
                dst = build_dir / item
                if src.is_file():
                    shutil.copy2(src, dst)
                elif src.is_dir():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
    except Exception as e:
        logger.warning("No se pudo sincronizar Dockerfile en %s: %s", target_file, e)

    return build_dir


# ---------------------------------------------------------------------------
# Student guide (Markdown content)
# ---------------------------------------------------------------------------

GUIDE_MARKDOWN = """# Guía de Simulación y Navegación ROS 2 Humble

Este entorno ejecuta **ROS 2 Humble**, **Ignition Gazebo** y **Navigation2 (Nav2)** dentro de un contenedor Docker con interfaz gráfica accesible directamente desde el navegador web (noVNC).

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
