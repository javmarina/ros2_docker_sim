"""
Unit and integration tests for the refactored ROS 2 Simulation Launcher modules.
Can be executed with pytest: `pytest test_launcher.py`
or directly: `python test_launcher.py`
"""

import json
import sys
import tempfile
from pathlib import Path

from PySide6 import QtGui, QtWidgets

# Ensure an application instance exists for Qt widgets
app = QtWidgets.QApplication.instance()
if app is None:
    app = QtWidgets.QApplication(["--platform", "offscreen"])

import exception_dialog
import theme
import utils
from config_store import ConfigStore
from docker_service import ContainerState
from main_window import ModernSimulationLauncher
from physical_tab import PhysicalRobotTab
from robot_registry import (
    RobotId,
    ScenarioId,
    SimulationWorld,
    get_all_robots,
    get_robot_by_id,
)


def test_theme_palettes_and_stylesheet():
    """Validates theme palettes, stylesheet generation, and badge styling."""
    assert "light" in theme.THEME_PALETTES
    assert "dark" in theme.THEME_PALETTES

    light_qss = theme.build_global_stylesheet(is_dark=False)
    dark_qss = theme.build_global_stylesheet(is_dark=True)
    assert "QMainWindow" in light_qss
    assert "QMainWindow" in dark_qss
    assert light_qss != dark_qss

    label = QtWidgets.QLabel()
    theme.style_badge(label, "OK", "success", is_dark=False)
    assert label.text() == "OK"
    assert "color:" in label.styleSheet()

    theme.style_status_label(label, "Active", "warning", is_dark=True)
    assert label.text() == "Active"
    assert "color:" in label.styleSheet()


def test_ansi_color_parser():
    """Validates ANSI color parser rendering to QTextDocument cursor."""
    parser = utils.AnsiColorParser()
    doc = QtGui.QTextDocument()
    cursor = QtGui.QTextCursor(doc)

    ansi_text = "\x1b[32mSuccess message\x1b[0m and \x1b[31mError message\x1b[0m"
    parser.parse_to_cursor(ansi_text, cursor)
    plain = doc.toPlainText()
    assert "Success message" in plain
    assert "Error message" in plain


def test_dockerfile_sync():
    """Validates Dockerfile synchronization helper in a temporary workspace."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        build_dir = utils.ensure_dockerfile_sync(ws)
        assert build_dir.is_dir()
        target_file = build_dir / "Dockerfile"
        assert target_file.is_file()
        content = target_file.read_text(encoding="utf-8")
        assert "ros:jazzy-desktop-full" in content


def test_exception_report_builder():
    """Validates error report formatting without opening GUI dialog."""
    try:
        raise ValueError("Test calculation fault: divide by zero")
    except ValueError:
        exc_type, exc_val, exc_tb = sys.exc_info()
        report = exception_dialog.build_error_report(
            exc_type, exc_val, exc_tb, docker_info="Instalado: Sí | En ejecución: No"
        )

    assert "INFORME DE ERROR - ROS 2 SIMULATION LAUNCHER" in report
    assert "ValueError" in report
    assert "Test calculation fault: divide by zero" in report
    assert exception_dialog.SUPPORT_EMAIL in report
    assert "Instalado: Sí | En ejecución: No" in report


def test_physical_tab_widget():
    """Validates PhysicalRobotTab construction, fields, and preference storage."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = ConfigStore(fallback_dir=Path(tmp_dir))
        config.set("robot_ip", "192.168.1.55")

        tab = PhysicalRobotTab(config, lambda: "/fake/ws")
        tab.load_preferences()

        assert tab.ent_robot_ip.text() == "192.168.1.55"
        assert tab.ent_robot_user.text() == "ubuntu"
        assert not tab.btn_robot_scp.isEnabled()

        # Update IP and verify save
        tab.ent_robot_ip.setText("192.168.1.99")
        tab.save_preferences()
        assert config.get("robot_ip") == "192.168.1.99"


