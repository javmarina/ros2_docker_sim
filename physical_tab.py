"""
Physical robot (TurtleBot 4) management tab widget.
Handles local Wi-Fi verification, ARP network detection, SSH connection params,
SFTP code synchronization, remote compilation (colcon build), and SSH terminal launching.
"""

import logging
import os
import stat
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from config_store import ConfigStore
from embedded_icon import get_themed_icon
from theme import THEME_PALETTES, style_badge
from utils import (
    _SFTP_IGNORE_DIRS,
    DEFAULT_TURTLEBOT4_MAC,
    find_workspace_packages,
    get_connected_ssid,
    get_ip_from_mac,
    get_local_ip,
    get_local_package_names,
    open_robot_ssh_terminal,
    ping_device,
    sftp_upload_dir,
    subnet_sweep,
)

logger = logging.getLogger("launcher")


class PhysicalRobotTab(QtWidgets.QWidget):
    """
    Tab widget dedicated to managing connection, file transfer, compilation,
    and remote terminal access for physical TurtleBot 4 robots.
    """

    sig_log_message = QtCore.Signal(str)
    sig_request_tab_switch = QtCore.Signal(int)
    sig_show_info = QtCore.Signal(str, str)
    sig_show_warning = QtCore.Signal(str, str)
    sig_scan_finished = QtCore.Signal(bool, str, bool, str, str)
    sig_launch_physical_rviz = QtCore.Signal(str, str)

    def __init__(
        self,
        config_store: ConfigStore,
        get_workspace_path_cb: Callable[[], str],
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.config_store = config_store
        self.get_workspace_path = get_workspace_path_cb

        self._is_dark = False
        self._is_scanning = False
        self._robot_detected = False
        self._last_detected_ip = ""
        self._last_scan_data = None
        self._has_checked_once = False
        self._is_loading = False
        self._container_running = False
        self._is_physical_rviz = False

        self._build_ui()
        self.sig_scan_finished.connect(self._on_scan_finished)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # Card 1: Network & Robot Status
        status_card = QtWidgets.QFrame()
        status_card.setProperty("card", True)
        status_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        s_layout = QtWidgets.QVBoxLayout(status_card)
        s_layout.setContentsMargins(16, 14, 16, 14)
        s_layout.setSpacing(12)

        lbl_status_title = QtWidgets.QLabel("Estado de conexión del TurtleBot 4")
        lbl_status_title.setProperty("heading", True)
        s_layout.addWidget(lbl_status_title)

        # Row 1: Wi-Fi
        wifi_row = QtWidgets.QHBoxLayout()
        wifi_row.setSpacing(10)
        lbl_wifi_title = QtWidgets.QLabel("Red Wi-Fi:")
        lbl_wifi_title.setFixedWidth(150)
        lbl_wifi_title.setProperty("heading_small", True)
        wifi_row.addWidget(lbl_wifi_title)

        self.lbl_wifi_badge = QtWidgets.QLabel("Sin comprobar")
        self.lbl_wifi_badge.setFixedHeight(24)
        style_badge(self.lbl_wifi_badge, "Sin comprobar", "neutral", self._is_dark)
        wifi_row.addWidget(self.lbl_wifi_badge)

        self.lbl_wifi_desc = QtWidgets.QLabel(
            "Verificando si el PC está conectado a la red Wi-Fi 'dd-wrt' del laboratorio."
        )
        self.lbl_wifi_desc.setProperty("secondary", True)
        wifi_row.addWidget(self.lbl_wifi_desc, 1)
        s_layout.addLayout(wifi_row)

        # Row 2: Robot Status & MAC
        robot_row = QtWidgets.QHBoxLayout()
        robot_row.setSpacing(10)
        lbl_robot_title = QtWidgets.QLabel("TurtleBot 4 (MAC):")
        lbl_robot_title.setFixedWidth(150)
        lbl_robot_title.setProperty("heading_small", True)
        robot_row.addWidget(lbl_robot_title)

        self.lbl_robot_badge = QtWidgets.QLabel("No escaneado")
        self.lbl_robot_badge.setFixedHeight(24)
        style_badge(self.lbl_robot_badge, "No escaneado", "neutral", self._is_dark)
        robot_row.addWidget(self.lbl_robot_badge)

        target_mac = self.config_store.get("robot_mac", DEFAULT_TURTLEBOT4_MAC)
        self.lbl_robot_desc = QtWidgets.QLabel(f"MAC objetivo: {target_mac}")
        self.lbl_robot_desc.setProperty("secondary", True)
        robot_row.addWidget(self.lbl_robot_desc, 1)
        s_layout.addLayout(robot_row)

        # Row 3: IP Address & Scan Button
        ip_row = QtWidgets.QHBoxLayout()
        ip_row.setSpacing(10)
        lbl_ip_title = QtWidgets.QLabel("Dirección IP del robot:")
        lbl_ip_title.setFixedWidth(150)
        lbl_ip_title.setProperty("heading_small", True)
        ip_row.addWidget(lbl_ip_title)

        self.ent_robot_ip = QtWidgets.QLineEdit()
        self.ent_robot_ip.setPlaceholderText("ej. 192.168.1.142")
        self.ent_robot_ip.setFixedWidth(160)
        self.ent_robot_ip.textChanged.connect(self._on_ip_changed)
        ip_row.addWidget(self.ent_robot_ip)

        self.btn_scan_robot = QtWidgets.QPushButton("Buscar / Escanear robot")
        self.btn_scan_robot.setIconSize(QtCore.QSize(16, 16))
        self.btn_scan_robot.clicked.connect(
            lambda: self.start_robot_scan(deep_sweep=True)
        )
        ip_row.addWidget(self.btn_scan_robot)

        lbl_ip_hint = QtWidgets.QLabel(
            "(Se autocompleta al detectar el robot en la red o puede introducirse manualmente)"
        )
        lbl_ip_hint.setProperty("note", True)
        ip_row.addWidget(lbl_ip_hint, 1)
        s_layout.addLayout(ip_row)

        layout.addWidget(status_card)

        # Card 2: SSH Parameters
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

        lbl_user = QtWidgets.QLabel("Usuario SSH:")
        lbl_user.setProperty("heading_small", True)
        ssh_grid.addWidget(lbl_user, 0, 0)
        self.ent_robot_user = QtWidgets.QLineEdit("ubuntu")
        self.ent_robot_user.textChanged.connect(self._on_field_changed)
        ssh_grid.addWidget(self.ent_robot_user, 0, 1)

        lbl_pwd = QtWidgets.QLabel("Contraseña SSH:")
        lbl_pwd.setProperty("heading_small", True)
        ssh_grid.addWidget(lbl_pwd, 0, 2)
        self.ent_robot_password = QtWidgets.QLineEdit("turtlebot4")
        self.ent_robot_password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.ent_robot_password.textChanged.connect(self._on_field_changed)
        ssh_grid.addWidget(self.ent_robot_password, 0, 3)

        lbl_port = QtWidgets.QLabel("Puerto SSH:")
        lbl_port.setProperty("heading_small", True)
        ssh_grid.addWidget(lbl_port, 1, 0)
        self.ent_robot_port = QtWidgets.QLineEdit("22")
        self.ent_robot_port.setFixedWidth(80)
        self.ent_robot_port.textChanged.connect(self._on_field_changed)
        ssh_grid.addWidget(self.ent_robot_port, 1, 1)

        lbl_ws = QtWidgets.QLabel("Workspace remoto:")
        lbl_ws.setProperty("heading_small", True)
        ssh_grid.addWidget(lbl_ws, 1, 2)
        self.ent_robot_ws = QtWidgets.QLineEdit("~/ros2_ws")
        self.ent_robot_ws.textChanged.connect(self._on_field_changed)
        ssh_grid.addWidget(self.ent_robot_ws, 1, 3)

        lbl_domain = QtWidgets.QLabel("ROS_DOMAIN_ID:")
        lbl_domain.setProperty("heading_small", True)
        ssh_grid.addWidget(lbl_domain, 2, 0)
        self.ent_robot_domain_id = QtWidgets.QLineEdit("0")
        self.ent_robot_domain_id.setFixedWidth(80)
        self.ent_robot_domain_id.textChanged.connect(self._on_field_changed)
        ssh_grid.addWidget(self.ent_robot_domain_id, 2, 1)

        ssh_layout.addLayout(ssh_grid)

        lbl_ssh_note = QtWidgets.QLabel(
            "Valores predeterminados para TurtleBot 4: usuario 'ubuntu', contraseña 'turtlebot4', workspace '~/ros2_ws', DOMAIN_ID '0'."
        )
        lbl_ssh_note.setProperty("note", True)
        ssh_layout.addWidget(lbl_ssh_note)

        layout.addWidget(ssh_card)

        # Card 3: Actions
        ops_card = QtWidgets.QFrame()
        ops_card.setProperty("card", True)
        ops_card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        ops_layout = QtWidgets.QVBoxLayout(ops_card)
        ops_layout.setContentsMargins(16, 14, 16, 14)
        ops_layout.setSpacing(12)

        lbl_ops_head = QtWidgets.QLabel("Operaciones en el robot")
        lbl_ops_head.setProperty("heading", True)
        ops_layout.addWidget(lbl_ops_head)

        btn_grid = QtWidgets.QGridLayout()
        btn_grid.setSpacing(10)

        self.btn_robot_scp = QtWidgets.QPushButton("Sincronizar código con robot")
        self.btn_robot_scp.setIconSize(QtCore.QSize(16, 16))
        self.btn_robot_scp.clicked.connect(self.on_send_code)
        self.btn_robot_sync = self.btn_robot_scp
        btn_grid.addWidget(self.btn_robot_scp, 0, 0)

        self.btn_robot_compile = QtWidgets.QPushButton(
            "Compilar en el robot (colcon build)"
        )
        self.btn_robot_compile.setIconSize(QtCore.QSize(16, 16))
        self.btn_robot_compile.clicked.connect(self.on_compile)
        btn_grid.addWidget(self.btn_robot_compile, 0, 1)

        self.btn_robot_terminal = QtWidgets.QPushButton(
            "Abrir terminal en el robot (SSH)"
        )
        self.btn_robot_terminal.setIconSize(QtCore.QSize(16, 16))
        self.btn_robot_terminal.setObjectName("btnRobotTerminal")
        self.btn_robot_terminal.clicked.connect(self.on_open_terminal)
        btn_grid.addWidget(self.btn_robot_terminal, 1, 0)

        self.btn_robot_rviz = QtWidgets.QPushButton(
            "Abrir RViz2 para robot físico (noVNC)"
        )
        self.btn_robot_rviz.setIconSize(QtCore.QSize(16, 16))
        self.btn_robot_rviz.setObjectName("btnRobotRviz")
        self.btn_robot_rviz.clicked.connect(self.on_launch_rviz)
        btn_grid.addWidget(self.btn_robot_rviz, 1, 1)

        self.btn_robot_remove = QtWidgets.QPushButton("Borrar código del robot")
        self.btn_robot_remove.setIconSize(QtCore.QSize(16, 16))
        self.btn_robot_remove.setObjectName("btnRobotRemove")
        self.btn_robot_remove.clicked.connect(self.on_remove_robot_files)
        btn_grid.addWidget(self.btn_robot_remove, 2, 0, 1, 2)

        ops_layout.addLayout(btn_grid)
        self._update_action_buttons()

        lbl_ops_info = QtWidgets.QLabel(
            "• 'Sincronizar código': Sincronización incremental (estilo rsync) de la carpeta 'src' local con el workspace remoto en el TurtleBot 4.\n"
            "• 'Compilar en el robot': Ejecuta 'colcon build --symlink-install' en el robot; la salida se muestra en directo en la pestaña 'Salida y logs'.\n"
            "• 'Abrir terminal en el robot': Lanza una sesión interactiva SSH en una ventana de consola independiente.\n"
            "• 'Abrir RViz2 para robot físico (noVNC)': Inicia RViz2 en el contenedor Docker conectado por DDS unicast a los topics del robot y abre la visualización en el navegador.\n"
            "• 'Borrar código del robot': Elimina del workspace del robot los paquetes presentes en tu máquina local."
        )
        lbl_ops_info.setProperty("secondary", True)
        ops_layout.addWidget(lbl_ops_info)

        layout.addWidget(ops_card)
        layout.addStretch()

    def on_tab_opened(self):
        """Called when this tab is selected in the UI."""
        if not self._has_checked_once:
            self._has_checked_once = True
            self.start_robot_scan(deep_sweep=False)

    def load_preferences(self):
        """Loads physical robot preferences from config store."""
        self._is_loading = True
        try:
            saved_ip = self.config_store.get("robot_ip", "")
            self.ent_robot_ip.setText(str(saved_ip))
            self.ent_robot_user.setText(
                str(self.config_store.get("robot_user", "ubuntu"))
            )
            self.ent_robot_password.setText(
                str(self.config_store.get("robot_password", "turtlebot4"))
            )
            self.ent_robot_port.setText(str(self.config_store.get("robot_port", "22")))
            self.ent_robot_ws.setText(
                str(self.config_store.get("robot_remote_ws", "~/ros2_ws"))
            )
            saved_domain = self.config_store.get(
                "robot_domain_id", self.config_store.get("ros_domain_id", "0")
            )
            self.ent_robot_domain_id.setText(str(saved_domain))
        finally:
            self._is_loading = False
            self._on_ip_changed()

    def save_preferences(self):
        """Persists physical robot settings to config store."""
        if self._is_loading:
            return
        self.config_store.set("robot_ip", self.ent_robot_ip.text().strip())
        self.config_store.set("robot_user", self.ent_robot_user.text().strip())
        self.config_store.set("robot_password", self.ent_robot_password.text().strip())
        self.config_store.set("robot_port", self.ent_robot_port.text().strip())
        self.config_store.set("robot_remote_ws", self.ent_robot_ws.text().strip())
        self.config_store.set(
            "robot_domain_id", self.ent_robot_domain_id.text().strip() or "0"
        )

    def _on_field_changed(self):
        self.save_preferences()

    def _on_ip_changed(self):
        self.save_preferences()
        current_ip = self.ent_robot_ip.text().strip()
        self._robot_detected = bool(current_ip and current_ip == self._last_detected_ip)
        self._update_action_buttons()

    def update_container_state(
        self, is_running: bool, is_physical_rviz: bool = False
    ):
        """Updates UI elements based on current container status."""
        self._container_running = is_running
        self._is_physical_rviz = is_physical_rviz
        self._update_action_buttons()

    def _update_action_buttons(self):
        ip = self.ent_robot_ip.text().strip()
        enabled = bool(self._robot_detected and ip)

        self.btn_robot_scp.setEnabled(enabled)
        self.btn_robot_compile.setEnabled(enabled)
        self.btn_robot_terminal.setEnabled(enabled)
        self.btn_robot_rviz.setEnabled(enabled)
        self.btn_robot_remove.setEnabled(enabled)

        if not enabled:
            tip = "Robot no detectado en la red Wi-Fi. Conéctate a la red del robot y pulsa 'Buscar / Escanear robot'."
        else:
            tip = ""

        self.btn_robot_scp.setToolTip(
            tip or "Sincronizar incrementalmente el código fuente con el TurtleBot 4 (SFTP/rsync)"
        )
        self.btn_robot_compile.setToolTip(
            tip
            or "Compilar espacio de trabajo remotamente en el TurtleBot 4 (colcon build)"
        )
        self.btn_robot_terminal.setToolTip(
            tip or "Abrir terminal interactiva SSH en el TurtleBot 4"
        )
        self.btn_robot_remove.setToolTip(
            tip
            or "Eliminar del workspace del robot los paquetes presentes en tu máquina local"
        )

        if self._container_running and self._is_physical_rviz:
            self.btn_robot_rviz.setText("RViz2 en ejecución (noVNC)")
            self.btn_robot_rviz.setToolTip(
                "RViz2 conectado al robot físico ya está en ejecución. Pulsa para reabrir la interfaz web."
            )
        else:
            self.btn_robot_rviz.setText("Abrir RViz2 para robot físico (noVNC)")
            self.btn_robot_rviz.setToolTip(
                tip
                or "Abrir RViz2 en el navegador (noVNC) conectado por DDS al TurtleBot 4"
            )

    def start_robot_scan(self, deep_sweep: bool = True):
        """Launches background network detection for the TurtleBot 4."""
        if self._is_scanning:
            return
        self._is_scanning = True
        self._robot_detected = False
        self._update_action_buttons()

        manual_ip = self.ent_robot_ip.text().strip()

        self.btn_scan_robot.setEnabled(False)
        self.btn_scan_robot.setText("Buscando en la red...")
        style_badge(self.lbl_wifi_badge, "Verificando...", "neutral", self._is_dark)
        style_badge(self.lbl_robot_badge, "Escaneando...", "neutral", self._is_dark)
        self.lbl_wifi_desc.setText("")
        self.lbl_robot_desc.setText(
            "Consultando tabla ARP y barriendo la subred local..."
        )

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

                if not robot_ip and manual_ip and ping_device(manual_ip, timeout=0.5):
                    robot_ip = manual_ip

                robot_found = bool(robot_ip)
                msg = f"SSID: {ssid or 'N/A'} | Robot IP: {robot_ip or 'No encontrado'}"
                self.sig_scan_finished.emit(
                    wifi_ok, ssid or "", robot_found, robot_ip or "", msg
                )
            except Exception as e:
                logger.exception("Error durante el escaneo del robot: %s", e)
                self.sig_scan_finished.emit(False, "", False, "", str(e))
            finally:
                self._is_scanning = False

        threading.Thread(target=_worker, daemon=True).start()

    @QtCore.Slot(bool, str, bool, str, str)
    def _on_scan_finished(
        self, wifi_ok: bool, ssid: str, robot_found: bool, robot_ip: str, msg: str
    ):
        self._last_scan_data = (wifi_ok, ssid, robot_found, robot_ip, msg)
        self._update_ui_status(wifi_ok, ssid, robot_found, robot_ip, msg)
        self.btn_scan_robot.setEnabled(True)
        self.btn_scan_robot.setText("Buscar / Escanear robot")

    def _update_ui_status(
        self, wifi_ok: bool, ssid: str, robot_found: bool, robot_ip: str, msg: str
    ):
        # 1. Wi-Fi status
        if not ssid:
            style_badge(self.lbl_wifi_badge, "Desconectado", "error", self._is_dark)
            self.lbl_wifi_desc.setText(
                "No se detecta conexión Wi-Fi activa. Conéctate a 'dd-wrt'."
            )
        elif wifi_ok:
            style_badge(
                self.lbl_wifi_badge, f"Conectado: {ssid}", "success", self._is_dark
            )
            self.lbl_wifi_desc.setText(
                f"Conexión activa a la red Wi-Fi del laboratorio ('{ssid}')."
            )
        else:
            style_badge(self.lbl_wifi_badge, f"Red: {ssid}", "warning", self._is_dark)
            self.lbl_wifi_desc.setText(
                f"Conectado a '{ssid}'. En el laboratorio se requiere la red 'dd-wrt'."
            )

        # 2. Robot MAC & IP
        target_mac = self.config_store.get("robot_mac", DEFAULT_TURTLEBOT4_MAC)
        if robot_found and robot_ip:
            self._robot_detected = True
            self._last_detected_ip = robot_ip
            style_badge(self.lbl_robot_badge, "Localizado", "success", self._is_dark)
            self.lbl_robot_desc.setText(
                f"TurtleBot 4 detectado en la IP {robot_ip} (MAC: {target_mac})."
            )
            current_ip = self.ent_robot_ip.text().strip()
            if not current_ip or current_ip != robot_ip:
                self.ent_robot_ip.setText(robot_ip)
                self.save_preferences()
        else:
            self._robot_detected = False
            self._last_detected_ip = ""
            style_badge(self.lbl_robot_badge, "No detectado", "error", self._is_dark)
            self.lbl_robot_desc.setText(
                f"Robot no encontrado en la subred (MAC: {target_mac}). Pulsa 'Buscar / Escanear robot'."
            )

        self._update_action_buttons()

    def refresh_theme(self, is_dark: bool):
        """Updates styling and icons according to dark/light theme."""
        self._is_dark = is_dark
        p = THEME_PALETTES["dark" if is_dark else "light"]
        col = p["icon_color"]

        self.btn_scan_robot.setIcon(
            get_themed_icon(
                "view-refresh",
                color=col,
                fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_BrowserReload,
            )
        )
        self.btn_robot_scp.setIcon(
            get_themed_icon(
                "document-open",
                color=col,
                fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_ArrowUp,
            )
        )
        self.btn_robot_compile.setIcon(
            get_themed_icon(
                "applications-development",
                color=col,
                fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_CommandLink,
            )
        )
        self.btn_robot_terminal.setIcon(
            get_themed_icon(
                "utilities-terminal",
                color=col,
                fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_DesktopIcon,
            )
        )
        self.btn_robot_rviz.setIcon(
            get_themed_icon(
                "applications-internet",
                color=col,
                fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_DesktopIcon,
            )
        )
        self.btn_robot_remove.setIcon(
            get_themed_icon(
                "user-trash",
                color=col,
                fallback_sp=QtWidgets.QStyle.StandardPixmap.SP_TrashIcon,
            )
        )

        if self._last_scan_data:
            wifi_ok, ssid, robot_found, robot_ip, msg = self._last_scan_data
            self._update_ui_status(wifi_ok, ssid, robot_found, robot_ip, msg)

    def on_send_code(self):
        """Transfers local workspace source code to the remote robot via incremental SFTP (rsync-like)."""
        robot_ip = self.ent_robot_ip.text().strip()
        if not robot_ip:
            self.sig_show_warning.emit(
                "TurtleBot 4",
                "Por favor introduce o escanea la dirección IP del TurtleBot 4 antes de transferir.",
            )
            return

        ws_path = self.get_workspace_path().strip()
        if not ws_path or not os.path.exists(ws_path):
            self.sig_show_warning.emit(
                "TurtleBot 4",
                "La carpeta local del espacio de trabajo (workspace) no existe o no es válida.",
            )
            return

        package_dirs = find_workspace_packages(ws_path)
        if not package_dirs:
            self.sig_show_warning.emit(
                "TurtleBot 4",
                "No se encontraron paquetes válidos de ROS 2 (carpetas que contengan 'package.xml') "
                "en el espacio de trabajo local para transferir.",
            )
            return

        user = self.ent_robot_user.text().strip() or "ubuntu"
        password = self.ent_robot_password.text().strip() or "turtlebot4"
        port = int(self.ent_robot_port.text().strip() or "22")
        remote_ws = self.ent_robot_ws.text().strip() or "~/ros2_ws"

        self.sig_request_tab_switch.emit(1)  # Tab Logs
        pkg_names_summary = ", ".join(name for name, _ in package_dirs)
        self.sig_log_message.emit(
            f"\n=== [Sync] Sincronizando paquetes de ROS 2 con TurtleBot 4 ({user}@{robot_ip}:{remote_ws}) ===\n"
            f"[Sync] Paquetes detectados ({len(package_dirs)}): {pkg_names_summary}\n"
        )

        def _worker():
            try:
                import paramiko
            except ImportError:
                self.sig_log_message.emit(
                    "\n[Error Sync] La librería 'paramiko' no está instalada en el entorno Python.\n"
                )
                self.sig_show_warning.emit(
                    "Dependencia faltante",
                    "Se requiere la librería 'paramiko' para transferir archivos vía SFTP.\nInstálala con: pip install paramiko",
                )
                return

            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.sig_log_message.emit(
                    f"[Sync] Estableciendo conexión SFTP con {user}@{robot_ip}:{port}...\n"
                )
                client.connect(
                    robot_ip, port=port, username=user, password=password, timeout=10.0
                )

                target_base = remote_ws
                if target_base.startswith("~"):
                    _, stdout_h, _ = client.exec_command("echo $HOME")
                    r_home = stdout_h.read().decode("utf-8").strip() or f"/home/{user}"
                    target_base = r_home + target_base[1:]

                remote_src_base = f"{target_base.rstrip('/')}/src"
                sftp = client.open_sftp()
                t0 = time.time()
                total_uploaded = 0
                total_skipped = 0

                for pkg_name, pkg_path in package_dirs:
                    dest_pkg_dir = f"{remote_src_base}/{pkg_name}"
                    self.sig_log_message.emit(
                        f"[Sync] Paquete '{pkg_name}' ({pkg_path} -> {dest_pkg_dir})\n"
                    )
                    stats = sftp_upload_dir(
                        sftp,
                        pkg_path,
                        dest_pkg_dir,
                        log_cb=lambda msg: self.sig_log_message.emit(msg),
                    )
                    total_uploaded += getattr(stats, "uploaded", int(stats))
                    total_skipped += getattr(stats, "skipped", 0)

                elapsed = time.time() - t0
                sftp.close()
                client.close()

                self.sig_log_message.emit(
                    f"\n[Sync] Sincronización completada con éxito en {elapsed:.1f}s: "
                    f"{total_uploaded} archivos transferidos, {total_skipped} sin cambios "
                    f"en {len(package_dirs)} paquete(s).\n"
                )
                self.sig_show_info.emit(
                    "Sincronización de código",
                    f"Sincronización completada con éxito en {elapsed:.1f} segundos.\n\n"
                    f"Paquetes transferidos ({len(package_dirs)}):\n"
                    + "\n".join(f"  • {name}" for name, _ in package_dirs)
                    + f"\n\n• {total_uploaded} archivos subidos o actualizados\n"
                    + f"• {total_skipped} archivos ya sincronizados (omitidos)",
                )
            except Exception as e:
                logger.exception("Error al sincronizar archivos vía SFTP: %s", e)
                self.sig_log_message.emit(
                    f"\n[Error Sync] Fallo en la sincronización: {e}\n"
                )
                self.sig_show_warning.emit(
                    "Error de Sincronización",
                    f"Error al sincronizar código con el TurtleBot 4:\n\n{e}",
                )

        threading.Thread(target=_worker, daemon=True).start()

    def on_compile(self):
        """Triggers remote workspace compilation on the robot via SSH."""
        robot_ip = self.ent_robot_ip.text().strip()
        if not robot_ip:
            self.sig_show_warning.emit(
                "TurtleBot 4",
                "Por favor introduce o escanea la dirección IP del TurtleBot 4 antes de compilar.",
            )
            return

        user = self.ent_robot_user.text().strip() or "ubuntu"
        password = self.ent_robot_password.text().strip() or "turtlebot4"
        port = int(self.ent_robot_port.text().strip() or "22")
        remote_ws = self.ent_robot_ws.text().strip() or "~/ros2_ws"

        self.sig_request_tab_switch.emit(1)  # Tab Logs
        self.sig_log_message.emit(
            f"\n=== [SSH] Iniciando compilación remota (colcon build) en TurtleBot 4 ({user}@{robot_ip}) ===\n"
        )

        def _worker():
            try:
                import paramiko
            except ImportError:
                self.sig_log_message.emit(
                    "\n[Error SSH] La librería 'paramiko' no está instalada en el entorno Python.\n"
                )
                self.sig_show_warning.emit(
                    "Dependencia faltante",
                    "Se requiere la librería 'paramiko' para compilar remotamente vía SSH.\nInstálala con: pip install paramiko",
                )
                return

            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.sig_log_message.emit(
                    f"[SSH] Conectando a {user}@{robot_ip}:{port}...\n"
                )
                client.connect(
                    robot_ip, port=port, username=user, password=password, timeout=10.0
                )

                build_cmd = (
                    f"bash -lc '"
                    f"if [ -f /opt/ros/humble/setup.bash ]; then source /opt/ros/humble/setup.bash; "
                    f"elif [ -f /opt/ros/jazzy/setup.bash ]; then source /opt/ros/jazzy/setup.bash; fi; "
                    f"cd {remote_ws} && colcon build --symlink-install"
                    f"'"
                )
                self.sig_log_message.emit(f"[SSH Ejecutando] {build_cmd}\n\n")

                _, stdout, _ = client.exec_command(build_cmd, get_pty=True)
                for line in iter(stdout.readline, ""):
                    self.sig_log_message.emit(line)

                rc = stdout.channel.recv_exit_status()
                client.close()

                if rc == 0:
                    self.sig_log_message.emit(
                        "\n[Robot Compilación] Compilación completada con ÉXITO.\n"
                    )
                    self.sig_show_info.emit(
                        "Compilación en Robot",
                        "El espacio de trabajo en el TurtleBot 4 se ha compilado correctamente.",
                    )
                else:
                    self.sig_log_message.emit(
                        f"\n[Robot Compilación Error] La compilación terminó con código de error {rc}.\n"
                    )
                    self.sig_show_warning.emit(
                        "Error de Compilación",
                        f"La compilación en el robot terminó con errores (código {rc}). Revisa los logs.",
                    )
            except Exception as e:
                logger.exception("Error al compilar remotamente en el robot: %s", e)
                self.sig_log_message.emit(
                    f"\n[SSH Error] Excepción al conectar/compilar en el robot: {e}\n"
                )
                self.sig_show_warning.emit(
                    "Error SSH",
                    f"Error al ejecutar la compilación en el TurtleBot 4:\n\n{e}",
                )

        threading.Thread(target=_worker, daemon=True).start()

    def on_open_terminal(self):
        """Launches a native SSH interactive terminal connected to the robot."""
        robot_ip = self.ent_robot_ip.text().strip()
        if not robot_ip:
            self.sig_show_warning.emit(
                "TurtleBot 4",
                "Por favor introduce o escanea la dirección IP del TurtleBot 4 antes de abrir la terminal.",
            )
            return

        user = self.ent_robot_user.text().strip() or "ubuntu"
        password = self.ent_robot_password.text().strip()
        port = self.ent_robot_port.text().strip() or "22"
        remote_ws = self.ent_robot_ws.text().strip() or "~/ros2_ws"

        success, msg = open_robot_ssh_terminal(
            ip=robot_ip, user=user, password=password, port=port, remote_ws=remote_ws
        )
        if success:
            self.sig_log_message.emit(f"\n[Terminal SSH] {msg}\n")
        else:
            self.sig_show_warning.emit("Terminal SSH", msg)

    def on_launch_rviz(self):
        """Launches RViz2 in Docker connected to the physical robot via DDS peer unicast."""
        robot_ip = self.ent_robot_ip.text().strip()
        if not robot_ip:
            self.sig_show_warning.emit(
                "TurtleBot 4",
                "Por favor introduce o escanea la dirección IP del TurtleBot 4 antes de abrir RViz2.",
            )
            return

        domain_id = self.ent_robot_domain_id.text().strip() or "0"
        self.sig_launch_physical_rviz.emit(robot_ip, domain_id)

    def on_remove_robot_files(self, confirm: bool = True):
        """
        Removes packages from the robot's workspace that are present on the user's host machine.
        Prevents other student groups sharing the physical robot from copying the code.
        """
        robot_ip = self.ent_robot_ip.text().strip()
        if not robot_ip:
            self.sig_show_warning.emit(
                "TurtleBot 4",
                "Por favor introduce o escanea la dirección IP del TurtleBot 4 antes de continuar.",
            )
            return

        ws_path = self.get_workspace_path().strip()
        if not ws_path or not os.path.exists(ws_path):
            self.sig_show_warning.emit(
                "TurtleBot 4",
                "La carpeta local del espacio de trabajo (workspace) no existe o no es válida.",
            )
            return

        local_pkgs = get_local_package_names(ws_path)
        if not local_pkgs:
            self.sig_show_warning.emit(
                "Borrar código del robot",
                "No se detectaron paquetes ROS 2 en tu espacio de trabajo local para contrastar con el robot.",
            )
            return

        user = self.ent_robot_user.text().strip() or "ubuntu"
        password = self.ent_robot_password.text().strip() or "turtlebot4"
        port = int(self.ent_robot_port.text().strip() or "22")
        remote_ws = self.ent_robot_ws.text().strip() or "~/ros2_ws"

        if confirm:
            pkg_list_str = "\n".join(f"  • {p}" for p in sorted(local_pkgs))
            reply = QtWidgets.QMessageBox.question(
                self,
                "Borrar código del robot",
                f"¿Deseas eliminar del TurtleBot 4 los paquetes que coincidan con tu máquina local?\n\n"
                f"Paquetes locales detectados ({len(local_pkgs)}):\n{pkg_list_str}\n\n"
                f"Esta acción borrará estos paquetes de '{remote_ws}/src' (así como sus artefactos en build e install).",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        self.sig_request_tab_switch.emit(1)  # Tab Logs
        self.sig_log_message.emit(
            f"\n=== [Cleanup] Buscando y eliminando paquetes locales en TurtleBot 4 ({user}@{robot_ip}:{remote_ws}) ===\n"
        )
        self.sig_log_message.emit(
            f"[Cleanup] Paquetes locales a contrastar: {', '.join(sorted(local_pkgs))}\n"
        )

        def _worker():
            try:
                import paramiko
            except ImportError:
                self.sig_log_message.emit(
                    "\n[Error Cleanup] La librería 'paramiko' no está instalada en el entorno Python.\n"
                )
                self.sig_show_warning.emit(
                    "Dependencia faltante",
                    "Se requiere la librería 'paramiko' para conectar con el robot.\nInstálala con: pip install paramiko",
                )
                return

            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.sig_log_message.emit(
                    f"[Cleanup] Conectando a {user}@{robot_ip}:{port}...\n"
                )
                client.connect(
                    robot_ip, port=port, username=user, password=password, timeout=10.0
                )

                target_base = remote_ws
                if target_base.startswith("~"):
                    _, stdout_h, _ = client.exec_command("echo $HOME")
                    r_home = stdout_h.read().decode("utf-8").strip() or f"/home/{user}"
                    target_base = r_home + target_base[1:]

                remote_src = f"{target_base.rstrip('/')}/src"

                sftp = client.open_sftp()
                remote_packages = set()
                try:
                    for attr in sftp.listdir_attr(remote_src):
                        if (
                            stat.S_ISDIR(attr.st_mode)
                            and not attr.filename.startswith(".")
                            and attr.filename not in _SFTP_IGNORE_DIRS
                        ):
                            remote_packages.add(attr.filename)
                except OSError:
                    pass
                finally:
                    sftp.close()

                # Find which packages on the robot match the user's host machine
                matching_pkgs = sorted(remote_packages & local_pkgs)

                if not matching_pkgs:
                    self.sig_log_message.emit(
                        f"\n[Cleanup] No se encontraron paquetes en {remote_src} que coincidan con tu máquina local.\n"
                        f"  (Paquetes remotos encontrados: {', '.join(sorted(remote_packages)) if remote_packages else 'ninguno'})\n"
                    )
                    client.close()
                    self.sig_show_info.emit(
                        "Borrar código del robot",
                        "No se encontró ningún paquete de tu espacio de trabajo local en el robot.",
                    )
                    return

                self.sig_log_message.emit(
                    f"[Cleanup] Se encontraron {len(matching_pkgs)} paquete(s) coincidentes para eliminar: {', '.join(matching_pkgs)}\n"
                )

                deleted_pkgs = []
                for pkg in matching_pkgs:
                    # Remove from src, build, and install
                    del_cmd = (
                        f"rm -rf "
                        f"'{remote_src}/{pkg}' "
                        f"'{target_base.rstrip('/')}/build/{pkg}' "
                        f"'{target_base.rstrip('/')}/install/{pkg}'"
                    )
                    _, stdout_d, _ = client.exec_command(del_cmd)
                    stdout_d.channel.recv_exit_status()
                    deleted_pkgs.append(pkg)
                    self.sig_log_message.emit(
                        f"  -> [Eliminado del robot] {pkg} (src, build, install)\n"
                    )

                client.close()

                summary = (
                    f"\n[Cleanup] Operación completada con éxito. Se han eliminado {len(deleted_pkgs)} paquete(s) del TurtleBot 4:\n"
                    + "\n".join(f"  • {p}" for p in deleted_pkgs)
                    + "\n"
                )
                self.sig_log_message.emit(summary)
                self.sig_show_info.emit(
                    "Borrar código del robot",
                    f"Se han eliminado con éxito {len(deleted_pkgs)} paquete(s) del TurtleBot 4:\n\n"
                    + "\n".join(f"• {p}" for p in deleted_pkgs)
                    + "\n\nTu código ya no está accesible para otros grupos de prácticas.",
                )

            except Exception as e:
                logger.exception("Error al eliminar archivos del robot: %s", e)
                self.sig_log_message.emit(
                    f"\n[Error Cleanup] Fallo al eliminar archivos del robot: {e}\n"
                )
                self.sig_show_warning.emit(
                    "Error de Limpieza",
                    f"Error al eliminar archivos del TurtleBot 4:\n\n{e}",
                )

        threading.Thread(target=_worker, daemon=True).start()
