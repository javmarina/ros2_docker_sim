"""
Registro declarativo y extensible de robots, mundos y escenarios de simulación.
Facilita la incorporación de nuevos robots o prácticas en la asignatura
sin necesidad de modificar la interfaz gráfica ni los servicios Docker.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

# El launch file sin dock, los mundos (worlds/) y los mapas (maps/) se copian a la imagen en el Dockerfile.
_MAPS_DIR = Path(__file__).parent / "maps"


def _build_camera_pose_cmd(world_enum: SimulationWorld) -> str:
    """Comando que ajusta la postura de la cámara GUI de Gazebo según el mundo."""
    if world_enum == SimulationWorld.CLASSROOM:
        cam_pose = "-2.5 10.5 9.0 0.0 0.675 -0.719"
    else:
        cam_pose = "-6 0 6 0 0.5 0"
    return (
        f"sed -i 's|<camera_pose>[^<]*</camera_pose>|<camera_pose>{cam_pose}</camera_pose>|' "
        "/opt/ros/humble/share/turtlebot4_ignition_bringup/gui/*/gui.config"
    )


# --- Enums para mayor robustez y extensibilidad futura ---


class SimulationWorld(str, Enum):
    """Mundos de simulación Gazebo soportados."""

    EMPTY = "empty"
    WALL = "wall"
    CLASSROOM = "classroom"
    NOT_APPLICABLE = "(No aplica)"

    @classmethod
    def all_simulation_worlds(cls) -> list[SimulationWorld]:
        """Retorna todos los mundos reales de simulación Gazebo (excluyendo NOT_APPLICABLE)."""
        return [w for w in cls if w != cls.NOT_APPLICABLE]

    @classmethod
    def has_map(cls, world: Any) -> bool:
        """Indica si el mundo cuenta con mapa YAML/PNG para localización Nav2."""
        val = world.value if isinstance(world, Enum) else str(world).strip().lower()
        map_yaml = _MAPS_DIR / f"{val}.yaml"
        return map_yaml.is_file() or val == cls.CLASSROOM.value

    @classmethod
    def is_valid(cls, val: Any) -> bool:
        """Verifica si un valor corresponde a un mundo registrado."""
        if isinstance(val, cls):
            return True
        val_str = str(val).strip().lower()
        return any(w.value.lower() == val_str for w in cls)

    @classmethod
    def from_str(
        cls, val: Any, default: SimulationWorld | None = None
    ) -> SimulationWorld:
        """Convierte una cadena a SimulationWorld con fallback seguro."""
        if default is None:
            default = cls.EMPTY
        if isinstance(val, cls):
            return val
        val_str = str(val).strip().lower()
        for w in cls:
            if w.value.lower() == val_str:
                return w
        return default


class ScenarioId(str, Enum):
    """Identificadores únicos de escenarios de ejecución."""

    CONTAINER_ONLY = "container_only"
    SIM_ONLY = "sim_only"
    RVIZ2 = "rviz2"
    NAV2 = "nav2"
    SLAM = "slam"
    TELEOP = "teleop"

    @classmethod
    def is_valid(cls, val: Any) -> bool:
        if isinstance(val, cls):
            return True
        val_str = str(val).strip().lower()
        return any(s.value.lower() == val_str for s in cls)

    @classmethod
    def from_str(cls, val: Any, default: ScenarioId | None = None) -> ScenarioId:
        if default is None:
            default = cls.CONTAINER_ONLY
        if isinstance(val, cls):
            return val
        val_str = str(val).strip().lower()
        for s in cls:
            if s.value.lower() == val_str:
                return s
        return default


class RobotId(str, Enum):
    """Identificadores únicos de perfiles de robot."""

    BASE = "base"
    TURTLEBOT4 = "turtlebot4"

    @classmethod
    def is_valid(cls, val: Any) -> bool:
        if isinstance(val, cls):
            return True
        val_str = str(val).strip().lower()
        if val_str == "generic":
            return True
        return any(r.value.lower() == val_str for r in cls)

    @classmethod
    def from_str(cls, val: Any, default: RobotId | None = None) -> RobotId:
        if default is None:
            default = cls.BASE
        if isinstance(val, cls):
            return val
        val_str = str(val).strip().lower()
        if val_str == "generic":
            return cls.BASE
        for r in cls:
            if r.value.lower() == val_str:
                return r
        return default


@dataclass
class Scenario:
    """Representa un escenario o modo de ejecución de ROS 2 para un robot."""

    id: str
    name: str
    description: str

    def __post_init__(self):
        if isinstance(self.id, Enum):
            self.id = self.id.value


class RobotProfile:
    """Perfil de configuración y comandos de lanzamiento para un robot."""

    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        supported_worlds: list[str],
        scenarios: list[Scenario],
        command_builder: Callable[[str, str, str, bool], str],
    ):
        self.id = id.value if isinstance(id, Enum) else id
        self.name = name
        self.description = description
        self.supported_worlds = supported_worlds
        self.scenarios = scenarios
        self.command_builder = command_builder

    def get_scenario_by_id(self, scenario_id: Any) -> Scenario | None:
        sc_val = (
            scenario_id.value if isinstance(scenario_id, Enum) else str(scenario_id)
        )
        target_id = ScenarioId.CONTAINER_ONLY.value if sc_val == "bash" else sc_val
        for sc in self.scenarios:
            if sc.id == target_id:
                return sc
        return None

    def get_scenario_by_name(self, name: str) -> Scenario | None:
        for sc in self.scenarios:
            if sc.name == name or name.startswith(sc.name):
                return sc
        if "bash" in name.lower():
            for sc in self.scenarios:
                if sc.id == ScenarioId.CONTAINER_ONLY.value:
                    return sc
        return None

    def build_command(
        self,
        scenario_id: str,
        world_name: str,
        extra_args: str = "",
        force_rebuild: bool = False,
    ) -> str:
        return self.command_builder(scenario_id, world_name, extra_args, force_rebuild)


# --- Generadores de comandos para robots específicos ---


def _build_env_prefix(force_rebuild: bool) -> str:  # noqa: ARG001 (kept for API symmetry)
    return (
        "source /opt/ros/humble/setup.bash && "
        "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi"
    )


def _build_container_only_command() -> str:
    return (
        "source /opt/ros/humble/setup.bash && "
        "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi && "
        'echo "=== Contenedor ROS 2 Humble listo en modo libre ===" && '
        'echo "Espacio de trabajo montado en: /ros2_ws/src" && '
        'echo "Servidor gráfico noVNC listo en: http://localhost:6080/vnc.html" && '
        'echo "Puedes abrir terminales interactivas o ejecutar tus propios comandos." && '
        "sleep infinity"
    )


def _build_turtlebot4_command(
    scenario_id: str, world_name: str, extra_args: str, force_rebuild: bool
) -> str:
    env = _build_env_prefix(force_rebuild)
    args = extra_args.strip()

    world_enum = SimulationWorld.from_str(world_name)
    actual_world = world_enum.value

    launch_file = "turtlebot4_nodock.launch.py"
    prefix = f"{env} && {_build_camera_pose_cmd(world_enum)}"

    sc_str = scenario_id.value if isinstance(scenario_id, Enum) else scenario_id

    # Spawn pose: en classroom, spawnear en el corredor despejado (x=1.5, y=1.5) si el usuario no especifica coordenadas
    launch_args = args
    if world_enum == SimulationWorld.CLASSROOM and "x:=" not in args and "y:=" not in args:
        launch_args = f"x:=1.5 y:=1.5 yaw:=0.0 {args}".strip()

    if sc_str == ScenarioId.NAV2.value:
        loc_part = (
            "localization:=true"
            if SimulationWorld.has_map(world_enum)
            else "slam:=true"
        )
        return f"{prefix} && ros2 launch turtlebot4_ignition_bringup {launch_file} world:={actual_world} nav2:=true {loc_part} rviz:=true {launch_args}".strip()
    elif sc_str == ScenarioId.SLAM.value:
        return f"{prefix} && ros2 launch turtlebot4_ignition_bringup {launch_file} world:={actual_world} slam:=true nav2:=true rviz:=true {launch_args}".strip()
    elif sc_str == ScenarioId.SIM_ONLY.value:
        return f"{prefix} && ros2 launch turtlebot4_ignition_bringup {launch_file} world:={actual_world} {launch_args}".strip()
    elif sc_str == ScenarioId.RVIZ2.value:
        return f"{env} && ros2 launch turtlebot4_viz view_robot.launch.py"
    elif sc_str == ScenarioId.TELEOP.value:
        extra = f"--ros-args {args.strip()}".strip() if args.strip() else ""
        return f"{env} && ros2 run teleop_twist_keyboard teleop_twist_keyboard {extra}".strip()
    else:  # ScenarioId.CONTAINER_ONLY, "bash"
        return _build_container_only_command()


def _build_generic_command(
    scenario_id: str, world_name: str, extra_args: str, force_rebuild: bool
) -> str:
    env = (
        "source /opt/ros/humble/setup.bash && "
        "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi"
    )
    args = extra_args.strip()
    sc_str = scenario_id.value if isinstance(scenario_id, Enum) else scenario_id

    if sc_str == ScenarioId.RVIZ2.value:
        return f"{env} && rviz2 {args}".strip()
    elif sc_str == ScenarioId.TELEOP.value:
        return f"{env} && ros2 run teleop_twist_keyboard teleop_twist_keyboard {args}".strip()
    else:  # ScenarioId.CONTAINER_ONLY, "bash"
        return _build_container_only_command()


# --- Catálogo de Escenarios Comunes ---
STANDARD_SCENARIOS = [
    Scenario(
        id=ScenarioId.CONTAINER_ONLY,
        name="Solo contenedor (sin procesos / modo libre)",
        description="Inicia el contenedor Docker con el workspace montado y servidor noVNC activo, sin ningún nodo ni launch. Control total mediante terminal.",
    ),
    Scenario(
        id=ScenarioId.SIM_ONLY,
        name="Solo simulación Gazebo",
        description="Ejecuta exclusivamente el simulador Gazebo con el robot en el mundo seleccionado.",
    ),
    Scenario(
        id=ScenarioId.RVIZ2,
        name="Solo visualización RViz2",
        description="Abre RViz2 con la descripción cinemática y modelo visual del robot.",
    ),
    Scenario(
        id=ScenarioId.NAV2,
        name="Gazebo Sim + Nav2 (Navegación completa y RViz2)",
        description="Simulación completa en Gazebo con localización AMCL/Nav2, planificación global/local y visualización en RViz2.",
    ),
    Scenario(
        id=ScenarioId.SLAM,
        name="Gazebo Sim + SLAM Toolbox (Modo mapeo)",
        description="Generación de mapas en tiempo real con SLAM Toolbox mediante LIDAR y teleoperación.",
    ),
    Scenario(
        id=ScenarioId.TELEOP,
        name="Teleoperación por teclado",
        description="Control interactivo de velocidad lineal y angular (teleop_twist_keyboard).",
    ),
]


# --- Registro de Robots Disponibles ---
ROBOT_REGISTRY: dict[str, RobotProfile] = {
    "generic": RobotProfile(
        id=RobotId.BASE,
        name="Entorno base ROS 2 (Sin robot específico)",
        description="Contenedor estándar con ROS 2 Humble y workspace montado, sin configuración de robot específico.",
        supported_worlds=[SimulationWorld.NOT_APPLICABLE.value],
        scenarios=[
            Scenario(
                id=ScenarioId.CONTAINER_ONLY,
                name="Solo contenedor (sin procesos / modo libre)",
                description="Inicia el contenedor Docker con el workspace montado y servidor noVNC activo, sin ningún nodo ni launch. Control total mediante terminal.",
            ),
            Scenario(
                id=ScenarioId.RVIZ2,
                name="Solo visualización RViz2",
                description="Abre RViz2 en el entorno virtual noVNC para visualización de topics y modelos.",
            ),
            Scenario(
                id=ScenarioId.TELEOP,
                name="Teleoperación por teclado",
                description="Control interactivo de velocidad lineal y angular (teleop_twist_keyboard).",
            ),
        ],
        command_builder=_build_generic_command,
    ),
    "turtlebot4": RobotProfile(
        id=RobotId.TURTLEBOT4,
        name="TurtleBot 4 (iRobot Create3)",
        description="Plataforma diferencial estándar de la asignatura con cámara OAK-D y LiDAR 2D.",
        supported_worlds=[w.value for w in SimulationWorld.all_simulation_worlds()],
        scenarios=STANDARD_SCENARIOS,
        command_builder=_build_turtlebot4_command,
    ),
}


def get_all_robots() -> list[RobotProfile]:
    """Retorna la lista de todos los robots registrados."""
    return list(ROBOT_REGISTRY.values())


def get_robot_by_id(robot_id: Any) -> RobotProfile | None:
    """Busca un robot por su identificador clave."""
    val = (
        robot_id.value if isinstance(robot_id, Enum) else str(robot_id).strip().lower()
    )
    if val in (RobotId.BASE.value, "generic"):
        return ROBOT_REGISTRY.get("generic")
    return ROBOT_REGISTRY.get(val)


def get_robot_by_name(name_str: str) -> RobotProfile | None:
    """Busca un robot por coincidencia en el nombre o subcadena."""
    for r in ROBOT_REGISTRY.values():
        if (
            r.name == name_str
            or r.id in name_str.lower()
            or ("base" in name_str.lower() and r.id == RobotId.BASE.value)
            or ("sin robot" in name_str.lower() and r.id == RobotId.BASE.value)
        ):
            return r
    return ROBOT_REGISTRY.get(RobotId.TURTLEBOT4.value)
