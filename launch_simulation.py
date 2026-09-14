"""
Launcher de Simulación ROS 2 Jazzy para la Asignatura de Robótica Móvil
Interfaz gráfica moderna, nativa de alta resolución (High-DPI) y modular con PySide6 y Docker.
"""

import os
import re
import sys
import logging
import platform
import webbrowser
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, List

from PySide6 import QtCore, QtGui, QtWidgets

# --- Configuración del módulo logging estándar ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("launcher")

# --- Habilitar AppUserModelID en Windows para icono en barra de tareas ---
if platform.system().lower() == "windows":
    try:
        import ctypes
        app_id = "lasalle.sistemasdenavegacion.ros2launcher.v2"
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
from embedded_icon import get_app_icon_path

# Dockerfile de respaldo en caso de que no exista en el directorio
DOCKERFILE_CONTENT = r"""# Dockerfile for University Course on Navigation and ROS 2 Jazzy
FROM osrf/ros:jazzy-desktop-full

ENV DEBIAN_FRONTEND=noninteractive
ENV RCUTILS_COLORIZED_OUTPUT=1

# Install Navigation2, SLAM Toolbox, TurtleBot4, TIAGo dependencies, and Gazebo (ros_gz)
RUN apt-get update && apt-get install -y --no-install-recommends \
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
    && rm -rf /var/lib/apt/lists/*

ENV ROBOT_MODEL=turtlebot4
EXPOSE 6080
WORKDIR /ros2_ws

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc \
    && echo "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi" >> /root/.bashrc

CMD ["/bin/bash"]
"""

