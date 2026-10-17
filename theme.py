"""
Theme palettes, dark mode detection, global and dialog stylesheet generation.
Centralizes design tokens, semantic status colors, and reusable widget styles.
"""

import logging
import sys
from typing import Optional, Tuple, Union

from PySide6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger("launcher")

# ---------------------------------------------------------------------------
# Semantic Status Tokens (Success, Warning, Error, Info, Neutral)
# ---------------------------------------------------------------------------

STATUS_COLORS = {
    "success": {
        "fg_light": "#15803d",
        "fg_dark": "#4ade80",
        "bg_light": "#dcfce7",
        "bg_dark": "rgba(34, 197, 94, 0.2)",
        "border_light": "#bbf7d0",
        "border_dark": "rgba(34, 197, 94, 0.4)",
    },
    "warning": {
        "fg_light": "#b45309",
        "fg_dark": "#fbbf24",
        "bg_light": "#fef3c7",
        "bg_dark": "rgba(245, 158, 11, 0.2)",
        "border_light": "#fde68a",
        "border_dark": "rgba(245, 158, 11, 0.4)",
    },
    "error": {
        "fg_light": "#b91c1c",
        "fg_dark": "#f87171",
        "bg_light": "#fee2e2",
        "bg_dark": "rgba(239, 68, 68, 0.2)",
        "border_light": "#fca5a5",
        "border_dark": "rgba(239, 68, 68, 0.4)",
    },
    "info": {
        "fg_light": "#1d4ed8",
        "fg_dark": "#60a5fa",
        "bg_light": "#dbeafe",
        "bg_dark": "rgba(59, 130, 246, 0.2)",
        "border_light": "#bfdbfe",
        "border_dark": "rgba(59, 130, 246, 0.4)",
    },
    "neutral": {
        "fg_light": "#475569",
        "fg_dark": "#cbd5e1",
        "bg_light": "#f1f5f9",
        "bg_dark": "rgba(148, 163, 184, 0.2)",
        "border_light": "#e2e8f0",
        "border_dark": "rgba(148, 163, 184, 0.4)",
    },
}


def get_status_colors(kind: str, is_dark: bool) -> Tuple[str, str, str]:
    """Returns (foreground_color, background_badge_color, border_badge_color) for a status kind."""
    c = STATUS_COLORS.get(kind, STATUS_COLORS["neutral"])
    mode = "dark" if is_dark else "light"
    return c[f"fg_{mode}"], c[f"bg_{mode}"], c[f"border_{mode}"]


# ---------------------------------------------------------------------------
# Core Theme Palettes (Light & Dark)
# ---------------------------------------------------------------------------

THEME_PALETTES = {
    "light": {
        # Surfaces
        "bg_window": "#f8fafc",
        "bg_card": "#ffffff",
        "bg_header": "#ffffff",
        "bg_input": "#ffffff",
        "bg_button": "#f1f5f9",
        "bg_button_hover": "#e2e8f0",
        "bg_button_pressed": "#cbd5e1",
        # Borders
        "border": "#e2e8f0",
        "border_input": "#cbd5e1",
        "border_input_hover": "#94a3b8",
        "border_focus": "#2563eb",
        # Typography
        "text_primary": "#0f172a",
        "text_secondary": "#475569",
        "text_muted": "#64748b",
        "text_title": "#1e3a8a",
        # Icons
        "icon_color": "#1e293b",
        "tab_icon_normal": "#475569",
        "tab_icon_selected": "#ffffff",
        # Actions / Accents
        "primary": "#2563eb",
        "primary_hover": "#1d4ed8",
        "success": "#16a34a",
        "success_hover": "#15803d",
        "danger": "#dc2626",
        "danger_hover": "#b91c1c",
    },
    "dark": {
        # Surfaces
        "bg_window": "#0f172a",
        "bg_card": "#1e293b",
        "bg_header": "#1e293b",
        "bg_input": "#0f172a",
        "bg_button": "#334155",
        "bg_button_hover": "#475569",
        "bg_button_pressed": "#1e293b",
        # Borders
        "border": "#334155",
        "border_input": "#475569",
        "border_input_hover": "#64748b",
        "border_focus": "#3b82f6",
        # Typography
        "text_primary": "#f8fafc",
        "text_secondary": "#cbd5e1",
        "text_muted": "#94a3b8",
        "text_title": "#60a5fa",
        # Icons
        "icon_color": "#e2e8f0",
        "tab_icon_normal": "#94a3b8",
        "tab_icon_selected": "#ffffff",
        # Actions / Accents
        "primary": "#2563eb",
        "primary_hover": "#1d4ed8",
        "success": "#16a34a",
        "success_hover": "#15803d",
        "danger": "#dc2626",
        "danger_hover": "#b91c1c",
    },
}

