"""
Launcher de Simulación ROS 2 Jazzy para la Asignatura de Robótica Móvil
Interfaz gráfica moderna, nativa de alta resolución (High-DPI) y modular con Tkinter y Docker.
"""

import os
import sys
import logging
import platform
import threading
import webbrowser
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from pathlib import Path
from typing import Optional, Dict

# --- Configuración del módulo logging estándar ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("launcher")

# --- Habilitar High-DPI y AppUserModelID en Windows ---
if platform.system().lower() == "windows":
    import ctypes
    try:
        # Per-Monitor DPI aware (Windows 10/11)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    try:
        # Identificador explícito de aplicación para Windows Taskbar:
        # Permite que la barra de tareas de Windows muestre el icono personalizado de la app
        # en lugar de agruparla bajo python.exe con el icono genérico de Python.
        app_id = "lasalle.sistemasdenavegacion.ros2launcher.v1"
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


def create_flat_button(
    parent,
    text: str,
    bg: str,
    hover_bg: str,
    fg: str = "white",
    command=None,
    font=("Segoe UI", 9, "bold"),
    padx=12,
    pady=6
) -> tk.Button:
    """Crea un botón plano moderno con hover effect y cursor hand2, sin bordes 3D retro."""
    btn = tk.Button(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        activebackground=hover_bg,
        activeforeground=fg,
        font=font,
        relief="flat",
        bd=0,
        padx=padx,
        pady=pady,
        cursor="hand2",
        command=command
    )
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover_bg) if str(btn["state"]) != "disabled" else None)
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg) if str(btn["state"]) != "disabled" else None)
    return btn