GUIDE_MARKDOWN = """# 📚 Guía de Simulación y Navegación ROS 2 Jazzy

Este entorno ejecuta **ROS 2 Jazzy**, **Gazebo Sim** y **Navigation2 (Nav2)** dentro de un contenedor Docker con interfaz gráfica accesible directamente desde el navegador web (noVNC).

---

### 🌐 1. Interfaz Gráfica Web (Gazebo y RViz2)
- No necesitas instalar servidores X11 (XQuartz o VcXsrv) en tu ordenador.
- Al iniciar la simulación, el navegador se abrirá automáticamente en:
  **`http://localhost:6080/vnc.html`**
- En esa pestaña interactuarás con el escritorio virtual con Gazebo Sim y RViz2.

---

### 💻 2. Terminal Docker Nativo (Windows Terminal / PowerShell)
- Pulsa el botón **"💻 Abrir Terminal Docker"** en la barra de acciones superior.
- Se abrirá automáticamente una ventana de terminal conectada al contenedor.
- El entorno de ROS 2 ya está cargado con los paquetes del sistema y tu workspace:
  - `ros2 topic list`
  - `ros2 run teleop_twist_keyboard teleop_twist_keyboard`
  - `ros2 topic echo /odom`

---

### 📁 3. Espacio de Trabajo (Workspace en Windows)
- La carpeta seleccionada en "Espacio de Trabajo" se monta automáticamente en:
  **`/ros2_ws/src`**
- Puedes editar tus paquetes y nodos de ROS 2 en Windows usando tu editor preferido (VS Code, etc.).
- Cualquier cambio en Windows se sincroniza instantáneamente con Docker.
- Para compilar tus paquetes, pulsa **"🔨 Compilar Workspace"** o escribe `colcon build` en la terminal.

---

### 🤖 4. Guía Rápida de Prácticas

#### A. Mapeo con SLAM Toolbox
1. Selecciona el escenario: **"Gazebo Sim + SLAM Toolbox (Modo mapeo)"**.
2. Pulsa **"🚀 Iniciar Simulación"**.
3. Abre una terminal con **"💻 Abrir Terminal Docker"** y pilota el robot:
   `ros2 run teleop_twist_keyboard teleop_twist_keyboard`
4. Una vez completado el mapa, guárdalo desde el plugin de SLAM en RViz2 o desde la terminal.

#### B. Navegación Autónoma con Nav2
1. Selecciona el escenario: **"Gazebo Sim + Nav2 (Navegación completa y RViz2)"**.
2. Pulsa **"🚀 Iniciar Simulación"**.
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
            self.proc = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True
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


# --- Ventana Principal del Launcher ---

class ModernSimulationLauncher(QtWidgets.QMainWindow):
    """Ventana principal del launcher con PySide6, High-DPI y estilo profesional moderno."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ROS 2 Jazzy - Launcher de Simulación (v{CURRENT_VERSION}) | Sistemas de Navegación")
        self.resize(1020, 680)
        self.setMinimumSize(880, 520)

        # Gestor de configuración persistente (guarda en AppData)
        self.config_store = ConfigStore(fallback_dir=Path(__file__).parent.resolve())
        self.active_sim_thread: Optional[ProcessRunnerThread] = None
        self.autoscroll_enabled = True
        self.ansi_parser = AnsiColorParser()
        self.latest_update_info: Optional[Dict] = None

        self._setup_window_icon()
        self._apply_global_styles()
        self._build_ui()
        self._load_saved_preferences()
        self._check_docker_live_status()

        # Comprobar actualizaciones en segundo plano a los 1.5s de arrancar
        QtCore.QTimer.singleShot(1500, self._check_for_updates_background)

    def _setup_window_icon(self):
        try:
            ico_path = get_app_icon_path()
            if ico_path and ico_path.is_file():
                app_icon = QtGui.QIcon(str(ico_path))
                self.setWindowIcon(app_icon)
                QtWidgets.QApplication.setWindowIcon(app_icon)
        except Exception as e:
            logger.warning("No se pudo configurar el icono de la ventana: %s", e)

    def _apply_global_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8fafc;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif;
            }
            QWidget {
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif;
                color: #0f172a;
            }
            /* Header */
            #headerFrame {
                background-color: #ffffff;
                border-bottom: 1px solid #e2e8f0;
                padding: 10px 18px;
            }
            #titleLabel {
                font-size: 15px;
                font-weight: 700;
                color: #1e3a8a;
            }
            #subtitleLabel {
                font-size: 11px;
                color: #64748b;
            }
            /* Cards */
            .QFrame[frameShape="1"] { /* StyledPanel */
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            /* Tab Widget */
            QTabWidget::pane {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background: #f1f5f9;
                color: #475569;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
                border: 1px solid #e2e8f0;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #2563eb;
                color: #ffffff;
                border-color: #2563eb;
            }
            QTabBar::tab:hover:!selected {
                background: #e2e8f0;
                color: #0f172a;
            }
            /* Inputs */
            QLineEdit, QComboBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                color: #1e293b;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #2563eb;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            /* Buttons */
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: 600;
                color: #1e293b;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
            QPushButton:pressed {
                background-color: #cbd5e1;
            }
            QPushButton:disabled {
                background-color: #f8fafc;
                color: #94a3b8;
                border-color: #f1f5f9;
            }
            /* Action Buttons Specific */
            #btnLaunch {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                font-weight: 700;
                padding: 9px 18px;
            }
            #btnLaunch:hover {
                background-color: #1d4ed8;
            }
            #btnTerminal {
                background-color: #0f172a;
                color: #ffffff;
                border: none;
                font-weight: 700;
                padding: 9px 14px;
            }
            #btnTerminal:hover {
                background-color: #1e293b;
            }
            #btnWeb {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                font-weight: 700;
                padding: 9px 14px;
            }
            #btnWeb:hover {
                background-color: #0369a1;
            }
            #btnStop {
                background-color: #dc2626;
                color: #ffffff;
                border: none;
                font-weight: 700;
                padding: 9px 14px;
            }
            #btnStop:hover {
                background-color: #b91c1c;
            }
            /* Progress Bar */
            QProgressBar {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                text-align: center;
                background-color: #ffffff;
                height: 16px;
                font-size: 10px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background-color: #2563eb;
                border-radius: 5px;
            }
        """)

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
        h_layout.setSpacing(12)

        left_box = QtWidgets.QVBoxLayout()
        left_box.setSpacing(1)

        title = QtWidgets.QLabel(f"🤖 ROS 2 Jazzy - Launcher de Simulación  (v{CURRENT_VERSION})")
        title.setObjectName("titleLabel")
        left_box.addWidget(title)

        sub = QtWidgets.QLabel("Sistemas de Navegación · Gazebo Sim & Navigation2 (Nav2)")
        sub.setObjectName("subtitleLabel")
        left_box.addWidget(sub)
        h_layout.addLayout(left_box)

        h_layout.addStretch()

        # Botón de versión / actualización
        self.btn_header_update = QtWidgets.QPushButton(f"v{CURRENT_VERSION}")
        self.btn_header_update.clicked.connect(self._on_header_update_clicked)
        self.btn_header_update.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        h_layout.addWidget(self.btn_header_update)

        # Badge de estado de Docker
        self.lbl_docker_badge = QtWidgets.QLabel("● Comprobando Docker...")
        self.lbl_docker_badge.setStyleSheet("""
            background-color: #fef3c7;
            color: #b45309;
            font-size: 11px;
            font-weight: 700;
            padding: 5px 10px;
            border-radius: 6px;
        """)
        h_layout.addWidget(self.lbl_docker_badge)

        btn_docker_refresh = QtWidgets.QPushButton("🔄 Docker")
        btn_docker_refresh.clicked.connect(self._check_docker_live_status)
        btn_docker_refresh.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        h_layout.addWidget(btn_docker_refresh)

        parent_layout.addWidget(header)

    def _build_action_bar(self, parent_layout: QtWidgets.QVBoxLayout):
        card = QtWidgets.QFrame()
        card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        c_layout = QtWidgets.QVBoxLayout(card)
        c_layout.setContentsMargins(14, 10, 14, 10)
        c_layout.setSpacing(8)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_launch = QtWidgets.QPushButton("🚀  Iniciar Simulación")
        self.btn_launch.setObjectName("btnLaunch")
        self.btn_launch.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_launch.clicked.connect(self._on_launch_simulation)
        btn_row.addWidget(self.btn_launch, 2)

        self.btn_terminal = QtWidgets.QPushButton("💻  Abrir Terminal Docker")
        self.btn_terminal.setObjectName("btnTerminal")
        self.btn_terminal.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_terminal.clicked.connect(self._on_open_terminal)
        btn_row.addWidget(self.btn_terminal, 1)

        self.btn_web = QtWidgets.QPushButton("🌐  Interfaz Web (noVNC)")
        self.btn_web.setObjectName("btnWeb")
        self.btn_web.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_web.clicked.connect(self._open_web_gui)
        btn_row.addWidget(self.btn_web, 1)

        self.btn_stop = QtWidgets.QPushButton("🛑  Detener Contenedor")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_stop.clicked.connect(self._on_stop_simulation)
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
        self.lbl_progress.setStyleSheet("font-size: 11px; color: #64748b;")
        prog_row.addWidget(self.lbl_progress)

        c_layout.addLayout(prog_row)
        parent_layout.addWidget(card)

    def _build_tabs(self, parent_layout: QtWidgets.QVBoxLayout):
        self.tab_widget = QtWidgets.QTabWidget()

        # 1. Configuración
        tab_config = QtWidgets.QWidget()
        self._build_config_tab(tab_config)
        self.tab_widget.addTab(tab_config, "🚀  Configuración de Simulación")

        # 2. Logs
        tab_logs = QtWidgets.QWidget()
        self._build_logs_tab(tab_logs)
        self.tab_widget.addTab(tab_logs, "📋  Salida y Logs")

        # 3. Comandos Rápidos
        tab_quick = QtWidgets.QWidget()
        self._build_quick_tab(tab_quick)
        self.tab_widget.addTab(tab_quick, "⚡  Comandos Rápidos")

        # 4. Ajustes Avanzados
        tab_advanced = QtWidgets.QWidget()
        self._build_advanced_tab(tab_advanced)
        self.tab_widget.addTab(tab_advanced, "⚙️  Ajustes Avanzados")

        # 5. Guía del Estudiante
        tab_guide = QtWidgets.QWidget()
        self._build_guide_tab(tab_guide)
        self.tab_widget.addTab(tab_guide, "📖  Guía del Estudiante")

        parent_layout.addWidget(self.tab_widget, 1)

    def _build_config_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # Tarjeta de Workspace
        ws_card = QtWidgets.QFrame()
        ws_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        ws_layout = QtWidgets.QVBoxLayout(ws_card)
        ws_layout.setContentsMargins(14, 12, 14, 12)
        ws_layout.setSpacing(8)

        ws_head = QtWidgets.QHBoxLayout()
        lbl_ws_title = QtWidgets.QLabel("📁 Espacio de Trabajo en Windows (Workspace)")
        lbl_ws_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #1e293b;")
        ws_head.addWidget(lbl_ws_title)
        ws_head.addStretch()
        lbl_saved = QtWidgets.QLabel("✓ Guardado en AppData")
        lbl_saved.setStyleSheet("font-size: 11px; color: #15803d; font-weight: 600;")
        ws_head.addWidget(lbl_saved)
        ws_layout.addLayout(ws_head)

        ws_input_row = QtWidgets.QHBoxLayout()
        self.ent_ws_path = QtWidgets.QLineEdit()
        self.ent_ws_path.textChanged.connect(self._on_workspace_path_edited)
        ws_input_row.addWidget(self.ent_ws_path, 1)

        btn_browse = QtWidgets.QPushButton("📂 Explorar...")
        btn_browse.clicked.connect(self._on_browse_workspace)
        ws_input_row.addWidget(btn_browse)
        ws_layout.addLayout(ws_input_row)

        ws_feedback = QtWidgets.QHBoxLayout()
        self.lbl_ws_status = QtWidgets.QLabel("Validando ruta...")
        self.lbl_ws_status.setStyleSheet("font-size: 11px; color: #64748b;")
        ws_feedback.addWidget(self.lbl_ws_status)
        ws_feedback.addStretch()

        lbl_ws_note = QtWidgets.QLabel("Se monta como volumen en /ros2_ws/src en el contenedor.")
        lbl_ws_note.setStyleSheet("font-size: 11px; font-style: italic; color: #94a3b8;")
        ws_feedback.addWidget(lbl_ws_note)
        ws_layout.addLayout(ws_feedback)

        layout.addWidget(ws_card)

        # Tarjeta de Parámetros de Simulación
        param_card = QtWidgets.QFrame()
        param_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        p_layout = QtWidgets.QVBoxLayout(param_card)
        p_layout.setContentsMargins(14, 12, 14, 12)
        p_layout.setSpacing(10)

        lbl_param_title = QtWidgets.QLabel("⚙️ Parámetros de Simulación y Navegación")
        lbl_param_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #1e293b;")
        p_layout.addWidget(lbl_param_title)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        # Fila 0: Robot y Mundo
        grid.addWidget(QtWidgets.QLabel("Modelo de Robot:"), 0, 0)
        self.cbo_robot = QtWidgets.QComboBox()
        for r in get_all_robots():
            self.cbo_robot.addItem(r.name)
        self.cbo_robot.currentIndexChanged.connect(self._on_robot_changed)
        grid.addWidget(self.cbo_robot, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Mundo Gazebo:"), 0, 2)
        self.cbo_world = QtWidgets.QComboBox()
        self.cbo_world.currentIndexChanged.connect(self._save_current_settings)
        grid.addWidget(self.cbo_world, 0, 3)

        # Fila 1: Escenario y ROS_DOMAIN_ID
        grid.addWidget(QtWidgets.QLabel("Escenario:"), 1, 0)
        self.cbo_scenario = QtWidgets.QComboBox()
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
        self.scenario_desc_frame.setStyleSheet("""
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 8px 12px;
        """)
        desc_layout = QtWidgets.QHBoxLayout(self.scenario_desc_frame)
        desc_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_scenario_desc = QtWidgets.QLabel("")
        self.lbl_scenario_desc.setStyleSheet("font-size: 11px; font-style: italic; color: #475569;")
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

        btn_scroll_bottom = QtWidgets.QPushButton("⬇ Ir al final")
        btn_scroll_bottom.clicked.connect(self._scroll_to_bottom)
        ctrl_bar.addWidget(btn_scroll_bottom)

        btn_clear = QtWidgets.QPushButton("🧹 Limpiar logs")
        btn_clear.clicked.connect(self._clear_logs)
        ctrl_bar.addWidget(btn_clear)

        layout.addLayout(ctrl_bar)

        # Consola de texto oscura
        self.txt_logs = QtWidgets.QPlainTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setMaximumBlockCount(10000)
        self.txt_logs.setStyleSheet("""
            QPlainTextEdit {
                background-color: #18181b;
                color: #e4e4e7;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 10px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.txt_logs, 1)

    def _build_quick_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        lbl_intro = QtWidgets.QLabel("Ejecuta comandos de inspección y control directamente en el contenedor:")
        lbl_intro.setStyleSheet("font-size: 12px; font-weight: 700; color: #1e293b;")
        layout.addWidget(lbl_intro)

        # Grid de botones rápidos
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)

        btn_topics = QtWidgets.QPushButton("📡 Listar Tópicos (ros2 topic list)")
        btn_topics.clicked.connect(lambda: self._execute_quick_command("ros2 topic list"))
        grid.addWidget(btn_topics, 0, 0)

        btn_nodes = QtWidgets.QPushButton("🧩 Listar Nodos (ros2 node list)")
        btn_nodes.clicked.connect(lambda: self._execute_quick_command("ros2 node list"))
        grid.addWidget(btn_nodes, 0, 1)

        btn_topics_info = QtWidgets.QPushButton("🔍 Tópicos con tipo (ros2 topic list -t)")
        btn_topics_info.clicked.connect(lambda: self._execute_quick_command("ros2 topic list -t"))
        grid.addWidget(btn_topics_info, 1, 0)

        btn_compile = QtWidgets.QPushButton("🔨 Compilar Workspace (colcon build)")
        btn_compile.clicked.connect(self._on_compile_workspace)
        grid.addWidget(btn_compile, 1, 1)

        layout.addLayout(grid)

        # Entrada para comando personalizado
        custom_card = QtWidgets.QFrame()
        custom_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        c_layout = QtWidgets.QVBoxLayout(custom_card)
        c_layout.setContentsMargins(14, 12, 14, 12)
        c_layout.setSpacing(8)

        lbl_custom = QtWidgets.QLabel("Comando ROS 2 Personalizado:")
        lbl_custom.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155;")
        c_layout.addWidget(lbl_custom)

        custom_row = QtWidgets.QHBoxLayout()
        self.ent_custom_cmd = QtWidgets.QLineEdit("ros2 topic list")
        self.ent_custom_cmd.returnPressed.connect(self._on_run_custom_command)
        custom_row.addWidget(self.ent_custom_cmd, 1)

        btn_run_custom = QtWidgets.QPushButton("▶ Ejecutar")
        btn_run_custom.setStyleSheet("background-color: #2563eb; color: #ffffff; font-weight: 700;")
        btn_run_custom.clicked.connect(self._on_run_custom_command)
        custom_row.addWidget(btn_run_custom)
        c_layout.addLayout(custom_row)

        lbl_custom_note = QtWidgets.QLabel("La salida del comando se imprimirá en directo en la pestaña 'Salida y Logs'.")
        lbl_custom_note.setStyleSheet("font-size: 11px; font-style: italic; color: #64748b;")
        c_layout.addWidget(lbl_custom_note)

        layout.addWidget(custom_card)
        layout.addStretch()

    def _build_advanced_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # Fila Puerto Web noVNC
        row_port = QtWidgets.QHBoxLayout()
        lbl_port = QtWidgets.QLabel("Puerto Servidor Web noVNC:")
        lbl_port.setFixedWidth(210)
        row_port.addWidget(lbl_port)
        self.ent_web_port = QtWidgets.QLineEdit()
        self.ent_web_port.setFixedWidth(90)
        self.ent_web_port.textChanged.connect(self._save_current_settings)
        row_port.addWidget(self.ent_web_port)
        lbl_port_note = QtWidgets.QLabel("(Por defecto: 6080 -> http://localhost:6080/vnc.html)")
        lbl_port_note.setStyleSheet("font-size: 11px; font-style: italic; color: #64748b;")
        row_port.addWidget(lbl_port_note)
        row_port.addStretch()
        layout.addLayout(row_port)

        # Fila Argumentos Extra
        row_args = QtWidgets.QHBoxLayout()
        lbl_args = QtWidgets.QLabel("Argumentos extra para ROS 2:")
        lbl_args.setFixedWidth(210)
        row_args.addWidget(lbl_args)
        self.ent_extra_args = QtWidgets.QLineEdit()
        self.ent_extra_args.textChanged.connect(self._save_current_settings)
        row_args.addWidget(self.ent_extra_args, 1)
        layout.addLayout(row_args)

        # Checkbox recompilación
        self.chk_force_rebuild = QtWidgets.QCheckBox("Forzar recompilación completa con colcon en cada inicio de simulación")
        self.chk_force_rebuild.stateChanged.connect(self._save_current_settings)
        layout.addWidget(self.chk_force_rebuild)

        # Tarjeta Mantenimiento Docker
        maint_card = QtWidgets.QFrame()
        maint_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        m_layout = QtWidgets.QVBoxLayout(maint_card)
        m_layout.setContentsMargins(14, 12, 14, 12)
        m_layout.setSpacing(10)

        lbl_maint = QtWidgets.QLabel("Mantenimiento de Docker y Caché:")
        lbl_maint.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155;")
        m_layout.addWidget(lbl_maint)

        maint_row = QtWidgets.QHBoxLayout()
        self.btn_prep_image = QtWidgets.QPushButton("📦 Reconstruir / Preparar Imagen Docker")
        self.btn_prep_image.clicked.connect(self._on_pull_or_build_image)
        maint_row.addWidget(self.btn_prep_image)

        btn_clean_cache = QtWidgets.QPushButton("🧹 Limpiar Volúmenes de Caché")
        btn_clean_cache.clicked.connect(self._on_clean_build_cache)
        maint_row.addWidget(btn_clean_cache)
        maint_row.addStretch()
        m_layout.addLayout(maint_row)

        layout.addWidget(maint_card)

        # Tarjeta Actualizaciones GitHub
        upd_card = QtWidgets.QFrame()
        upd_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        u_layout = QtWidgets.QVBoxLayout(upd_card)
        u_layout.setContentsMargins(14, 12, 14, 12)
        u_layout.setSpacing(10)

        lbl_upd = QtWidgets.QLabel("Actualizaciones del Software (GitHub):")
        lbl_upd.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155;")
        u_layout.addWidget(lbl_upd)

        upd_row = QtWidgets.QHBoxLayout()
        lbl_inst = QtWidgets.QLabel(f"Versión instalada: v{CURRENT_VERSION}")
        lbl_inst.setStyleSheet("font-weight: 600;")
        upd_row.addWidget(lbl_inst)

        self.btn_check_updates = QtWidgets.QPushButton("🔄 Comprobar actualizaciones")
        self.btn_check_updates.clicked.connect(self._on_manual_check_updates)
        upd_row.addWidget(self.btn_check_updates)

        self.lbl_update_status = QtWidgets.QLabel("Comprobando al iniciar...")
        self.lbl_update_status.setStyleSheet("font-size: 11px; font-style: italic; color: #64748b;")
        upd_row.addWidget(self.lbl_update_status)
        upd_row.addStretch()
        u_layout.addLayout(upd_row)

        layout.addWidget(upd_card)

        # Ruta en AppData
        lbl_appdata = QtWidgets.QLabel(f"Archivo de configuración: {self.config_store.config_path}")
        lbl_appdata.setStyleSheet("font-size: 11px; color: #94a3b8;")
        layout.addWidget(lbl_appdata)
        layout.addStretch()

    def _build_guide_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(14, 12, 14, 12)

        txt_guide = QtWidgets.QTextBrowser()
        txt_guide.setMarkdown(GUIDE_MARKDOWN)
        txt_guide.setStyleSheet("""
            QTextBrowser {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 16px;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        layout.addWidget(txt_guide)

    # --- Persistencia y Carga de Configuraciones ---

    def _load_saved_preferences(self):
        # 1. Workspace
        saved_ws = self.config_store.get("workspace_path")
        self.ent_ws_path.setText(saved_ws)
        self._update_workspace_validation()

        # 2. Robot
        saved_robot_id = self.config_store.get("robot_id", "turtlebot4")
        robot_profile = get_robot_by_id(saved_robot_id) or get_all_robots()[0]
        self.cbo_robot.setCurrentText(robot_profile.name)
        self._update_worlds_and_scenarios(robot_profile)

        # 3. Mundo
        saved_world = self.config_store.get("world_name", "warehouse")
        idx_w = self.cbo_world.findText(saved_world)
        if idx_w >= 0:
            self.cbo_world.setCurrentIndex(idx_w)

        # 4. Escenario
        saved_sc = self.config_store.get("scenario_id", "nav2")
        sc_obj = robot_profile.get_scenario_by_id(saved_sc)
        if sc_obj:
            idx_s = self.cbo_scenario.findText(sc_obj.name)
            if idx_s >= 0:
                self.cbo_scenario.setCurrentIndex(idx_s)
        self._on_scenario_changed()

        # 5. Domain ID, Puerto, Args
        self.ent_domain_id.setText(str(self.config_store.get("ros_domain_id", "42")))
        self.ent_web_port.setText(str(self.config_store.get("web_port", str(DEFAULT_NOVNC_PORT))))
        self.ent_extra_args.setText(str(self.config_store.get("extra_args", "use_sim_time:=true")))
        self.chk_force_rebuild.setChecked(bool(self.config_store.get("force_rebuild", False)))

    def _save_current_settings(self):
        selected_robot_name = self.cbo_robot.currentText()
        robot_profile = get_robot_by_name(selected_robot_name)
        robot_id = robot_profile.id if robot_profile else "turtlebot4"

        selected_scenario_name = self.cbo_scenario.currentText()
        scenario_id = "nav2"
        if robot_profile:
            sc_obj = robot_profile.get_scenario_by_name(selected_scenario_name)
            if sc_obj:
                scenario_id = sc_obj.id

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
        path_str = self.ent_ws_path.text().strip()
        is_valid, msg = ConfigStore.validate_workspace(path_str)
        if is_valid:
            if "detectado" in msg:
                self.lbl_ws_status.setText(f"✓ {msg}")
                self.lbl_ws_status.setStyleSheet("font-size: 11px; color: #15803d; font-weight: 600;")
            else:
                self.lbl_ws_status.setText(f"✓ {msg}")
                self.lbl_ws_status.setStyleSheet("font-size: 11px; color: #1e293b;")
        else:
            self.lbl_ws_status.setText(f"⚠ {msg}")
            self.lbl_ws_status.setStyleSheet("font-size: 11px; color: #dc2626; font-weight: 600;")

    def _on_robot_changed(self):
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
        selected_robot_name = self.cbo_robot.currentText()
        robot_profile = get_robot_by_name(selected_robot_name)
        if robot_profile:
            scenario_name = self.cbo_scenario.currentText()
            sc_obj = robot_profile.get_scenario_by_name(scenario_name)
            if sc_obj:
                self.lbl_scenario_desc.setText(f"ℹ {sc_obj.description}")
            else:
                self.lbl_scenario_desc.setText("")
        self._save_current_settings()

    def _check_docker_live_status(self):
        self.lbl_docker_badge.setText("● Comprobando Docker...")
        self.lbl_docker_badge.setStyleSheet("""
            background-color: #fef3c7; color: #b45309; font-size: 11px; font-weight: 700;
            padding: 5px 10px; border-radius: 6px;
        """)

        def _worker():
            installed, _ = DockerService.check_docker_installed()
            if not installed:
                QtCore.QMetaObject.invokeMethod(
                    self, "_set_docker_badge", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "❌ Docker no encontrado"),
                    QtCore.Q_ARG(str, "#fee2e2"),
                    QtCore.Q_ARG(str, "#b91c1c")
                )
                return

            running, daemon_msg = DockerService.check_docker_running()
            if running:
                QtCore.QMetaObject.invokeMethod(
                    self, "_set_docker_badge", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, f"● {daemon_msg}"),
                    QtCore.Q_ARG(str, "#dcfce7"),
                    QtCore.Q_ARG(str, "#15803d")
                )
            else:
                QtCore.QMetaObject.invokeMethod(
                    self, "_set_docker_badge", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "⚠️ Docker detenido"),
                    QtCore.Q_ARG(str, "#fef3c7"),
                    QtCore.Q_ARG(str, "#b45309")
                )

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(str, str, str)
    def _set_docker_badge(self, text: str, bg_color: str, fg_color: str):
        self.lbl_docker_badge.setText(text)
        self.lbl_docker_badge.setStyleSheet(f"""
            background-color: {bg_color}; color: {fg_color}; font-size: 11px; font-weight: 700;
            padding: 5px 10px; border-radius: 6px;
        """)

    # --- Actualizaciones Automáticas ---

    def _on_header_update_clicked(self):
        if self.latest_update_info:
            self._prompt_update_available(self.latest_update_info)
        else:
            self._on_manual_check_updates()

    def _check_for_updates_background(self):
        def _worker():
            has_update, info, msg = check_for_updates(timeout=2.5)
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
        self.btn_header_update.setText(f"✨ Actualizar a v{ver}")
        self.btn_header_update.setStyleSheet("""
            background-color: #16a34a; color: #ffffff; font-weight: 700;
            padding: 4px 10px; font-size: 11px; border-radius: 6px;
        """)
        self.lbl_update_status.setText(f"Nueva versión v{ver} disponible")
        self.lbl_update_status.setStyleSheet("font-size: 11px; color: #16a34a; font-weight: 600;")
        if self.latest_update_info:
            self._prompt_update_available(self.latest_update_info)

    def _prompt_update_available(self, update_info: dict):
        target_dir = Path(__file__).parent.resolve()
        dialog = UpdateModalDialog(self, update_info, target_dir)
        dialog.exec()

    def _on_manual_check_updates(self):
        self.btn_check_updates.setEnabled(False)
        self.lbl_update_status.setText("Buscando nueva versión en GitHub...")
        self.lbl_update_status.setStyleSheet("font-size: 11px; color: #64748b; font-style: italic;")

        def _worker():
            has_update, info, msg = check_for_updates(timeout=3.5)
            QtCore.QMetaObject.invokeMethod(
                self, "_on_manual_update_result", QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(bool, has_update),
                QtCore.Q_ARG(object, info),
                QtCore.Q_ARG(str, msg)
            )

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(bool, object, str)
    def _on_manual_update_result(self, has_update: bool, info: Optional[Dict], msg: str):
        self.btn_check_updates.setEnabled(True)
        if has_update and info:
            ver = info.get("version", "")
            self.latest_update_info = info
            self.btn_header_update.setText(f"✨ Actualizar a v{ver}")
            self.btn_header_update.setStyleSheet("""
                background-color: #16a34a; color: #ffffff; font-weight: 700;
                padding: 4px 10px; font-size: 11px; border-radius: 6px;
            """)
            self.lbl_update_status.setText(f"Nueva versión v{ver} disponible")
            self.lbl_update_status.setStyleSheet("font-size: 11px; color: #16a34a; font-weight: 600;")
            self._prompt_update_available(info)
        elif info:
            self.latest_update_info = None
            self.lbl_update_status.setText(f"Al día (v{CURRENT_VERSION})")
            self.lbl_update_status.setStyleSheet("font-size: 11px; color: #15803d;")
            QtWidgets.QMessageBox.information(
                self,
                "Actualizaciones",
                f"¡Ya tienes instalada la versión más reciente (v{CURRENT_VERSION})!"
            )
        else:
            self.latest_update_info = None
            self.lbl_update_status.setText(msg)
            self.lbl_update_status.setStyleSheet("font-size: 11px; color: #dc2626;")
            QtWidgets.QMessageBox.warning(self, "Actualizaciones", msg)

    # --- Acciones Principales: Terminal Docker, Simulación, Web ---

    def _open_web_gui(self):
        port = self.ent_web_port.text().strip() or str(DEFAULT_NOVNC_PORT)
        url = f"http://localhost:{port}/vnc.html?autoconnect=true&resize=scale"
        webbrowser.open(url)

    def _on_open_terminal(self):
        def _worker():
            if not DockerService.is_container_running(DEFAULT_CONTAINER_NAME):
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
            "¿Deseas iniciar una sesión de contenedor ahora para abrir la terminal?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self._launch_interactive_shell_container()

    def _launch_interactive_shell_container(self):
        image_name = COURSE_IMAGE_NAME
        running, _ = DockerService.check_docker_running()
        if not running:
            QtWidgets.QMessageBox.critical(self, "Docker", "Docker Desktop no está en ejecución.")
            return

        self.tab_widget.setCurrentIndex(1)  # Tab Logs
        self._append_log("\nIniciando contenedor en modo terminal...\n")

        ws_path = self.ent_ws_path.text().strip()
        domain_id = self.ent_domain_id.text().strip() or "42"
        web_port = self.ent_web_port.text().strip() or str(DEFAULT_NOVNC_PORT)

        DockerService.stop_container(DEFAULT_CONTAINER_NAME)

        docker_cmd = [
            "docker", "run", "-d", "--rm",
            "--name", DEFAULT_CONTAINER_NAME,
            "-p", f"{web_port}:6080",
            "-e", f"ROS_DOMAIN_ID={domain_id}",
            "-e", "RCUTILS_COLORIZED_OUTPUT=1",
            "-v", "ros2_jazzy_build_cache:/ros2_ws/build",
            "-v", "ros2_jazzy_install_cache:/ros2_ws/install",
            "-v", "ros2_jazzy_log_cache:/ros2_ws/log",
        ]

        if ws_path and os.path.exists(ws_path):
            norm_path = Path(ws_path).resolve().as_posix()
            docker_cmd.extend(["-v", f"{norm_path}:/ros2_ws/src:rw"])

        docker_cmd.extend([image_name, "tail", "-f", "/dev/null"])

        try:
            subprocess.run(docker_cmd, check=True)
            self._append_log("Contenedor iniciado con éxito en segundo plano.\n")
            DockerService.open_container_terminal(DEFAULT_CONTAINER_NAME)
        except Exception as e:
            self._append_log(f"Error al iniciar contenedor: {e}\n")

    def _on_launch_simulation(self):
        image_name = COURSE_IMAGE_NAME
        running, err = DockerService.check_docker_running()
        if not running:
            QtWidgets.QMessageBox.critical(
                self,
                "Error de Docker",
                f"Docker no está en ejecución:\n\n{err}\n\nPor favor inicia Docker Desktop primero."
            )
            return

        self._save_current_settings()
        self.tab_widget.setCurrentIndex(1)  # Tab Logs
        self._append_log("\n" + "="*50 + "\nIniciando simulación de ROS 2...\n" + "="*50 + "\n")

        def _worker():
            if not DockerService.is_image_available(image_name):
                self._append_log(f"Imagen '{image_name}' no encontrada localmente. Iniciando preparación...\n")
                self._on_pull_or_build_image()
                return

            DockerService.stop_container(DEFAULT_CONTAINER_NAME)

            selected_robot_name = self.cbo_robot.currentText()
            robot_profile = get_robot_by_name(selected_robot_name) or get_all_robots()[0]

            selected_scenario_name = self.cbo_scenario.currentText()
            scenario_obj = robot_profile.get_scenario_by_name(selected_scenario_name)
            scenario_id = scenario_obj.id if scenario_obj else "nav2"

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
            QtCore.QTimer.singleShot(2500, self._open_web_gui)

            self.active_sim_thread = ProcessRunnerThread(docker_cmd)
            self.active_sim_thread.signals.line_received.connect(self._append_log)
            self.active_sim_thread.signals.finished.connect(
                lambda rc: self._append_log(f"\n[El proceso de simulación finalizó con código de salida {rc}]\n")
            )
            self.active_sim_thread.signals.error.connect(
                lambda err: self._append_log(f"\n[Error durante la ejecución: {err}]\n")
            )
            self.active_sim_thread.start()

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stop_simulation(self):
        self.tab_widget.setCurrentIndex(1)  # Logs
        def _worker():
            self._append_log("\nDeteniendo contenedor de simulación...\n")
            ok, msg = DockerService.stop_container(DEFAULT_CONTAINER_NAME)
            self._append_log(f"{msg}\n")
            if ok:
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_info_box", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "Simulación"),
                    QtCore.Q_ARG(str, "Contenedor detenido correctamente.")
                )
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

        def _worker():
            proc = DockerService.execute_in_container_stream(DEFAULT_CONTAINER_NAME, cmd_str, self._append_log)
            if proc:
                for line in iter(proc.stdout.readline, ''):
                    self._append_log(line)
                proc.stdout.close()
                rc = proc.wait()
                self._append_log(f"\n[Comando finalizado con código {rc}]\n")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_run_custom_command(self):
        cmd = self.ent_custom_cmd.text().strip()
        if cmd:
            self._execute_quick_command(cmd)

    def _on_compile_workspace(self):
        image_name = COURSE_IMAGE_NAME
        running, err = DockerService.check_docker_running()
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

            runner = ProcessRunnerThread(build_cmd)
            runner.signals.line_received.connect(self._append_log)
            runner.signals.finished.connect(self._on_compile_finished)
            runner.start()

        threading.Thread(target=_worker, daemon=True).start()

    def _on_compile_finished(self, rc: int):
        if rc == 0:
            self._append_log("\n✅ [Compilación exitosa]\n")
            QtWidgets.QMessageBox.information(self, "Compilación", "Workspace compilado correctamente.")
        else:
            self._append_log(f"\n❌ [Compilación con errores (código {rc})]\n")
            QtWidgets.QMessageBox.critical(self, "Compilación", f"La compilación terminó con código de error {rc}.")

    def _on_clean_build_cache(self):
        answer = QtWidgets.QMessageBox.question(
            self,
            "Limpiar Caché",
            "¿Deseas eliminar la caché de compilación de Docker?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        self._append_log("\nLimpiando volúmenes de caché...\n")
        ok, msg = DockerService.clean_build_volumes()
        self._append_log(f"{msg}\n")
        if ok:
            QtWidgets.QMessageBox.information(self, "Caché", msg)

    def _on_pull_or_build_image(self):
        image_name = COURSE_IMAGE_NAME
        self.tab_widget.setCurrentIndex(1)  # Logs
        self._append_log(f"\n--- Preparando imagen de la asignatura: {image_name} ---\n")

        self.btn_prep_image.setEnabled(False)
        self._set_progress(-1, "Comprobando imagen...")

        workspace_dir = Path(__file__).parent.resolve()
        dockerfile_root = workspace_dir / "Dockerfile"
        if dockerfile_root.exists():
            build_dir = workspace_dir
        else:
            build_dir = workspace_dir / ".docker_build"
            build_dir.mkdir(parents=True, exist_ok=True)
            with open(build_dir / "Dockerfile", "w", encoding="utf-8") as f:
                f.write(DOCKERFILE_CONTENT)

        def _worker():
            self._append_log(f"Construyendo imagen desde: {build_dir}\n")
            success, msg = DockerService.build_image_stream(
                str(build_dir),
                image_name,
                lambda pct, txt: QtCore.QMetaObject.invokeMethod(
                    self, "_set_progress", QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(float, pct),
                    QtCore.Q_ARG(str, txt)
                ),
                self._append_log
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
        if success:
            self._append_log(f"\n✅ ÉXITO: {msg}\n")
            QtWidgets.QMessageBox.information(self, "Imagen", f"Imagen '{COURSE_IMAGE_NAME}' lista.")
        else:
            self._append_log(f"\n❌ ERROR: {msg}\n")
            QtWidgets.QMessageBox.critical(self, "Error", f"Error al preparar imagen:\n{msg}")

    # --- Consola de Logs y Control de Auto-Scroll ---

    @QtCore.Slot(str)
    def _append_log(self, text: str):
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

    def closeEvent(self, event: QtGui.QCloseEvent):
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


def main():
    # Inicializar aplicación Qt
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("ROS 2 Simulation Launcher")
    app.setOrganizationName("La Salle URL")

    # Configurar icono nativo de aplicación
    try:
        ico_path = get_app_icon_path()
        if ico_path and ico_path.is_file():
            app.setWindowIcon(QtGui.QIcon(str(ico_path)))
    except Exception:
        pass

    window = ModernSimulationLauncher()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
