"""
Icono nativo de la aplicación embebido en Base64.
Garantiza que el launcher sea 100% autónomo y funcione sin depender de rutas externas ni carpetas de descargas.
"""

import base64
import tempfile
from pathlib import Path

FAVICON_ICO_BASE64 = "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XfDzVV7/8lRf//JTX//xUWD/8VFg//BPYf/wT2H/701i/+9MYv/uS2P/7kpk/+1JZP/tSGT/7Edl/+xGZv/rRWb/60Rn/+pDZ//qQmj/6UBo/+lAaf/oPmn/6T5p8Ok9aS4AAAAAAAAAAAAAAAAAAAAAAAAAAP9AQAT1WF3Q9Fde//RWXv/zVV//81Rf//JTYP/yUmD/8VFh//FQYf/wT2L/8E5i/+9NY//vTGP/7kpk/+5KZP/tSGX/7Uhl/+xGZv/sRWb/60Rn/+tDZ//qQmj/6kFo/+lAaf/pP2n/6T1p0P9AgAQAAAAAAAAAAAAAAAAAAAAA9Vpck/VZXP/0WFz/9Fdd//NWXv/zVV7/8lNf//JTX//xUWD/8VFg//BPYf/wTmH/701i/+9MYv/uS2P/7kpj/+1JZP/tSGT/7Edl/+xGZf/rRWb/60Rm/+pCZ//qQmf/6UBo/+lAaP/oPmn/6D1qkwAAAAAAAAAAAAAAAPZbWzj2XFz/9ltc//VZXf/1WV3/9Fde//RXXv/1cnv//u3u//7u7//1dID/8VFh//FQYf/xVmj//ePm//719v/0hpb/7ktk/+5KZf/tSGX/+9Xc///7/P/2qbj/60Rn/+tDaP/qQmj/6kFp/+lAaf/pP2r/6EBpOAAAAAAAAAAA915bqPZcW//2W1v/9Vpc//VZXP/0WF3/9Fdd//7q6/////////////7w8f/xUWD/8VFg//m0u//////////////////uS2P/7kpk//J7j//////////////////rRWb/60Rn/+pDZ//qQmj/6UFo/+lAaf/oPmmoAAAAAPViWBr4X1r/915b//ddW//2W1z/9ltc//VZXf/1WV3/+8fJ/////////////M/S//JTYP/yUmD/9pKc/////////////e3v/+9NY//vTGP/8GB3/////////////////+xGZv/sRWb/60Rn/+tDZ//qQmj/6kFo/+lAaf/rO2wa+F9YZvhfWf/3Xlr/911a//ZcWv/2W1v/9Vpc//VZXP/0WF3/+rK1//qztv/zVV7/8lNf//JTX//xUWD/96Gp//m2vf/xXW7/701i/+9MYv/uS2P/9ZCg//i4w//waoH/7Edl/+xGZf/rRWb/60Rm/+pDZ//qQmf/6UBo/+k/aWb5Ylmk+WFZ//hgWv/4X1r/915b//ddW//2XFz/9ltc//VZXf/1WV3/9Fde//RXXv/zVV//81Rf//JTYP/yUmD/8VFh//FQYf/wT2L/8E5j/+9NY//vTGP/7ktk/+5KZf/tSGX/7Uhl/+xGZv/sRmf/60Rn/+tDaP/qQmj/60FopPljWNH5Ylj/+GBZ//hgWf/3Xlr/911a//ZcW//2W1v/9Vpc//VZXP/0WF3/9Fdd//NWXv/zVV7/8lRf//JTX//xUWD/8VFg//BPYf/wT2H/701i/+9MYv/uS2P/7kpk/+1JZP/tSGT/7Edl/+xGZv/rRWb/60Rn/+pDZ//qQmjR+mRX7/pjWP/5Ylj/+WFZ//hgWf/4X1r/915b//ddW//3Zmb//NHR//zR0//2aGz/9Fde//RWXv/zVV//+8bK//zW2f/1d4L/8VFh//FQYf/wT2L/+brB//za3//0hpX/7kpk/+5KZP/tSGX/7Uhl/+xGZv/sRWb/60Rn/+tDZ+/6ZFb/+mRX//liV//5Ylj/+GBY//hfWf/3Xlr/911a//3e3f////////////3m5v/0WFz/9Fdd//morP/////////////9/f/xUWD/8VFg//Nxf//////////////////uS2P/7kpj/+1JZP/tSGT/7Edl/+xGZf/rRWb/60Rm//tmV//7ZVf/+mRY//pjWP/5Yln/+WFZ//hgWv/4X1r//d7e/////////////ubm//VZXf/1WV3/+ams//////////////39//JTYP/yUmH/9HJ//////////////////+9NY//vTGP/7ktk/+5KZf/tSGX/7Uhm/+xGZv/sRmf/+2ZV7/tmVv/6ZVf/+mRX//liWP/5Ylj/+GBZ//hgWf/4aWX//dHQ//3S0v/3amr/9Vpc//VZXP/0WF3/+8fJ//zX2P/2eYD/8lRf//JTX//xUWD/+rvB//za3v/1iJT/701i/+9MYv/uS2P/7kpk/+1JZP/tSGX/7Edl/+xGZe/7aFXR/GdW//tmVv/7ZVf/+mRX//pjWP/5Yln/+WFZ//hgWf/4X1r/915b//ddW//2W1z/9ltc//VZXf/1WV3/9Fde//RWXv/zVV//81Rf//JTYP/yUmD/8VFh//FQYf/wT2L/8E5i/+9NY//vTGP/7kpk/+5KZP/tSGX/7Uhl0fxoVKT8aFX/+2dV//tmVv/6ZFb/+mRX//liWP/5Ylj/+GBY//hfWf/3Xlr/911a//ZcWv/2W1v/9Vpc//VZXP/0WF3/9Fdd//NWXv/zVV7/8lNf//JTX//xUWD/8VFg//BPYf/wTmH/701i/+9MYv/uS2P/7kpj/+1JZP/sSGWk/WxVZv1qVf/8aFb//GdW//tmV//7ZVf/+mRY//pjWP/5Yln//Lez//y3tf/4X1r/915b//ddW//2XFz/+qan//u6vP/2Z2r/9Fde//RXXv/zVV//+Jad//q8wf/0c37/8VFh//FQYf/wT2L/8E5j/+9NY//vTGP/7ktk/+5LZGb/bFga/WpU//xpVf/8aFX/+2dW//tmVv/6ZVf/+mRX//3Lx/////////////3S0P/3Xlr/911a//mZmP////////////7u7v/0WF3/9Fdd//Rrcv/////////////////xUWD/8VFg//BPYf/wT2H/701i/+9MYv/uS2P/605iGgAAAAD9bFOo/WpU//1pVf/8aFX//GdW//tmVv/7ZVf//uzr/////////////vHx//hgWf/4X1r//Lq5//////////////////VZXf/1WV3/94WK//////////////////JTYP/yUmD/8VFh//FQYf/wT2L/8E5i//BMY6gAAAAAAAAAAP9tUjj9a1P//WpU//xpVP/8aFX/+2dV//tmVv/7f3P//u/t//7w7//6gXn/+GBY//hfWf/3ZGD//uXk///29v/5kJD/9Vpc//VZXP/0WFz//dna///8/P/5sLT/8lNf//JTX//xUWD/8VFg//BPYf/wTmH/8U1gOAAAAAAAAAAAAAAAAP1tU5P+bFT//WpV//1qVf/8aFb//GhW//tmV//7ZVf/+mRY//pjWP/5Yln/+WFZ//hgWv/4X1r/915b//ddW//2XFz/9ltc//VZXf/1WV3/9Fde//RXXv/zVV//81Rf//JTYP/yUmH/8VFh//FQYZMAAAAAAAAAAAAAAAAAAAAA/4BABP5sU9D9a1T//WpU//xpVf/8aFX/+2dW//tmVv/6ZVf/+mRX//liWP/5Ylj/+GBZ//hgWf/3Xlr/911a//ZcW//2W1v/9Vpc//VZXP/0WF3/9Fdd//NWXv/zVV7/8lRf//JTX//yUWDQ/0CABAAAAAAAAAAAAAAAAAAAAAAAAAAA/29TLv5sU/D+bFT//WpU//1qVf/8aFX//GdW//tmVv/7ZVf/+mRX//pjWP/5Yln/+WFZ//hgWf/4X1r/915b//ddW//2W1z/9ltc//VZXf/1WV3/9Fde//RWXv/zVV//81Rg8PRTXi4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/25RPP5sU/D9a1P//WpU//xpVP/8aFX/+2dV//tmVv/6ZFb/+mRX//liWP/5Ylj/+GBY//hfWf/3Xlr/911a//ZcWv/2W1v/9Vpc//VZXP/0WF3/9Fdd//NWXfDyVV08AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/29TLv5tU9D+bFT//WpU//1qVf/8aFb//GdW//tmV//7ZVf/+mRY//pjWP/5Yln/+WFZ//hgWv/4X1r/915b//ddW//2XFz/9ltc//VZXf/1WF3Q9FleLgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/4BABP1sU5P9a1P//WpU//xpVf/8aFX/+2dW//tmVv/6ZVf/+mRX//liWP/5Ylj/+GBZ//hgWf/3Xlr/911a//ZcW//2W1v/9Vpck/9AQAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP9tUjj9bFOo/WpU//1pVf/8aFX//GdW//tmVv/7ZVf/+mRX//pjWP/5Ylj/+WFZ//hgWf/4X1r/915bqPZbWzgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/bFga/WlVZvxoVKT7aFXR+2ZV7/tmVv/6ZFb/+mNX7/ljWNH5Ylmk+F9YZvViWBoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