class ModernSimulationLauncher:
    """Aplicación principal con interfaz moderna, nítida y desacoplada."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"ROS 2 Jazzy - Launcher de Simulación (v{CURRENT_VERSION}) | Sistemas de Navegación")
        # Dimensiones optimizadas para portátiles de 14" (1080p con 150% de escalado)
        self.root.geometry("1000x620")
        self.root.minsize(850, 480)

        # Configurar icono de la aplicación (barra de tareas y esquina de ventana)
        self._setup_window_icon()

        # Gestor de configuración persistente (guarda en AppData)
        self.config_store = ConfigStore(fallback_dir=Path(__file__).parent.resolve())

        self.host_os = DockerService.get_host_os()
        self.active_simulation_proc: Optional[subprocess.Popen] = None
        self._autoscroll_enabled = True
        self._current_ansi_tags = []
        self._latest_update_info: Optional[Dict] = None

        # Estructura de pestañas personalizadas modernas
        self.tabs_dict: Dict[str, tk.Frame] = {}
        self.tab_buttons: Dict[str, tk.Button] = {}
        self.current_tab_name = "config"

        self._init_styles()
        self._build_layout()
        self._load_saved_preferences()
        self._check_docker_live_status()
        self.root.after(1500, self._check_for_updates_background)

    def _setup_window_icon(self):
        """Configura el icono nativo de la ventana (esquina superior) y barra de tareas de Windows."""
        try:
            ico_path = get_app_icon_path()
            if ico_path and ico_path.is_file():
                self.root.iconbitmap(default=str(ico_path))
                self.root.iconbitmap(str(ico_path))
                logger.info(f"Icono de aplicación (.ico) configurado exitosamente: {ico_path}")

                # Refuerzo nativo Win32: enviar explícitamente WM_SETICON y actualizar Class Icon
                if platform.system().lower() == "windows":
                    try:
                        import ctypes
                        user32 = ctypes.windll.user32
                        WM_SETICON = 0x80
                        IMAGE_ICON = 1
                        LR_LOADFROMFILE = 0x10
                        GA_ROOT = 2

                        self.root.update_idletasks()
                        hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
                        if hwnd:
                            h_small = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                            h_big = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                            if h_small:
                                user32.SendMessageW(hwnd, WM_SETICON, 0, h_small)  # ICON_SMALL
                                try:
                                    user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
                                    user32.SetClassLongPtrW(hwnd, -34, h_small)      # GCLP_HICONSM
                                except Exception:
                                    pass
                            if h_big:
                                user32.SendMessageW(hwnd, WM_SETICON, 1, h_big)    # ICON_BIG
                                try:
                                    user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
                                    user32.SetClassLongPtrW(hwnd, -14, h_big)        # GCLP_HICON
                                except Exception:
                                    pass
                    except Exception as win_err:
                        logger.debug(f"Ajuste Win32 WM_SETICON omitido: {win_err}")
        except Exception as e:
            logger.warning(f"No se pudo configurar el icono de la ventana: {e}")

    def _init_styles(self):
        """Configura el tema nativo de Windows (vista) y paleta de colores limpia."""
        style = ttk.Style()
        # Usar el tema nativo de Windows para inputs limpios y modernos (evita el aspecto retro de 'clam')
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "winnative" in style.theme_names():
            style.theme_use("winnative")
        else:
            style.theme_use("default")

        # Paleta moderna Slate
        self.bg_color = "#f8fafc"        # Slate 50
        self.card_bg = "#ffffff"         # Blanco puro
        self.border_color = "#e2e8f0"    # Slate 200
        self.primary_color = "#2563eb"   # Azul moderno (Indigo)
        self.primary_hover = "#1d4ed8"
        self.success_color = "#16a34a"   # Verde
        self.danger_color = "#dc2626"    # Rojo
        self.text_main = "#0f172a"       # Slate 900
        self.text_muted = "#64748b"      # Slate 500

        self.root.configure(bg=self.bg_color)

    def _build_layout(self):
        """Construye la distribución por pestañas limpias sin sobrecarga vertical."""
        # 1. Cabecera principal con estado en vivo
        self._build_header()

        # Contenedor principal con espaciado equilibrado
        main_container = tk.Frame(self.root, bg=self.bg_color)
        main_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))

        # 2. Barra de Acciones Rápidas fija arriba (siempre accesible desde cualquier pestaña)
        self._build_action_bar_card(main_container)

        # 3. Panel de Pestañas Principal (Configuración, Logs, Comandos Rápidos, Ajustes, Guía)
        self._build_modern_tabs(main_container)

    def _build_header(self):
        """Barra superior compacta con logo, título e indicador dinámico de Docker."""
        header_frame = tk.Frame(self.root, bg="#ffffff", padx=16, pady=8, highlightbackground=self.border_color, highlightthickness=1)
        header_frame.pack(fill=tk.X, pady=(0, 8))

        left_box = tk.Frame(header_frame, bg="#ffffff")
        left_box.pack(side=tk.LEFT)

        title_lbl = tk.Label(
            left_box,
            text=f"🤖 ROS 2 Jazzy - Launcher de Simulación  (v{CURRENT_VERSION})",
            font=("Segoe UI", 11, "bold"),
            bg="#ffffff",
            fg="#1e3a8a"
        )
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(
            left_box,
            text="Sistemas de Navegación · Gazebo Sim & Navigation2 (Nav2)",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg=self.text_muted
        )
        sub_lbl.pack(anchor="w")

        # Indicador de estado a la derecha
        right_box = tk.Frame(header_frame, bg="#ffffff")
        right_box.pack(side=tk.RIGHT)

        # Botón de actualización del launcher en la cabecera (visible y directo)
        self.btn_header_update = create_flat_button(
            right_box,
            text=f"v{CURRENT_VERSION}",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#475569",
            command=self._on_header_update_click,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3
        )
        self.btn_header_update.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_docker_badge = tk.Label(
            right_box,
            text="● Comprobando Docker...",
            bg="#fef3c7",
            fg="#b45309",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=3,
            relief="flat"
        )
        self.lbl_docker_badge.pack(side=tk.LEFT, padx=(0, 6))

        btn_refresh_docker = create_flat_button(
            right_box,
            text="🔄 Docker",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#334155",
            command=self._check_docker_live_status,
            font=("Segoe UI", 8),
            padx=8,
            pady=3
        )
        btn_refresh_docker.pack(side=tk.LEFT)


    def _build_workspace_card(self, parent):
        """Tarjeta para la selección y validación del workspace en Windows montado en Docker."""
        card = tk.Frame(parent, bg=self.card_bg, padx=16, pady=12, highlightbackground=self.border_color, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        top_row = tk.Frame(card, bg=self.card_bg)
        top_row.pack(fill=tk.X)

        title = tk.Label(
            top_row,
            text="📁 Espacio de Trabajo en Windows (Workspace)",
            font=("Segoe UI", 10, "bold"),
            bg=self.card_bg,
            fg="#1e293b"
        )
        title.pack(side=tk.LEFT)

        saved_tag = tk.Label(
            top_row,
            text="✓ Guardado en AppData (Persistente)",
            font=("Segoe UI", 8),
            bg=self.card_bg,
            fg="#15803d"
        )
        saved_tag.pack(side=tk.RIGHT)

        input_row = tk.Frame(card, bg=self.card_bg)
        input_row.pack(fill=tk.X, pady=(8, 4))

        self.ent_ws_path = ttk.Entry(input_row, font=("Segoe UI", 9))
        self.ent_ws_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.ent_ws_path.bind("<KeyRelease>", lambda e: self._on_workspace_path_edited())

        btn_browse = create_flat_button(
            input_row,
            text="📂 Explorar...",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#1e293b",
            command=self._on_browse_workspace,
            font=("Segoe UI", 9),
            padx=12,
            pady=5
        )
        btn_browse.pack(side=tk.RIGHT)

        # Fila con estado de la carpeta y ayuda para el estudiante
        feedback_row = tk.Frame(card, bg=self.card_bg)
        feedback_row.pack(fill=tk.X, pady=(4, 0))

        self.lbl_ws_status = tk.Label(
            feedback_row,
            text="Validando ruta...",
            font=("Segoe UI", 8),
            bg=self.card_bg,
            fg=self.text_muted
        )
        self.lbl_ws_status.pack(side=tk.LEFT)

        note_lbl = tk.Label(
            feedback_row,
            text="Se monta como volumen en /ros2_ws/src en el contenedor.",
            font=("Segoe UI", 8, "italic"),
            bg=self.card_bg,
            fg=self.text_muted
        )
        note_lbl.pack(side=tk.RIGHT)

    def _build_robot_scenario_card(self, parent):
        """Tarjeta con la configuración del robot, escenario y parámetros de simulación."""
        card = tk.Frame(parent, bg=self.card_bg, padx=16, pady=12, highlightbackground=self.border_color, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        title = tk.Label(
            card,
            text="⚙️ Parámetros de Simulación y Navegación",
            font=("Segoe UI", 10, "bold"),
            bg=self.card_bg,
            fg="#1e293b"
        )
        title.pack(anchor="w", pady=(0, 10))

        grid_f = tk.Frame(card, bg=self.card_bg)
        grid_f.pack(fill=tk.X)

        # Fila 0: Robot y Mundo
        tk.Label(grid_f, text="Modelo de Robot:", font=("Segoe UI", 9), bg=self.card_bg, fg="#334155").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        
        all_robots = get_all_robots()
        robot_names = [r.name for r in all_robots]
        self.cbo_robot = ttk.Combobox(grid_f, values=robot_names, state="readonly", width=32, font=("Segoe UI", 9))
        self.cbo_robot.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=4)
        self.cbo_robot.bind("<<ComboboxSelected>>", self._on_robot_changed)

        tk.Label(grid_f, text="Mundo Gazebo:", font=("Segoe UI", 9), bg=self.card_bg, fg="#334155").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=4)
        self.cbo_world = ttk.Combobox(grid_f, state="readonly", width=20, font=("Segoe UI", 9))
        self.cbo_world.grid(row=0, column=3, sticky="ew", pady=4)
        self.cbo_world.bind("<<ComboboxSelected>>", lambda e: self._save_current_settings())

        # Fila 1: Escenario y ROS Domain ID
        tk.Label(grid_f, text="Escenario:", font=("Segoe UI", 9), bg=self.card_bg, fg="#334155").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=6)
        self.cbo_scenario = ttk.Combobox(grid_f, state="readonly", width=32, font=("Segoe UI", 9))
        self.cbo_scenario.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=6)
        self.cbo_scenario.bind("<<ComboboxSelected>>", self._on_scenario_changed)

        tk.Label(grid_f, text="ROS_DOMAIN_ID:", font=("Segoe UI", 9), bg=self.card_bg, fg="#334155").grid(row=1, column=2, sticky="w", padx=(0, 6), pady=6)
        self.ent_domain_id = ttk.Entry(grid_f, width=10, font=("Segoe UI", 9))
        self.ent_domain_id.grid(row=1, column=3, sticky="w", pady=6)
        self.ent_domain_id.bind("<KeyRelease>", lambda e: self._save_current_settings())

        grid_f.columnconfigure(1, weight=1)
        grid_f.columnconfigure(3, weight=1)

        # Fila informativa dinámica de lo que hace el escenario seleccionado
        info_frame = tk.Frame(card, bg="#f8fafc", padx=10, pady=6, highlightbackground="#e2e8f0", highlightthickness=1)
        info_frame.pack(fill=tk.X, pady=(10, 0))

        self.lbl_scenario_desc = tk.Label(
            info_frame,
            text="",
            bg="#f8fafc",
            fg="#475569",
            font=("Segoe UI", 8, "italic"),
            anchor="w"
        )
        self.lbl_scenario_desc.pack(fill=tk.X)

    def _build_action_bar_card(self, parent):
        """Barra de acciones con botones planos modernos, compacta y siempre accesible."""
        card = tk.Frame(parent, bg=self.card_bg, padx=12, pady=8, highlightbackground=self.border_color, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 8))

        btn_row = tk.Frame(card, bg=self.card_bg)
        btn_row.pack(fill=tk.X)

        # 1. Botón Principal: Iniciar Simulación (Azul Indigo moderno)
        self.btn_launch = create_flat_button(
            btn_row,
            text="🚀  Iniciar Simulación",
            bg="#2563eb",
            hover_bg="#1d4ed8",
            fg="white",
            command=self._on_launch_simulation,
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=7
        )
        self.btn_launch.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        # 2. Botón Terminal Docker (Gris pizarra / Terminal)
        self.btn_terminal = create_flat_button(
            btn_row,
            text="💻  Abrir Terminal Docker",
            bg="#0f172a",
            hover_bg="#1e293b",
            fg="white",
            command=self._on_open_terminal,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7
        )
        self.btn_terminal.pack(side=tk.LEFT, padx=(0, 8))

        # 3. Botón Interfaz Web noVNC (Cian/Azul cielo)
        self.btn_open_web = create_flat_button(
            btn_row,
            text="🌐  Interfaz Web (noVNC)",
            bg="#0284c7",
            hover_bg="#0369a1",
            fg="white",
            command=self._open_web_gui,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7
        )
        self.btn_open_web.pack(side=tk.LEFT, padx=(0, 8))

        # 4. Botón Detener Contenedor (Rojo suave)
        self.btn_stop = create_flat_button(
            btn_row,
            text="🛑  Detener Contenedor",
            bg="#dc2626",
            hover_bg="#b91c1c",
            fg="white",
            command=self._on_stop_simulation,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7
        )
        self.btn_stop.pack(side=tk.RIGHT)

        # Barra de progreso para descargas/construcción de imagen
        self.progress_frame = tk.Frame(card, bg=self.card_bg)
        self.progress_frame.pack(fill=tk.X, pady=(6, 0))
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.lbl_progress = tk.Label(self.progress_frame, text="Listo", font=("Segoe UI", 8), bg=self.card_bg, fg=self.text_muted)
        self.lbl_progress.pack(side=tk.RIGHT)

    def _build_modern_tabs(self, parent):
        """Barra de navegación moderna por pestañas con diseño plano (sin pestañas retro de Tkinter)."""
        tabs_container = tk.Frame(parent, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1)
        tabs_container.pack(fill=tk.BOTH, expand=True)

        # Barra superior de botones de pestaña (Segmented bar)
        nav_bar = tk.Frame(tabs_container, bg="#f1f5f9", padx=6, pady=4)
        nav_bar.pack(fill=tk.X)

        tabs_meta = [
            ("config", "🚀  Configuración de Simulación"),
            ("logs", "📋  Salida y Logs"),
            ("quick", "⚡  Comandos Rápidos"),
            ("advanced", "⚙️  Ajustes Avanzados"),
            ("guide", "📖  Guía del Estudiante")
        ]

        for tab_id, label_text in tabs_meta:
            btn = tk.Button(
                nav_bar,
                text=label_text,
                font=("Segoe UI", 9, "bold"),
                relief="flat",
                bd=0,
                padx=12,
                pady=5,
                cursor="hand2",
                command=lambda tid=tab_id: self._select_tab(tid)
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.tab_buttons[tab_id] = btn

            # Crear contenedor para cada pestaña
            content_frame = tk.Frame(tabs_container, bg=self.card_bg, padx=12, pady=10)
            self.tabs_dict[tab_id] = content_frame

        # Contenido de cada pestaña
        self._build_config_tab_content(self.tabs_dict["config"])
        self._build_logs_tab_content(self.tabs_dict["logs"])
        self._build_quick_tab_content(self.tabs_dict["quick"])
        self._build_advanced_tab_content(self.tabs_dict["advanced"])
        self._build_guide_tab_content(self.tabs_dict["guide"])

        # Seleccionar la primera pestaña (Configuración)
        self._select_tab("config")

    def _build_config_tab_content(self, container):
        """Pestaña de Configuración principal: Workspace y Selección de Robot/Mundo/Escenario."""
        # 1. Tarjeta de Espacio de Trabajo
        self._build_workspace_card(container)
        # 2. Tarjeta de Robot y Parámetros
        self._build_robot_scenario_card(container)

    def _select_tab(self, tab_id: str):
        """Cambia de pestaña visualmente con botones segmentados modernos."""
        self.current_tab_name = tab_id
        for tid, frame in self.tabs_dict.items():
            if tid == tab_id:
                frame.pack(fill=tk.BOTH, expand=True)
                self.tab_buttons[tid].configure(bg="#2563eb", fg="white", activebackground="#1d4ed8", activeforeground="white")
            else:
                frame.pack_forget()
                self.tab_buttons[tid].configure(bg="#f1f5f9", fg="#475569", activebackground="#e2e8f0", activeforeground="#0f172a")


    def _build_logs_tab_content(self, container):
        """Consola de logs con fondo oscuro moderno y auto-scroll inteligente."""
        ctrl_bar = tk.Frame(container, bg=self.card_bg)
        ctrl_bar.pack(fill=tk.X, pady=(0, 6))

        self.lbl_autoscroll_status = tk.Label(
            ctrl_bar,
            text="● Auto-scroll: Activo",
            font=("Segoe UI", 8, "bold"),
            bg=self.card_bg,
            fg="#16a34a"
        )
        self.lbl_autoscroll_status.pack(side=tk.LEFT)

        btn_clear = create_flat_button(
            ctrl_bar,
            text="🧹 Limpiar logs",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#334155",
            command=self._clear_logs,
            font=("Segoe UI", 8),
            padx=10,
            pady=3
        )
        btn_clear.pack(side=tk.RIGHT, padx=4)

        btn_scroll_bottom = create_flat_button(
            ctrl_bar,
            text="⬇ Ir al final",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#334155",
            command=self._scroll_to_bottom,
            font=("Segoe UI", 8),
            padx=10,
            pady=3
        )
        btn_scroll_bottom.pack(side=tk.RIGHT, padx=4)

        self.txt_logs = scrolledtext.ScrolledText(
            container,
            wrap=tk.WORD,
            bg="#18181b",        # Zinc 900
            fg="#e4e4e7",        # Zinc 200
            insertbackground="white",
            font=("Consolas", 10),
            padx=10,
            pady=10,
            relief="flat",
            bd=0
        )
        self.txt_logs.pack(fill=tk.BOTH, expand=True)

        self._setup_autoscroll_detection()
        self._init_ansi_tags()

    def _build_quick_tab_content(self, container):
        """Pestaña con atajos rápidos de comandos ROS 2 para estudiantes."""
        intro_lbl = tk.Label(
            container,
            text="Ejecuta comandos de inspección y control directamente en el contenedor:",
            font=("Segoe UI", 9, "bold"),
            bg=self.card_bg,
            fg="#1e293b"
        )
        intro_lbl.pack(anchor="w", pady=(0, 10))

        # Cuadrícula de botones rápidos planos
        grid_cmds = tk.Frame(container, bg=self.card_bg)
        grid_cmds.pack(fill=tk.X, pady=(0, 14))

        btn_topics = create_flat_button(
            grid_cmds,
            text="📡 Listar Tópicos (ros2 topic list)",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#1e293b",
            command=lambda: self._execute_quick_command("ros2 topic list"),
            padx=12,
            pady=8
        )
        btn_topics.grid(row=0, column=0, sticky="ew", padx=6, pady=4)

        btn_nodes = create_flat_button(
            grid_cmds,
            text="🧩 Listar Nodos (ros2 node list)",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#1e293b",
            command=lambda: self._execute_quick_command("ros2 node list"),
            padx=12,
            pady=8
        )
        btn_nodes.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        btn_topics_info = create_flat_button(
            grid_cmds,
            text="🔍 Tópicos con tipo (ros2 topic list -t)",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#1e293b",
            command=lambda: self._execute_quick_command("ros2 topic list -t"),
            padx=12,
            pady=8
        )
        btn_topics_info.grid(row=1, column=0, sticky="ew", padx=6, pady=4)

        btn_compile = create_flat_button(
            grid_cmds,
            text="🔨 Compilar Workspace (colcon build)",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#1e293b",
            command=self._on_compile_workspace,
            padx=12,
            pady=8
        )
        btn_compile.grid(row=1, column=1, sticky="ew", padx=6, pady=4)

        grid_cmds.columnconfigure(0, weight=1)
        grid_cmds.columnconfigure(1, weight=1)

        # Entrada de comando personalizado
        custom_frame = tk.LabelFrame(container, text=" Comando ROS 2 Personalizado ", bg=self.card_bg, font=("Segoe UI", 9, "bold"), fg="#334155", padx=12, pady=10)
        custom_frame.pack(fill=tk.X, pady=(6, 0))

        entry_row = tk.Frame(custom_frame, bg=self.card_bg)
        entry_row.pack(fill=tk.X)

        self.ent_custom_cmd = ttk.Entry(entry_row, font=("Consolas", 10))
        self.ent_custom_cmd.insert(0, "ros2 topic list")
        self.ent_custom_cmd.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.ent_custom_cmd.bind("<Return>", lambda e: self._on_run_custom_command())

        btn_run_custom = create_flat_button(
            entry_row,
            text="▶ Ejecutar",
            bg="#2563eb",
            hover_bg="#1d4ed8",
            fg="white",
            command=self._on_run_custom_command,
            padx=14,
            pady=5
        )
        btn_run_custom.pack(side=tk.RIGHT)

        tk.Label(
            custom_frame,
            text="La salida del comando se imprimirá en directo en la pestaña 'Salida y Logs de Simulación'.",
            font=("Segoe UI", 8, "italic"),
            bg=self.card_bg,
            fg=self.text_muted
        ).pack(anchor="w", pady=(6, 0))

    def _build_advanced_tab_content(self, container):
        """Pestaña de ajustes avanzados (puerto web, argumentos extra, actualizaciones de GitHub)."""
        # Fila Puerto Web noVNC
        row_port = tk.Frame(container, bg=self.card_bg)
        row_port.pack(fill=tk.X, pady=6)
        tk.Label(row_port, text="Puerto Servidor Web noVNC:", font=("Segoe UI", 9), bg=self.card_bg, width=28, anchor="w").pack(side=tk.LEFT)
        self.ent_web_port = ttk.Entry(row_port, width=10, font=("Segoe UI", 9))
        self.ent_web_port.pack(side=tk.LEFT, padx=(0, 8))
        self.ent_web_port.bind("<KeyRelease>", lambda e: self._save_current_settings())
        tk.Label(row_port, text="(Por defecto: 6080 -> http://localhost:6080/vnc.html)", font=("Segoe UI", 8, "italic"), bg=self.card_bg, fg=self.text_muted).pack(side=tk.LEFT)

        # Fila Argumentos Extra ROS 2
        row_args = tk.Frame(container, bg=self.card_bg)
        row_args.pack(fill=tk.X, pady=6)
        tk.Label(row_args, text="Argumentos extra para ROS 2:", font=("Segoe UI", 9), bg=self.card_bg, width=28, anchor="w").pack(side=tk.LEFT)
        self.ent_extra_args = ttk.Entry(row_args, font=("Segoe UI", 9))
        self.ent_extra_args.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ent_extra_args.bind("<KeyRelease>", lambda e: self._save_current_settings())

        # Checkbox forzar recompilación
        self.var_force_rebuild = tk.BooleanVar(value=False)
        cb_rebuild = ttk.Checkbutton(
            container,
            text="Forzar recompilación completa con colcon en cada inicio de simulación",
            variable=self.var_force_rebuild,
            command=self._save_current_settings
        )
        cb_rebuild.pack(anchor="w", pady=(10, 12))

        # Botones de mantenimiento de Docker
        maint_box = tk.LabelFrame(container, text=" Mantenimiento de Docker y Caché ", bg=self.card_bg, font=("Segoe UI", 9, "bold"), fg="#334155", padx=12, pady=10)
        maint_box.pack(fill=tk.X, pady=(6, 0))

        maint_btns = tk.Frame(maint_box, bg=self.card_bg)
        maint_btns.pack(fill=tk.X)

        self.btn_prep_image = create_flat_button(
            maint_btns,
            text="📦 Reconstruir / Preparar Imagen Docker",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#1e293b",
            command=self._on_pull_or_build_image,
            padx=12,
            pady=6
        )
        self.btn_prep_image.pack(side=tk.LEFT, padx=(0, 10))

        btn_clean_cache = create_flat_button(
            maint_btns,
            text="🧹 Limpiar Volúmenes de Caché",
            bg="#f1f5f9",
            hover_bg="#e2e8f0",
            fg="#1e293b",
            command=self._on_clean_build_cache,
            padx=12,
            pady=6
        )
        btn_clean_cache.pack(side=tk.LEFT)

        # Actualizaciones automáticas desde GitHub
        update_box = tk.LabelFrame(container, text=" Actualizaciones del Software (GitHub) ", bg=self.card_bg, font=("Segoe UI", 9, "bold"), fg="#334155", padx=12, pady=10)
        update_box.pack(fill=tk.X, pady=(12, 0))

        update_row = tk.Frame(update_box, bg=self.card_bg)
        update_row.pack(fill=tk.X)

        tk.Label(
            update_row,
            text=f"Versión instalada: v{CURRENT_VERSION}",
            font=("Segoe UI", 9, "bold"),
            bg=self.card_bg,
            fg="#1e293b"
        ).pack(side=tk.LEFT, padx=(0, 15))

        self.btn_check_updates = create_flat_button(
            update_row,
            text="🔄 Comprobar actualizaciones",
            bg="#2563eb",
            hover_bg="#1d4ed8",
            fg="white",
            command=self._on_manual_check_updates,
            padx=12,
            pady=5
        )
        self.btn_check_updates.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_update_status = tk.Label(
            update_row,
            text="Comprobando al iniciar...",
            font=("Segoe UI", 8, "italic"),
            bg=self.card_bg,
            fg=self.text_muted
        )
        self.lbl_update_status.pack(side=tk.LEFT)

        # Etiqueta indicadora de la ruta de guardado en AppData
        appdata_lbl = tk.Label(
            container,
            text=f"Archivo de configuración: {self.config_store.config_path}",
            font=("Segoe UI", 8),
            bg=self.card_bg,
            fg=self.text_muted
        )
        appdata_lbl.pack(anchor="w", pady=(18, 0))

    def _build_guide_tab_content(self, container):
        """Guía del estudiante en texto limpio y legible."""
        guide_text = scrolledtext.ScrolledText(
            container,
            wrap=tk.WORD,
            bg="#ffffff",
            fg="#1e293b",
            font=("Segoe UI", 9),
            padx=12,
            pady=12,
            relief="flat",
            bd=0
        )
        guide_text.pack(fill=tk.BOTH, expand=True)

        content = """============================================================