def test_main_window_integration():
    """Validates full ModernSimulationLauncher instantiation, tab pages, and aliases."""
    win = ModernSimulationLauncher(enable_background_tasks=False)
    try:
        assert win.tab_widget.count() == 6
        assert win.cbo_robot.count() == len(get_all_robots())
        assert win.btn_launch is not None
        assert win.btn_stop is not None
        assert win.btn_terminal is not None
        assert win.btn_web is not None

        # Verify backwards-compatibility attribute aliases
        assert win.ent_robot_ip is win.physical_tab.ent_robot_ip
        assert win.btn_robot_terminal is win.physical_tab.btn_robot_terminal
        assert win.lbl_wifi_badge is win.physical_tab.lbl_wifi_badge

        # Verify scenario selection and world populating
        base_bot = get_robot_by_id("base")
        if base_bot:
            win._update_worlds_and_scenarios(base_bot)
            assert win.cbo_world.count() == len(base_bot.supported_worlds)
            assert win.cbo_scenario.count() == len(base_bot.scenarios)
    finally:
        win.close()
        QtWidgets.QApplication.processEvents()


def test_robot_registry():
    """Validates robot profiles, scenarios, enums, and command building."""
    # Enum validation
    assert SimulationWorld.is_valid("empty")
    assert SimulationWorld.is_valid("wall")
    assert SimulationWorld.is_valid("classroom")
    assert not SimulationWorld.is_valid("warehouse")
    assert SimulationWorld.from_str("non_existent") == SimulationWorld.EMPTY

    assert ScenarioId.is_valid("nav2")
    assert ScenarioId.is_valid("slam")
    assert not ScenarioId.is_valid("teleport")

    assert RobotId.is_valid("base")
    assert RobotId.is_valid("generic")
    assert RobotId.is_valid("turtlebot4")
    assert not RobotId.is_valid("drone")

    robots = get_all_robots()
    assert len(robots) >= 2
    tb4 = get_robot_by_id(RobotId.TURTLEBOT4)
    assert tb4 is not None
    assert tb4.supported_worlds == ["empty", "wall", "classroom"]
    sc = tb4.get_scenario_by_id(ScenarioId.SLAM)
    assert sc is not None
    cmd = tb4.build_command(ScenarioId.SLAM, SimulationWorld.EMPTY)
    assert "turtlebot4" in cmd or "slam" in cmd
    assert "turtlebot4_nodock.launch.py" in cmd
    assert "world:=empty" in cmd

    # Verificar mundo empty
    cmd_empty = tb4.build_command(ScenarioId.SIM_ONLY, SimulationWorld.EMPTY)
    assert "turtlebot4_nodock.launch.py" in cmd_empty
    assert "world:=empty" in cmd_empty

    # Verificar mundo wall
    cmd_wall = tb4.build_command(ScenarioId.SIM_ONLY, SimulationWorld.WALL)
    assert "turtlebot4_nodock.launch.py" in cmd_wall
    assert "world:=wall" in cmd_wall

    # Verificar mundo classroom con Nav2 (mundo con mapa -> localization:=true)
    cmd_classroom = tb4.build_command(ScenarioId.NAV2, SimulationWorld.CLASSROOM)
    assert "turtlebot4_nodock.launch.py" in cmd_classroom
    assert "world:=classroom" in cmd_classroom
    assert "nav2:=true" in cmd_classroom
    assert "localization:=true" in cmd_classroom
    assert "x:=1.5 y:=1.5" in cmd_classroom

    # Verificar mundo sin mapa con Nav2 (empty -> slam:=true dinámico)
    cmd_empty_nav2 = tb4.build_command(ScenarioId.NAV2, SimulationWorld.EMPTY)
    assert "turtlebot4_nodock.launch.py" in cmd_empty_nav2
    assert "world:=empty" in cmd_empty_nav2
    assert "slam:=true" in cmd_empty_nav2


