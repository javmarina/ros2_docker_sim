"""
Servicio Docker para el Launcher de ROS 2 Jazzy.
Gestiona el ciclo de vida del contenedor, volúmenes, descarga/construcción de imágenes
y la apertura de terminales interactivas (Windows Terminal / PowerShell / CMD).
"""

import os
import re
import sys
import shutil
import socket
import logging
import platform
import subprocess
from pathlib import Path
from typing import Tuple, Callable, Optional, List

logger = logging.getLogger("docker_service")

DEFAULT_CONTAINER_NAME = "ros2_jazzy_nav_sim"
COURSE_IMAGE_NAME = "ros2-jazzy-nav-course:latest"
DEFAULT_NOVNC_PORT = 6080


class DockerService:
    """Encapsula todas las operaciones con el daemon de Docker y ejecución de procesos."""

    @staticmethod
    def get_host_os() -> str:
        system = platform.system().lower()
        if "darwin" in system:
            return "mac"
        elif "windows" in system:
            return "windows"
        return "linux"

    @staticmethod
    def get_host_ip() -> str:
        """Obtiene la IP local de la máquina anfitriona."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def check_docker_installed() -> Tuple[bool, str]:
        """Comprueba si el binario de docker está instalado y en el PATH."""
        try:
            res = subprocess.run(
                ["docker", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            if res.returncode == 0:
                return True, res.stdout.strip()
            return False, "Docker no está instalado o no se encuentra en el PATH."
        except FileNotFoundError:
            return False, "Docker no encontrado en el PATH del sistema."

    @staticmethod
    def check_docker_running() -> Tuple[bool, str]:
        """Comprueba si el servicio/daemon de Docker está activo."""
        try:
            res = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            if res.returncode == 0:
                return True, f"Docker activo (v{res.stdout.strip()})"
            err_msg = res.stderr.strip()
            if not err_msg:
                err_msg = "Docker Desktop no está en ejecución."
            return False, err_msg
        except Exception as e:
            return False, str(e)

    @staticmethod
    def is_container_running(container_name: str = DEFAULT_CONTAINER_NAME) -> bool:
        """Verifica si el contenedor especificado está actualmente en ejecución."""
        try:
            res = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            return bool(res.stdout.strip())
        except Exception:
            return False

    @staticmethod
    def is_image_available(image_name: str = COURSE_IMAGE_NAME) -> bool:
        """Verifica si la imagen existe localmente en Docker."""
        try:
            res = subprocess.run(
                ["docker", "image", "inspect", image_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            return res.returncode == 0
        except Exception:
            return False

    @staticmethod
    def stop_container(container_name: str = DEFAULT_CONTAINER_NAME) -> Tuple[bool, str]:
        """Detiene y elimina de forma inmediata el contenedor para evitar bloqueos."""
        logger.info("Deteniendo contenedor '%s'...", container_name)
        try:
            res = subprocess.run(
                ["docker", "rm", "-f", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            if res.returncode == 0:
                logger.debug("Contenedor '%s' detenido y eliminado.", container_name)
                return True, f"Contenedor '{container_name}' detenido correctamente."
            logger.debug("No había contenedor '%s' activo.", container_name)
            return True, "No había contenedor activo para detener."
        except Exception as e:
            logger.error("Error al detener contenedor '%s': %s", container_name, e, exc_info=True)
            return False, str(e)

    @staticmethod
    def clean_build_volumes() -> Tuple[bool, str]:
        """Elimina los volúmenes persistentes de caché de compilación de colcon."""
        logger.info("Eliminando volúmenes de caché ros2_jazzy_*...")
        try:
            volumes = ["ros2_jazzy_build_cache", "ros2_jazzy_install_cache", "ros2_jazzy_log_cache"]
            for v in volumes:
                subprocess.run(
                    ["docker", "volume", "rm", "-f", v],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False
                )
            logger.debug("Volúmenes de caché eliminados.")
            return True, "Caché de compilación eliminada correctamente."
        except Exception as e:
            logger.error("Error al limpiar volúmenes: %s", e, exc_info=True)
            return False, str(e)

    @classmethod
    def open_container_terminal(cls, container_name: str = DEFAULT_CONTAINER_NAME) -> Tuple[bool, str]:
        """
        Abre una terminal interactiva nativa conectada al contenedor con el entorno ROS 2 ya cargado.
        En Windows prioriza Windows Terminal (wt.exe), con fallback a PowerShell y CMD.
        """
        logger.info("Solicitud para abrir terminal interactiva en contenedor '%s'", container_name)
        if not cls.is_container_running(container_name):
            logger.warning("open_container_terminal: Contenedor '%s' no está corriendo", container_name)
            return False, f"El contenedor '{container_name}' no está en ejecución. Inicia la simulación primero."

        host_os = cls.get_host_os()
        # Comando para iniciar sesión con ROS 2 y workspace ya cargados
        bash_init = (
            "source /opt/ros/jazzy/setup.bash && "
            "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi && "
            "cd /ros2_ws && exec bash"
        )

        try:
            if host_os == "windows":
                # Intentar detectar Windows Terminal (wt.exe)
                wt_path = shutil.which("wt")
                if not wt_path:
                    # Comprobar ruta estándar en WindowsApps
                    local_appdata = os.getenv("LOCALAPPDATA", "")
                    candidate = Path(local_appdata) / "Microsoft" / "WindowsApps" / "wt.exe"
                    if candidate.exists():
                        wt_path = str(candidate)

                if wt_path:
                    # Iniciar nueva pestaña o ventana con Windows Terminal
                    wt_cmd = [
                        wt_path, "-w", "0", "nt",
                        "--title", f"ROS 2 Jazzy - {container_name}",
                        "docker", "exec", "-it", container_name,
                        "bash", "-c", bash_init
                    ]
                    subprocess.Popen(wt_cmd)
                    return True, "Terminal abierta en Windows Terminal."
                
                # Fallback: PowerShell nativo
                ps_path = shutil.which("powershell")
                if ps_path:
                    ps_cmd = (
                        f'start "ROS 2 Jazzy Terminal" powershell -NoExit -Command '
                        f'& {{ docker exec -it {container_name} bash -c "{bash_init}" }}'
                    )
                    subprocess.Popen(["cmd.exe", "/c", ps_cmd])
                    return True, "Terminal abierta en PowerShell."

                # Fallback final: CMD
                cmd_cmd = (
                    f'start "ROS 2 Jazzy Terminal" cmd /k '
                    f'docker exec -it {container_name} bash -c "{bash_init}"'
                )
                subprocess.Popen(["cmd.exe", "/c", cmd_cmd])
                return True, "Terminal abierta en Símbolo del sistema (CMD)."

            elif host_os == "mac":
                script = (
                    f'tell application "Terminal" to do script '
                    f'"docker exec -it {container_name} bash -c \\"{bash_init}\\""'
                )
                subprocess.Popen(["osascript", "-e", script])
                return True, "Terminal abierta en Terminal de macOS."

            else:
                # Linux: intentar emuladores de terminal comunes
                for term in ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"]:
                    term_path = shutil.which(term)
                    if term_path:
                        subprocess.Popen([
                            term_path, "-e",
                            f'docker exec -it {container_name} bash -c "{bash_init}"'
                        ])
                        return True, f"Terminal abierta en {term}."
                return False, "No se encontró ningún emulador de terminal compatible en el sistema."

        except Exception as e:
            return False, f"Error al abrir la terminal: {str(e)}"

    @staticmethod
    def execute_in_container_stream(
        container_name: str,
        command_str: str,
        log_cb: Callable[[str], None]
    ) -> Optional[subprocess.Popen]:
        """
        Ejecuta un comando no interactivo dentro del contenedor y transmite su salida.
        Útil para botones de comandos rápidos (ros2 topic list, colcon build, etc.).
        """
        full_cmd = (
            "source /opt/ros/jazzy/setup.bash && "
            "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi && "
            f"{command_str}"
        )
        docker_cmd = [
            "docker", "exec", container_name,
            "/bin/bash", "-c", full_cmd
        ]

        try:
            proc = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True
            )
            return proc
        except Exception as e:
            log_cb(f"Error al iniciar comando: {e}\n")
            return None

    @classmethod
    def build_docker_run_args(
        cls,
        image_name: str,
        container_name: str,
        ros_cmd: str,
        domain_id: str,
        robot_model: str,
        ws_path: str,
        web_port: str = "6080"
    ) -> List[str]:
        """
        Construye la lista de argumentos para ejecutar el contenedor de simulación
        garantizando un montaje de volúmenes seguro en Windows y variables de visualización virtual.
        """
        docker_cmd = [
            "docker", "run", "--rm",
            "-it",
            "--name", container_name,
            "-p", f"{web_port}:6080",
            "-e", f"ROS_DOMAIN_ID={domain_id}",
            "-e", f"ROBOT_MODEL={robot_model}",
            "-e", "RCUTILS_COLORIZED_OUTPUT=1",
            "-e", "DISPLAY=:99",
            "-e", "QT_X11_NO_MITSHM=1",
            "-e", "LIBGL_ALWAYS_SOFTWARE=1",
            "-e", "MESA_GL_VERSION_OVERRIDE=3.3",
            "-e", "GALLIUM_DRIVER=llvmpipe",
            "-e", "QT_QPA_PLATFORM=xcb",
            "-e", "OGRE_RTT_MODE=Copy",
            "-v", "ros2_jazzy_build_cache:/ros2_ws/build",
            "-v", "ros2_jazzy_install_cache:/ros2_ws/install",
            "-v", "ros2_jazzy_log_cache:/ros2_ws/log",
        ]

        # Montaje seguro del espacio de trabajo
        if ws_path and os.path.exists(ws_path):
            norm_path = Path(ws_path).resolve().as_posix()
            docker_cmd.extend(["-v", f"{norm_path}:/ros2_ws/src:rw"])

        # Comando interno de inicialización de display virtual + servidor noVNC + ROS2
        final_shell_cmd = (
            "Xvfb :99 -screen 0 1600x900x24 >/dev/null 2>&1 & "
            "sleep 1 && "
            "openbox >/dev/null 2>&1 & "
            "x11vnc -display :99 -forever -shared -nopw -rfbport 5900 >/dev/null 2>&1 & "
            "websockify --web=/usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 & "
            f"echo '=== Servidor Web noVNC listo en http://localhost:{web_port}/vnc.html ===' && "
            f"{ros_cmd}"
        )

        docker_cmd.append(image_name)
        docker_cmd.extend(["/bin/bash", "-c", final_shell_cmd])
        return docker_cmd

    @staticmethod
    def pull_image_stream(
        image_name: str,
        progress_cb: Callable[[float, str], None],
        log_cb: Callable[[str], None]
    ) -> Tuple[bool, str]:
        """Descarga una imagen de Docker analizando el progreso capa a capa."""
        cmd = ["docker", "pull", image_name]
        log_cb(f"Ejecutando: {' '.join(cmd)}\n")

        layers = {}
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True
            )

            for line in iter(process.stdout.readline, ''):
                clean_line = line.strip()
                if clean_line:
                    log_cb(clean_line + "\n")

                match = re.match(
                    r"^([a-f0-9]+):\s+([^\[]+)(?:\[.*?\]\s*([0-9\.]+)(?:kB|MB|GB)?/([0-9\.]+)(?:kB|MB|GB)?)?",
                    clean_line,
                    re.IGNORECASE
                )
                if match:
                    layer_id, status, cur_str, tot_str = match.groups()
                    status = status.strip()
                    if "complete" in status.lower() or "already exists" in status.lower():
                        layers[layer_id] = 100.0
                    elif cur_str and tot_str:
                        try:
                            cur_val = float(cur_str)
                            tot_val = float(tot_str)
                            if tot_val > 0:
                                layers[layer_id] = min(99.0, (cur_val / tot_val) * 100.0)
                        except ValueError:
                            pass

                if layers:
                    avg_progress = sum(layers.values()) / max(1, len(layers))
                    progress_cb(avg_progress, f"Descargando {image_name}... ({avg_progress:.1f}%)")
                else:
                    progress_cb(-1, f"Descargando {image_name}...")

            process.stdout.close()
            return_code = process.wait()
            if return_code == 0:
                progress_cb(100.0, f"Imagen '{image_name}' lista.")
                return True, "Descarga completada con éxito."
            else:
                progress_cb(0.0, "Fallo en la descarga.")
                return False, f"El proceso terminó con código {return_code}."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def build_image_stream(
        dockerfile_dir: str,
        tag_name: str,
        progress_cb: Callable[[float, str], None],
        log_cb: Callable[[str], None]
    ) -> Tuple[bool, str]:
        """Construye una imagen Docker a partir de un Dockerfile con estimación de progreso."""
        cmd = ["docker", "build", "-t", tag_name, dockerfile_dir]
        log_cb(f"Ejecutando: {' '.join(cmd)}\n")

        total_steps = 10
        current_step = 0

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True
            )

            for line in iter(process.stdout.readline, ''):
                clean_line = line.strip()
                if clean_line:
                    log_cb(clean_line + "\n")

                step_match = re.search(r"Step\s+(\d+)/(\d+)", clean_line, re.IGNORECASE)
                if step_match:
                    current_step = int(step_match.group(1))
                    total_steps = int(step_match.group(2))
                    pct = (current_step / total_steps) * 100.0
                    progress_cb(pct, f"Construyendo imagen - Paso {current_step}/{total_steps}...")
                elif clean_line.startswith("#"):
                    bk_match = re.search(r"\[(\d+)/(\d+)\]", clean_line)
                    if bk_match:
                        current_step = int(bk_match.group(1))
                        total_steps = int(bk_match.group(2))
                        pct = (current_step / total_steps) * 100.0
                        progress_cb(pct, f"BuildKit - Paso {current_step}/{total_steps}...")

            process.stdout.close()
            return_code = process.wait()
            if return_code == 0:
                progress_cb(100.0, f"Imagen '{tag_name}' construida con éxito.")
                return True, "Construcción completada."
            else:
                progress_cb(0.0, "Fallo en la construcción.")
                return False, f"La construcción finalizó con código {return_code}."
        except Exception as e:
            return False, str(e)