import sys
import PySide6.QtSvg  # noqa: F401 — side-effect import; ensures Qt SVG plugin is bundled by PyInstaller

def get_app_icon_path() -> Path:
    """
    Retorna la ruta al archivo .ico de la aplicación.
    Soporta ejecución congelada con PyInstaller (sys._MEIPASS) y ejecución normal.
    Si el archivo no existe en disco, se reconstruye automáticamente
    a partir del contenido embebido en Base64.
    """
    # 1. Si se ejecuta como binario congelado con PyInstaller
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_dir = Path(sys._MEIPASS)
        for cand in [
            bundle_dir / "assets" / "app_icon.ico",
            bundle_dir / "assets" / "favicon.ico",
            bundle_dir / "app_icon.ico",
            bundle_dir / "favicon.ico"
        ]:
            if cand.is_file() and cand.stat().st_size > 0:
                return cand

    # 2. Búsqueda en assets local
    assets_dir = Path(__file__).parent.resolve() / "assets"
    for cand in [assets_dir / "app_icon.ico", assets_dir / "favicon.ico"]:
        if cand.is_file() and cand.stat().st_size > 0:
            return cand

    # 3. Reconstruir a partir de Base64 embebido si no se encuentra
    try:
        assets_dir.mkdir(parents=True, exist_ok=True)
        ico_path = assets_dir / "favicon.ico"
        ico_data = base64.b64decode(FAVICON_ICO_BASE64)
        ico_path.write_bytes(ico_data)
        return ico_path
    except Exception:
        temp_ico = Path(tempfile.gettempdir()) / "ros2_sim_launcher_favicon.ico"
        if not temp_ico.is_file() or temp_ico.stat().st_size == 0:
            try:
                temp_ico.write_bytes(base64.b64decode(FAVICON_ICO_BASE64))
            except Exception:
                pass
        return temp_ico


