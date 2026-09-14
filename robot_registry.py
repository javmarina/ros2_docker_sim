"""
Registro declarativo y extensible de robots, mundos y escenarios de simulación.
Facilita la incorporación de nuevos robots o prácticas en la asignatura
sin necesidad de modificar la interfaz gráfica ni los servicios Docker.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable


@dataclass
class Scenario:
    """Representa un escenario o modo de ejecución de ROS 2 para un robot."""
    id: str
    name: str
    description: str


class RobotProfile:
    """Perfil de configuración y comandos de lanzamiento para un robot."""

    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        supported_worlds: List[str],
        scenarios: List[Scenario],
        command_builder: Callable[[str, str, str, bool], str]
    ):
        self.id = id
        self.name = name
        self.description = description
        self.supported_worlds = supported_worlds
        self.scenarios = scenarios
        self.command_builder = command_builder

    def get_scenario_by_id(self, scenario_id: str) -> Optional[Scenario]:
        target_id = "container_only" if scenario_id == "bash" else scenario_id
        for sc in self.scenarios:
            if sc.id == target_id:
                return sc
        return None

    def get_scenario_by_name(self, name: str) -> Optional[Scenario]:
        for sc in self.scenarios:
            if sc.name == name or name.startswith(sc.name):
                return sc
        if "bash" in name.lower():
            for sc in self.scenarios:
                if sc.id == "container_only":
                    return sc
        return None

    def build_command(self, scenario_id: str, world_name: str, extra_args: str = "", force_rebuild: bool = False) -> str:
        return self.command_builder(scenario_id, world_name, extra_args, force_rebuild)


# --- Generadores de comandos para robots específicos ---

def _build_env_prefix(force_rebuild: bool) -> str:
    force_val = "1" if force_rebuild else "0"
    return (
        "source /opt/ros/jazzy/setup.bash && "
        "if [ -d /ros2_ws/src/tiago_robot-humble-devel ]; then "
        f'  if [ "{force_val}" = "1" ] || [ ! -f /ros2_ws/install/setup.bash ]; then '
        '    echo "=== [1/2] Compilando paquetes del workspace con colcon ===" && '
        "    cd /ros2_ws && colcon build --symlink-install --packages-select tiago_description tiago_bringup tiago_controller_configuration tiago_robot; "
        "  else "
        '    echo "=== [1/2] Reutilizando compilación en caché (arranque instantáneo) ==="; '
        "  fi; "
        "fi && "
        "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi"
    )


def _build_container_only_command() -> str:
    return (
        "source /opt/ros/jazzy/setup.bash && "
        "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi && "
        'echo "=== Contenedor ROS 2 Jazzy listo en modo libre ===" && '
        'echo "Espacio de trabajo montado en: /ros2_ws/src" && '
        'echo "Servidor gráfico noVNC listo en: http://localhost:6080/vnc.html" && '
        'echo "Puedes abrir terminales interactivas o ejecutar tus propios comandos." && '
        "sleep infinity"
    )


def _build_turtlebot4_command(scenario_id: str, world_name: str, extra_args: str, force_rebuild: bool) -> str:
    env = _build_env_prefix(force_rebuild)
    args = extra_args.strip()

    if scenario_id == "nav2":
        return f"{env} && ros2 launch turtlebot4_gz_bringup turtlebot4_gz.launch.py world:={world_name} nav2:=true rviz:=true {args}"
    elif scenario_id == "slam":
        return f"{env} && ros2 launch turtlebot4_gz_bringup turtlebot4_gz.launch.py world:={world_name} slam:=true rviz:=true {args}"
    elif scenario_id == "sim_only":
        return f"{env} && ros2 launch turtlebot4_gz_bringup turtlebot4_gz.launch.py world:={world_name} {args}"
    elif scenario_id == "rviz2":
        return f"{env} && ros2 launch turtlebot4_viz view_robot.launch.py"
    elif scenario_id == "teleop":
        return f"{env} && ros2 run teleop_twist_keyboard teleop_twist_keyboard"
    else:  # "container_only", "bash"
        return _build_container_only_command()


def _build_tiago_command(scenario_id: str, world_name: str, extra_args: str, force_rebuild: bool) -> str:
    env = _build_env_prefix(force_rebuild)
    args = extra_args.strip()

    if scenario_id == "nav2":
        return (
            f"{env} && "
            f"ros2 launch tiago_description robot_state_publisher.launch.py {args} & "
            f"sleep 3 && "
            f"ros2 launch nav2_bringup navigation_launch.py use_sim_time:=true {args} & "
            f"sleep 2 && rviz2"
        )
    elif scenario_id == "slam":
        return (
            f"{env} && "
            f"ros2 launch tiago_description robot_state_publisher.launch.py {args} & "
            f"sleep 3 && "
            f"ros2 launch slam_toolbox online_async_launch.py use_sim_time:=true & "
            f"sleep 2 && rviz2"
        )
    elif scenario_id == "sim_only":
        return f"{env} && ros2 launch tiago_description show.launch.py {args}"
    elif scenario_id == "rviz2":
        return f"{env} && rviz2"
    elif scenario_id == "teleop":
        return f"{env} && ros2 run teleop_twist_keyboard teleop_twist_keyboard"
    else:  # "container_only", "bash"
        return _build_container_only_command()


def _build_generic_command(scenario_id: str, world_name: str, extra_args: str, force_rebuild: bool) -> str:
    env = (
        "source /opt/ros/jazzy/setup.bash && "
        "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi"
    )
    args = extra_args.strip()

    if scenario_id == "rviz2":
        return f"{env} && rviz2 {args}".strip()
    elif scenario_id == "teleop":
        return f"{env} && ros2 run teleop_twist_keyboard teleop_twist_keyboard {args}".strip()
    else:  # "container_only", "bash"
        return _build_container_only_command()


# --- Catálogo de Escenarios Comunes ---
STANDARD_SCENARIOS = [
    Scenario(
        id="nav2",
        name="Gazebo Sim + Nav2 (Navegación completa y RViz2)",
        description="Simulación completa en Gazebo con localización AMCL/Nav2, planificación global/local y visualización en RViz2."
    ),
    Scenario(
        id="slam",
        name="Gazebo Sim + SLAM Toolbox (Modo mapeo)",
        description="Generación de mapas en tiempo real con SLAM Toolbox mediante LIDAR y teleoperación."
    ),
    Scenario(
        id="sim_only",
        name="Solo simulación Gazebo",
        description="Ejecuta exclusivamente el simulador Gazebo con el robot en el mundo seleccionado."
    ),
    Scenario(
        id="rviz2",
        name="Solo visualización RViz2",
        description="Abre RViz2 con la descripción cinemática y modelo visual del robot."
    ),
    Scenario(
        id="teleop",
        name="Teleoperación por teclado",
        description="Control interactivo de velocidad lineal y angular (teleop_twist_keyboard)."
    ),
    Scenario(
        id="container_only",
        name="Solo contenedor (sin procesos / modo libre)",
        description="Inicia el contenedor Docker con el workspace montado y servidor noVNC activo, sin ningún nodo ni launch. Control total mediante terminal."
    ),
]


# --- Registro de Robots Disponibles ---
ROBOT_REGISTRY: Dict[str, RobotProfile] = {
    "turtlebot4": RobotProfile(
        id="turtlebot4",
        name="TurtleBot 4 (iRobot Create3)",
        description="Plataforma diferencial estándar de la asignatura con cámara OAK-D y LiDAR 2D.",
        supported_worlds=["warehouse", "depot", "maze", "empty"],
        scenarios=STANDARD_SCENARIOS,
        command_builder=_build_turtlebot4_command
    ),
    "tiago": RobotProfile(
        id="tiago",
        name="PAL Robotics TIAGo",
        description="Robot móvil de servicio con base móvil diferencial, columna telescópica y sensores.",
        supported_worlds=["warehouse", "depot", "maze", "empty"],
        scenarios=STANDARD_SCENARIOS,
        command_builder=_build_tiago_command
    ),
    "generic": RobotProfile(
        id="base",
        name="Entorno base ROS 2 (Sin robot específico)",
        description="Contenedor estándar con ROS 2 Jazzy y workspace montado, sin configuración de robot específico.",
        supported_worlds=["(No aplica)"],
        scenarios=[
            Scenario(
                id="container_only",
                name="Solo contenedor (sin procesos / modo libre)",
                description="Inicia el contenedor Docker con el workspace montado y servidor noVNC activo, sin ningún nodo ni launch. Control total mediante terminal."
            ),
            Scenario(
                id="rviz2",
                name="Solo visualización RViz2",
                description="Abre RViz2 en el entorno virtual noVNC para visualización de topics y modelos."
            ),
            Scenario(
                id="teleop",
                name="Teleoperación por teclado",
                description="Control interactivo de velocidad lineal y angular (teleop_twist_keyboard)."
            ),
        ],
        command_builder=_build_generic_command
    )
}


def get_all_robots() -> List[RobotProfile]:
    """Retorna la lista de todos los robots registrados."""
    return list(ROBOT_REGISTRY.values())


def get_robot_by_id(robot_id: str) -> Optional[RobotProfile]:
    """Busca un robot por su identificador clave."""
    if robot_id in ("base", "generic"):
        return ROBOT_REGISTRY.get("generic")
    return ROBOT_REGISTRY.get(robot_id)


def get_robot_by_name(name_str: str) -> Optional[RobotProfile]:
    """Busca un robot por coincidencia en el nombre o subcadena."""
    for r in ROBOT_REGISTRY.values():
        if (
            r.name == name_str
            or r.id in name_str.lower()
            or ("tiago" in name_str.lower() and r.id == "tiago")
            or ("base" in name_str.lower() and r.id == "base")
            or ("sin robot" in name_str.lower() and r.id == "base")
        ):
            return r
    return ROBOT_REGISTRY.get("turtlebot4")

