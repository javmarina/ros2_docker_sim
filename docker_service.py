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
from typing import Tuple, Callable, Optional, List, Dict
from enum import Enum
import hashlib

logger = logging.getLogger("docker_service")

class DockerState(Enum):
    """Estados del ciclo de vida del servicio de Docker."""
    NOT_RUNNING = "NOT_RUNNING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"

    @property
    def is_running(self) -> bool:
        return self == DockerState.RUNNING

    @property
    def is_starting(self) -> bool:
        return self == DockerState.STARTING

    @property
    def is_not_running(self) -> bool:
        return self == DockerState.NOT_RUNNING


DEFAULT_CONTAINER_NAME = "ros2_jazzy_nav_sim"
DOCKERFILE_HASH_LABEL = "org.nav_course.dockerfile_hash"
COURSE_IMAGE_NAME = "ros2-jazzy-nav-course:latest"
DEFAULT_NOVNC_PORT = 6080
WIN32_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
WIN32_NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0


class DockerService:
    """Encapsula todas las operaciones con el daemon de Docker y ejecución de procesos."""

    DOCKERFILE_HASH_LABEL = DOCKERFILE_HASH_LABEL

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

    @classmethod
    def ensure_docker_in_path(cls) -> None:
        """
        Asegura que el ejecutable de docker esté disponible en PATH.
        Si no se encuentra (habitual en instalaciones per-user sin admin en Windows
        o consolas abiertas antes de la instalación), busca en las rutas estándar conocidas
        y añade dinámicamente la carpeta 'resources/bin' a os.environ['PATH'].
        """
        if shutil.which("docker"):
            return

        host_os = cls.get_host_os()
        if host_os == "windows":
            candidates_bin = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "DockerDesktop" / "resources" / "bin",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Docker" / "resources" / "bin",
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Docker" / "Docker" / "resources" / "bin",
                Path(r"C:\Program Files\Docker\Docker\resources\bin"),
                Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Docker" / "Docker" / "resources" / "bin",
                Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "DockerDesktop" / "resources" / "bin",
            ]
            for p in candidates_bin:
                if (p / "docker.exe").is_file():
                    logger.info("Auto-detectada ruta bin de Docker en Windows: %s. Añadiendo a PATH.", p)
                    os.environ["PATH"] = f"{p}{os.pathsep}{os.environ.get('PATH', '')}"
                    return

            # Si encontramos Docker Desktop.exe mediante registro u otras rutas, probar su subcarpeta resources/bin
            desktop_exe = cls.find_docker_desktop_path()
            if desktop_exe:
                fallback_bin = desktop_exe.parent / "resources" / "bin"
                if (fallback_bin / "docker.exe").is_file():
                    logger.info("Auto-detectada ruta bin de Docker desde Desktop.exe: %s. Añadiendo a PATH.", fallback_bin)
                    os.environ["PATH"] = f"{fallback_bin}{os.pathsep}{os.environ.get('PATH', '')}"
                    return

        elif host_os == "mac":
            mac_bins = [
                Path("/usr/local/bin"),
                Path("/opt/homebrew/bin"),
                Path("/Applications/Docker.app/Contents/Resources/bin"),
                Path.home() / ".docker" / "bin",
            ]
            for p in mac_bins:
                if (p / "docker").is_file():
                    os.environ["PATH"] = f"{p}:{os.environ.get('PATH', '')}"
                    return

    @classmethod
    def check_docker_installed(cls, timeout: float = 4.0) -> Tuple[bool, str]:
        """Comprueba si el binario de docker está instalado y en el PATH."""
        cls.ensure_docker_in_path()
        try:
            res = subprocess.run(
                ["docker", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=timeout,
                creationflags=WIN32_NO_WINDOW
            )
            if res.returncode == 0:
                return True, res.stdout.strip()
            return False, "Docker no está instalado o no se encuentra en el PATH."
        except subprocess.TimeoutExpired:
            return False, "Tiempo de espera agotado al verificar Docker en el PATH."
        except FileNotFoundError:
            return False, "Docker no encontrado en el PATH del sistema."
        except Exception as e:
            return False, str(e)

    @classmethod
    def check_docker_running(cls, timeout: float = 4.0) -> Tuple[bool, str]:
        """Comprueba si el servicio/daemon de Docker está activo."""
        cls.ensure_docker_in_path()
        try:
            res = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=timeout,
                creationflags=WIN32_NO_WINDOW
            )
            if res.returncode == 0:
                return True, f"Docker activo (v{res.stdout.strip()})"
            err_msg = res.stderr.strip()
            if not err_msg:
                err_msg = "Docker Desktop no está en ejecución."
            return False, err_msg
        except subprocess.TimeoutExpired:
            return False, "Tiempo de espera agotado al conectar con el daemon de Docker."
        except Exception as e:
            return False, str(e)

    @classmethod
    def is_docker_installed(cls, timeout: float = 4.0) -> bool:
        """Comprueba de forma rápida si Docker está instalado."""
        installed, _ = cls.check_docker_installed(timeout=timeout)
        return installed

    @classmethod
    def is_docker_running(cls, timeout: float = 4.0) -> bool:
        """Comprueba de forma rápida si el daemon de Docker está en ejecución."""
        running, _ = cls.check_docker_running(timeout=timeout)
        return running

    @classmethod
    def get_docker_state(cls, timeout: float = 4.0) -> DockerState:
        """Determina el estado actual de Docker como DockerState enum."""
        return DockerState.RUNNING if cls.is_docker_running(timeout=timeout) else DockerState.NOT_RUNNING

    @classmethod
    def find_docker_desktop_path(cls) -> Optional[Path]:
        """Busca la ruta del ejecutable de Docker Desktop en el sistema."""
        host_os = cls.get_host_os()
        if host_os == "windows":
            candidates = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "DockerDesktop" / "Docker Desktop.exe",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Docker" / "Docker Desktop.exe",
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Docker" / "Docker" / "Docker Desktop.exe",
                Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe"),
                Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Docker" / "Docker" / "Docker Desktop.exe",
                Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "DockerDesktop" / "Docker Desktop.exe",
            ]
            for p in candidates:
                if p.is_file():
                    return p

            # Buscar en PATH
            which_p = shutil.which("Docker Desktop.exe") or shutil.which("Docker Desktop")
            if which_p:
                p = Path(which_p)
                if p.is_file():
                    return p

            # Buscar ruta en el registro de Windows
            reg_cand = cls._find_docker_in_windows_registry()
            if reg_cand:
                return reg_cand

        elif host_os == "mac":
            mac_cand = Path("/Applications/Docker.app")
            if mac_cand.exists():
                return mac_cand

        return None

    @staticmethod
    def _find_docker_in_windows_registry() -> Optional[Path]:
        """Consulta directa en el registro de desinstalación de Windows."""
        try:
            import winreg
            sub_keys = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\DockerDesktop",
            ]
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for sub_key in sub_keys:
                    try:
                        with winreg.OpenKey(root, sub_key) as k:
                            loc, _ = winreg.QueryValueEx(k, "InstallLocation")
                            cand = Path(loc) / "Docker Desktop.exe"
                            if cand.is_file():
                                return cand
                    except OSError:
                        continue
        except Exception:
            pass
        return None

    @classmethod
    def start_docker_desktop(cls) -> Tuple[bool, str]:
        """
        Inicia Docker Desktop en el sistema anfitrión si no está corriendo.
        Retorna (éxito, mensaje).
        """
        running, _ = cls.check_docker_running(timeout=2.0)
        if running:
            return True, "Docker Desktop ya se encuentra en ejecución."

        host_os = cls.get_host_os()
        if host_os == "windows":
            exe_path = cls.find_docker_desktop_path()
            if not exe_path:
                return False, (
                    "No se encontró el ejecutable de Docker Desktop en las ubicaciones estándar.\n"
                    "Por favor comprueba que Docker Desktop esté instalado en tu sistema Windows."
                )

            logger.info("Iniciando Docker Desktop desde: %s", exe_path)
            try:
                # Usar os.startfile para ejecución no bloqueante desacoplada de la consola
                if hasattr(os, "startfile"):
                    os.startfile(str(exe_path))
                else:
                    subprocess.Popen([str(exe_path)], close_fds=True)
                logger.info("Comando de arranque de Docker Desktop enviado al sistema.")
                return True, "Arrancando Docker Desktop en Windows..."
            except Exception as e:
                logger.warning("Fallo al iniciar con startfile, intentando con Popen: %s", e)
                try:
                    subprocess.Popen([str(exe_path)], close_fds=True)
                    logger.info("Comando de arranque de Docker Desktop enviado vía Popen.")
                    return True, "Arrancando Docker Desktop en Windows..."
                except Exception as e2:
                    logger.error("Error al arrancar Docker Desktop: %s", e2, exc_info=True)
                    return False, f"No se pudo arrancar Docker Desktop: {e2}"

        elif host_os == "mac":
            try:
                subprocess.Popen(["open", "-a", "Docker"])
                return True, "Arrancando Docker en macOS..."
            except Exception as e:
                return False, f"Error al arrancar Docker en macOS: {e}"

        else:
            # Linux: intentar iniciar el servicio docker
            try:
                subprocess.Popen(["sudo", "systemctl", "start", "docker"])
                return True, "Iniciando servicio Docker (systemctl)..."
            except Exception as e:
                return False, f"Error al iniciar servicio Docker en Linux: {e}"


    @staticmethod
    def is_container_running(container_name: str = DEFAULT_CONTAINER_NAME, timeout: float = 3.0) -> bool:
        """Verifica si el contenedor especificado está actualmente en ejecución."""
        try:
            res = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=timeout,
                creationflags=WIN32_NO_WINDOW
            )
            return bool(res.stdout.strip())
        except Exception:
            return False

    @staticmethod
    def is_image_available(image_name: str = COURSE_IMAGE_NAME, timeout: float = 5.0) -> bool:
        """Verifica si la imagen existe localmente en Docker."""
        try:
            res = subprocess.run(
                ["docker", "image", "inspect", image_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=timeout,
                creationflags=WIN32_NO_WINDOW
            )
            return res.returncode == 0
        except Exception:
            return False

    @staticmethod
    def compute_dockerfile_hash(content: str) -> str:
        """
        Calcula un hash SHA256 determinista del contenido del Dockerfile.
        Normaliza saltos de línea (CRLF/LF) y descarta líneas en blanco
        y comentarios iniciales para evitar falsos positivos de reconstrucción.
        """
        normalized_lines = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(f"LABEL {DOCKERFILE_HASH_LABEL}"):
                continue
            normalized_lines.append(line)
        normalized_text = "\n".join(normalized_lines)
        return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def get_image_label(image_name: str, label_name: str, timeout: float = 5.0) -> Optional[str]:
        """Obtiene el valor de una etiqueta de metadatos de una imagen Docker."""
        try:
            cmd = [
                "docker", "inspect",
                "--format", f'{{{{index .Config.Labels "{label_name}"}}}}',
                image_name
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                creationflags=WIN32_NO_WINDOW
            )
            if result.returncode == 0:
                val = result.stdout.strip()
                if val and val != "<no value>":
                    return val
            return None
        except Exception:
            return None

    @classmethod
    def is_image_up_to_date(
        cls,
        image_name: str = COURSE_IMAGE_NAME,
        expected_hash: str = "",
        fallback_hash: Optional[str] = None
    ) -> bool:
        """
        Verifica si la imagen Docker local existe y contiene todas las capas esperadas.
        Comprueba la etiqueta de metadatos embebida en la imagen Docker
        o, alternativamente, el fallback_hash guardado en la configuración.
        """
        if not expected_hash:
            return cls.is_image_available(image_name)
        if not cls.is_image_available(image_name):
            return False

        # Comprobar etiqueta Docker de la imagen
        actual_label = cls.get_image_label(image_name, DOCKERFILE_HASH_LABEL)
        if actual_label and actual_label == expected_hash:
            return True

        # Fallback a hash persistido en la configuración local
        if fallback_hash and fallback_hash == expected_hash:
            return True
            

        return False

    @staticmethod
    def stop_container(container_name: str = DEFAULT_CONTAINER_NAME, timeout: float = 15.0) -> Tuple[bool, str]:
        """Detiene y elimina de forma inmediata el contenedor para evitar bloqueos."""
        logger.info("Deteniendo contenedor '%s'...", container_name)
        try:
            res = subprocess.run(
                ["docker", "rm", "-f", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=timeout,
                creationflags=WIN32_NO_WINDOW
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
    def clean_build_volumes(timeout: float = 10.0) -> Tuple[bool, str]:
        """Elimina los volúmenes persistentes de caché de compilación de colcon."""
        logger.info("Eliminando volúmenes de caché ros2_jazzy_*...")
        try:
            volumes = ["ros2_jazzy_build_cache", "ros2_jazzy_install_cache", "ros2_jazzy_log_cache"]
            for v in volumes:
                subprocess.run(
                    ["docker", "volume", "rm", "-f", v],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=timeout,
                    creationflags=WIN32_NO_WINDOW
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
        """
        logger.info("[Terminal] Solicitud recibida para abrir terminal interactiva en contenedor '%s'", container_name)
        running = cls.is_container_running(container_name)
        logger.info("[Terminal] Estado del contenedor '%s': running=%s", container_name, running)
        if not running:
            logger.warning("[Terminal] Contenedor '%s' no está corriendo", container_name)
            return False, f"El contenedor '{container_name}' no está en ejecución. Inicia la simulación primero."

        host_os = cls.get_host_os()
        logger.info("[Terminal] Sistema operativo detectado: %s", host_os)

        bash_init = (
            "source /opt/ros/jazzy/setup.bash && "
            "test ! -f /ros2_ws/install/setup.bash || source /ros2_ws/install/setup.bash && "
            "cd /ros2_ws && exec bash"
        )

        try:
            if host_os == "windows":
                # Al pasar la orden como string simple a subprocess.Popen, Python no introduce barras de escape (\")
                # con list2cmdline, permitiendo que 'start' reconozca correctamente el título y ejecute docker.
                cmd = f'cmd.exe /c start "ROS 2 Jazzy - {container_name}" docker exec -it {container_name} bash'
                logger.info("[Terminal] Comando a ejecutar en Windows: %s", cmd)
                proc = subprocess.Popen(cmd)
                logger.info("[Terminal] Proceso lanzado con éxito. PID: %s", proc.pid)
                return True, f"Terminal abierta en nueva ventana (PID: {proc.pid})."

            elif host_os == "mac":
                script = (
                    f'tell application "Terminal" to do script '
                    f'"docker exec -it {container_name} bash -c \\"{bash_init}\\""'
                )
                logger.info("[Terminal] Ejecutando osascript en macOS...")
                proc = subprocess.Popen(["osascript", "-e", script])
                logger.info("[Terminal] osascript lanzado con PID: %s", proc.pid)
                return True, "Terminal abierta en Terminal de macOS."

            else:
                # Linux: intentar emuladores de terminal comunes
                for term in ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"]:
                    term_path = shutil.which(term)
                    if term_path:
                        logger.info("[Terminal] Emulador Linux encontrado: %s", term_path)
                        proc = subprocess.Popen([
                            term_path, "-e",
                            f'docker exec -it {container_name} bash -c "{bash_init}"'
                        ])
                        logger.info("[Terminal] Terminal lanzada con PID: %s", proc.pid)
                        return True, f"Terminal abierta en {term}."
                logger.error("[Terminal] No se encontró ningún emulador de terminal compatible en Linux")
                return False, "No se encontró ningún emulador de terminal compatible en el sistema."

        except Exception as e:
            logger.exception("[Terminal] Excepción al intentar abrir la terminal: %s", e)
            return False, f"Error al abrir la terminal: {str(e)}"

    @classmethod
    def get_container_exec_args(cls, container_name: str, command_str: str) -> List[str]:
        """
        Construye la lista de argumentos para ejecutar un comando dentro del contenedor
        cargando de forma segura el entorno de ROS 2 y el workspace.
        """
        full_cmd = (
            "source /opt/ros/jazzy/setup.bash && "
            "test ! -f /ros2_ws/install/setup.bash || source /ros2_ws/install/setup.bash; "
            f"{command_str}"
        )
        return [
            "docker", "exec", container_name,
            "/bin/bash", "-c", full_cmd
        ]

    @classmethod
    def execute_in_container_stream(
        cls,
        container_name: str,
        command_str: str,
        log_cb: Callable[[str], None]
    ) -> Optional[subprocess.Popen]:
        """
        Ejecuta un comando no interactivo dentro del contenedor y transmite su salida.
        Útil para botones de comandos rápidos (ros2 topic list, colcon build, etc.).
        """
        docker_cmd = cls.get_container_exec_args(container_name, command_str)

        try:
            proc = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True,
                creationflags=WIN32_NO_WINDOW
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
            "--name", container_name,
            "-p", f"{web_port}:6080",
            "--ipc=host",
            "-e", f"ROS_DOMAIN_ID={domain_id}",
            "-e", f"ROBOT_MODEL={robot_model}",
            "-e", "RCUTILS_COLORIZED_OUTPUT=1",
            "-e", "PYTHONUNBUFFERED=1",
            "-e", "DISPLAY=:99",
            "-e", "QT_X11_NO_MITSHM=1",
            "-e", "LIBGL_ALWAYS_SOFTWARE=1",
            "-e", "MESA_GL_VERSION_OVERRIDE=3.3",
            "-e", "GALLIUM_DRIVER=llvmpipe",
            "-e", "QT_QPA_PLATFORM=xcb",
            "-e", "OGRE_RTT_MODE=Copy",
            "-v", "ros2_jazzy_gz_cache:/root/.gz",
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
            "rm -rf /dev/shm/fastrtps* >/dev/null 2>&1; "
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
                universal_newlines=True,
                creationflags=WIN32_NO_WINDOW
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
        log_cb: Callable[[str], None],
        labels: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str]:
        """Construye una imagen Docker a partir de un Dockerfile con estimación de progreso y caché inteligente."""
        cmd = ["docker", "build", "--progress=plain", "-t", tag_name]
        
        # Nota: Docker BuildKit aprovecha automáticamente la caché de capas local existente para la imagen.
        if labels:
            for k, v in labels.items():
                cmd.extend(["--label", f"{k}={v}"])

        cmd.append(dockerfile_dir)
        log_cb(f"Ejecutando: {' '.join(cmd)}\n")

        total_steps = 10
        current_step = 0

        def safe_log(text: str):
            try:
                log_cb(text)
            except Exception:
                pass

        def safe_progress(pct: float, text: str):
            try:
                progress_cb(pct, text)
            except Exception:
                pass

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True,
                creationflags=WIN32_NO_WINDOW
            )

            for line in iter(process.stdout.readline, ''):
                clean_line = line.strip()
                if clean_line:
                    safe_log(clean_line + "\n")

                step_match = re.search(r"Step\s+(\d+)/(\d+)", clean_line, re.IGNORECASE)
                if step_match:
                    current_step = int(step_match.group(1))
                    total_steps = int(step_match.group(2))
                    pct = (current_step / total_steps) * 100.0
                    safe_progress(pct, f"Construyendo imagen - Paso {current_step}/{total_steps}...")
                elif clean_line.startswith("#"):
                    bk_match = re.search(r"\[(\d+)/(\d+)\]", clean_line)
                    if bk_match:
                        current_step = int(bk_match.group(1))
                        total_steps = int(bk_match.group(2))
                        pct = (current_step / total_steps) * 100.0
                        safe_progress(pct, f"BuildKit - Paso {current_step}/{total_steps}...")
                    elif current_step > 0:
                        pct = (current_step / total_steps) * 100.0
                        if "===" in clean_line:
                            stage = clean_line.split("===")[1].strip() if len(clean_line.split("===")) > 1 else clean_line
                            safe_progress(pct, f"Paso {current_step}/{total_steps} - {stage}")
                        elif any(k in clean_line for k in ("Unpacking", "Setting up", "Preparing to unpack")):
                            tokens = clean_line.split()
                            pkg = tokens[-1].strip("().") if tokens else ""
                            safe_progress(pct, f"Paso {current_step}/{total_steps} - Instalando: {pkg}")
                        elif "Get:" in clean_line or "Fetch" in clean_line:
                            safe_progress(pct, f"Paso {current_step}/{total_steps} - Descargando paquetes...")

            process.stdout.close()
            return_code = process.wait()
            if return_code == 0:
                safe_progress(100.0, f"Imagen '{tag_name}' construida con éxito.")
                return True, "Construcción completada."
            else:
                safe_progress(0.0, "Fallo en la construcción.")
                return False, f"La construcción finalizó con código {return_code}."
        except Exception as e:
            return False, str(e)


# Inicialización: verificar e inyectar Docker en el PATH si está instalado en rutas estándar
DockerService.ensure_docker_in_path()