def test_config_store_workspace_validation():
    """Validates ConfigStore workspace path check logic."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Non-existent path
        valid, msg = ConfigStore.validate_workspace(
            str(Path(tmp_dir) / "does_not_exist")
        )
        assert not valid

        # Empty directory
        valid, msg = ConfigStore.validate_workspace(tmp_dir)
        assert valid

        # Directory with src and a package
        pkg_dir = Path(tmp_dir) / "src" / "test_pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.xml").write_text("<package></package>", encoding="utf-8")
        valid, msg = ConfigStore.validate_workspace(tmp_dir)
        assert valid
        assert "detectado" in msg


def test_dialog_stylesheets_and_variants():
    """Validates centralized dialog stylesheet generation, status color tokens, and button variants."""
    # Test semantic status colors
    fg_light, bg_light, border_light = theme.get_status_colors("success", is_dark=False)
    assert fg_light == "#15803d"
    assert bg_light == "#dcfce7"

    fg_dark, bg_dark, border_dark = theme.get_status_colors("error", is_dark=True)
    assert fg_dark == "#f87171"
    assert "239, 68, 68" in bg_dark

    # Test dialog stylesheets
    exc_qss = theme.build_dialog_stylesheet(is_dark=True, dialog_type="exception")
    assert "#errReportText" in exc_qss
    assert "#errHeaderFrame" in exc_qss

    updater_qss = theme.build_dialog_stylesheet(is_dark=False, dialog_type="updater")
    assert "#btnUpdate" in updater_qss
    assert "#progressBar" in updater_qss

    default_qss = theme.build_dialog_stylesheet(is_dark=False, dialog_type="default")
    assert "QDialog" in default_qss
    assert "QMessageBox" in default_qss
    assert "QMessageBox" in exc_qss
    assert "QMessageBox" in theme.build_global_stylesheet(is_dark=True)

    # Test arrow_url sanitization for Windows backslashes in QSS
    win_qss = theme.build_global_stylesheet(False, r"C:\Users\test\chevron_down.svg")
    assert r"C:\Users" not in win_qss
    assert "C:/Users/test/chevron_down.svg" in win_qss

    # Test button variant styling and rendered colors in main window
    win = ModernSimulationLauncher(enable_background_tasks=False)
    try:
        # Verify action buttons retain their distinctive brand colors
        pm = QtGui.QPixmap(win.btn_launch.size())
        win.btn_launch.render(pm)
        assert QtGui.QColor(pm.toImage().pixel(10, 10)).name() == "#2563eb"

        pm_term = QtGui.QPixmap(win.btn_terminal.size())
        win.btn_terminal.render(pm_term)
        assert QtGui.QColor(pm_term.toImage().pixel(10, 10)).name() in (
            "#0f172a",
            "#1e293b",
        )

        win._set_button_variant(win.btn_header_update, "success")
        assert win.btn_header_update.property("variant") == "success"

        win._set_button_variant(win.btn_docker, "danger")
        assert win.btn_docker.property("variant") == "danger"

        win._set_button_variant(win.btn_docker, None)
        assert win.btn_docker.property("variant") is None

        # Verify theme toggle button exists and updates theme
        assert hasattr(win, "btn_theme_toggle")
        initial_dark = win._is_dark
        expected_initial_text = "Modo claro" if initial_dark else "Modo oscuro"
        assert win.btn_theme_toggle.text() == expected_initial_text

        win._toggle_theme()
        assert win._is_dark == (not initial_dark)
        expected_toggled_text = "Modo claro" if win._is_dark else "Modo oscuro"
        assert win.btn_theme_toggle.text() == expected_toggled_text

        # Restore original theme
        win._toggle_theme()
        assert win._is_dark == initial_dark
    finally:
        win.close()
        QtWidgets.QApplication.processEvents()


def test_container_state_and_button_robustness():
    """Validates ContainerState enum, three-state lifecycle, and button disabling while starting/stopping."""
    assert ContainerState.NOT_RUNNING.is_not_running
    assert not ContainerState.NOT_RUNNING.is_busy
    assert ContainerState.STARTING.is_starting
    assert ContainerState.STARTING.is_busy
    assert ContainerState.RUNNING.is_running
    assert not ContainerState.RUNNING.is_busy
    assert ContainerState.STOPPING.is_stopping
    assert ContainerState.STOPPING.is_busy

    win = ModernSimulationLauncher(enable_background_tasks=False)
    try:
        # Initial state: NOT_RUNNING -> launch enabled, stop disabled
        win.sig_container_status.emit(ContainerState.NOT_RUNNING)
        QtWidgets.QApplication.processEvents()
        assert win.container_state == ContainerState.NOT_RUNNING
        assert win.btn_launch.isEnabled()
        assert not win.btn_stop.isEnabled()
        assert not win._is_container_running
        assert not win._is_launching_sim

        # Transition to STARTING -> BOTH buttons must be disabled
        win.sig_container_status.emit(ContainerState.STARTING)
        QtWidgets.QApplication.processEvents()
        assert win.container_state == ContainerState.STARTING
        assert not win.btn_launch.isEnabled()
        assert not win.btn_stop.isEnabled()
        assert win._is_launching_sim
        assert not win._is_container_running

        # Transition to RUNNING -> launch disabled, stop enabled
        win.sig_container_status.emit(ContainerState.RUNNING)
        QtWidgets.QApplication.processEvents()
        assert win.container_state == ContainerState.RUNNING
        assert not win.btn_launch.isEnabled()
        assert win.btn_stop.isEnabled()
        assert win._is_container_running
        assert not win._is_launching_sim

        # Transition to STOPPING -> BOTH buttons must be disabled
        win.sig_container_status.emit(ContainerState.STOPPING)
        QtWidgets.QApplication.processEvents()
        assert win.container_state == ContainerState.STOPPING
        assert not win.btn_launch.isEnabled()
        assert not win.btn_stop.isEnabled()
        assert win._is_stopping_sim
        assert not win._is_container_running

        # Transition back to NOT_RUNNING
        win.sig_container_status.emit(ContainerState.NOT_RUNNING)
        QtWidgets.QApplication.processEvents()
        assert win.container_state == ContainerState.NOT_RUNNING
        assert win.btn_launch.isEnabled()
        assert not win.btn_stop.isEnabled()
    finally:
        win.close()
        QtWidgets.QApplication.processEvents()


def test_config_store_world_fallback():
    """Validates that any obsolete world, robot, or scenario previously saved in settings defaults safely."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_file = Path(tmp_dir) / "config.json"
        config_file.write_text(
            json.dumps({"world_name": "warehouse"}), encoding="utf-8"
        )
        store = ConfigStore(fallback_dir=Path(tmp_dir))
        store._config_path = config_file
        store.load()
        assert store.get("world_name") == SimulationWorld.EMPTY.value

        config_file.write_text(json.dumps({"world_name": "depot"}), encoding="utf-8")
        store.load()
        assert store.get("world_name") == SimulationWorld.EMPTY.value

        config_file.write_text(json.dumps({"world_name": "maze"}), encoding="utf-8")
        store.load()
        assert store.get("world_name") == SimulationWorld.EMPTY.value

        # Valid worlds preserved
        config_file.write_text(json.dumps({"world_name": "wall"}), encoding="utf-8")
        store.load()
        assert store.get("world_name") == SimulationWorld.WALL.value

        config_file.write_text(
            json.dumps({"world_name": "classroom"}), encoding="utf-8"
        )
        store.load()
        assert store.get("world_name") == SimulationWorld.CLASSROOM.value

        # Fallback for invalid robot_id and scenario_id
        config_file.write_text(
            json.dumps({"robot_id": "invalid_bot", "scenario_id": "invalid_sc"}),
            encoding="utf-8",
        )
        store.load()
        assert store.get("robot_id") == RobotId.BASE.value
        assert store.get("scenario_id") == ScenarioId.CONTAINER_ONLY.value