📚 GUÍA DE SIMULACIÓN Y NAVEGACIÓN ROS 2 JAZZY
============================================================

Este entorno ejecuta ROS 2 Jazzy, Gazebo Sim y Navigation2 (Nav2) dentro de un contenedor Docker
con interfaz gráfica accesible directamente desde el navegador web (noVNC).

------------------------------------------------------------
🌐 1. INTERFAZ GRÁFICA WEB (Gazebo y RViz2)
------------------------------------------------------------
• No necesitas instalar XQuartz ni VcXsrv en Windows.
• Al iniciar la simulación, el navegador se abrirá automáticamente en:
      http://localhost:6080/vnc.html
• En esa pestaña verás el escritorio virtual con Gazebo Sim y RViz2.

------------------------------------------------------------
💻 2. TERMINAL DOCKER NATIVO (Windows Terminal / PowerShell)
------------------------------------------------------------
• Pulsa el botón "💻 Abrir Terminal Docker" en la barra superior.
• Se abrirá automáticamente una ventana de Windows Terminal o PowerShell conectada al contenedor.
• Ya incluye el entorno de ROS 2 configurado ('source /opt/ros/jazzy/setup.bash' y '/ros2_ws/install/setup.bash').
• Podrás ejecutar de inmediato comandos como:
      ros2 topic list
      ros2 run teleop_twist_keyboard teleop_twist_keyboard
      ros2 topic echo /odom

