"""
Modal dialog and global exception handling dispatcher for unexpected errors.
"""

import sys
import platform
import datetime
import traceback
import urllib.parse
import logging
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from updater import CURRENT_VERSION
from embedded_icon import get_app_icon_path
from theme import is_dark_mode, build_dialog_stylesheet

logger = logging.getLogger("launcher")

SUPPORT_EMAIL = "javier.marina@salle.url.edu"


def build_error_report(exc_type, exc_value, exc_tb, docker_info: Optional[str] = None) -> str:
    """
    Builds a detailed technical error report string from an exception.
    Pure function — testable without initializing a QApplication.
    """
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb_lines = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    if docker_info is None:
        try:
            from docker_service import DockerService
            docker_inst = "Sí" if DockerService.is_docker_installed() else "No"
            docker_run = "Sí" if DockerService.is_docker_running() else "No"
            docker_info = f"Instalado: {docker_inst} | En ejecución: {docker_run}"
        except Exception:
            docker_info = "No disponible"

    err_type_name = getattr(exc_type, "__name__", str(exc_type))

    return (
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
        f"Docker: {docker_info}\n"
        "\n"
        "--- DETALLES DE LA EXCEPCIÓN ---\n"
        f"Tipo de error: {err_type_name}\n"
        f"Mensaje: {exc_value}\n"
        "\n"
        "--- TRAZA COMPLETA (TRACEBACK) ---\n"
        f"{tb_lines}\n"
        "============================================================\n"
    )


class ExceptionModalDialog(QtWidgets.QDialog):
    """
    Modal dialog displaying uncaught exceptions, allowing users to copy
    the diagnostic report or email it directly to support.
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

        try:
            ico_p = get_app_icon_path()
            if ico_p and ico_p.is_file():
                self.setWindowIcon(QtGui.QIcon(str(ico_p)))
        except Exception:
            pass

        self.report_text = build_error_report(self.exc_type, self.exc_value, self.exc_tb)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(14)

        # Header card
        header_frame = QtWidgets.QFrame()
        header_frame.setObjectName("errHeaderFrame")
        h_layout = QtWidgets.QHBoxLayout(header_frame)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(14)

        icon_label = QtWidgets.QLabel()
        warn_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical)
        icon_label.setPixmap(warn_icon.pixmap(40, 40))
        icon_label.setFixedWidth(44)
        h_layout.addWidget(icon_label)

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setSpacing(3)
        lbl_title = QtWidgets.QLabel("Se ha producido un error inesperado en la aplicación")
        lbl_title.setObjectName("errTitle")

        err_name = getattr(self.exc_type, "__name__", str(self.exc_type))
        short_msg = str(self.exc_value).strip().splitlines()[0] if str(self.exc_value).strip() else "Sin descripción"
        lbl_summary = QtWidgets.QLabel(f"<b>{err_name}:</b> {short_msg[:120]}")
        lbl_summary.setObjectName("errSummary")
        lbl_summary.setWordWrap(True)

        lbl_instruct = QtWidgets.QLabel(
            "Puedes copiar el informe técnico y enviarlo por correo para que podamos solucionarlo:"
        )
        lbl_instruct.setObjectName("errInstruction")

        text_layout.addWidget(lbl_title)
        text_layout.addWidget(lbl_summary)
        text_layout.addWidget(lbl_instruct)
        h_layout.addLayout(text_layout, 1)
        main_layout.addWidget(header_frame)

        # Trace text view
        self.txt_report = QtWidgets.QPlainTextEdit()
        self.txt_report.setObjectName("errReportText")
        self.txt_report.setReadOnly(True)
        self.txt_report.setPlainText(self.report_text)
        main_layout.addWidget(self.txt_report, 1)

        # Bottom actions
        action_layout = QtWidgets.QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_copy = QtWidgets.QPushButton("  Copiar informe técnico")
        self.btn_copy.setObjectName("btnCopyReport")
        copy_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self.btn_copy.setIcon(copy_icon)
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        action_layout.addWidget(self.btn_copy)

        self.btn_email = QtWidgets.QPushButton("  Enviar a soporte por correo")
        self.btn_email.setObjectName("btnEmailReport")
        email_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogYesButton)
        self.btn_email.setIcon(email_icon)
        self.btn_email.clicked.connect(self._send_email)
        action_layout.addWidget(self.btn_email)

        action_layout.addStretch()

        self.lbl_feedback = QtWidgets.QLabel("")
        self.lbl_feedback.setObjectName("errFeedback")
        action_layout.addWidget(self.lbl_feedback)

        self.btn_close = QtWidgets.QPushButton("Cerrar")
        self.btn_close.setObjectName("btnClose")
        self.btn_close.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_close)

        main_layout.addLayout(action_layout)

    def _apply_styles(self):
        is_dark = is_dark_mode()
        self.setStyleSheet(build_dialog_stylesheet(is_dark, dialog_type="exception"))

    def _copy_to_clipboard(self):
        cb = QtGui.QGuiApplication.clipboard()
        if cb:
            cb.setText(self.report_text)
            self.lbl_feedback.setText("¡Informe copiado al portapapeles!")
            QtCore.QTimer.singleShot(4000, lambda: self.lbl_feedback.setText(""))

    def _send_email(self):
        self._copy_to_clipboard()
        err_name = getattr(self.exc_type, "__name__", str(self.exc_type))
        subject = f"[Error Launcher ROS 2] {err_name} - v{CURRENT_VERSION}"
        body = (
            "Hola soporte,\n\n"
            "Se ha producido el siguiente error en el Launcher de ROS 2 Jazzy:\n\n"
            f"{self.report_text}\n"
        )
        mailto_url = f"mailto:{SUPPORT_EMAIL}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(mailto_url))
        self.lbl_feedback.setText("Abriendo cliente de correo... Recuerda pegar el informe (Ctrl+V) antes de enviar.")


class GlobalExceptionDispatcher(QtCore.QObject):
    """
    Central exception dispatcher bridging unhandled exceptions from any thread
    to the Qt main GUI thread via a thread-safe QueuedConnection.
    """
    sig_exception = QtCore.Signal(object, object, object)

    def __init__(self):
        super().__init__()
        self._active = False
        self.sig_exception.connect(self._on_exception, QtCore.Qt.ConnectionType.QueuedConnection)

    @QtCore.Slot(object, object, object)
    def _on_exception(self, exc_type, exc_value, exc_tb):
        if self._active:
            return
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
    """Global handler for sys.excepthook."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    logger.critical("Excepción no controlada capturada:", exc_info=(exc_type, exc_value, exc_tb))

    if _global_dispatcher is not None:
        _global_dispatcher.sig_exception.emit(exc_type, exc_value, exc_tb)
    else:
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
    """Global handler for threading.excepthook (secondary background threads)."""
    _global_excepthook(args.exc_type, args.exc_value, args.exc_traceback)


def setup_global_exception_handler() -> GlobalExceptionDispatcher:
    """Installs sys.excepthook and threading.excepthook connected to Qt GUI."""
    global _global_dispatcher
    _global_dispatcher = GlobalExceptionDispatcher()
    sys.excepthook = _global_excepthook
    import threading
    threading.excepthook = _thread_excepthook
    return _global_dispatcher