# Compatibility aliases mapping redundant legacy keys to core tokens
_LIGHT_ALIASES = {
    "card_desc_bg": "#f8fafc",
    "card_desc_border": "#e2e8f0",
    "tab_bg": "#f1f5f9",
    "tab_text": "#475569",
    "tab_hover": "#e2e8f0",
    "tab_hover_text": "#0f172a",
    "dropdown_bg": "#f8fafc",
    "dropdown_hover": "#e2e8f0",
    "progress_bg": "#ffffff",
    "logs_border": "#cbd5e1",
    "btn_terminal_bg": "#0f172a",
    "btn_terminal_border": "transparent",
    "btn_terminal_hover": "#1e293b",
}
THEME_PALETTES["light"].update(_LIGHT_ALIASES)

_DARK_ALIASES = {
    "card_desc_bg": "#0f172a",
    "card_desc_border": "#334155",
    "tab_bg": "#0f172a",
    "tab_text": "#94a3b8",
    "tab_hover": "#334155",
    "tab_hover_text": "#f8fafc",
    "dropdown_bg": "#0f172a",
    "dropdown_hover": "#334155",
    "progress_bg": "#0f172a",
    "logs_border": "#334155",
    "btn_terminal_bg": "#1e293b",
    "btn_terminal_border": "#475569",
    "btn_terminal_hover": "#334155",
}
THEME_PALETTES["dark"].update(_DARK_ALIASES)


# ---------------------------------------------------------------------------
# OS Dark Mode & Windows DWM Integration
# ---------------------------------------------------------------------------


def is_dark_mode() -> bool:
    """Determines if the OS is currently in Dark Mode via Qt style hints."""
    app = QtWidgets.QApplication.instance()
    if app:
        hints = app.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == QtCore.Qt.ColorScheme.Dark
    return False


def set_window_dark_mode(target: Union[QtWidgets.QWidget, int], dark: bool):
    """
    Enables/disables Windows 10/11 immersive dark title bar via DWM.
    Safe cross-platform no-op on non-Windows platforms.
    Accepts either a QWidget (window) or an integer HWND.
    """
    if sys.platform != "win32":
        return
    try:
        if isinstance(target, int):
            hwnd = target
        elif hasattr(target, "winId"):
            hwnd = int(target.winId())
        else:
            hwnd = int(target)
        import ctypes

        val = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 on Win11/Win10 20H1+, 19 on earlier builds
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(val), ctypes.sizeof(val)
        )
        if res != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(val), ctypes.sizeof(val)
            )
    except Exception as e:
        logger.debug("No se pudo configurar DWM immersive dark mode: %s", e)


class _ThemeWindowEventFilter(QtCore.QObject):
    """Event filter that ensures all top-level windows and dialogs (e.g. QMessageBox)
    receive the Windows 10/11 DWM immersive dark mode attribute when shown."""

    def __init__(self, is_dark: bool = False):
        super().__init__()
        self.is_dark = is_dark

    def set_dark(self, is_dark: bool):
        self.is_dark = is_dark

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.Show:
            if obj.isWidgetType() and getattr(obj, "isWindow", lambda: False)():
                set_window_dark_mode(obj, self.is_dark)
        return super().eventFilter(obj, event)