def test_docker_startup_progress_timer():
    """Validates Docker startup elapsed timer, UI badge formatting, and timer cleanup on state change."""
    import time

    from docker_service import DockerState

    win = ModernSimulationLauncher(enable_background_tasks=False)
    try:
        # 1. Direct progress slot test
        win._on_docker_poll_progress(12, 90)
        assert "12s" in win.lbl_docker_badge.text()
        assert "12s / 90s" in win.lbl_progress.text()

        # 2. Timer tick logic test
        win._docker_state = DockerState.STARTING
        win._docker_start_time = time.monotonic() - 5.0
        win._docker_start_max_seconds = 90
        win._start_docker_progress_timer()
        assert win._docker_poll_timer is not None
        assert win._docker_poll_timer.isActive()

        # Emulate timer tick
        win._on_docker_progress_tick()
        QtWidgets.QApplication.processEvents()
        assert (
            "5s" in win.lbl_docker_badge.text() or "6s" in win.lbl_docker_badge.text()
        )

        # 3. State transition to RUNNING should stop the progress timer
        win._set_docker_state(DockerState.RUNNING)
        assert not win._docker_poll_timer.isActive()

        # 4. Starting state transition to NOT_RUNNING should also stop timer
        win._docker_state = DockerState.STARTING
        win._start_docker_progress_timer()
        assert win._docker_poll_timer.isActive()
        win._set_docker_state(DockerState.NOT_RUNNING)
        assert not win._docker_poll_timer.isActive()
    finally:
        win.close()
        QtWidgets.QApplication.processEvents()


