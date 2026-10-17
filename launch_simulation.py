"""
Launcher de Simulación ROS 2 Jazzy para la Asignatura de Robótica Móvil
Punto de entrada principal de la aplicación con PySide6 y Docker.
"""

import logging
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

# Configuración del logging estándar
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("launcher")

# Habilitar AppUserModelID en Windows para icono agrupado en barra de tareas
if sys.platform == "win32":
    try:
        import ctypes

        app_id = "lasalle.sistemasdenavegacion.ros2launcher.v107"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

# Módulos del proyecto
from embedded_icon import get_app_icon_path
from exception_dialog import _global_excepthook, setup_global_exception_handler
from main_window import ModernSimulationLauncher
from theme import THEME_PALETTES, apply_theme_to_application, is_dark_mode


def main():
    """Punto de entrada principal de la aplicación GUI."""
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("ROS 2 Simulation Launcher")
    app.setOrganizationName("La Salle URL")

    # Inicializar tema global (paleta, estilos de diálogos y DWM dark mode)
    apply_theme_to_application(is_dark_mode())

    # Registrar despachador y capturadores globales de excepciones
    setup_global_exception_handler()

    # Configurar icono nativo de aplicación
    ico_path = None
    try:
        ico_path = get_app_icon_path()
        if ico_path and ico_path.is_file():
            app.setWindowIcon(QtGui.QIcon(str(ico_path)))
    except Exception as e:
        logger.debug("No se pudo configurar icono de aplicación: %s", e)

    try:
        window = ModernSimulationLauncher()
        window.show()

        # Garantizar que Windows Taskbar y Alt+Tab reciban el icono nativo (32x32 y 16x16)
        if sys.platform == "win32" and ico_path and ico_path.is_file():
            try:
                import ctypes

                hwnd = int(window.winId())
                ico_str = str(ico_path)
                hicon_big = ctypes.windll.user32.LoadImageW(
                    None, ico_str, 1, 32, 32, 0x00000010
                )
                hicon_small = ctypes.windll.user32.LoadImageW(
                    None, ico_str, 1, 16, 16, 0x00000010
                )
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