_GLOBAL_WINDOW_FILTER: Optional[_ThemeWindowEventFilter] = None
_ACTIVE_THEME_DARK: Optional[bool] = None


def get_active_theme_mode() -> bool:
    """Returns True if the active theme is dark mode, considering user preference and OS default."""
    if _ACTIVE_THEME_DARK is not None:
        return _ACTIVE_THEME_DARK
    return is_dark_mode()


def create_theme_palette(is_dark: bool) -> QtGui.QPalette:
    """Creates a consistent QPalette for the given theme mode."""
    p = THEME_PALETTES["dark" if is_dark else "light"]
    palette = QtGui.QPalette()

    bg = QtGui.QColor(p["bg_window"])
    fg = QtGui.QColor(p["text_primary"])
    base = QtGui.QColor(p["bg_input"])
    card = QtGui.QColor(p["bg_card"])
    button = QtGui.QColor(p["bg_button"])
    button_fg = QtGui.QColor(p["text_primary"])
    highlight = QtGui.QColor(p["primary"])
    highlight_text = QtGui.QColor("#ffffff")
    disabled_text = QtGui.QColor(p["text_muted"])
    disabled_bg = QtGui.QColor(p["bg_button"])

    # Active / Inactive
    palette.setColor(QtGui.QPalette.ColorRole.Window, bg)
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, fg)
    palette.setColor(QtGui.QPalette.ColorRole.Base, base)
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, card)
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, card)
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, fg)
    palette.setColor(QtGui.QPalette.ColorRole.Text, fg)
    palette.setColor(QtGui.QPalette.ColorRole.Button, button)
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, button_fg)
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, highlight_text)
    palette.setColor(QtGui.QPalette.ColorRole.PlaceholderText, disabled_text)

    # Disabled
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.WindowText,
        disabled_text,
    )
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text, disabled_text
    )
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.ButtonText,
        disabled_text,
    )
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Button, disabled_bg
    )

    return palette


def apply_theme_to_application(is_dark: bool, arrow_url: str = ""):
    """
    Applies the full theme (palette, application stylesheet, DWM titlebars)
    globally to the QApplication instance and all child windows/dialogs.
    """
    global _GLOBAL_WINDOW_FILTER, _ACTIVE_THEME_DARK
    _ACTIVE_THEME_DARK = is_dark

    app = QtWidgets.QApplication.instance()
    if not app:
        return

    # 1. Update application palette
    app.setPalette(create_theme_palette(is_dark))

    # 2. Update application-wide stylesheet
    qss = build_global_stylesheet(is_dark, arrow_url)
    app.setStyleSheet(qss)

    # 3. Ensure global DWM window filter is installed and updated
    if _GLOBAL_WINDOW_FILTER is None:
        _GLOBAL_WINDOW_FILTER = _ThemeWindowEventFilter(is_dark)
        app.installEventFilter(_GLOBAL_WINDOW_FILTER)
    else:
        _GLOBAL_WINDOW_FILTER.set_dark(is_dark)

    # 4. Update any existing top-level windows
    for widget in app.topLevelWidgets():
        if widget.isWindow():
            set_window_dark_mode(widget, is_dark)


# ---------------------------------------------------------------------------
# Reusable Badge & Label Styling Helpers
# ---------------------------------------------------------------------------


def style_badge(label: QtWidgets.QLabel, text: str, kind: str, is_dark: bool = False):
    """Applies consistent styling to status badges using centralized semantic colors."""
    label.setText(text)
    fg, bg, _ = get_status_colors(kind, is_dark)
    label.setStyleSheet(f"""
        background-color: {bg};
        color: {fg};
        font-size: 11px;
        font-weight: 700;
        padding: 0 12px;
        border-radius: 6px;
    """)