------------------------------------------------------------
📁 3. ESPACIO DE TRABAJO (Workspace en Windows)
------------------------------------------------------------
• La carpeta de Windows que elijas en "Espacio de Trabajo" se monta automáticamente en:
      /ros2_ws/src
• Puedes editar tus paquetes y nodos de ROS 2 en Windows usando tu editor favorito (VS Code, etc.).
• Cualquier archivo creado o modificado en Windows se sincroniza en tiempo real con Docker.
• Para compilar tus paquetes, pulsa "🔨 Compilar Workspace" o ejecuta 'colcon build' en la terminal.

------------------------------------------------------------
🤖 4. GUÍA RÁPIDA DE PRÁCTICAS
------------------------------------------------------------
A. Mapeo con SLAM Toolbox:
   1. Elige el escenario: "Gazebo Sim + SLAM Toolbox (Modo mapeo)".
   2. Pulsa "🚀 Iniciar Simulación".
   3. Pulsa "💻 Abrir Terminal Docker" y conduce el robot con:
          ros2 run teleop_twist_keyboard teleop_twist_keyboard
   4. Una vez completado el mapa, guárdalo desde el plugin de SLAM en RViz2.

B. Navegación Autónoma con Nav2:
   1. Elige el escenario: "Gazebo Sim + Nav2 (Navegación completa y RViz2)".
   2. Pulsa "🚀 Iniciar Simulación".
   3. En RViz2, establece la posición inicial estimada con la herramienta "2D Pose Estimate".
   4. Envía metas de navegación con el botón "Nav2 Goal".