def test_docker_service_detection():
    """Validates DockerService fast detection, version extraction, and state enum mapping."""
    import time

    from docker_service import DockerService, DockerState

    installed, ver_info = DockerService.check_docker_installed()
    assert isinstance(installed, bool)
    assert isinstance(ver_info, str)

    t0 = time.monotonic()
    running, daemon_msg = DockerService.check_docker_running(timeout=5.0)
    elapsed = time.monotonic() - t0

    assert isinstance(running, bool)
    assert isinstance(daemon_msg, str)
    # The optimized query must complete well within 3 seconds
    assert elapsed < 3.0

    state = DockerService.get_docker_state()
    if running:
        assert state == DockerState.RUNNING
        assert "Docker activo" in daemon_msg
    else:
        assert state in (DockerState.NOT_RUNNING, DockerState.STARTING)

    status_state, status_msg = DockerService.get_docker_status(timeout=5.0)
    assert isinstance(status_state, DockerState)
    assert isinstance(status_msg, str)
    assert status_state == state

    # Validar que los métodos de proceso y canal IPC funcionen y retornen booleanos
    assert isinstance(DockerService.is_docker_desktop_process_running(), bool)
    assert isinstance(DockerService.is_docker_pipe_ready(), bool)

    # Validar que _apply_docker_status acepte directamente el enum DockerState sin hackeos de strings
    win = ModernSimulationLauncher(enable_background_tasks=False)
    try:
        win._apply_docker_status(True, DockerState.STARTING, "Arrancando...")
        assert win.docker_state == DockerState.STARTING
        assert "Arrancando" in win.lbl_docker_badge.text()

        win._apply_docker_status(True, DockerState.RUNNING, "Docker activo (v29.0)")
        assert win.docker_state == DockerState.RUNNING
        assert "activo" in win.lbl_docker_badge.text()

        win._apply_docker_status(True, DockerState.NOT_RUNNING, "Detenido")
        assert win.docker_state == DockerState.NOT_RUNNING
        assert "detenido" in win.lbl_docker_badge.text()
    finally:
        win.close()
        QtWidgets.QApplication.processEvents()


def test_docker_command_length_windows_limits():
    """Verifica que ningún comando de Docker generado supere el límite de Windows CreateProcess (32,767 caracteres)."""
    from docker_service import DockerService

    max_len = 0
    worst_case = ""
    for robot in get_all_robots():
        for world in robot.supported_worlds:
            for sc in robot.scenarios:
                cmd = robot.build_command(sc.id, world)
                docker_cmd = DockerService.build_docker_run_args(
                    "ros2-jazzy-nav-course:latest",
                    "test_container",
                    cmd,
                    "42",
                    robot.id,
                    "C:/fake/ws",
                )
                cmd_str = " ".join(docker_cmd)
                length = len(cmd_str)
                if length > max_len:
                    max_len = length
                    worst_case = f"{robot.id} / {world} / {sc.id}"
                # Must be strictly below Windows CreateProcessW 32,767 character ceiling
                assert length < 32767, (
                    f"Comando demasiado largo ({length} caracteres) para {worst_case}"
                )

    # Incluso en el peor caso (classroom con mapas y launch sin dock), debe ser < 20,000 chars
    assert max_len < 20000, (
        f"El peor caso ({worst_case}) es {max_len} caracteres, esperado < 20000"
    )