def style_status_label(
    label: QtWidgets.QLabel, text: str, kind: str, is_dark: bool = False
):
    """Applies accessible text color to status labels using centralized semantic colors."""
    label.setText(text)
    fg, _, _ = get_status_colors(kind, is_dark)
    weight = "normal" if kind == "neutral" else "600"
    label.setStyleSheet(f"font-size: 11px; color: {fg}; font-weight: {weight};")


# ---------------------------------------------------------------------------
# Dialog Stylesheet Generator (Exception, Updater, and generic Modal Dialogs)
# ---------------------------------------------------------------------------


def build_dialog_stylesheet(is_dark: bool, dialog_type: str = "default") -> str:
    """
    Generates a unified stylesheet for modal dialogs (Exception, Updater, etc.).
    Fully supports both light and dark modes using centralized design tokens.
    """
    p = THEME_PALETTES["dark" if is_dark else "light"]
    mode = "dark" if is_dark else "light"
    success_fg = STATUS_COLORS["success"][f"fg_{mode}"]
    success_bg = STATUS_COLORS["success"][f"bg_{mode}"]
    error_fg = STATUS_COLORS["error"][f"fg_{mode}"]

    base_css = f"""
        QDialog, QMessageBox {{
            background-color: {p["bg_window"]};
            color: {p["text_primary"]};
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
        }}
        QLabel {{
            color: {p["text_primary"]};
        }}
        QMessageBox QLabel, QDialog QLabel {{
            color: {p["text_primary"]};
            background-color: transparent;
        }}
        QMessageBox QLabel#qt_msgbox_label {{
            font-size: 13px;
            font-weight: 500;
            color: {p["text_primary"]};
            line-height: 1.4;
            background-color: transparent;
        }}
        QMessageBox QLabel#qt_msgbox_informativelabel {{
            font-size: 12px;
            color: {p["text_secondary"]};
            background-color: transparent;
        }}
        QMessageBox QLabel#qt_msgboxex_icon_label {{
            background-color: transparent;
        }}
        QMessageBox QPushButton, QDialog QPushButton {{
            background-color: {p["bg_button"]};
            border: 1px solid {p["border_input"]};
            border-radius: 6px;
            padding: 6px 18px;
            min-width: 68px;
            min-height: 20px;
            font-size: 12px;
            font-weight: 600;
            color: {p["text_primary"]};
        }}
        QMessageBox QPushButton:hover, QDialog QPushButton:hover {{
            background-color: {p["bg_button_hover"]};
            border-color: {p["border_input_hover"]};
        }}
        QMessageBox QPushButton:pressed, QDialog QPushButton:pressed {{
            background-color: {p["bg_button_pressed"]};
        }}
        QMessageBox QPushButton:focus, QDialog QPushButton:focus {{
            border: 1px solid {p["border_focus"]};
        }}
        QMessageBox QPushButton:default, QDialog QPushButton:default {{
            background-color: {p["primary"]};
            color: #ffffff;
            border: 1px solid {p["primary"]};
            font-weight: 700;
        }}
        QMessageBox QPushButton:default:hover, QDialog QPushButton:default:hover {{
            background-color: {p["primary_hover"]};
            border-color: {p["primary_hover"]};
        }}
        QMessageBox QDialogButtonBox {{
            background-color: transparent;
            border: none;
        }}
        QMessageBox QTextEdit, QMessageBox QPlainTextEdit,
        QDialog QTextEdit, QDialog QPlainTextEdit {{
            background-color: {p["bg_input"]};
            color: {p["text_primary"]};
            border: 1px solid {p["border_input"]};
            border-radius: 6px;
        }}
    """

    if dialog_type == "exception":
        report_bg = "#020617" if is_dark else "#ffffff"
        report_fg = "#94a3b8" if is_dark else "#334155"
        return (
            base_css
            + f"""
            #errHeaderFrame {{
                background-color: {p["bg_card"]};
                border: 1px solid {p["border"]};
                border-left: 5px solid {error_fg};
                border-radius: 8px;
            }}
            #errTitle {{
                font-size: 14px;
                font-weight: 700;
                color: {error_fg};
            }}
            #errSummary {{
                font-size: 12px;
                color: {p["text_primary"]};
            }}
            #errInstruction {{
                font-size: 11px;
                color: {p["text_muted"]};
                margin-top: 2px;
            }}
            #errReportText {{
                background-color: {report_bg};
                color: {report_fg};
                font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid {p["border"]};
                border-radius: 6px;
                padding: 10px;
            }}
            #btnCopyReport {{
                background-color: {p["bg_button"]};
                color: {p["text_primary"]};
                border: 1px solid {p["border_input"]};
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 600;
                font-size: 12px;
            }}
            #btnCopyReport:hover {{
                background-color: {p["bg_button_hover"]};
            }}
            #btnEmailReport {{
                background-color: {p["danger"]};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 600;
                font-size: 12px;
            }}
            #btnEmailReport:hover {{
                background-color: {p["danger_hover"]};
            }}
            #btnClose {{
                background-color: transparent;
                color: {p["text_muted"]};
                border: 1px solid {p["border"]};
                border-radius: 6px;
                padding: 7px 16px;
                font-size: 12px;
            }}
            #btnClose:hover {{
                background-color: {p["bg_button"]};
                color: {p["text_primary"]};
            }}
            #errFeedback {{
                font-size: 11px;
                color: {success_fg};
                font-weight: 600;
            }}
        """
        )

    elif dialog_type == "updater":
        return (
            base_css
            + f"""
            #headerCard {{
                background-color: {p["bg_card"]};
                border: 1px solid {p["border"]};
                border-radius: 8px;
            }}
            #badgeLabel {{
                background-color: {success_bg};
                color: {success_fg};
                font-weight: 700;
                font-size: 13px;
                padding: 4px 10px;
                border-radius: 6px;
            }}
            #currentLabel {{
                color: {p["text_secondary"]};
                font-size: 12px;
                margin-left: 6px;
            }}
            #dateLabel {{
                color: {p["text_muted"]};
                font-size: 11px;
            }}
            #lblNotes {{
                font-size: 13px;
                font-weight: 600;
                color: {p["text_primary"]};
            }}
            #changelogBox {{
                background-color: {p["bg_card"]};
                border: 1px solid {p["border_input"]};
                border-radius: 6px;
                padding: 10px;
                color: {p["text_primary"]};
                font-size: 12px;
                line-height: 1.4;
            }}
            #progressBar {{
                border: 1px solid {p["border_input"]};
                border-radius: 6px;
                text-align: center;
                background-color: {p["bg_input"]};
                height: 20px;
                font-size: 11px;
                font-weight: 600;
                color: {p["text_primary"]};
            }}
            #progressBar::chunk {{
                background-color: {p["success"]};
                border-radius: 5px;
            }}
            #statusLabel {{
                color: {p["text_secondary"]};
                font-size: 12px;
            }}
            #btnLater {{
                background-color: {p["bg_button"]};
                color: {p["text_primary"]};
                border: 1px solid {p["border_input"]};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            #btnLater:hover {{
                background-color: {p["bg_button_hover"]};
            }}
            #btnUpdate {{
                background-color: {p["success"]};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 700;
            }}
            #btnUpdate:hover {{
                background-color: {p["success_hover"]};
            }}
            #btnUpdate:disabled {{
                background-color: {p["text_muted"]};
            }}
        """
        )

    return base_css


