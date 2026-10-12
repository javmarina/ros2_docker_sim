"""
Unit and integration tests for the refactored ROS 2 Simulation Launcher modules.
Can be executed with pytest: `pytest test_launcher.py`
or directly: `python test_launcher.py`
"""

import sys
import tempfile
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

# Ensure an application instance exists for Qt widgets
app = QtWidgets.QApplication.instance()
if app is None:
    app = QtWidgets.QApplication(["--platform", "offscreen"])

import theme
import utils
import exception_dialog
from config_store import ConfigStore
from physical_tab import PhysicalRobotTab
from docker_service import ContainerState
from main_window import ModernSimulationLauncher
from robot_registry import get_all_robots, get_robot_by_id


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
    except ValueError as err:
        exc_type, exc_val, exc_tb = sys.exc_info()
        report = exception_dialog.build_error_report(exc_type, exc_val, exc_tb, docker_info="Instalado: Sí | En ejecución: No")

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
    """Validates robot profiles, scenarios, and command building."""
    robots = get_all_robots()
    assert len(robots) >= 2
    tb4 = get_robot_by_id("turtlebot4")
    assert tb4 is not None
    assert tb4.supported_worlds == ["empty", "warehouse", "depot", "maze"]
    sc = tb4.get_scenario_by_id("slam")
    assert sc is not None
    cmd = tb4.build_command("slam", "depot")
    assert "turtlebot4" in cmd or "slam" in cmd
    assert "turtlebot4_nodock.launch.py" in cmd

    # Verificar que el dock está eliminado en TODOS los mundos
    cmd_empty = tb4.build_command("sim_only", "empty")
    assert "turtlebot4_nodock.launch.py" in cmd_empty
    assert "world:=empty" in cmd_empty

    cmd_warehouse = tb4.build_command("sim_only", "warehouse")
    assert "turtlebot4_nodock.launch.py" in cmd_warehouse
    assert "world:=warehouse" in cmd_warehouse

    cmd_depot = tb4.build_command("nav2", "depot")
    assert "turtlebot4_nodock.launch.py" in cmd_depot
    assert "world:=depot" in cmd_depot
    assert "nav2:=true" in cmd_depot


def test_config_store_workspace_validation():
    """Validates ConfigStore workspace path check logic."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Non-existent path
        valid, msg = ConfigStore.validate_workspace(str(Path(tmp_dir) / "does_not_exist"))
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
        assert QtGui.QColor(pm_term.toImage().pixel(10, 10)).name() in ("#0f172a", "#1e293b")

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
    test_dialog_stylesheets_and_variants()
    print("[OK] test_dialog_stylesheets_and_variants passed")
    test_container_state_and_button_robustness()
    print("[OK] test_container_state_and_button_robustness passed")
    print("\nAll 10 test suites passed successfully!")