"""
        guide_text.insert(tk.END, content)
        guide_text.configure(state="disabled")

    # --- Persistencia y Carga de Configuraciones ---

    def _load_saved_preferences(self):
        """Carga las preferencias guardadas desde AppData y actualiza la interfaz."""
        # 1. Workspace
        saved_ws = self.config_store.get("workspace_path")
        self.ent_ws_path.delete(0, tk.END)
        self.ent_ws_path.insert(0, saved_ws)
        self._update_workspace_validation()

        # 2. Robot
        saved_robot_id = self.config_store.get("robot_id", "turtlebot4")
        robot_profile = get_robot_by_id(saved_robot_id) or get_all_robots()[0]
        self.cbo_robot.set(robot_profile.name)
        self._update_worlds_and_scenarios(robot_profile)

        # 3. Mundo
        saved_world = self.config_store.get("world_name", "warehouse")
        if saved_world in self.cbo_world["values"]:
            self.cbo_world.set(saved_world)
        elif self.cbo_world["values"]:
            self.cbo_world.current(0)

        # 4. Escenario
        saved_scenario_id = self.config_store.get("scenario_id", "nav2")
        scenario_obj = robot_profile.get_scenario_by_id(saved_scenario_id)
        if scenario_obj and scenario_obj.name in self.cbo_scenario["values"]:
            self.cbo_scenario.set(scenario_obj.name)
        elif self.cbo_scenario["values"]:
            self.cbo_scenario.current(0)
        self._on_scenario_changed()

        # 5. Domain ID y Puerto
        saved_domain = self.config_store.get("ros_domain_id", "42")
        self.ent_domain_id.delete(0, tk.END)
        self.ent_domain_id.insert(0, str(saved_domain))

        saved_port = self.config_store.get("web_port", str(DEFAULT_NOVNC_PORT))
        self.ent_web_port.delete(0, tk.END)
        self.ent_web_port.insert(0, str(saved_port))

        saved_args = self.config_store.get("extra_args", "use_sim_time:=true")
        self.ent_extra_args.delete(0, tk.END)
        self.ent_extra_args.insert(0, saved_args)

        saved_rebuild = self.config_store.get("force_rebuild", False)
        self.var_force_rebuild.set(saved_rebuild)

    def _save_current_settings(self):
        """Guarda los valores actuales de la interfaz en AppData de forma transparente."""
        selected_robot_name = self.cbo_robot.get()
        robot_profile = get_robot_by_name(selected_robot_name)
        robot_id = robot_profile.id if robot_profile else "turtlebot4"

        selected_scenario_name = self.cbo_scenario.get()
        scenario_id = "nav2"
        if robot_profile:
            sc_obj = robot_profile.get_scenario_by_name(selected_scenario_name)
            if sc_obj:
                scenario_id = sc_obj.id

        data = {
            "workspace_path": self.ent_ws_path.get().strip(),
            "robot_id": robot_id,
            "scenario_id": scenario_id,
            "world_name": self.cbo_world.get().strip() or "warehouse",
            "ros_domain_id": self.ent_domain_id.get().strip() or "42",
            "web_port": self.ent_web_port.get().strip() or str(DEFAULT_NOVNC_PORT),
            "extra_args": self.ent_extra_args.get().strip(),
            "force_rebuild": bool(self.var_force_rebuild.get())
        }
        self.config_store.update(data, auto_save=True)

    # --- Manejadores de Eventos de la Interfaz ---

    def _on_workspace_path_edited(self):
        self._update_workspace_validation()
        self._save_current_settings()

    def _on_browse_workspace(self):
        current_dir = self.ent_ws_path.get().strip()
        if not os.path.exists(current_dir):
            current_dir = str(Path.home())

        chosen = filedialog.askdirectory(initialdir=current_dir, title="Seleccionar carpeta de desarrollo (Workspace)")
        if chosen:
            self.ent_ws_path.delete(0, tk.END)
            self.ent_ws_path.insert(0, chosen)
            self._update_workspace_validation()
            self._save_current_settings()

    def _update_workspace_validation(self):
        """Valida la ruta del workspace y actualiza la etiqueta informativa."""
        path_str = self.ent_ws_path.get().strip()
        is_valid, msg = ConfigStore.validate_workspace(path_str)
        if is_valid:
            if "detectado" in msg:
                self.lbl_ws_status.configure(text=f"✓ {msg}", fg="#15803d")
            else:
                self.lbl_ws_status.configure(text=f"✓ {msg}", fg="#1e293b")
        else:
            self.lbl_ws_status.configure(text=f"⚠ {msg}", fg="#dc2626")

    def _on_robot_changed(self, event=None):
        selected_name = self.cbo_robot.get()
        robot_profile = get_robot_by_name(selected_name)
        if robot_profile:
            self._update_worlds_and_scenarios(robot_profile)
            self._on_scenario_changed()
            self._save_current_settings()

    def _update_worlds_and_scenarios(self, robot_profile: RobotProfile):
        self.cbo_world["values"] = robot_profile.supported_worlds
        if robot_profile.supported_worlds:
            self.cbo_world.current(0)

        scenario_names = [sc.name for sc in robot_profile.scenarios]
        self.cbo_scenario["values"] = scenario_names
        if scenario_names:
            self.cbo_scenario.current(0)

    def _on_scenario_changed(self, event=None):
        selected_robot_name = self.cbo_robot.get()
        robot_profile = get_robot_by_name(selected_robot_name)
        if robot_profile:
            scenario_name = self.cbo_scenario.get()
            sc_obj = robot_profile.get_scenario_by_name(scenario_name)
            if sc_obj:
                self.lbl_scenario_desc.configure(text=f"ℹ {sc_obj.description}")
            else:
                self.lbl_scenario_desc.configure(text="")
        self._save_current_settings()

    def _check_docker_live_status(self):
        """Comprueba el daemon de Docker en un hilo secundario y actualiza el badge."""
        def _worker():
            installed, ver_str = DockerService.check_docker_installed()
            if not installed:
                self.root.after(0, lambda: self._set_docker_badge("❌ Docker no encontrado", "#fee2e2", "#b91c1c"))
                return

            running, daemon_msg = DockerService.check_docker_running()
            if running:
                self.root.after(0, lambda: self._set_docker_badge(f"● {daemon_msg}", "#dcfce7", "#15803d"))
            else:
                self.root.after(0, lambda: self._set_docker_badge("⚠️ Docker detenido", "#fef3c7", "#b45309"))

        threading.Thread(target=_worker, daemon=True).start()

    def _set_docker_badge(self, text: str, bg_color: str, fg_color: str):
        self.lbl_docker_badge.configure(text=text, bg=bg_color, fg=fg_color)

    # --- Actualizaciones Automáticas (GitHub) ---

    def _on_header_update_click(self):
        """Gestiona el clic en el botón de versión / actualización de la cabecera."""
        if self._latest_update_info:
            self._prompt_update_available(self._latest_update_info)
        else:
            self._on_manual_check_updates()

    def _check_for_updates_background(self):
        """Comprueba silenciosamente en segundo plano si hay actualizaciones al iniciar el launcher."""
        logger.debug("_check_for_updates_background: Iniciando comprobación silenciosa en background...")
        def _worker():
            has_update, info, msg = check_for_updates(timeout=2.0)
            logger.debug("_check_for_updates_background completado: has_update=%s, msg='%s'", has_update, msg)
            if has_update and info:
                ver = info.get('version', '')
                logger.info("Actualización encontrada: v%s. Abriendo modal...", ver)
                self._latest_update_info = info
                self.root.after(0, lambda: self.btn_header_update.configure(
                    text=f"✨ Actualizar a v{ver}",
                    bg="#16a34a",
                    activebackground="#15803d",
                    fg="#ffffff"
                ))
                self.root.after(0, lambda: self._prompt_update_available(info))
                self.root.after(0, lambda: self.lbl_update_status.configure(
                    text=f"Nueva versión v{ver} disponible",
                    fg="#15803d"
                ))
            else:
                self._latest_update_info = None
                self.root.after(0, lambda: self.btn_header_update.configure(
                    text=f"v{CURRENT_VERSION} (Al día)",
                    bg="#f1f5f9",
                    activebackground="#e2e8f0",
                    fg="#15803d"
                ))
                self.root.after(0, lambda: self.lbl_update_status.configure(
                    text=f"Launcher actualizado (v{CURRENT_VERSION})",
                    fg=self.text_muted
                ))
        threading.Thread(target=_worker, daemon=True).start()

    def _prompt_update_available(self, update_info: dict):
        """Abre la ventana modal para ofrecer al alumno la actualización."""
        target_dir = Path(__file__).parent.resolve()
        logger.info("_prompt_update_available: Mostrando ventana modal con target_dir=%s", target_dir)
        UpdateModalDialog(self.root, update_info, target_dir)

    def _on_manual_check_updates(self):
        """Comprobación manual invocada por el usuario desde la pestaña de Ajustes o cabecera."""
        logger.info("Usuario pulsó 'Comprobar actualizaciones ahora'")
        self.btn_check_updates.configure(state="disabled")
        self.lbl_update_status.configure(text="Buscando nueva versión en GitHub...", fg=self.text_muted)

        def _worker():
            has_update, info, msg = check_for_updates(timeout=3.0)
            logger.debug("_on_manual_check_updates completado: has_update=%s, msg='%s'", has_update, msg)
            self.root.after(0, lambda: self.btn_check_updates.configure(state="normal"))

            if has_update and info:
                ver = info.get('version', '')
                logger.info("Mostrando aviso de actualización disponible: v%s", ver)
                self._latest_update_info = info
                self.root.after(0, lambda: self.btn_header_update.configure(
                    text=f"✨ Actualizar a v{ver}",
                    bg="#16a34a",
                    activebackground="#15803d",
                    fg="#ffffff"
                ))
                self.root.after(0, lambda: self.lbl_update_status.configure(
                    text=f"Nueva versión v{ver} disponible",
                    fg="#15803d"
                ))
                self.root.after(0, lambda: self._prompt_update_available(info))
            elif "pendiente" in msg.lower():
                self._latest_update_info = None
                logger.warning("Repositorio no configurado aún (%s)", msg)
                self.root.after(0, lambda: self.lbl_update_status.configure(text=msg, fg="#b45309"))
                self.root.after(0, lambda: messagebox.showinfo(
                    "Actualizaciones",
                    f"{msg}\n\nPara activar las actualizaciones automáticas, edita la variable 'DEFAULT_GITHUB_REPO' en updater.py con tu repositorio de GitHub (ej: 'tu_usuario/tu_repositorio').",
                    parent=self.root
                ))
            elif info:
                self._latest_update_info = None
                logger.info("El launcher está al día (v%s).", CURRENT_VERSION)
                self.root.after(0, lambda: self.btn_header_update.configure(
                    text=f"v{CURRENT_VERSION} (Al día)",
                    bg="#f1f5f9",
                    activebackground="#e2e8f0",
                    fg="#15803d"
                ))
                self.root.after(0, lambda: self.lbl_update_status.configure(
                    text=f"Al día (v{CURRENT_VERSION})",
                    fg="#15803d"
                ))
                self.root.after(0, lambda: messagebox.showinfo(
                    "Actualizaciones",
                    f"¡Ya tienes instalada la versión más reciente (v{CURRENT_VERSION})!",
                    parent=self.root
                ))
            else:
                self._latest_update_info = None
                logger.warning("Error o timeout comprobando versión: %s", msg)
                self.root.after(0, lambda: self.lbl_update_status.configure(text=msg, fg="#b91c1c"))
                self.root.after(0, lambda: messagebox.showwarning("Actualizaciones", msg, parent=self.root))

        threading.Thread(target=_worker, daemon=True).start()

    # --- Acciones Principales: Terminal Docker, Simulación, Web ---

    def _on_open_terminal(self):
        """Funcionalidad 1: Abre una terminal interactiva nativa del contenedor Docker."""
        def _worker():
            if not DockerService.is_container_running(DEFAULT_CONTAINER_NAME):
                answer = messagebox.askyesno(
                    "Contenedor no iniciado",
                    "El contenedor de simulación no está activo.\n\n"
                    "¿Deseas iniciar una sesión de contenedor ahora para abrir la terminal?",
                    parent=self.root
                )
                if answer:
                    self._launch_interactive_shell_container()
                return

            ok, msg = DockerService.open_container_terminal(DEFAULT_CONTAINER_NAME)
            if ok:
                self._log(f"\n[Terminal] {msg}\n")
            else:
                self._log(f"\n[Error Terminal] {msg}\n")
                messagebox.showwarning("Terminal", msg, parent=self.root)

        threading.Thread(target=_worker, daemon=True).start()

    def _launch_interactive_shell_container(self):
        """Inicia un contenedor en segundo plano con bash para permitir el uso de terminal."""
        image_name = COURSE_IMAGE_NAME
        running, _ = DockerService.check_docker_running()
        if not running:
            messagebox.showerror("Docker", "Docker Desktop no está en ejecución.", parent=self.root)
            return

        self._select_tab("logs")
        self._log("\nIniciando contenedor en modo terminal...\n")

        ws_path = self.ent_ws_path.get().strip()
        domain_id = self.ent_domain_id.get().strip() or "42"
        web_port = self.ent_web_port.get().strip() or str(DEFAULT_NOVNC_PORT)

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
            self._log("Contenedor iniciado con éxito en segundo plano.\n")
            DockerService.open_container_terminal(DEFAULT_CONTAINER_NAME)
        except Exception as e:
            self._log(f"Error al iniciar contenedor: {e}\n")

    def _open_web_gui(self):
        """Abre el navegador predeterminado en la URL de noVNC."""
        port = self.ent_web_port.get().strip() or str(DEFAULT_NOVNC_PORT)
        url = f"http://localhost:{port}/vnc.html?autoconnect=true&resize=scale"
        webbrowser.open(url)

    def _on_launch_simulation(self):
        """Inicia el contenedor Docker con la simulación completa y el servidor web noVNC."""
        image_name = COURSE_IMAGE_NAME

        running, err = DockerService.check_docker_running()
        if not running:
            messagebox.showerror("Error de Docker", f"Docker no está en ejecución:\n{err}\nPor favor inicia Docker Desktop primero.")
            return

        self._save_current_settings()
        self._select_tab("logs")
        self._log("\n" + "="*50 + "\nIniciando simulación de ROS 2...\n" + "="*50 + "\n")

        def _worker():
            if not DockerService.is_image_available(image_name):
                self._log(f"Imagen '{image_name}' no encontrada localmente. Iniciando preparación...\n")
                self._on_pull_or_build_image()
                return

            DockerService.stop_container(DEFAULT_CONTAINER_NAME)

            selected_robot_name = self.cbo_robot.get()
            robot_profile = get_robot_by_name(selected_robot_name) or get_all_robots()[0]
            
            selected_scenario_name = self.cbo_scenario.get()
            scenario_obj = robot_profile.get_scenario_by_name(selected_scenario_name)
            scenario_id = scenario_obj.id if scenario_obj else "nav2"

            world_name = self.cbo_world.get().strip() or "warehouse"
            extra_args = self.ent_extra_args.get().strip()
            force_rebuild = self.var_force_rebuild.get()
            domain_id = self.ent_domain_id.get().strip() or "42"
            ws_path = self.ent_ws_path.get().strip()
            web_port = self.ent_web_port.get().strip() or str(DEFAULT_NOVNC_PORT)

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

            self._log(f"Comando Docker generado:\n{' '.join(docker_cmd)}\n\n")
            self.root.after(2500, self._open_web_gui)

            try:
                self.active_simulation_proc = subprocess.Popen(
                    docker_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    universal_newlines=True
                )

                for line in iter(self.active_simulation_proc.stdout.readline, ''):
                    self._log(line)

                self.active_simulation_proc.stdout.close()
                rc = self.active_simulation_proc.wait()
                self._log(f"\n[El proceso de simulación finalizó con código de salida {rc}]\n")
            except Exception as e:
                self._log(f"\n[Error durante la ejecución: {e}]\n")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stop_simulation(self):
        """Detiene y elimina el contenedor activo."""
        self._select_tab("logs")

        def _worker():
            self._log("\nDeteniendo contenedor de simulación...\n")
            ok, msg = DockerService.stop_container(DEFAULT_CONTAINER_NAME)
            self._log(f"{msg}\n")
            if ok:
                self.root.after(0, lambda: messagebox.showinfo("Simulación", "Contenedor detenido correctamente."))

        threading.Thread(target=_worker, daemon=True).start()

    # --- Comandos Rápidos y Compilación ---

    def _execute_quick_command(self, cmd_str: str):
        """Ejecuta un comando rápido dentro del contenedor activo y muestra el resultado en logs."""
        if not DockerService.is_container_running(DEFAULT_CONTAINER_NAME):
            messagebox.showwarning(
                "Contenedor inactivo",
                "El contenedor no está en ejecución. Inicia la simulación primero para ejecutar comandos."
            )
            return

        self._select_tab("logs")
        self._log(f"\n>>> Ejecutando comando en contenedor: {cmd_str}\n")

        def _worker():
            proc = DockerService.execute_in_container_stream(DEFAULT_CONTAINER_NAME, cmd_str, self._log)
            if proc:
                for line in iter(proc.stdout.readline, ''):
                    self._log(line)
                proc.stdout.close()
                rc = proc.wait()
                self._log(f"\n[Comando finalizado con código {rc}]\n")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_run_custom_command(self):
        cmd = self.ent_custom_cmd.get().strip()
        if cmd:
            self._execute_quick_command(cmd)

    def _on_compile_workspace(self):
        """Ejecuta colcon build para compilar paquetes del espacio de trabajo montado."""
        image_name = COURSE_IMAGE_NAME
        running, err = DockerService.check_docker_running()
        if not running:
            messagebox.showerror("Docker", f"Docker no está en ejecución:\n{err}")
            return

        ws_path = self.ent_ws_path.get().strip()
        self._select_tab("logs")
        self._log("\n=== Compilando paquetes del workspace con colcon... ===\n")

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

            try:
                proc = subprocess.Popen(
                    build_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    universal_newlines=True
                )
                for line in iter(proc.stdout.readline, ''):
                    self._log(line)
                proc.stdout.close()
                rc = proc.wait()
                if rc == 0:
                    self._log("\n✅ [Compilación exitosa]\n")
                    self.root.after(0, lambda: messagebox.showinfo("Compilación", "Workspace compilado correctamente."))
                else:
                    self._log(f"\n❌ [Compilación con errores (código {rc})]\n")
                    self.root.after(0, lambda: messagebox.showerror("Compilación", f"La compilación terminó con código de error {rc}."))
            except Exception as e:
                self._log(f"\nError: {e}\n")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_clean_build_cache(self):
        """Elimina volúmenes de Docker que contienen la caché de colcon."""
        if not messagebox.askyesno("Limpiar Caché", "¿Deseas eliminar la caché de compilación de Docker?"):
            return

        self._log("\nLimpiando volúmenes de caché...\n")
        ok, msg = DockerService.clean_build_volumes()
        self._log(f"{msg}\n")
        if ok:
            messagebox.showinfo("Caché", msg)

    def _on_pull_or_build_image(self):
        """Descarga o construye la imagen de la asignatura a partir del Dockerfile."""
        image_name = COURSE_IMAGE_NAME
        self._select_tab("logs")
        self._log(f"\n--- Preparando imagen de la asignatura: {image_name} ---\n")

        def _worker():
            self.btn_prep_image.configure(state="disabled")
            self._set_progress(-1, "Comprobando imagen...")

            workspace_dir = Path(__file__).parent
            dockerfile_root = workspace_dir / "Dockerfile"

            if dockerfile_root.exists():
                build_dir = workspace_dir
            else:
                build_dir = workspace_dir / ".docker_build"
                build_dir.mkdir(parents=True, exist_ok=True)
                with open(build_dir / "Dockerfile", "w", encoding="utf-8") as f:
                    f.write(DOCKERFILE_CONTENT)

            self._log(f"Construyendo imagen desde: {build_dir}\n")
            success, msg = DockerService.build_image_stream(
                str(build_dir),
                image_name,
                self._set_progress,
                self._log
            )

            self.root.after(0, lambda: self.btn_prep_image.configure(state="normal"))
            if success:
                self._log(f"\n✅ ÉXITO: {msg}\n")
                self.root.after(0, lambda: messagebox.showinfo("Imagen", f"Imagen '{image_name}' lista."))
            else:
                self._log(f"\n❌ ERROR: {msg}\n")
                self.root.after(0, lambda: messagebox.showerror("Error", f"Error al preparar imagen:\n{msg}"))

        threading.Thread(target=_worker, daemon=True).start()

    # --- Consola de Logs y Renderizado ANSI ---

    def _log(self, text: str):
        """Añade texto a la consola analizando secuencias de escape ANSI."""
        def _append():
            import re
            ansi_pattern = re.compile(r'(\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\))')
            tokens = ansi_pattern.split(text)

            color_codes = {
                30: "ansi_30", 31: "ansi_31", 32: "ansi_32", 33: "ansi_33",
                34: "ansi_34", 35: "ansi_35", 36: "ansi_36", 37: "ansi_37",
                90: "ansi_90", 91: "ansi_91", 92: "ansi_92", 93: "ansi_93",
                94: "ansi_94", 95: "ansi_95", 96: "ansi_96", 97: "ansi_97"
            }

            for token in tokens:
                if not token:
                    continue

                if token.startswith('\x1b['):
                    if token.endswith('m'):
                        params_str = token[2:-1]
                        params = [int(p) for p in params_str.split(';') if p] if params_str else [0]

                        for code in params:
                            if code == 0:
                                self._current_ansi_tags.clear()
                            elif code == 1:
                                if "ansi_bold" not in self._current_ansi_tags:
                                    self._current_ansi_tags.append("ansi_bold")
                            elif code in color_codes:
                                self._current_ansi_tags = [t for t in self._current_ansi_tags if not t.startswith("ansi_") or t in ("ansi_bold", "ansi_underline")]
                                self._current_ansi_tags.append(color_codes[code])
                            elif code == 39:
                                self._current_ansi_tags = [t for t in self._current_ansi_tags if not t.startswith("ansi_") or t in ("ansi_bold", "ansi_underline")]
                elif token.startswith('\x1b'):
                    pass
                else:
                    clean_text = token.replace('\x07', '')
                    if clean_text:
                        if self._current_ansi_tags:
                            self.txt_logs.insert(tk.END, clean_text, tuple(self._current_ansi_tags))
                        else:
                            self.txt_logs.insert(tk.END, clean_text)

            if self._autoscroll_enabled:
                self.txt_logs.see(tk.END)

        self.root.after(0, _append)

    def _clear_logs(self):
        self.txt_logs.delete("1.0", tk.END)
        self._current_ansi_tags.clear()
        self._autoscroll_enabled = True
        self._update_autoscroll_ui()

    def _set_progress(self, pct: float, status_str: str):
        def _update():
            if pct < 0:
                self.progress_bar.configure(mode="indeterminate")
                self.progress_bar.start(10)
            else:
                self.progress_bar.configure(mode="determinate")
                self.progress_bar.stop()
                self.progress_bar["value"] = pct
            self.lbl_progress.configure(text=status_str)
        self.root.after(0, _update)

    def _setup_autoscroll_detection(self):
        orig_yscroll = self.txt_logs.vbar.cget("command")

        def _on_yview(*args):
            orig_yscroll(*args)
            self._update_autoscroll_state()

        self.txt_logs.vbar.configure(command=_on_yview)

        def _on_vbar_set(first, last):
            self.txt_logs.vbar.set(first, last)
            try:
                was_enabled = self._autoscroll_enabled
                self._autoscroll_enabled = (float(last) >= 0.995)
                if was_enabled != self._autoscroll_enabled:
                    self._update_autoscroll_ui()
            except ValueError:
                pass

        self.txt_logs.configure(yscrollcommand=_on_vbar_set)
        self.txt_logs.bind("<MouseWheel>", lambda e: self.root.after_idle(self._update_autoscroll_state))

    def _update_autoscroll_state(self):
        try:
            _, last = self.txt_logs.yview()
            self._autoscroll_enabled = (last >= 0.995)
            self._update_autoscroll_ui()
        except Exception:
            pass

    def _update_autoscroll_ui(self):
        if self._autoscroll_enabled:
            self.lbl_autoscroll_status.configure(text="● Auto-scroll: Activo", fg="#16a34a")
        else:
            self.lbl_autoscroll_status.configure(text="○ Auto-scroll: Pausado", fg="#dc2626")

    def _scroll_to_bottom(self):
        self.txt_logs.see(tk.END)
        self._autoscroll_enabled = True
        self._update_autoscroll_ui()

    def _init_ansi_tags(self):
        ansi_color_map = {
            "ansi_30": "#4f5666",
            "ansi_31": "#e06c75",
            "ansi_32": "#98c379",
            "ansi_33": "#e5c07b",
            "ansi_34": "#61afef",
            "ansi_35": "#c678dd",
            "ansi_36": "#56b6c2",
            "ansi_37": "#abb2bf",
            "ansi_90": "#5c6370",
            "ansi_91": "#ff6c6b",
            "ansi_92": "#98be65",
            "ansi_93": "#da8548",
            "ansi_94": "#51afef",
            "ansi_95": "#a9a1e1",
            "ansi_96": "#46d9ff",
            "ansi_97": "#ffffff",
        }
        for tag_name, hex_color in ansi_color_map.items():
            self.txt_logs.tag_configure(tag_name, foreground=hex_color)

        self.txt_logs.tag_configure("ansi_bold", font=("Consolas", 10, "bold"))
        self.txt_logs.tag_configure("ansi_underline", underline=True)


def main():
    root = tk.Tk()
    
    # Pre-configurar icono de forma temprana para que la barra de tareas de Windows lo detecte al mapear la ventana
    try:
        early_ico = get_app_icon_path()
        if early_ico and early_ico.is_file():
            root.iconbitmap(default=str(early_ico))
            root.iconbitmap(str(early_ico))
    except Exception:
        pass

    app = ModernSimulationLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
