"""
Launcher de Simulación ROS 2 Jazzy para la Asignatura de Robótica Móvil
Interfaz gráfica moderna, nativa y modular (Windows / macOS / Linux) con Tkinter y Docker.
"""

import os
import sys
import platform
import threading
import webbrowser
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from pathlib import Path
from typing import Optional

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


class ModernSimulationLauncher:
    """Aplicación principal con interfaz gráfica moderna para ROS 2 Jazzy Simulation Launcher."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"ROS 2 Jazzy - Launcher de Simulación (v{CURRENT_VERSION}) | Robótica Móvil")
        self.root.geometry("980x850")
        self.root.minsize(900, 720)

        # Gestor de configuración persistente (guarda en AppData)
        self.config_store = ConfigStore(fallback_dir=Path(__file__).parent.resolve())

        self.host_os = DockerService.get_host_os()
        self.active_simulation_proc: Optional[subprocess.Popen] = None
        self._autoscroll_enabled = True
        self._current_ansi_tags = []

        self._init_styles()
        self._build_layout()
        self._load_saved_preferences()
        self._check_docker_live_status()
        self.root.after(1500, self._check_for_updates_background)

    def _init_styles(self):
        """Configura el tema y la paleta de colores moderna."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Paleta moderna Slate & Indigo
        self.bg_color = "#f8fafc"        # Slate 50
        self.card_bg = "#ffffff"         # Blanco puro para tarjetas
        self.border_color = "#e2e8f0"    # Slate 200
        self.primary_color = "#2563eb"   # Azul moderno (Indigo 600)
        self.primary_hover = "#1d4ed8"
        self.success_color = "#16a34a"   # Verde
        self.danger_color = "#dc2626"    # Rojo
        self.text_main = "#0f172a"       # Slate 900
        self.text_muted = "#64748b"      # Slate 500

        self.root.configure(bg=self.bg_color)

        style.configure("TFrame", background=self.bg_color)
        style.configure("Card.TFrame", background=self.card_bg, relief="solid", borderwidth=1)
        style.configure("CardInner.TFrame", background=self.card_bg)

        style.configure("TLabel", background=self.bg_color, foreground=self.text_main, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=self.card_bg, foreground=self.text_main, font=("Segoe UI", 9))
        style.configure("CardMuted.TLabel", background=self.card_bg, foreground=self.text_muted, font=("Segoe UI", 8))
        style.configure("CardTitle.TLabel", background=self.card_bg, foreground="#1e293b", font=("Segoe UI", 10, "bold"))
        
        style.configure("HeaderTitle.TLabel", background=self.bg_color, foreground="#1e3a8a", font=("Segoe UI", 13, "bold"))
        style.configure("HeaderSubtitle.TLabel", background=self.bg_color, foreground=self.text_muted, font=("Segoe UI", 9))

        # Estilos de botones
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8))
        style.configure("Terminal.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 6))
        style.configure("Danger.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 6))
        style.configure("Secondary.TButton", font=("Segoe UI", 9), padding=(8, 4))

        # Pestañas
        style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 9, "bold"), padding=(14, 6))

    def _build_layout(self):
        """Construye la distribución por tarjetas limpias y jerarquizadas."""
        # 1. Cabecera principal con estado en vivo
        self._build_header()

        # Contenedor central scrolleable para mantener la interfaz adaptativa
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))

        # 2. Tarjeta 1: Espacio de Trabajo (Workspace de Windows)
        self._build_workspace_card(main_container)

        # 3. Tarjeta 2: Configuración del Robot y Escenario de Simulación
        self._build_robot_scenario_card(main_container)

        # 4. Tarjeta 3: Barra de Acciones Rápidas (Lanzar, Terminal, Web, Detener)
        self._build_action_bar_card(main_container)

        # 5. Panel de Pestañas Inferior (Logs, Comandos Rápidos, Ajustes, Guía)
        self._build_notebook_tabs(main_container)

    def _build_header(self):
        """Barra superior con título, asignatura e indicador dinámico de Docker."""
        header_frame = ttk.Frame(self.root, padding="16 12 16 6")
        header_frame.pack(fill=tk.X)

        left_box = ttk.Frame(header_frame)
        left_box.pack(side=tk.LEFT)

        title_lbl = ttk.Label(left_box, text=f"🤖 ROS 2 Jazzy - Launcher de Simulación (v{CURRENT_VERSION})", style="HeaderTitle.TLabel")
        title_lbl.pack(anchor="w")

        sub_lbl = ttk.Label(left_box, text="Robótica Móvil · Gazebo Sim & Navigation2 (Nav2)", style="HeaderSubtitle.TLabel")
        sub_lbl.pack(anchor="w")

        # Indicador de estado a la derecha
        right_box = ttk.Frame(header_frame)
        right_box.pack(side=tk.RIGHT, pady=2)

        self.lbl_docker_badge = tk.Label(
            right_box,
            text="● Comprobando Docker...",
            bg="#fef3c7",
            fg="#b45309",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
            relief="solid",
            bd=1
        )
        self.lbl_docker_badge.pack(side=tk.LEFT, padx=(0, 6))

        btn_refresh_docker = ttk.Button(right_box, text="🔄", width=3, style="Secondary.TButton", command=self._check_docker_live_status)
        btn_refresh_docker.pack(side=tk.LEFT)

    def _build_workspace_card(self, parent):
        """Tarjeta para la selección y validación del workspace en Windows montado en Docker."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(4, 8))

        top_row = ttk.Frame(card, style="CardInner.TFrame")
        top_row.pack(fill=tk.X)

        title = ttk.Label(top_row, text="📁 Espacio de Trabajo en Windows (Workspace)", style="CardTitle.TLabel")
        title.pack(side=tk.LEFT)

        saved_tag = ttk.Label(
            top_row,
            text="✓ Guardado en AppData (Persistente)",
            style="CardMuted.TLabel",
            foreground="#15803d"
        )
        saved_tag.pack(side=tk.RIGHT)

        input_row = ttk.Frame(card, style="CardInner.TFrame")
        input_row.pack(fill=tk.X, pady=(6, 2))

        self.ent_ws_path = ttk.Entry(input_row, font=("Segoe UI", 9))
        self.ent_ws_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.ent_ws_path.bind("<KeyRelease>", lambda e: self._on_workspace_path_edited())

        btn_browse = ttk.Button(input_row, text="📂 Explorar...", style="Secondary.TButton", command=self._on_browse_workspace)
        btn_browse.pack(side=tk.RIGHT)

        # Fila con estado de la carpeta y ayuda para el estudiante
        feedback_row = ttk.Frame(card, style="CardInner.TFrame")
        feedback_row.pack(fill=tk.X, pady=(3, 0))

        self.lbl_ws_status = ttk.Label(
            feedback_row,
            text="Validando ruta...",
            style="Card.TLabel",
            foreground=self.text_muted,
            font=("Segoe UI", 8)
        )
        self.lbl_ws_status.pack(side=tk.LEFT)

        note_lbl = ttk.Label(
            feedback_row,
            text="Se monta como volumen en /ros2_ws/src en el contenedor.",
            style="CardMuted.TLabel"
        )
        note_lbl.pack(side=tk.RIGHT)

    def _build_robot_scenario_card(self, parent):
        """Tarjeta con la configuración del robot, escenario y parámetros de simulación."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 8))

        title = ttk.Label(card, text="⚙️ Parámetros de Simulación y Navegación", style="CardTitle.TLabel")
        title.pack(anchor="w", pady=(0, 8))

        grid_f = ttk.Frame(card, style="CardInner.TFrame")
        grid_f.pack(fill=tk.X)

        # Fila 0: Robot y Mundo
        ttk.Label(grid_f, text="Modelo de Robot:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        
        all_robots = get_all_robots()
        robot_names = [r.name for r in all_robots]
        self.cbo_robot = ttk.Combobox(grid_f, values=robot_names, state="readonly", width=30)
        self.cbo_robot.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=4)
        self.cbo_robot.bind("<<ComboboxSelected>>", self._on_robot_changed)

        ttk.Label(grid_f, text="Mundo Gazebo:", style="Card.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=4)
        self.cbo_world = ttk.Combobox(grid_f, state="readonly", width=20)
        self.cbo_world.grid(row=0, column=3, sticky="ew", pady=4)
        self.cbo_world.bind("<<ComboboxSelected>>", lambda e: self._save_current_settings())

        # Fila 1: Escenario y ROS Domain ID
        ttk.Label(grid_f, text="Escenario:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        self.cbo_scenario = ttk.Combobox(grid_f, state="readonly", width=30)
        self.cbo_scenario.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=4)
        self.cbo_scenario.bind("<<ComboboxSelected>>", self._on_scenario_changed)

        ttk.Label(grid_f, text="ROS_DOMAIN_ID:", style="Card.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 6), pady=4)
        self.ent_domain_id = ttk.Entry(grid_f, width=10)
        self.ent_domain_id.grid(row=1, column=3, sticky="w", pady=4)
        self.ent_domain_id.bind("<KeyRelease>", lambda e: self._save_current_settings())

        grid_f.columnconfigure(1, weight=1)
        grid_f.columnconfigure(3, weight=1)

        # Fila informativa dinámica de lo que hace el escenario seleccionado
        info_frame = ttk.Frame(card, style="CardInner.TFrame")
        info_frame.pack(fill=tk.X, pady=(8, 0))

        self.lbl_scenario_desc = tk.Label(
            info_frame,
            text="",
            bg="#f1f5f9",
            fg="#334155",
            font=("Segoe UI", 8, "italic"),
            anchor="w",
            padx=8,
            pady=4,
            relief="flat"
        )
        self.lbl_scenario_desc.pack(fill=tk.X)

    def _build_action_bar_card(self, parent):
        """Barra de acciones principales: Lanzar simulación, Abrir Terminal, Web GUI, Detener."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=10)
        card.pack(fill=tk.X, pady=(0, 8))

        btn_row = ttk.Frame(card, style="CardInner.TFrame")
        btn_row.pack(fill=tk.X)

        # Botón Principal: Iniciar Simulación
        self.btn_launch = ttk.Button(
            btn_row,
            text="🚀 Iniciar Simulación",
            style="Primary.TButton",
            command=self._on_launch_simulation
        )
        self.btn_launch.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        # Botón Terminal Docker (Funcionalidad 1 solicitada)
        self.btn_terminal = ttk.Button(
            btn_row,
            text="💻 Abrir Terminal Docker",
            style="Terminal.TButton",
            command=self._on_open_terminal
        )
        self.btn_terminal.pack(side=tk.LEFT, padx=(0, 8))

        # Botón Navegador Web (noVNC)
        self.btn_open_web = ttk.Button(
            btn_row,
            text="🌐 Interfaz Web (noVNC)",
            style="Secondary.TButton",
            command=self._open_web_gui
        )
        self.btn_open_web.pack(side=tk.LEFT, padx=(0, 8))

        # Botón Detener Simulación
        self.btn_stop = ttk.Button(
            btn_row,
            text="🛑 Detener Contenedor",
            style="Danger.TButton",
            command=self._on_stop_simulation
        )
        self.btn_stop.pack(side=tk.RIGHT)

        # Barra de progreso para descargas/construcción de imagen
        self.progress_frame = ttk.Frame(card, style="CardInner.TFrame")
        self.progress_frame.pack(fill=tk.X, pady=(8, 0))
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.lbl_progress = ttk.Label(self.progress_frame, text="Listo", style="CardMuted.TLabel")
        self.lbl_progress.pack(side=tk.RIGHT)

    def _build_notebook_tabs(self, parent):
        """Pestañas inferiores: Logs, Comandos Rápidos, Ajustes Avanzados y Guía."""
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Pestaña 1: Logs de Simulación
        self.tab_logs = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_logs, text="📋 Salida y Logs de Simulación")

        # Pestaña 2: Comandos Rápidos ROS 2 (Integrados)
        self.tab_quick = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_quick, text="⚡ Comandos Rápidos ROS 2")

        # Pestaña 3: Ajustes Avanzados
        self.tab_advanced = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.tab_advanced, text="⚙️ Ajustes Avanzados")

        # Pestaña 4: Guía del Estudiante
        self.tab_guide = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_guide, text="📖 Guía del Estudiante")

        self._build_logs_tab_content()
        self._build_quick_tab_content()
        self._build_advanced_tab_content()
        self._build_guide_tab_content()

    def _build_logs_tab_content(self):
        """Contenido de la consola de logs con soporte ANSI y auto-scroll inteligente."""
        ctrl_bar = ttk.Frame(self.tab_logs)
        ctrl_bar.pack(fill=tk.X, pady=(0, 6))

        self.lbl_autoscroll_status = ttk.Label(
            ctrl_bar,
            text="● Auto-scroll: Activo",
            font=("Segoe UI", 8, "bold"),
            foreground="#16a34a"
        )
        self.lbl_autoscroll_status.pack(side=tk.LEFT)

        btn_clear = ttk.Button(ctrl_bar, text="🧹 Limpiar logs", style="Secondary.TButton", command=self._clear_logs)
        btn_clear.pack(side=tk.RIGHT, padx=4)

        btn_scroll_bottom = ttk.Button(ctrl_bar, text="⬇ Ir al final", style="Secondary.TButton", command=self._scroll_to_bottom)
        btn_scroll_bottom.pack(side=tk.RIGHT, padx=4)

        self.txt_logs = scrolledtext.ScrolledText(
            self.tab_logs,
            wrap=tk.WORD,
            bg="#18181b",        # Zinc 900
            fg="#e4e4e7",        # Zinc 200
            insertbackground="white",
            font=("Consolas", 9),
            padx=8,
            pady=8
        )
        self.txt_logs.pack(fill=tk.BOTH, expand=True)

        self._setup_autoscroll_detection()
        self._init_ansi_tags()

    def _build_quick_tab_content(self):
        """Pestaña con atajos rápidos de comandos ROS 2 para estudiantes."""
        container = ttk.Frame(self.tab_quick)
        container.pack(fill=tk.BOTH, expand=True)

        intro_lbl = ttk.Label(
            container,
            text="Ejecuta comandos de inspección y control directamente en el contenedor en ejecución:",
            font=("Segoe UI", 9, "bold")
        )
        intro_lbl.pack(anchor="w", pady=(0, 8))

        # Cuadrícula de botones rápidos
        grid_cmds = ttk.Frame(container)
        grid_cmds.pack(fill=tk.X, pady=(0, 12))

        btn_topics = ttk.Button(
            grid_cmds,
            text="📡 Listar Tópicos (ros2 topic list)",
            style="Secondary.TButton",
            command=lambda: self._execute_quick_command("ros2 topic list")
        )
        btn_topics.grid(row=0, column=0, sticky="ew", padx=4, pady=4)

        btn_nodes = ttk.Button(
            grid_cmds,
            text="🧩 Listar Nodos (ros2 node list)",
            style="Secondary.TButton",
            command=lambda: self._execute_quick_command("ros2 node list")
        )
        btn_nodes.grid(row=0, column=1, sticky="ew", padx=4, pady=4)

        btn_topics_info = ttk.Button(
            grid_cmds,
            text="🔍 Tópicos con tipo (ros2 topic list -t)",
            style="Secondary.TButton",
            command=lambda: self._execute_quick_command("ros2 topic list -t")
        )
        btn_topics_info.grid(row=1, column=0, sticky="ew", padx=4, pady=4)

        btn_compile = ttk.Button(
            grid_cmds,
            text="🔨 Compilar Workspace (colcon build)",
            style="Secondary.TButton",
            command=self._on_compile_workspace
        )
        btn_compile.grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        grid_cmds.columnconfigure(0, weight=1)
        grid_cmds.columnconfigure(1, weight=1)

        # Entrada de comando personalizado
        custom_frame = ttk.LabelFrame(container, text=" Comando ROS 2 Personalizado ", padding=10)
        custom_frame.pack(fill=tk.X, pady=(6, 0))

        entry_row = ttk.Frame(custom_frame)
        entry_row.pack(fill=tk.X)

        self.ent_custom_cmd = ttk.Entry(entry_row, font=("Consolas", 9))
        self.ent_custom_cmd.insert(0, "ros2 topic list")
        self.ent_custom_cmd.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.ent_custom_cmd.bind("<Return>", lambda e: self._on_run_custom_command())

        btn_run_custom = ttk.Button(
            entry_row,
            text="▶ Ejecutar",
            style="Primary.TButton",
            command=self._on_run_custom_command
        )
        btn_run_custom.pack(side=tk.RIGHT)

        ttk.Label(
            custom_frame,
            text="La salida del comando se imprimirá en directo en la pestaña 'Salida y Logs de Simulación'.",
            font=("Segoe UI", 8, "italic"),
            foreground=self.text_muted
        ).pack(anchor="w", pady=(4, 0))

    def _build_advanced_tab_content(self):
        """Pestaña de ajustes avanzados (puerto web, argumentos extra, reconstrucción de imagen)."""
        container = ttk.Frame(self.tab_advanced)
        container.pack(fill=tk.BOTH, expand=True)

        # Fila Puerto Web noVNC
        row_port = ttk.Frame(container)
        row_port.pack(fill=tk.X, pady=4)
        ttk.Label(row_port, text="Puerto Servidor Web noVNC:", width=28).pack(side=tk.LEFT)
        self.ent_web_port = ttk.Entry(row_port, width=10)
        self.ent_web_port.pack(side=tk.LEFT, padx=(0, 8))
        self.ent_web_port.bind("<KeyRelease>", lambda e: self._save_current_settings())
        ttk.Label(row_port, text="(Por defecto: 6080 -> http://localhost:6080/vnc.html)", font=("Segoe UI", 8, "italic"), foreground=self.text_muted).pack(side=tk.LEFT)

        # Fila Argumentos Extra ROS 2
        row_args = ttk.Frame(container)
        row_args.pack(fill=tk.X, pady=4)
        ttk.Label(row_args, text="Argumentos extra para ROS 2:", width=28).pack(side=tk.LEFT)
        self.ent_extra_args = ttk.Entry(row_args)
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
        cb_rebuild.pack(anchor="w", pady=(8, 12))

        # Botones de mantenimiento de Docker
        maint_box = ttk.LabelFrame(container, text=" Mantenimiento de Docker y Caché ", padding=10)
        maint_box.pack(fill=tk.X, pady=(6, 0))

        maint_btns = ttk.Frame(maint_box)
        maint_btns.pack(fill=tk.X)

        self.btn_prep_image = ttk.Button(
            maint_btns,
            text="📦 Reconstruir / Preparar Imagen Docker",
            style="Secondary.TButton",
            command=self._on_pull_or_build_image
        )
        self.btn_prep_image.pack(side=tk.LEFT, padx=(0, 10))

        btn_clean_cache = ttk.Button(
            maint_btns,
            text="🧹 Limpiar Volúmenes de Caché",
            style="Secondary.TButton",
            command=self._on_clean_build_cache
        )
        btn_clean_cache.pack(side=tk.LEFT)

        # Actualizaciones automáticas desde GitHub
        update_box = ttk.LabelFrame(container, text=" Actualizaciones del Software (GitHub) ", padding=10)
        update_box.pack(fill=tk.X, pady=(10, 0))

        update_row = ttk.Frame(update_box)
        update_row.pack(fill=tk.X)

        ttk.Label(
            update_row,
            text=f"Versión instalada: v{CURRENT_VERSION}",
            font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT, padx=(0, 15))

        self.btn_check_updates = ttk.Button(
            update_row,
            text="🔄 Comprobar actualizaciones",
            style="Secondary.TButton",
            command=self._on_manual_check_updates
        )
        self.btn_check_updates.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_update_status = ttk.Label(
            update_row,
            text="Comprobando al iniciar...",
            font=("Segoe UI", 8, "italic"),
            foreground=self.text_muted
        )
        self.lbl_update_status.pack(side=tk.LEFT)

        # Etiqueta indicadora de la ruta de guardado en AppData
        appdata_lbl = ttk.Label(
            container,
            text=f"Archivo de configuración: {self.config_store.config_path}",
            font=("Segoe UI", 8),
            foreground=self.text_muted
        )
        appdata_lbl.pack(anchor="w", pady=(18, 0))

    def _build_guide_tab_content(self):
        """Pestaña con la guía de usuario y prácticas para los estudiantes."""
        guide_text = scrolledtext.ScrolledText(
            self.tab_guide,
            wrap=tk.WORD,
            bg="#ffffff",
            fg="#1e293b",
            font=("Segoe UI", 9),
            padx=12,
            pady=12
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
                self.lbl_ws_status.configure(text=f"✓ {msg}", foreground="#15803d")
            else:
                self.lbl_ws_status.configure(text=f"✓ {msg}", foreground="#1e293b")
        else:
            self.lbl_ws_status.configure(text=f"⚠ {msg}", foreground="#dc2626")

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

    def _check_for_updates_background(self):
        """Comprueba silenciosamente en segundo plano si hay actualizaciones al iniciar el launcher."""
        def _worker():
            has_update, info, msg = check_for_updates(timeout=2.0)
            if has_update and info:
                self.root.after(0, lambda: self._prompt_update_available(info))
                self.root.after(0, lambda: self.lbl_update_status.configure(
                    text=f"Nueva versión v{info.get('version')} disponible",
                    foreground="#15803d"
                ))
            else:
                self.root.after(0, lambda: self.lbl_update_status.configure(
                    text=f"Launcher actualizado (v{CURRENT_VERSION})",
                    foreground=self.text_muted
                ))
        threading.Thread(target=_worker, daemon=True).start()

    def _prompt_update_available(self, update_info: dict):
        """Abre la ventana modal para ofrecer al alumno la actualización."""
        target_dir = Path(__file__).parent.resolve()
        UpdateModalDialog(self.root, update_info, target_dir)

    def _on_manual_check_updates(self):
        """Comprobación manual invocada por el usuario desde la pestaña de Ajustes."""
        self.btn_check_updates.configure(state="disabled")
        self.lbl_update_status.configure(text="Buscando nueva versión en GitHub...", foreground=self.text_muted)

        def _worker():
            has_update, info, msg = check_for_updates(timeout=3.0)
            self.root.after(0, lambda: self.btn_check_updates.configure(state="normal"))

            if has_update and info:
                self.root.after(0, lambda: self.lbl_update_status.configure(
                    text=f"Nueva versión v{info.get('version')} disponible",
                    foreground="#15803d"
                ))
                self.root.after(0, lambda: self._prompt_update_available(info))
            elif "pendiente" in msg.lower():
                self.root.after(0, lambda: self.lbl_update_status.configure(text=msg, foreground="#b45309"))
                self.root.after(0, lambda: messagebox.showinfo(
                    "Actualizaciones",
                    f"{msg}\n\nPara activar las actualizaciones automáticas, edita la variable 'DEFAULT_GITHUB_REPO' en updater.py con tu repositorio de GitHub (ej: 'tu_usuario/tu_repositorio').",
                    parent=self.root
                ))
            elif info:
                self.root.after(0, lambda: self.lbl_update_status.configure(
                    text=f"Al día (v{CURRENT_VERSION})",
                    foreground="#15803d"
                ))
                self.root.after(0, lambda: messagebox.showinfo(
                    "Actualizaciones",
                    f"¡Ya tienes instalada la versión más reciente (v{CURRENT_VERSION})!",
                    parent=self.root
                ))
            else:
                self.root.after(0, lambda: self.lbl_update_status.configure(text=msg, foreground="#b91c1c"))
                self.root.after(0, lambda: messagebox.showwarning("Actualizaciones", msg, parent=self.root))

        threading.Thread(target=_worker, daemon=True).start()

    # --- Acciones Principales: Terminal Docker, Simulación, Web ---

    def _on_open_terminal(self):
        """Funcionalidad 1: Abre una terminal interactiva nativa del contenedor Docker."""
        def _worker():
            # Comprobar si el contenedor está en ejecución
            if not DockerService.is_container_running(DEFAULT_CONTAINER_NAME):
                # Si no está corriendo, preguntar si desea iniciarlo en modo interactivo
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

        self.notebook.select(self.tab_logs)
        self._log("\nIniciando contenedor en modo terminal...\n")

        ws_path = self.ent_ws_path.get().strip()
        domain_id = self.ent_domain_id.get().strip() or "42"
        web_port = self.ent_web_port.get().strip() or str(DEFAULT_NOVNC_PORT)

        # Detener contenedor previo si existiera
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
            # Abrir la terminal
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
        self.notebook.select(self.tab_logs)
        self._log("\n" + "="*50 + "\nIniciando simulación de ROS 2...\n" + "="*50 + "\n")

        def _worker():
            if not DockerService.is_image_available(image_name):
                self._log(f"Imagen '{image_name}' no encontrada localmente. Iniciando preparación...\n")
                self._on_pull_or_build_image()
                return

            # Detener contenedor previo
            DockerService.stop_container(DEFAULT_CONTAINER_NAME)

            # Obtener perfil del robot y generar comando
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

            # Abrir navegador automáticamente tras 2.5 segundos
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
        self.notebook.select(self.tab_logs)

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

        self.notebook.select(self.tab_logs)
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
        self.notebook.select(self.tab_logs)
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
        self.notebook.select(self.tab_logs)
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
            self.lbl_autoscroll_status.configure(text="● Auto-scroll: Activo", foreground="#16a34a")
        else:
            self.lbl_autoscroll_status.configure(text="○ Auto-scroll: Pausado", foreground="#dc2626")

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

        self.txt_logs.tag_configure("ansi_bold", font=("Consolas", 9, "bold"))
        self.txt_logs.tag_configure("ansi_underline", underline=True)


def main():
    root = tk.Tk()
    app = ModernSimulationLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