CHEVRON_DOWN_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAACXBIWXMAAA7EAAAOxAGVKw4bAAABR0lEQVRoge2WsU7CUBRAz9V/4Ac"
    "Mk6y4uhEGBwZkamKii5XvUVwcSBxEGB2UX5CJhE7IX7hyHaxKMMXb9nXynvnd985pXtOC4ziO4ziO4zj/FbEubHUvT0TkDkCR/nR8"
    "Mwkp0jq96gp6DaCqF9PJ7ZNlbs96QCpfA2qCjtq9OCqm+pt2L44EHX3vnz4oC+aA7TlVhiEi2r04UmVY1MU8pEgfWG/Olo3IkF+n"
    "Z5nYty58S16TeqO5Ajr8vDsCdOqN5mq5mM2te0G2vAhnL+PBg3UfcwDAcjGbh4jYJf/8OLjP45QrAMpHhJSHAgFQPCK0PBQMgPwRV"
    "chDiQCwR1Ql/3VYaXYJAlQlD4ECINcHKZg8lLxCm2Rcp22CykPAAPgzIrg8BA6AzIhK5KGCAPiMODg8SgQ5BnlX5DzP74HjOI7jOI"
    "7jOI6FD1tJ0NqY1t70AAAAAElFTkSuQmCC"
)