# ---------------------------------------------------------------------------
# Global Application Stylesheet Generator
# ---------------------------------------------------------------------------


def build_global_stylesheet(is_dark: bool, arrow_url: str = "") -> str:
    """Generates the complete QSS stylesheet for the application based on the active theme."""
    p = THEME_PALETTES["dark" if is_dark else "light"]
    err_fg, err_bg, err_border = get_status_colors("error", is_dark)
    clean_arrow_url = str(arrow_url).replace("\\", "/") if arrow_url else ""
    return f"""
        QMainWindow, QDialog, QMessageBox {{
            background-color: {p["bg_window"]};
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif;
            color: {p["text_primary"]};
        }}
        QWidget {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif;
            color: {p["text_primary"]};
        }}
        /* Diálogos modales y cuadros de mensaje (QDialog & QMessageBox) */
        QDialog, QMessageBox {{
            background-color: {p["bg_window"]};
            color: {p["text_primary"]};
        }}
        QMessageBox QLabel, QDialog QLabel {{
            color: {p["text_primary"]};
            background-color: transparent;
        }}
        QMessageBox QLabel#qt_msgbox_label {{
            font-size: 13px;
            font-weight: 500;
            color: {p["text_primary"]};
            line-height: 1.4;
            background-color: transparent;
        }}
        QMessageBox QLabel#qt_msgbox_informativelabel {{
            font-size: 12px;
            color: {p["text_secondary"]};
            background-color: transparent;
        }}
        QMessageBox QLabel#qt_msgboxex_icon_label {{
            background-color: transparent;
        }}
        QMessageBox QPushButton, QDialog QPushButton {{
            background-color: {p["bg_button"]};
            border: 1px solid {p["border_input"]};
            border-radius: 6px;
            padding: 6px 18px;
            min-width: 68px;
            min-height: 20px;
            font-size: 12px;
            font-weight: 600;
            color: {p["text_primary"]};
        }}
        QMessageBox QPushButton:hover, QDialog QPushButton:hover {{
            background-color: {p["bg_button_hover"]};
            border-color: {p["border_input_hover"]};
        }}
        QMessageBox QPushButton:pressed, QDialog QPushButton:pressed {{
            background-color: {p["bg_button_pressed"]};
        }}
        QMessageBox QPushButton:focus, QDialog QPushButton:focus {{
            border: 1px solid {p["border_focus"]};
        }}
        QMessageBox QPushButton:default, QDialog QPushButton:default {{
            background-color: {p["primary"]};
            color: #ffffff;
            border: 1px solid {p["primary"]};
            font-weight: 700;
        }}
        QMessageBox QPushButton:default:hover, QDialog QPushButton:default:hover {{
            background-color: {p["primary_hover"]};
            border-color: {p["primary_hover"]};
        }}
        QMessageBox QDialogButtonBox {{
            background-color: transparent;
            border: none;
        }}
        QMessageBox QTextEdit, QMessageBox QPlainTextEdit,
        QDialog QTextEdit, QDialog QPlainTextEdit {{
            background-color: {p["bg_input"]};
            color: {p["text_primary"]};
            border: 1px solid {p["border_input"]};
            border-radius: 6px;
        }}
        /* Header */
        #headerFrame {{
            background-color: {p["bg_header"]};
            border-bottom: 1px solid {p["border"]};
            padding: 10px 18px;
        }}
        #titleLabel {{
            font-size: 15px;
            font-weight: 700;
            color: {p["text_title"]};
        }}
        #subtitleLabel {{
            font-size: 11px;
            color: {p["text_muted"]};
        }}
        /* Cards semánticas */
        QFrame[card="true"] {{
            background-color: {p["bg_card"]};
            border: 1px solid {p["border"]};
            border-radius: 8px;
        }}
        /* Títulos y textos semánticos dentro de tarjetas */
        QLabel[heading="true"] {{
            font-size: 15px;
            font-weight: 700;
            color: {p["text_title"]};
        }}
        QLabel[heading_small="true"] {{
            font-size: 12px;
            font-weight: 600;
            color: {p["text_primary"]};
        }}
        QLabel[secondary="true"] {{
            font-size: 11px;
            color: {p["text_secondary"]};
        }}
        QLabel[note="true"] {{
            font-size: 11px;
            font-style: italic;
            color: {p["text_muted"]};
        }}
        /* Tab Widget */
        QTabWidget::pane {{
            border: 1px solid {p["border"]};
            border-radius: 8px;
            background-color: {p["bg_window"]};
            top: -1px;
        }}
        QTabBar::tab {{
            background: {p["tab_bg"]};
            color: {p["tab_text"]};
            padding: 8px 16px;
            font-size: 12px;
            font-weight: 600;
            border: 1px solid {p["border"]};
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 4px;
        }}
        QTabBar::tab:selected {{
            background: {p["primary"]};
            color: #ffffff;
            border-color: {p["primary"]};
        }}
        QTabBar::tab:hover:!selected {{
            background: {p["tab_hover"]};
            color: {p["tab_hover_text"]};
        }}
        /* Inputs */
        QLineEdit {{
            background-color: {p["bg_input"]};
            border: 1px solid {p["border_input"]};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
            color: {p["text_primary"]};
        }}
        QLineEdit:hover {{
            border-color: {p["border_input_hover"]};
        }}
        QLineEdit:focus {{
            border: 1px solid {p["border_focus"]};
        }}
        /* Dropdowns (QComboBox) */
        QComboBox {{
            background-color: {p["bg_input"]};
            border: 1px solid {p["border_input"]};
            border-radius: 6px;
            padding: 6px 30px 6px 10px;
            font-size: 12px;
            color: {p["text_primary"]};
            min-height: 20px;
        }}
        QComboBox:hover {{
            border-color: {p["border_input_hover"]};
        }}
        QComboBox:focus, QComboBox:on {{
            border: 1px solid {p["border_focus"]};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 26px;
            border-left: 1px solid {p["border"]};
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
            background-color: {p["dropdown_bg"]};
        }}
        QComboBox::drop-down:hover {{
            background-color: {p["dropdown_hover"]};
        }}
        QComboBox::down-arrow {{
            image: url("{clean_arrow_url}");
            width: 12px;
            height: 12px;
        }}
        QComboBox::down-arrow:disabled {{
            opacity: 0.3;
        }}
        QComboBox QAbstractItemView {{
            border: 1px solid {p["border_input"]};
            border-radius: 6px;
            background-color: {p["bg_card"]};
            color: {p["text_primary"]};
            selection-background-color: {p["primary"]};
            selection-color: #ffffff;
            outline: 0;
            padding: 4px;
        }}
        /* Buttons */
        QPushButton {{
            background-color: {p["bg_button"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            padding: 7px 14px;
            font-size: 12px;
            font-weight: 600;
            color: {p["text_primary"]};
        }}
        QPushButton:hover {{
            background-color: {p["bg_button_hover"]};
        }}
        QPushButton:pressed {{
            background-color: {p["bg_button_pressed"]};
        }}
        QPushButton:disabled {{
            background-color: {p["bg_button"]};
            color: {p["text_muted"]};
            border-color: {p["border"]};
        }}
        /* Semantic button variants */
        QPushButton[variant="primary"], #btnLaunch, #btnRobotTerminal {{
            background-color: {p["primary"]};
            color: #ffffff;
            border: none;
            font-weight: 700;
        }}
        QPushButton[variant="primary"]:hover, #btnLaunch:hover, #btnRobotTerminal:hover {{
            background-color: {p["primary_hover"]};
        }}
        QPushButton[variant="primary"]:disabled, #btnLaunch:disabled, #btnRobotTerminal:disabled {{
            background-color: {p["bg_button"]};
            color: {p["text_muted"]};
            border: 1px solid {p["border"]};
        }}
        QPushButton[variant="success"] {{
            background-color: {p["success"]};
            color: #ffffff;
            border: none;
            font-weight: 700;
        }}
        QPushButton[variant="success"]:hover {{
            background-color: {p["success_hover"]};
        }}
        /* Header buttons */
        #btnHeaderUpdate, #btnDocker, #btnThemeToggle {{
            background-color: {p["bg_button"]};
            color: {p["text_primary"]};
            border: 1px solid {p["border"]};
            font-weight: 600;
            font-size: 11px;
            border-radius: 6px;
            padding: 0 10px;
        }}
        #btnHeaderUpdate:hover, #btnDocker:hover, #btnThemeToggle:hover {{
            background-color: {p["bg_button_hover"]};
        }}
        #btnHeaderUpdate[variant="success"] {{
            background-color: {p["success"]};
            color: #ffffff;
            border: none;
            font-weight: 700;
        }}
        #btnHeaderUpdate[variant="success"]:hover {{
            background-color: {p["success_hover"]};
        }}
        #btnDocker[variant="primary"] {{
            background-color: {p["primary"]};
            color: #ffffff;
            border: 1px solid {p["primary_hover"]};
            font-weight: 700;
        }}
        #btnDocker[variant="primary"]:hover {{
            background-color: {p["primary_hover"]};
        }}
        #btnDocker[variant="danger"] {{
            background-color: {err_bg};
            color: {err_fg};
            border: 1px solid {err_border};
            font-weight: 600;
        }}
        #btnDocker[variant="danger"]:hover {{
            background-color: {err_border};
        }}
        #btnTerminal {{
            background-color: {p["btn_terminal_bg"]};
            color: #ffffff;
            border: 1px solid {p["btn_terminal_border"]};
            font-weight: 700;
            padding: 9px 12px;
        }}
        #btnTerminal:hover {{
            background-color: {p["btn_terminal_hover"]};
        }}
        #btnWeb {{
            background-color: #0284c7;
            color: #ffffff;
            border: none;
            font-weight: 700;
            padding: 9px 12px;
        }}
        #btnWeb:hover {{
            background-color: #0369a1;
        }}
        #btnStop {{
            background-color: {p["danger"]};
            color: #ffffff;
            border: none;
            font-weight: 700;
            padding: 9px 12px;
        }}
        #btnStop:hover {{
            background-color: {p["danger_hover"]};
        }}
        #btnStop:disabled {{
            background-color: {p["bg_button"]};
            color: {p["text_muted"]};
            border: 1px solid {p["border"]};
        }}
        /* Progress Bar */
        QProgressBar {{
            border: 1px solid {p["border_input"]};
            border-radius: 6px;
            text-align: center;
            background-color: {p["progress_bg"]};
            color: {p["text_primary"]};
            height: 16px;
            font-size: 10px;
            font-weight: 600;
        }}
        QProgressBar::chunk {{
            background-color: {p["primary"]};
            border-radius: 5px;
        }}
        /* Scenario description box */
        #scenarioDescFrame {{
            background-color: {p["card_desc_bg"]};
            border: 1px solid {p["card_desc_border"]};
            border-radius: 6px;
            padding: 8px 12px;
        }}
        #lblScenarioDesc {{
            font-size: 11px;
            font-style: italic;
            color: {p["text_secondary"]};
        }}
        /* Log box & Guide */
        #txtLogs {{
            background-color: #0f172a;
            color: #e2e8f0;
            font-family: 'Cascadia Code', 'Consolas', 'DejaVu Sans Mono', monospace;
            font-size: 11px;
            border: 1px solid {p["logs_border"]};
            border-radius: 6px;
            padding: 8px;
        }}
        #txtGuide {{
            background-color: {p["bg_card"]};
            color: {p["text_primary"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            padding: 16px;
            font-size: 13px;
            line-height: 1.5;
        }}
        /* Scroll Areas */
        QScrollArea {{
            background-color: transparent;
            border: none;
        }}
        QScrollArea > QWidget > QWidget {{
            background-color: transparent;
        }}
        /* Scrollbars */
        QScrollBar:vertical {{
            border: none;
            background-color: transparent;
            width: 8px;
            margin: 0px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {p["border_input_hover"]};
            min-height: 25px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {p["border_focus"]};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            border: none;
            background: none;
        }}
        QScrollBar:horizontal {{
            border: none;
            background-color: transparent;
            height: 8px;
            margin: 0px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {p["border_input_hover"]};
            min-width: 25px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {p["border_focus"]};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            border: none;
            background: none;
            width: 0px;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            border: none;
            background: none;
        }}
    """
