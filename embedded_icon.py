"""
Icono nativo de la aplicación embebido en Base64.
Garantiza que el launcher sea 100% autónomo y funcione sin depender de rutas externas ni carpetas de descargas.
"""

import base64
import tempfile
from pathlib import Path

FAVICON_ICO_BASE64 = "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XfDzVV7/8lRf//JTX//xUWD/8VFg//BPYf/wT2H/701i/+9MYv/uS2P/7kpk/+1JZP/tSGT/7Edl/+xGZv/rRWb/60Rn/+pDZ//qQmj/6UBo/+lAaf/oPmn/6T5p8Ok9aS4AAAAAAAAAAAAAAAAAAAAAAAAAAP9AQAT1WF3Q9Fde//RWXv/zVV//81Rf//JTYP/yUmD/8VFh//FQYf/wT2L/8E5i/+9NY//vTGP/7kpk/+5KZP/tSGX/7Uhl/+xGZv/sRWb/60Rn/+tDZ//qQmj/6kFo/+lAaf/pP2n/6T1p0P9AgAQAAAAAAAAAAAAAAAAAAAAA9Vpck/VZXP/0WFz/9Fdd//NWXv/zVV7/8lNf//JTX//xUWD/8VFg//BPYf/wTmH/701i/+9MYv/uS2P/7kpj/+1JZP/tSGT/7Edl/+xGZf/rRWb/60Rm/+pCZ//qQmf/6UBo/+lAaP/oPmn/6D1qkwAAAAAAAAAAAAAAAPZbWzj2XFz/9ltc//VZXf/1WV3/9Fde//RXXv/1cnv//u3u//7u7//1dID/8VFh//FQYf/xVmj//ePm//719v/0hpb/7ktk/+5KZf/tSGX/+9Xc///7/P/2qbj/60Rn/+tDaP/qQmj/6kFp/+lAaf/pP2r/6EBpOAAAAAAAAAAA915bqPZcW//2W1v/9Vpc//VZXP/0WF3/9Fdd//7q6/////////////7w8f/xUWD/8VFg//m0u//////////////////uS2P/7kpk//J7j//////////////////rRWb/60Rn/+pDZ//qQmj/6UFo/+lAaf/oPmmoAAAAAPViWBr4X1r/915b//ddW//2W1z/9ltc//VZXf/1WV3/+8fJ/////////////M/S//JTYP/yUmD/9pKc/////////////e3v/+9NY//vTGP/8GB3/////////////////+xGZv/sRWb/60Rn/+tDZ//qQmj/6kFo/+lAaf/rO2wa+F9YZvhfWf/3Xlr/911a//ZcWv/2W1v/9Vpc//VZXP/0WF3/+rK1//qztv/zVV7/8lNf//JTX//xUWD/96Gp//m2vf/xXW7/701i/+9MYv/uS2P/9ZCg//i4w//waoH/7Edl/+xGZf/rRWb/60Rm/+pDZ//qQmf/6UBo/+k/aWb5Ylmk+WFZ//hgWv/4X1r/915b//ddW//2XFz/9ltc//VZXf/1WV3/9Fde//RXXv/zVV//81Rf//JTYP/yUmD/8VFh//FQYf/wT2L/8E5j/+9NY//vTGP/7ktk/+5KZf/tSGX/7Uhl/+xGZv/sRmf/60Rn/+tDaP/qQmj/60FopPljWNH5Ylj/+GBZ//hgWf/3Xlr/911a//ZcW//2W1v/9Vpc//VZXP/0WF3/9Fdd//NWXv/zVV7/8lRf//JTX//xUWD/8VFg//BPYf/wT2H/701i/+9MYv/uS2P/7kpk/+1JZP/tSGT/7Edl/+xGZv/rRWb/60Rn/+pDZ//qQmjR+mRX7/pjWP/5Ylj/+WFZ//hgWf/4X1r/915b//ddW//3Zmb//NHR//zR0//2aGz/9Fde//RWXv/zVV//+8bK//zW2f/1d4L/8VFh//FQYf/wT2L/+brB//za3//0hpX/7kpk/+5KZP/tSGX/7Uhl/+xGZv/sRWb/60Rn/+tDZ+/6ZFb/+mRX//liV//5Ylj/+GBY//hfWf/3Xlr/911a//3e3f////////////3m5v/0WFz/9Fdd//morP/////////////9/f/xUWD/8VFg//Nxf//////////////////uS2P/7kpj/+1JZP/tSGT/7Edl/+xGZf/rRWb/60Rm//tmV//7ZVf/+mRY//pjWP/5Yln/+WFZ//hgWv/4X1r//d7e/////////////ubm//VZXf/1WV3/+ams//////////////39//JTYP/yUmH/9HJ//////////////////+9NY//vTGP/7ktk/+5KZf/tSGX/7Uhm/+xGZv/sRmf/+2ZV7/tmVv/6ZVf/+mRX//liWP/5Ylj/+GBZ//hgWf/4aWX//dHQ//3S0v/3amr/9Vpc//VZXP/0WF3/+8fJ//zX2P/2eYD/8lRf//JTX//xUWD/+rvB//za3v/1iJT/701i/+9MYv/uS2P/7kpk/+1JZP/tSGX/7Edl/+xGZe/7aFXR/GdW//tmVv/7ZVf/+mRX//pjWP/5Yln/+WFZ//hgWf/4X1r/915b//ddW//2W1z/9ltc//VZXf/1WV3/9Fde//RWXv/zVV//81Rf//JTYP/yUmD/8VFh//FQYf/wT2L/8E5i/+9NY//vTGP/7kpk/+5KZP/tSGX/7Uhl0fxoVKT8aFX/+2dV//tmVv/6ZFb/+mRX//liWP/5Ylj/+GBY//hfWf/3Xlr/911a//ZcWv/2W1v/9Vpc//VZXP/0WF3/9Fdd//NWXv/zVV7/8lNf//JTX//xUWD/8VFg//BPYf/wTmH/701i/+9MYv/uS2P/7kpj/+1JZP/sSGWk/WxVZv1qVf/8aFb//GdW//tmV//7ZVf/+mRY//pjWP/5Yln//Lez//y3tf/4X1r/915b//ddW//2XFz/+qan//u6vP/2Z2r/9Fde//RXXv/zVV//+Jad//q8wf/0c37/8VFh//FQYf/wT2L/8E5j/+9NY//vTGP/7ktk/+5LZGb/bFga/WpU//xpVf/8aFX/+2dW//tmVv/6ZVf/+mRX//3Lx/////////////3S0P/3Xlr/911a//mZmP////////////7u7v/0WF3/9Fdd//Rrcv/////////////////xUWD/8VFg//BPYf/wT2H/701i/+9MYv/uS2P/605iGgAAAAD9bFOo/WpU//1pVf/8aFX//GdW//tmVv/7ZVf//uzr/////////////vHx//hgWf/4X1r//Lq5//////////////////VZXf/1WV3/94WK//////////////////JTYP/yUmD/8VFh//FQYf/wT2L/8E5i//BMY6gAAAAAAAAAAP9tUjj9a1P//WpU//xpVP/8aFX/+2dV//tmVv/7f3P//u/t//7w7//6gXn/+GBY//hfWf/3ZGD//uXk///29v/5kJD/9Vpc//VZXP/0WFz//dna///8/P/5sLT/8lNf//JTX//xUWD/8VFg//BPYf/wTmH/8U1gOAAAAAAAAAAAAAAAAP1tU5P+bFT//WpV//1qVf/8aFb//GhW//tmV//7ZVf/+mRY//pjWP/5Yln/+WFZ//hgWv/4X1r/915b//ddW//2XFz/9ltc//VZXf/1WV3/9Fde//RXXv/zVV//81Rf//JTYP/yUmH/8VFh//FQYZMAAAAAAAAAAAAAAAAAAAAA/4BABP5sU9D9a1T//WpU//xpVf/8aFX/+2dW//tmVv/6ZVf/+mRX//liWP/5Ylj/+GBZ//hgWf/3Xlr/911a//ZcW//2W1v/9Vpc//VZXP/0WF3/9Fdd//NWXv/zVV7/8lRf//JTX//yUWDQ/0CABAAAAAAAAAAAAAAAAAAAAAAAAAAA/29TLv5sU/D+bFT//WpU//1qVf/8aFX//GdW//tmVv/7ZVf/+mRX//pjWP/5Yln/+WFZ//hgWf/4X1r/915b//ddW//2W1z/9ltc//VZXf/1WV3/9Fde//RWXv/zVV//81Rg8PRTXi4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/25RPP5sU/D9a1P//WpU//xpVP/8aFX/+2dV//tmVv/6ZFb/+mRX//liWP/5Ylj/+GBY//hfWf/3Xlr/911a//ZcWv/2W1v/9Vpc//VZXP/0WF3/9Fdd//NWXfDyVV08AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/29TLv5tU9D+bFT//WpU//1qVf/8aFb//GdW//tmV//7ZVf/+mRY//pjWP/5Yln/+WFZ//hgWv/4X1r/915b//ddW//2XFz/9ltc//VZXf/1WF3Q9FleLgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/4BABP1sU5P9a1P//WpU//xpVf/8aFX/+2dW//tmVv/6ZVf/+mRX//liWP/5Ylj/+GBZ//hgWf/3Xlr/911a//ZcW//2W1v/9Vpck/9AQAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP9tUjj9bFOo/WpU//1pVf/8aFX//GdW//tmVv/7ZVf/+mRX//pjWP/5Ylj/+WFZ//hgWf/4X1r/915bqPZbWzgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/bFga/WlVZvxoVKT7aFXR+2ZV7/tmVv/6ZFb/+mNX7/ljWNH5Ylmk+F9YZvViWBoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

import sys

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