def get_dropdown_arrow_path(dark_mode: bool = False) -> Path:
    """
    Retorna la ruta al archivo de la flecha del dropdown (PNG o SVG).
    Soporta modo claro (flecha oscura #475569) y modo oscuro (flecha clara #cbd5e1).
    Soporta ejecución congelada con PyInstaller (sys._MEIPASS) y ejecución en script.
    """
    suffix = "_dark" if dark_mode else ""
    stroke_color = "#cbd5e1" if dark_mode else "#475569"

    # 1. PyInstaller frozen
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_dir = Path(sys._MEIPASS)
        for cand in [
            bundle_dir / "assets" / f"chevron_down{suffix}.svg",
            bundle_dir / "assets" / f"chevron_down{suffix}.png",
            bundle_dir / "assets" / "chevron_down.png",
            bundle_dir / "chevron_down.png"
        ]:
            if cand.is_file() and cand.stat().st_size > 0:
                return cand

    # 2. Assets local
    assets_dir = Path(__file__).parent.resolve() / "assets"
    svg_cand = assets_dir / f"chevron_down{suffix}.svg"
    if svg_cand.is_file() and svg_cand.stat().st_size > 0:
        return svg_cand

    # 3. Generar SVG vectorial de alta resolución en assets o tempdir
    svg_content = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
        f'<polyline points="6 9 12 15 18 9" fill="none" stroke="{stroke_color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )
    try:
        assets_dir.mkdir(parents=True, exist_ok=True)
        svg_cand.write_text(svg_content, encoding="utf-8")
        return svg_cand
    except Exception:
        temp_svg = Path(tempfile.gettempdir()) / f"ros2_sim_launcher_chevron_down{suffix}.svg"
        try:
            temp_svg.write_text(svg_content, encoding="utf-8")
            return temp_svg
        except Exception:
            # Fallback a PNG base64 original si falla escritura SVG
            return assets_dir / "chevron_down.png"


from typing import Optional

VECTOR_ICONS = {
    # Actions
    "media-playback-start": '<polygon points="5 3 19 12 5 21 5 3" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    "utilities-terminal": '<polyline points="4 17 10 11 4 5" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><line x1="12" y1="19" x2="20" y2="19" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>',
    "applications-internet": '<circle cx="12" cy="12" r="10" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="2" y1="12" x2="22" y2="12" stroke="{color}" stroke-width="2"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" fill="none" stroke="{color}" stroke-width="2"/>',
    "media-playback-stop": '<rect x="4.5" y="4.5" width="15" height="15" rx="2" ry="2" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    "view-refresh": '<polyline points="23 4 23 10 17 10" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><polyline points="1 20 1 14 7 14" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    "system-software-update": '<circle cx="12" cy="12" r="10" fill="none" stroke="{color}" stroke-width="2"/><polyline points="16 12 12 8 8 12" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><line x1="12" y1="16" x2="12" y2="8" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>',
    "process-working": '<line x1="12" y1="2" x2="12" y2="6" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/><line x1="12" y1="18" x2="12" y2="22" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/><line x1="2" y1="12" x2="6" y2="12" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/><line x1="18" y1="12" x2="22" y2="12" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>',

    # Tabs
    "document-properties": '<circle cx="12" cy="12" r="3" fill="none" stroke="{color}" stroke-width="2"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" fill="none" stroke="{color}" stroke-width="2"/>',
    "applications-development": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "applications-system": '<line x1="4" y1="21" x2="4" y2="14" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="4" y1="10" x2="4" y2="3" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="12" y1="21" x2="12" y2="12" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="12" y1="8" x2="12" y2="3" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="20" y1="21" x2="20" y2="16" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="20" y1="12" x2="20" y2="3" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="1" y1="14" x2="7" y2="14" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="9" y1="8" x2="15" y2="8" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="17" y1="16" x2="23" y2="16" stroke="{color}" stroke-width="2" stroke-linecap="round"/>',
    "help-browser": '<circle cx="12" cy="12" r="10" fill="none" stroke="{color}" stroke-width="2"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"/><line x1="12" y1="17" x2="12.01" y2="17" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>',

    # Tools and inner controls
    "document-open": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "go-down": '<line x1="12" y1="5" x2="12" y2="19" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/><polyline points="19 12 12 19 5 12" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    "edit-clear": '<circle cx="12" cy="12" r="10" fill="none" stroke="{color}" stroke-width="2"/><line x1="15" y1="9" x2="9" y2="15" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/><line x1="9" y1="9" x2="15" y2="15" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>',
    "emblem-documents": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="none" stroke="{color}" stroke-width="2"/><polyline points="14 2 14 8 20 8" fill="none" stroke="{color}" stroke-width="2"/><line x1="16" y1="13" x2="8" y2="13" stroke="{color}" stroke-width="2"/><line x1="16" y1="17" x2="8" y2="17" stroke="{color}" stroke-width="2"/>',
    "network-wired": '<rect x="2" y="2" width="20" height="8" rx="2" ry="2" fill="none" stroke="{color}" stroke-width="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2" fill="none" stroke="{color}" stroke-width="2"/><line x1="6" y1="6" x2="6.01" y2="6" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/><line x1="6" y1="18" x2="6.01" y2="18" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>',
    "accessories-character-map": '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><line x1="7" y1="7" x2="7.01" y2="7" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>',
    "user-trash": '<polyline points="3 6 5 6 21 6" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "window-close": '<line x1="18" y1="6" x2="6" y2="18" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/><line x1="6" y1="6" x2="18" y2="18" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>',
}


