"""
Main application window for the ROS 2 Simulation Launcher.
"""

import os
import sys
import time
import logging
import threading
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Tuple, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from config_store import ConfigStore
from robot_registry import (
    get_all_robots,
    get_robot_by_id,
    get_robot_by_name,
    RobotProfile
)
from docker_service import (
    DockerService,
    DockerState,
    ContainerState,
    COURSE_IMAGE_NAME,
    DEFAULT_CONTAINER_NAME,
    DEFAULT_NOVNC_PORT
)
from updater import (
    CURRENT_VERSION,
    check_for_updates,
    UpdateModalDialog
)
from embedded_icon import (
    get_app_icon_path,
    get_dropdown_arrow_path,
    get_themed_icon
)
from theme import (
    THEME_PALETTES,
    get_status_colors,
    is_dark_mode,
    set_window_dark_mode,
    build_global_stylesheet,
    style_badge,
    style_status_label
)
from utils import (
    ProcessRunnerThread,
    AnsiColorParser,
    DOCKERFILE_CONTENT,
    ensure_dockerfile_sync,
    GUIDE_MARKDOWN
)
from physical_tab import PhysicalRobotTab

logger = logging.getLogger("launcher")


class ModernSimulationLauncher(QtWidgets.QMainWindow):
    """
    Main application window providing controls for ROS 2 simulations,
    Docker container lifecycle, quick inspection commands, and hardware management.
    """

    sig_docker_state_changed = QtCore.Signal(object)
    sig_manual_update_result = QtCore.Signal(bool, object, str)
    sig_docker_status = QtCore.Signal(bool, bool, str)
    sig_docker_ready = QtCore.Signal()
    sig_docker_failed = QtCore.Signal(str)
    sig_docker_poll_progress = QtCore.Signal(int, int)
    sig_container_status = QtCore.Signal(object)
    sig_container_state_changed = QtCore.Signal(object)
    sig_log_received = QtCore.Signal(str)
    sig_robot_scan_finished = QtCore.Signal(bool, str, bool, str, str)

    def __init__(self, enable_background_tasks: Optional[bool] = None):
        super().__init__()
        self.setWindowTitle(f"ROS 2 Jazzy - Launcher de simulación (v{CURRENT_VERSION}) | Sistemas de Navegación")
        self.resize(1020, 680)
        self.setMinimumSize(880, 520)

        # Determinar si se habilitan las tareas de sondeo en segundo plano (desactivadas en pruebas)
        if enable_background_tasks is None:
            self._enable_background_tasks = not bool(os.environ.get("PYTEST_CURRENT_TEST"))
        else:
            self._enable_background_tasks = enable_background_tasks
        self._is_closing = False

        self.config_store = ConfigStore(fallback_dir=Path(__file__).parent.resolve())
        self.active_sim_thread: Optional[ProcessRunnerThread] = None
        self.active_cmd_thread: Optional[ProcessRunnerThread] = None
        self.compile_runner: Optional[ProcessRunnerThread] = None
        self.autoscroll_enabled = True
        self.ansi_parser = AnsiColorParser()
        self.latest_update_info: Optional[Dict] = None

        self._docker_state: DockerState = DockerState.NOT_RUNNING
        self._docker_poll_timer: Optional[QtCore.QTimer] = None
        self._docker_poll_count = 0
        self._is_loading_preferences = True

        self._container_state: ContainerState = ContainerState.NOT_RUNNING
        self._container_miss_count = 0
        self._is_checking_container: bool = False
        self._container_poll_timer: Optional[QtCore.QTimer] = None

        # Cross-thread signal connections
        self.sig_manual_update_result.connect(self._on_manual_update_result)
        self.sig_docker_status.connect(self._apply_docker_status)
        self.sig_docker_ready.connect(self._on_docker_ready)
        self.sig_docker_failed.connect(self._on_docker_start_failed)
        self.sig_docker_poll_progress.connect(self._on_docker_poll_progress)
        self.sig_container_status.connect(self._on_container_status_changed)
        self.sig_container_state_changed.connect(self._on_container_status_changed)
        self.sig_log_received.connect(self._append_log_main_thread)

        saved_theme = self.config_store.get("theme_mode", "")
        if saved_theme in ("dark", "light"):
            self._is_dark = (saved_theme == "dark")
        else:
            self._is_dark = self.is_dark_mode()

        self._setup_window_icon()
        self._build_ui()
        self._apply_theme(self._is_dark)
        self._load_saved_preferences()
        self._update_action_buttons_state()

        if self._enable_background_tasks:
            self._start_container_poll_timer()
            self._check_docker_live_status()

            if "--force-update" in sys.argv:
                QtCore.QTimer.singleShot(1000, lambda: self._on_manual_check_updates(force=True))
            else:
                QtCore.QTimer.singleShot(1500, self._check_for_updates_background)

        hints = QtWidgets.QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_color_scheme_changed)

    @property
    def docker_state(self) -> DockerState:
        return self._docker_state

    def _set_docker_state(self, new_state: DockerState):
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

    @property
    def container_state(self) -> ContainerState:
        return self._container_state

    def _set_container_state(self, new_state: ContainerState):
        self._on_container_status_changed(new_state)

    @property
    def _is_container_running(self) -> bool:
        return self._container_state == ContainerState.RUNNING

    @_is_container_running.setter
    def _is_container_running(self, val: bool):
        self._container_state = ContainerState.RUNNING if val else ContainerState.NOT_RUNNING

    @property
    def _is_launching_sim(self) -> bool:
        return self._container_state == ContainerState.STARTING

    @_is_launching_sim.setter
    def _is_launching_sim(self, val: bool):
        if val:
            self._container_state = ContainerState.STARTING
        elif self._container_state == ContainerState.STARTING:
            self._container_state = ContainerState.NOT_RUNNING

    @property
    def _is_stopping_sim(self) -> bool:
        return self._container_state == ContainerState.STOPPING

    @_is_stopping_sim.setter
    def _is_stopping_sim(self, val: bool):
        if val:
            self._container_state = ContainerState.STOPPING
        elif self._container_state == ContainerState.STOPPING:
            self._container_state = ContainerState.NOT_RUNNING

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
        return is_dark_mode()

    @QtCore.Slot(QtCore.Qt.ColorScheme)
    def _on_color_scheme_changed(self, scheme: QtCore.Qt.ColorScheme):
        is_dark = (scheme == QtCore.Qt.ColorScheme.Dark)
        logger.info("Cambio de tema nativo del sistema detectado: %s", "Oscuro" if is_dark else "Claro")
        self._apply_theme(is_dark)

    def _apply_theme(self, is_dark: Optional[bool] = None):
        if is_dark is None:
            is_dark = self.is_dark_mode()
        self._is_dark = is_dark
        self._apply_global_styles(is_dark)
        if sys.platform == "win32":
            set_window_dark_mode(int(self.winId()), is_dark)
        self._refresh_icons(is_dark)
        self._update_workspace_validation()
        self._refresh_docker_badge_style()
        if hasattr(self, "physical_tab"):
            self.physical_tab.refresh_theme(is_dark)

    def _toggle_theme(self):
        new_dark = not self._is_dark
        if hasattr(self, "config_store"):
            self.config_store.set("theme_mode", "dark" if new_dark else "light")
        self._apply_theme(new_dark)

    def _style_badge(self, label: QtWidgets.QLabel, text: str, kind: str):
        style_badge(label, text, kind, getattr(self, "_is_dark", False))

    def _style_status_label(self, label: QtWidgets.QLabel, text: str, kind: str):
        style_status_label(label, text, kind, getattr(self, "_is_dark", False))

    def _set_button_variant(self, btn: QtWidgets.QPushButton, variant: Optional[str] = None):
        btn.setProperty("variant", variant if variant else None)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _refresh_docker_badge_style(self):
        if hasattr(self, "_last_docker_status"):
            installed, running, daemon_msg = self._last_docker_status
            self._apply_docker_status(installed, running, daemon_msg)

    def _refresh_icons(self, is_dark: bool):
        p = THEME_PALETTES["dark" if is_dark else "light"]
        col = p["icon_color"]

        if hasattr(self, "btn_theme_toggle"):
            if is_dark:
                self.btn_theme_toggle.setText("Modo claro")
                self.btn_theme_toggle.setIcon(get_themed_icon("weather-clear", color=col, fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton))
                self.btn_theme_toggle.setToolTip("Cambiar a tema claro")
            else:
                self.btn_theme_toggle.setText("Modo oscuro")
                self.btn_theme_toggle.setIcon(get_themed_icon("weather-clear-night", color=col, fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton))
                self.btn_theme_toggle.setToolTip("Cambiar a tema oscuro")

        if hasattr(self, "btn_header_update"):
            if self.latest_update_info:
                self._set_button_variant(self.btn_header_update, "success")
            else:
                self._set_button_variant(self.btn_header_update, None)
                self.btn_header_update.setIcon(get_themed_icon("system-software-update", color=col, fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_ArrowUp))
        if hasattr(self, "btn_docker"):
            if self._docker_state == DockerState.RUNNING:
                self.btn_docker.setIcon(get_themed_icon("view-refresh", color=col, fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload))

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
        ]
        for attr, key, fallback in btn_icon_map:
            if hasattr(self, attr):
                getattr(self, attr).setIcon(get_themed_icon(key, color=col, fallback_sp=fallback))

        if hasattr(self, "physical_tab"):
            self.physical_tab.refresh_theme(is_dark)

        if hasattr(self, "tab_widget"):
            self._on_tab_changed(self.tab_widget.currentIndex())

        if hasattr(self, "txt_guide"):
            self._update_guide_styles()

    def _apply_global_styles(self, is_dark: bool):
        arrow_path = get_dropdown_arrow_path(is_dark)
        arrow_url = arrow_path.as_posix() if hasattr(arrow_path, "as_posix") else str(arrow_path).replace("\\", "/")
        stylesheet = build_global_stylesheet(is_dark, arrow_url)
        self.setStyleSheet(stylesheet)

    # -----------------------------------------------------------------------
    # UI Building
    # -----------------------------------------------------------------------

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._build_header(main_layout)

        content_container = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_container)
        content_layout.setContentsMargins(18, 12, 18, 14)
        content_layout.setSpacing(10)

        self._build_action_bar(content_layout)
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

        self.btn_theme_toggle = QtWidgets.QPushButton("Modo claro" if self._is_dark else "Modo oscuro")
        self.btn_theme_toggle.setObjectName("btnThemeToggle")
        self.btn_theme_toggle.setIconSize(QtCore.QSize(16, 16))
        self.btn_theme_toggle.clicked.connect(self._toggle_theme)
        self.btn_theme_toggle.setFixedHeight(30)
        self.btn_theme_toggle.setMinimumWidth(115)
        self.btn_theme_toggle.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        h_layout.addWidget(self.btn_theme_toggle)

        self.btn_header_update = QtWidgets.QPushButton(f"v{CURRENT_VERSION}")
        self.btn_header_update.setObjectName("btnHeaderUpdate")
        self.btn_header_update.setIconSize(QtCore.QSize(16, 16))
        self.btn_header_update.clicked.connect(self._on_header_update_clicked)
        self.btn_header_update.setFixedHeight(30)
        self.btn_header_update.setMinimumWidth(115)
        self.btn_header_update.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        h_layout.addWidget(self.btn_header_update)

        self.lbl_docker_badge = QtWidgets.QLabel("● Comprobando Docker...")
        self.lbl_docker_badge.setFixedHeight(30)
        self.lbl_docker_badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._style_badge(self.lbl_docker_badge, "● Comprobando Docker...", "warning")
        h_layout.addWidget(self.lbl_docker_badge)

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

        self.tab_icon_keys = [
            "document-properties",
            "utilities-terminal",
            "applications-development",
            "network-wired",
            "applications-system",
            "help-browser"
        ]

        # 1. Config Tab
        self.tab_config = QtWidgets.QWidget()
        self._build_config_tab(self.tab_config)
        self.tab_widget.addTab(self.tab_config, QtGui.QIcon(), "Configuración de simulación")

        # 2. Logs Tab
        self.tab_logs = QtWidgets.QWidget()
        self._build_logs_tab(self.tab_logs)
        self.tab_widget.addTab(self.tab_logs, QtGui.QIcon(), "Salida y logs")

        # 3. Quick Commands Tab
        self.tab_quick = QtWidgets.QWidget()
        self._build_quick_tab(self.tab_quick)
        self.tab_widget.addTab(self.tab_quick, QtGui.QIcon(), "Comandos rápidos")

        # 4. Physical Robot Tab (TurtleBot 4)
        self.tab_physical = QtWidgets.QScrollArea()
        self.tab_physical.setObjectName("scrollPhysical")
        self.tab_physical.setWidgetResizable(True)
        self.tab_physical.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.tab_physical.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tab_physical.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tab_physical.viewport().setAutoFillBackground(False)

        self.physical_tab = PhysicalRobotTab(
            self.config_store,
            lambda: self.ent_ws_path.text(),
            parent=self
        )
        self.physical_tab.sig_log_message.connect(self._append_log)
        self.physical_tab.sig_request_tab_switch.connect(self.tab_widget.setCurrentIndex)
        self.physical_tab.sig_show_info.connect(self._show_info_box)
        self.physical_tab.sig_show_warning.connect(self._show_warning_box)
        self.tab_physical.setWidget(self.physical_tab)
        self.tab_widget.addTab(self.tab_physical, QtGui.QIcon(), "TurtleBot 4")

        # Backward compatibility attribute aliases
        self.ent_robot_ip = self.physical_tab.ent_robot_ip
        self.ent_robot_user = self.physical_tab.ent_robot_user
        self.ent_robot_password = self.physical_tab.ent_robot_password
        self.ent_robot_port = self.physical_tab.ent_robot_port
        self.ent_robot_ws = self.physical_tab.ent_robot_ws
        self.btn_scan_robot = self.physical_tab.btn_scan_robot
        self.btn_robot_scp = self.physical_tab.btn_robot_scp
        self.btn_robot_compile = self.physical_tab.btn_robot_compile
        self.btn_robot_terminal = self.physical_tab.btn_robot_terminal
        self.lbl_wifi_badge = self.physical_tab.lbl_wifi_badge
        self.lbl_robot_badge = self.physical_tab.lbl_robot_badge

        # 5. Advanced Settings Tab
        self.tab_advanced = QtWidgets.QWidget()
        self._build_advanced_tab(self.tab_advanced)
        self.tab_widget.addTab(self.tab_advanced, QtGui.QIcon(), "Ajustes avanzados")

        # 6. Student Guide Tab
        self.tab_guide = QtWidgets.QWidget()
        self._build_guide_tab(self.tab_guide)
        self.tab_widget.addTab(self.tab_guide, QtGui.QIcon(), "Guía del estudiante")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self._on_tab_changed(self.tab_widget.currentIndex())

        parent_layout.addWidget(self.tab_widget, 1)

    def _on_tab_changed(self, index: int):
        p = THEME_PALETTES["dark" if self._is_dark else "light"]
        for i in range(self.tab_widget.count()):
            is_sel = (i == index)
            col = p["tab_icon_selected"] if is_sel else p["tab_icon_normal"]
            if i < len(self.tab_icon_keys):
                self.tab_widget.setTabIcon(i, get_themed_icon(self.tab_icon_keys[i], color=col))
        if index == 3 and hasattr(self, "physical_tab"):
            self.physical_tab.on_tab_opened()

    def _build_config_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # Workspace Card
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

        # Sim Parameters Card
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

        ctrl_bar = QtWidgets.QHBoxLayout()
        self.lbl_autoscroll = QtWidgets.QLabel()
        self._style_status_label(self.lbl_autoscroll, "● Auto-scroll: Activo", "success")
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

        self.txt_logs = QtWidgets.QPlainTextEdit()
        self.txt_logs.setObjectName("txtLogs")
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setMaximumBlockCount(10000)
        layout.addWidget(self.txt_logs, 1)

    def _build_quick_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        cmd_card = QtWidgets.QFrame()
        cmd_card.setProperty("card", True)
        cmd_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        cmd_layout = QtWidgets.QVBoxLayout(cmd_card)
        cmd_layout.setContentsMargins(16, 14, 16, 14)
        cmd_layout.setSpacing(12)

        lbl_intro = QtWidgets.QLabel("Comandos de inspección y control")
        lbl_intro.setProperty("heading", True)
        cmd_layout.addWidget(lbl_intro)

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
        btn_run_custom.setProperty("variant", "primary")
        btn_run_custom.clicked.connect(self._on_run_custom_command)
        custom_row.addWidget(btn_run_custom)
        c_layout.addLayout(custom_row)

        lbl_custom_note = QtWidgets.QLabel("La salida del comando se imprimirá en directo en la pestaña 'Salida y logs'.")
        lbl_custom_note.setProperty("note", True)
        c_layout.addWidget(lbl_custom_note)

        layout.addWidget(custom_card)
        layout.addStretch()

    def _build_advanced_tab(self, parent: QtWidgets.QWidget):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # Network & Env Card
        net_card = QtWidgets.QFrame()
        net_card.setProperty("card", True)
        net_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        n_layout = QtWidgets.QVBoxLayout(net_card)
        n_layout.setContentsMargins(16, 14, 16, 14)
        n_layout.setSpacing(10)

        lbl_net_title = QtWidgets.QLabel("Ajustes de red y entorno")
        lbl_net_title.setProperty("heading", True)
        n_layout.addWidget(lbl_net_title)

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

        row_args = QtWidgets.QHBoxLayout()
        lbl_args = QtWidgets.QLabel("Argumentos extra para ROS 2:")
        lbl_args.setFixedWidth(210)
        row_args.addWidget(lbl_args)
        self.ent_extra_args = QtWidgets.QLineEdit()
        self.ent_extra_args.textChanged.connect(self._save_current_settings)
        row_args.addWidget(self.ent_extra_args, 1)
        n_layout.addLayout(row_args)

        self.chk_force_rebuild = QtWidgets.QCheckBox("Forzar recompilación completa con colcon en cada inicio de simulación")
        self.chk_force_rebuild.stateChanged.connect(self._save_current_settings)
        n_layout.addWidget(self.chk_force_rebuild)

        layout.addWidget(net_card)

        # Maintenance Card
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

        # Updates Card
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

    # -----------------------------------------------------------------------
    # Preferences & Settings
    # -----------------------------------------------------------------------

    def _load_saved_preferences(self):
        self._is_loading_preferences = True
        try:
            saved_ws = self.config_store.get("workspace_path")
            self.ent_ws_path.setText(saved_ws)
            self._update_workspace_validation()

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

            saved_world = self.config_store.get("world_name", "warehouse")
            idx_w = self.cbo_world.findText(saved_world)
            if idx_w >= 0:
                self.cbo_world.blockSignals(True)
                self.cbo_world.setCurrentIndex(idx_w)
                self.cbo_world.blockSignals(False)

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

            self.ent_domain_id.setText(str(self.config_store.get("ros_domain_id", "42")))
            self.ent_web_port.setText(str(self.config_store.get("web_port", str(DEFAULT_NOVNC_PORT))))
            self.ent_extra_args.setText(str(self.config_store.get("extra_args", "use_sim_time:=true")))
            self.chk_force_rebuild.setChecked(bool(self.config_store.get("force_rebuild", False)))

            if hasattr(self, "physical_tab"):
                self.physical_tab.load_preferences()
        finally:
            self._is_loading_preferences = False

    def _save_current_settings(self):
        if getattr(self, "_is_loading_preferences", False):
            return

        robot_id = self.cbo_robot.currentData()
        if robot_id:
            self.config_store.set("robot_id", robot_id)

        self.config_store.set("world_name", self.cbo_world.currentText().strip())

        selected_robot_name = self.cbo_robot.currentText()
        robot_profile = get_robot_by_id(robot_id) if robot_id else None
        if not robot_profile:
            robot_profile = get_robot_by_name(selected_robot_name)
        if robot_profile:
            selected_sc_name = self.cbo_scenario.currentText()
            sc_obj = robot_profile.get_scenario_by_name(selected_sc_name)
            if sc_obj:
                self.config_store.set("scenario_id", sc_obj.id)

        self.config_store.set("workspace_path", self.ent_ws_path.text().strip())
        self.config_store.set("ros_domain_id", self.ent_domain_id.text().strip())
        self.config_store.set("web_port", self.ent_web_port.text().strip())
        self.config_store.set("extra_args", self.ent_extra_args.text().strip())
        self.config_store.set("force_rebuild", self.chk_force_rebuild.isChecked())

        if hasattr(self, "physical_tab"):
            self.physical_tab.save_preferences()

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
            kind = "success" if "detectado" in msg else "info"
            self._style_status_label(self.lbl_ws_status, f"[OK] {msg}", kind)
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

    # -----------------------------------------------------------------------
    # Container & Docker Monitoring
    # -----------------------------------------------------------------------

    def _start_container_poll_timer(self):
        if self._container_poll_timer is None:
            self._container_poll_timer = QtCore.QTimer(self)
            self._container_poll_timer.setInterval(2000)
            self._container_poll_timer.timeout.connect(self._check_container_live_status)
        if not self._container_poll_timer.isActive():
            self._container_poll_timer.start()

    def _check_container_live_status(self):
        if self._docker_state != DockerState.RUNNING or self._is_closing:
            if self._container_state != ContainerState.NOT_RUNNING and not self._is_closing:
                self.sig_container_status.emit(ContainerState.NOT_RUNNING)
            return

        # Do not check or interfere during transitions
        if self._container_state in (ContainerState.STARTING, ContainerState.STOPPING):
            return

        if self._is_checking_container:
            return
        self._is_checking_container = True

        def _worker():
            try:
                if self._is_closing:
                    return
                running = DockerService.is_container_running(DEFAULT_CONTAINER_NAME, timeout=3.5)
                if self._is_closing:
                    return

                # Avoid transient false negatives while active_sim_thread is still running
                if not running and self.active_sim_thread and self.active_sim_thread.isRunning():
                    self._container_miss_count = getattr(self, "_container_miss_count", 0) + 1
                    if self._container_miss_count < 2:
                        return
                else:
                    self._container_miss_count = 0

                # Ensure we haven't entered a transition state while worker was running
                if not self._is_closing and self._container_state not in (ContainerState.STARTING, ContainerState.STOPPING):
                    new_state = ContainerState.RUNNING if running else ContainerState.NOT_RUNNING
                    self.sig_container_status.emit(new_state)
            except Exception:
                pass
            finally:
                self._is_checking_container = False

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(object)
    def _on_container_status_changed(self, status):
        if isinstance(status, ContainerState):
            new_state = status
        elif isinstance(status, bool):
            new_state = ContainerState.RUNNING if status else ContainerState.NOT_RUNNING
        else:
            return

        changed = (self._container_state != new_state)
        self._container_state = new_state
        if changed:
            logger.info("Estado del contenedor: %s", new_state.value)
        self._update_action_buttons_state()

    @QtCore.Slot()
    def _update_action_buttons_state(self):
        state = self._container_state
        docker_starting = (self._docker_state == DockerState.STARTING)

        selected_sc_name = self.cbo_scenario.currentText()
        is_container_only = (
            "solo contenedor" in selected_sc_name.lower()
            or "modo libre" in selected_sc_name.lower()
        )

        can_launch = (state == ContainerState.NOT_RUNNING) and not docker_starting
        self.btn_launch.setEnabled(can_launch)
        self.btn_launch.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor if can_launch else QtCore.Qt.CursorShape.ArrowCursor
        )

        can_stop = (state == ContainerState.RUNNING) and not docker_starting
        self.btn_stop.setEnabled(can_stop)
        self.btn_stop.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor if can_stop else QtCore.Qt.CursorShape.ArrowCursor
        )

        if docker_starting:
            self.btn_launch.setToolTip("Esperando a que Docker Desktop termine de arrancar...")
            self.btn_stop.setToolTip("Docker Desktop se está iniciando...")
        elif state == ContainerState.STARTING:
            self.btn_launch.setToolTip("Iniciando contenedor o simulación...")
            self.btn_stop.setToolTip("El contenedor se está iniciando...")
            self.prog_bar.setRange(0, 0)
            self.lbl_progress.setText("Iniciando contenedor..." if is_container_only else "Iniciando simulación...")
        elif state == ContainerState.STOPPING:
            self.btn_launch.setToolTip("Deteniendo contenedor...")
            self.btn_stop.setToolTip("Deteniendo contenedor en ejecución...")
            self.prog_bar.setRange(0, 0)
            self.lbl_progress.setText("Deteniendo contenedor...")
        elif state == ContainerState.RUNNING:
            self.btn_launch.setToolTip("La simulación o contenedor ya se encuentra en ejecución.")
            self.btn_stop.setToolTip("Detiene y elimina el contenedor Docker en ejecución.")
            self.prog_bar.setRange(0, 100)
            self.prog_bar.setValue(100)
            self.lbl_progress.setText("Contenedor en ejecución" if is_container_only else "Simulación en ejecución")
        else:
            self.prog_bar.setRange(0, 100)
            self.prog_bar.setValue(0)
            self.lbl_progress.setText("Listo")
            self.btn_stop.setToolTip("El contenedor no está en ejecución.")
            if is_container_only:
                self.btn_launch.setToolTip("Inicia el contenedor Docker con el workspace montado en modo libre")
            else:
                self.btn_launch.setToolTip("Inicia la simulación ROS 2 seleccionada")

    def _check_docker_live_status(self):
        if self._docker_state == DockerState.STARTING or self._is_closing:
            return

        self._style_badge(self.lbl_docker_badge, "● Comprobando Docker...", "warning")

        def _worker():
            try:
                if self._is_closing:
                    return
                installed, _ = DockerService.check_docker_installed()
                if self._is_closing:
                    return
                if not installed:
                    self.sig_docker_status.emit(False, False, "")
                    return
                running, daemon_msg = DockerService.check_docker_running()
                if self._is_closing:
                    return
                self.sig_docker_status.emit(True, running, daemon_msg)
            except Exception as e:
                logger.debug("Error en _worker de verificación de Docker: %s", e)

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
            err_fg, _, _ = get_status_colors("error", is_dark)
            self._style_badge(self.lbl_docker_badge, "● Docker no encontrado", "error")
            self.btn_docker.setText("Instalar Docker")
            self.btn_docker.setIcon(get_themed_icon("help-browser", color=err_fg, fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_DialogHelpButton))
            self.btn_docker.setToolTip("Docker no está instalado en este sistema. Clic para ver opciones de descarga.")
            self._set_button_variant(self.btn_docker, "danger")
            self.btn_docker.setEnabled(True)
            self.sig_container_status.emit(ContainerState.NOT_RUNNING)
        elif running:
            self._style_badge(self.lbl_docker_badge, f"● {daemon_msg}", "success")
            self.btn_docker.setText("Docker")
            self.btn_docker.setIcon(get_themed_icon("view-refresh", color=p["icon_color"], fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload))
            self.btn_docker.setToolTip("Docker activo y funcionando. Clic para volver a comprobar el estado.")
            self._set_button_variant(self.btn_docker, None)
            self.btn_docker.setEnabled(True)
            self._check_container_live_status()
            self._update_docker_image_ui_state()
        else:
            self._style_badge(self.lbl_docker_badge, "● Docker detenido", "warning")
            self.btn_docker.setText("Iniciar Docker")
            self.btn_docker.setIcon(get_themed_icon("media-playback-start", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_MediaPlay))
            self.btn_docker.setToolTip("Docker no está corriendo. Clic para arrancar Docker Desktop en Windows.")
            self._set_button_variant(self.btn_docker, "primary")
            self.btn_docker.setEnabled(True)
            self.sig_container_status.emit(ContainerState.NOT_RUNNING)

    def _on_docker_button_clicked(self):
        if self._docker_state == DockerState.STARTING:
            return

        installed, _ = DockerService.check_docker_installed()
        if not installed:
            ans = QtWidgets.QMessageBox.question(
                self,
                "Docker no encontrado",
                "Docker no se encuentra instalado en tu sistema.\n\n¿Deseas abrir el navegador para descargar e instalar Docker Desktop?",
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
        self._set_button_variant(self.btn_docker, None)

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

            time.sleep(3.0)
            elapsed += 3.0

            while elapsed < max_seconds:
                if self._docker_state != DockerState.STARTING:
                    return

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

    # -----------------------------------------------------------------------
    # Updates Management
    # -----------------------------------------------------------------------

    def _on_header_update_clicked(self):
        if self.latest_update_info:
            self._prompt_update_available(self.latest_update_info)
        else:
            self._on_manual_check_updates()

    def _check_for_updates_background(self, force: bool = False):
        if self._is_closing:
            return

        def _worker():
            try:
                if self._is_closing:
                    return
                has_update, info, _ = check_for_updates(timeout=3.0, force=force)
                if self._is_closing:
                    return
                if has_update and info:
                    ver = info.get("version", "")
                    self.latest_update_info = info
                    QtCore.QMetaObject.invokeMethod(
                        self, "_on_update_found_bg", QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, ver)
                    )
                else:
                    self.latest_update_info = None
            except Exception as e:
                logger.debug("Error en worker de comprobación de actualizaciones: %s", e)

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(str)
    def _on_update_found_bg(self, ver: str):
        self.btn_header_update.setText(f"Actualizar v{ver}")
        self.btn_header_update.setIcon(get_themed_icon("system-software-update", color="#ffffff", fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_ArrowUp))
        self._set_button_variant(self.btn_header_update, "success")
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
            self._set_button_variant(self.btn_header_update, "success")
            self._style_status_label(self.lbl_update_status, f"Nueva versión v{ver} disponible", "success")
            self._prompt_update_available(info, is_forced=is_forced)
        elif info:
            self.latest_update_info = None
            self._set_button_variant(self.btn_header_update, None)
            self._style_status_label(self.lbl_update_status, f"Al día (v{CURRENT_VERSION})", "success")
            QtWidgets.QMessageBox.information(
                self,
                "Actualizaciones",
                f"¡Ya tienes instalada la versión más reciente (v{CURRENT_VERSION})!"
            )
        else:
            self.latest_update_info = None
            self._set_button_variant(self.btn_header_update, None)
            self._style_status_label(self.lbl_update_status, msg, "error")
            QtWidgets.QMessageBox.warning(self, "Actualizaciones", msg)

    # -----------------------------------------------------------------------
    # Simulation & Container Execution
    # -----------------------------------------------------------------------

    def _open_web_gui(self):
        port = self.ent_web_port.text().strip() or str(DEFAULT_NOVNC_PORT)
        url = f"http://localhost:{port}/vnc.html?autoconnect=true&resize=scale"
        webbrowser.open(url)

    def _on_open_terminal(self):
        if self._docker_state == DockerState.STARTING:
            self._show_warning_box("Docker", "Docker Desktop se está iniciando en este momento.\nPor favor espera a que el servicio esté listo.")
            return

        if self._container_state == ContainerState.STARTING:
            self._show_warning_box("Terminal", "El contenedor se está iniciando en este momento.\nPor favor espera a que esté listo.")
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

        if self._container_state in (ContainerState.STARTING, ContainerState.STOPPING):
            return

        if self._container_state == ContainerState.RUNNING:
            self._show_warning_box("Simulación", "La simulación o contenedor ya se encuentra en ejecución.\nDetén el contenedor actual antes de iniciar una nueva simulación.")
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

        # Disable both buttons immediately by entering STARTING state
        self.sig_container_status.emit(ContainerState.STARTING)

        def _worker():
            try:
                if not DockerService.is_image_available(image_name):
                    self._append_log(f"Imagen '{image_name}' no encontrada localmente. Iniciando preparación...\n")
                    self.sig_container_status.emit(ContainerState.NOT_RUNNING)
                    QtCore.QMetaObject.invokeMethod(self, "_prompt_initial_image_build", QtCore.Qt.ConnectionType.QueuedConnection)
                    return

                expected_hash = DockerService.compute_dockerfile_hash(DOCKERFILE_CONTENT)
                stored_hash = self.config_store.get("dockerfile_content_hash")
                is_up_to_date = DockerService.is_image_up_to_date(
                    image_name, expected_hash, fallback_hash=stored_hash
                )
                if not is_up_to_date and not skip_update_check:
                    self._append_log(
                        f"[AVISO] Se detectaron modificaciones en DOCKERFILE_CONTENT pendientes de aplicar a la imagen '{image_name}'.\n"
                    )
                    self.sig_container_status.emit(ContainerState.NOT_RUNNING)
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

                def _on_sim_finished(rc):
                    self._append_log(f"\n[El proceso finalizó con código de salida {rc}]\n")
                    self.sig_container_status.emit(ContainerState.NOT_RUNNING)

                def _on_sim_error(err):
                    self._append_log(f"\n[Error durante la ejecución: {err}]\n")
                    self.sig_container_status.emit(ContainerState.NOT_RUNNING)

                self.active_sim_thread = ProcessRunnerThread(docker_cmd)
                self.active_sim_thread.signals.line_received.connect(self._append_log)
                self.active_sim_thread.signals.finished.connect(_on_sim_finished)
                self.active_sim_thread.signals.error.connect(_on_sim_error)
                self.active_sim_thread.start()

                # Esperar a que el contenedor esté efectivamente en ejecución antes de cambiar a RUNNING
                max_startup_seconds = 15.0
                poll_interval = 0.4
                elapsed = 0.0
                container_started = False

                while elapsed < max_startup_seconds:
                    if not self.active_sim_thread or not self.active_sim_thread.isRunning():
                        # Proceso finalizó prematuramente
                        break
                    if DockerService.is_container_running(DEFAULT_CONTAINER_NAME, timeout=1.5):
                        container_started = True
                        break
                    time.sleep(poll_interval)
                    elapsed += poll_interval

                if container_started:
                    self.sig_container_status.emit(ContainerState.RUNNING)
                    if scenario_id in ("container_only", "bash"):
                        self._append_log("Abriendo terminal nativa conectada al contenedor...\n")
                        QtCore.QTimer.singleShot(1000, self._on_open_terminal)
                    else:
                        QtCore.QTimer.singleShot(1500, self._open_web_gui)
                else:
                    if self.active_sim_thread and self.active_sim_thread.isRunning():
                        # Si sigue corriendo el proceso aunque docker ps tardara, pasamos a RUNNING
                        self.sig_container_status.emit(ContainerState.RUNNING)
                        if scenario_id in ("container_only", "bash"):
                            QtCore.QTimer.singleShot(1000, self._on_open_terminal)
                        else:
                            QtCore.QTimer.singleShot(1500, self._open_web_gui)
                    else:
                        self.sig_container_status.emit(ContainerState.NOT_RUNNING)

            except Exception as e:
                self._append_log(f"\n[Error durante el arranque: {e}]\n")
                self.sig_container_status.emit(ContainerState.NOT_RUNNING)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stop_simulation(self):
        if self._container_state in (ContainerState.NOT_RUNNING, ContainerState.STOPPING):
            return

        self.tab_widget.setCurrentIndex(1)  # Logs
        self.sig_container_status.emit(ContainerState.STOPPING)

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
                self.sig_container_status.emit(ContainerState.NOT_RUNNING)

        threading.Thread(target=_worker, daemon=True).start()

    # -----------------------------------------------------------------------
    # Quick Commands & Compilation
    # -----------------------------------------------------------------------

    def _execute_quick_command(self, cmd_str: str):
        if self._container_state == ContainerState.STARTING:
            QtWidgets.QMessageBox.information(
                self,
                "Contenedor iniciando",
                "El contenedor se está iniciando en este momento.\nPor favor espera a que esté listo antes de ejecutar comandos."
            )
            return

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
            deleted_items = []

            # 1. Clean host folders if they exist
            if ws_path and os.path.exists(ws_path):
                host_ws_root = Path(ws_path).resolve()
                if (host_ws_root / "package.xml").is_file():
                    host_ws_root = host_ws_root.parent
                for folder in ["build", "install", "log"]:
                    target_dir = host_ws_root / folder
                    if target_dir.is_dir():
                        try:
                            import shutil
                            shutil.rmtree(target_dir, ignore_errors=True)
                            deleted_items.append(f"Directorio local '{folder}/'")
                        except Exception as e:
                            logger.warning("No se pudo eliminar %s en host: %s", target_dir, e)

            # 2. Clean docker volumes
            vols_to_clean = ["ros2_jazzy_build_cache", "ros2_jazzy_install_cache", "ros2_jazzy_log_cache"]
            for vol in vols_to_clean:
                clean_cmd = ["docker", "volume", "rm", "-f", vol]
                try:
                    subprocess.run(
                        clean_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=5.0,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    )
                    deleted_items.append(f"Volumen Docker '{vol}'")
                except Exception as e:
                    logger.warning("No se pudo resetear el volumen %s: %s", vol, e)

            # 3. Clean inside container if running
            if DockerService.is_container_running(DEFAULT_CONTAINER_NAME):
                DockerService.clean_build_volumes(DEFAULT_CONTAINER_NAME)
                deleted_items.append("Directorios temporales internos del contenedor")

            self._append_log("\n[Limpieza completada con éxito]\nElementos procesados:\n")
            for item in deleted_items:
                self._append_log(f"  • {item} limpiado.\n")
            self._append_log("\nPuedes pulsar 'Compilar workspace' para reconstruir desde cero.\n\n")

            QtCore.QMetaObject.invokeMethod(
                self, "_show_info_box", QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, "Limpieza de Compilación"),
                QtCore.Q_ARG(str, "Los directorios y volúmenes de compilación ('build', 'install', 'log') han sido eliminados correctamente.\n\nEl workspace está listo para compilarse desde cero.")
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _on_clean_build_cache(self):
        ans = QtWidgets.QMessageBox.question(
            self,
            "Limpiar Caché Docker",
            "¿Deseas resetear los volúmenes de caché de compilación de Docker?\n\n"
            "Esto forzará una compilación limpia de todos los paquetes ROS 2.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if ans != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        self.tab_widget.setCurrentIndex(1)
        self._append_log("\nLimpiando volúmenes de caché de compilación...\n")

        def _worker():
            ok, msg = DockerService.clean_build_volumes(DEFAULT_CONTAINER_NAME)
            self._append_log(f"{msg}\n")
            QtCore.QMetaObject.invokeMethod(
                self, "_show_info_box", QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(str, "Caché Docker"),
                QtCore.Q_ARG(str, msg)
            )

        threading.Thread(target=_worker, daemon=True).start()

    # -----------------------------------------------------------------------
    # Image Preparation & Build
    # -----------------------------------------------------------------------

    def _on_pull_or_build_image(self, on_success_callback: Optional[Callable[[], None]] = None):
        image_name = COURSE_IMAGE_NAME
        self.tab_widget.setCurrentIndex(1)
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
        if not hasattr(self, "lbl_image_status"):
            return

        def _check_worker():
            try:
                if self._is_closing:
                    return
                installed, _ = DockerService.check_docker_installed()
                running, _ = DockerService.check_docker_running()
                if self._is_closing:
                    return
                if not installed or not running:
                    QtCore.QMetaObject.invokeMethod(
                        self, "_apply_docker_image_ui_state", QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, "docker_down"),
                        QtCore.Q_ARG(str, "Docker no disponible")
                    )
                    return

                if not DockerService.is_image_available(COURSE_IMAGE_NAME):
                    if self._is_closing:
                        return
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
                if self._is_closing:
                    return
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
            except Exception as e:
                logger.debug("Error en worker de verificación de imagen: %s", e)

        threading.Thread(target=_check_worker, daemon=True).start()

    @QtCore.Slot(str, str)
    def _apply_docker_image_ui_state(self, state_key: str, status_text: str):
        if not hasattr(self, "lbl_image_status"):
            return
        if state_key == "up_to_date":
            self._style_status_label(self.lbl_image_status, status_text, "success")
            self.btn_prep_image.setText("Reconstruir imagen Docker")
        elif state_key == "update_available":
            self._style_status_label(self.lbl_image_status, status_text, "warning")
            self.btn_prep_image.setText("Actualizar imagen Docker (Caché)")
        elif state_key == "not_installed":
            self._style_status_label(self.lbl_image_status, status_text, "error")
            self.btn_prep_image.setText("Construir imagen Docker")
        else:
            self._style_status_label(self.lbl_image_status, status_text, "neutral")
            self.btn_prep_image.setText("Reconstruir / preparar imagen Docker")

    # -----------------------------------------------------------------------
    # Logging Console & Helpers
    # -----------------------------------------------------------------------

    @QtCore.Slot(str)
    def _append_log(self, text: str):
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
            self._style_status_label(self.lbl_autoscroll, "● Auto-scroll: Activo", "success")
        else:
            self._style_status_label(self.lbl_autoscroll, "○ Auto-scroll: Pausado", "error")

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

    # -----------------------------------------------------------------------
    # Window Close Event
    # -----------------------------------------------------------------------

    def closeEvent(self, event: QtGui.QCloseEvent):
        self._is_closing = True
        self._set_docker_state(DockerState.NOT_RUNNING)
        self._save_current_settings()

        if self._docker_poll_timer and self._docker_poll_timer.isActive():
            self._docker_poll_timer.stop()
        if self._container_poll_timer and self._container_poll_timer.isActive():
            self._container_poll_timer.stop()

        if self.active_cmd_thread and self.active_cmd_thread.isRunning():
            self.active_cmd_thread.terminate_process()
            self.active_cmd_thread.wait(500)

        # En modo de pruebas o sin tareas en segundo plano, cerrar inmediatamente
        if not self._enable_background_tasks:
            event.accept()
            return

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