def test_dialog_and_message_box_dark_mode():
    """Validates that modal dialogs and QMessageBox correctly respect dark mode with dark background and legible text."""
    dark_pal = theme.create_theme_palette(is_dark=True)
    assert dark_pal.color(QtGui.QPalette.ColorRole.Window).name() == "#0f172a"
    assert dark_pal.color(QtGui.QPalette.ColorRole.WindowText).name() == "#f8fafc"

    light_pal = theme.create_theme_palette(is_dark=False)
    assert light_pal.color(QtGui.QPalette.ColorRole.Window).name() == "#f8fafc"
    assert light_pal.color(QtGui.QPalette.ColorRole.WindowText).name() == "#0f172a"

    # Test dark mode application
    theme.apply_theme_to_application(is_dark=True)
    assert theme.get_active_theme_mode() is True

    msg_dark = QtWidgets.QMessageBox()
    msg_dark.setWindowTitle("Simulación")
    msg_dark.setText("Contenedor detenido correctamente.")
    msg_dark.setIcon(QtWidgets.QMessageBox.Icon.Information)
    msg_dark.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
    msg_dark.show()
    try:
        pm_dark = QtGui.QPixmap(msg_dark.size())
        msg_dark.render(pm_dark)
        assert pm_dark.toImage().pixelColor(10, 10).name() == "#0f172a"

        label_dark = msg_dark.findChild(QtWidgets.QLabel, "qt_msgbox_label")
        assert label_dark is not None
        assert (
            label_dark.palette().color(label_dark.foregroundRole()).name() == "#f8fafc"
        )
    finally:
        msg_dark.close()

    # Test light mode application
    theme.apply_theme_to_application(is_dark=False)
    assert theme.get_active_theme_mode() is False

    msg_light = QtWidgets.QMessageBox()
    msg_light.setText("Texto en modo claro")
    msg_light.show()
    try:
        pm_light = QtGui.QPixmap(msg_light.size())
        msg_light.render(pm_light)
        assert pm_light.toImage().pixelColor(10, 10).name() == "#f8fafc"

        label_light = msg_light.findChild(QtWidgets.QLabel, "qt_msgbox_label")
        assert label_light is not None
        assert (
            label_light.palette().color(label_light.foregroundRole()).name()
            == "#0f172a"
        )
    finally:
        msg_light.close()


if __name__ == "__main__":
    print("Running tests...")
    test_theme_palettes_and_stylesheet()
    print("[OK] test_theme_palettes_and_stylesheet passed")
    test_ansi_color_parser()
    print("[OK] test_ansi_color_parser passed")
    test_dockerfile_sync()
    print("[OK] test_dockerfile_sync passed")
    test_exception_report_builder()
    print("[OK] test_exception_report_builder passed")
    test_physical_tab_widget()
    print("[OK] test_physical_tab_widget passed")
    test_main_window_integration()
    print("[OK] test_main_window_integration passed")
    test_robot_registry()
    print("[OK] test_robot_registry passed")
    test_config_store_workspace_validation()
    print("[OK] test_config_store_workspace_validation passed")
    test_config_store_world_fallback()
    print("[OK] test_config_store_world_fallback passed")
    test_dialog_stylesheets_and_variants()
    print("[OK] test_dialog_stylesheets_and_variants passed")
    test_container_state_and_button_robustness()
    print("[OK] test_container_state_and_button_robustness passed")
    test_docker_startup_progress_timer()
    print("[OK] test_docker_startup_progress_timer passed")
    test_docker_service_detection()
    print("[OK] test_docker_service_detection passed")
    test_docker_command_length_windows_limits()
    print("[OK] test_docker_command_length_windows_limits passed")
    test_dialog_and_message_box_dark_mode()
    print("[OK] test_dialog_and_message_box_dark_mode passed")
    print("\nAll 15 test suites passed successfully!")