def _render_vector_icon(key: str, normal_color: str, selected_color: Optional[str] = None) -> "QtGui.QIcon":
    """
    Renderiza un SVG vectorial nítido a múltiples resoluciones (16..128px)
    para visualización perfecta en cualquier escala High-DPI.
    """
    from PySide6 import QtGui, QtCore, QtSvg

    body = VECTOR_ICONS[key]

    def make_pixmap(color: str, size: int) -> QtGui.QPixmap:
        svg_xml = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">{body.format(color=color)}</svg>'
        img = QtGui.QImage(size, size, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QtCore.Qt.GlobalColor.transparent)
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        svg_ren = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_xml.encode("utf-8")))
        svg_ren.render(p)
        p.end()
        return QtGui.QPixmap.fromImage(img)

    icon = QtGui.QIcon()
    for sz in (16, 20, 24, 32, 48, 64, 128):
        pm_norm = make_pixmap(normal_color, sz)
        icon.addPixmap(pm_norm, QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        icon.addPixmap(pm_norm, QtGui.QIcon.Mode.Active, QtGui.QIcon.State.Off)
        if selected_color:
            pm_sel = make_pixmap(selected_color, sz)
            icon.addPixmap(pm_sel, QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.On)
            icon.addPixmap(pm_sel, QtGui.QIcon.Mode.Active, QtGui.QIcon.State.On)
            icon.addPixmap(pm_sel, QtGui.QIcon.Mode.Selected, QtGui.QIcon.State.Off)
            icon.addPixmap(pm_sel, QtGui.QIcon.Mode.Selected, QtGui.QIcon.State.On)
        else:
            icon.addPixmap(pm_norm, QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.On)
            icon.addPixmap(pm_norm, QtGui.QIcon.Mode.Active, QtGui.QIcon.State.On)
            icon.addPixmap(pm_norm, QtGui.QIcon.Mode.Selected, QtGui.QIcon.State.Off)
            icon.addPixmap(pm_norm, QtGui.QIcon.Mode.Selected, QtGui.QIcon.State.On)

    return icon


def _tint_pixmap(pm: "QtGui.QPixmap", color_hex: str) -> "QtGui.QPixmap":
    from PySide6 import QtGui, QtCore
    tinted = QtGui.QPixmap(pm.size())
    tinted.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(tinted)
    p.drawPixmap(0, 0, pm)
    p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(tinted.rect(), QtGui.QColor(color_hex))
    p.end()
    return tinted


def get_themed_icon(
    name: str,
    color: Optional[str] = None,
    selected_color: Optional[str] = None,
    fallback_sp: Optional["QtWidgets.QStyle.StandardPixmap"] = None
) -> "QtGui.QIcon":
    """
    Retorna un icono moderno de alta resolución, renderizado vectorialmente (SVG)
    para evitar cualquier pixelación en monitores High-DPI (125%, 150%, 200%).
    Soporta colores personalizados y estados seleccionado/activo para pestañas.
    Si el icono no está en el catálogo vectorial, recurre a QIcon.fromTheme o QStyle.
    """
    if name in VECTOR_ICONS:
        normal_col = color if color else "#334155"
        return _render_vector_icon(name, normal_col, selected_color)

    from PySide6 import QtGui, QtWidgets

    base = QtGui.QIcon.fromTheme(name)
    if base.isNull():
        if fallback_sp is not None:
            app = QtWidgets.QApplication.instance()
            if app:
                return app.style().standardIcon(fallback_sp)
        return QtGui.QIcon()

    if not color and not selected_color:
        return base

    icon = QtGui.QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128):
        pm = base.pixmap(size, size)
        if pm.isNull():
            continue

        if color:
            normal_pm = _tint_pixmap(pm, color)
            icon.addPixmap(normal_pm, QtGui.QIcon.Mode.Normal)
        else:
            icon.addPixmap(pm, QtGui.QIcon.Mode.Normal)

        if selected_color:
            sel_pm = _tint_pixmap(pm, selected_color)
            icon.addPixmap(sel_pm, QtGui.QIcon.Mode.Selected)
            icon.addPixmap(sel_pm, QtGui.QIcon.Mode.Active)

    return icon


