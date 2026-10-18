# Copyright 2023 Clearpath Robotics, Inc. & Universidad Ramon Llull (La Salle URL)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Launch file para TurtleBot 4 en Gazebo SIN docking station.
# Elimina el dock en el mundo de simulación (empty) permitiendo
# giros y traslaciones 360° libres sin colisiones contra la base de carga.

import os

from ament_index_python.packages import get_package_share_directory
from irobot_create_common_bringup.namespace import GetNamespacedName
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace

ARGUMENTS = [
    DeclareLaunchArgument(
        "rviz",
        default_value="false",
        choices=["true", "false"],
        description="Start rviz.",
    ),
    DeclareLaunchArgument(
        "use_sim_time",
        default_value="true",
        choices=["true", "false"],
        description="use_sim_time",
    ),
    DeclareLaunchArgument(
        "model",
        default_value="standard",
        choices=["standard", "lite"],
        description="Turtlebot4 Model",
    ),
    DeclareLaunchArgument("namespace", default_value="", description="Robot namespace"),
    DeclareLaunchArgument(
        "localization",
        default_value="false",
        choices=["true", "false"],
        description="Whether to launch localization",
    ),
    DeclareLaunchArgument(
        "slam",
        default_value="false",
        choices=["true", "false"],
        description="Whether to launch SLAM",
    ),
    DeclareLaunchArgument(
        "nav2",
        default_value="false",
        choices=["true", "false"],
        description="Whether to launch Nav2",
    ),
    DeclareLaunchArgument(
        "world",
        default_value="empty",
        description="Simulation World (empty, wall, classroom)",
    ),
]

for pose_element in ["x", "y", "z", "yaw"]:
    ARGUMENTS.append(
        DeclareLaunchArgument(
            pose_element,
            default_value="0.0",
            description=f"{pose_element} component of the robot pose.",
        )
    )


def generate_launch_description():
    pkg_turtlebot4_ignition_bringup = get_package_share_directory(
        "turtlebot4_ignition_bringup"
    )
    pkg_turtlebot4_description = get_package_share_directory("turtlebot4_description")
    pkg_turtlebot4_viz = get_package_share_directory("turtlebot4_viz")
    pkg_turtlebot4_navigation = get_package_share_directory("turtlebot4_navigation")
    pkg_irobot_create_common_bringup = get_package_share_directory(
        "irobot_create_common_bringup"
    )
    pkg_irobot_create_ignition_bringup = get_package_share_directory(
        "irobot_create_ignition_bringup"
    )

    # Launch file paths
    ignition_launch = PathJoinSubstitution(
        [pkg_turtlebot4_ignition_bringup, "launch", "ignition.launch.py"]
    )
    robot_description_launch = PathJoinSubstitution(
        [pkg_turtlebot4_description, "launch", "robot_description.launch.py"]
    )
    turtlebot4_ros_ign_bridge_launch = PathJoinSubstitution(
        [pkg_turtlebot4_ignition_bringup, "launch", "ros_ign_bridge.launch.py"]
    )
    turtlebot4_node_launch = PathJoinSubstitution(
        [pkg_turtlebot4_ignition_bringup, "launch", "turtlebot4_nodes.launch.py"]
    )
    create3_nodes_launch = PathJoinSubstitution(
        [pkg_irobot_create_common_bringup, "launch", "create3_nodes.launch.py"]
    )
    create3_ignition_nodes_launch = PathJoinSubstitution(
        [pkg_irobot_create_ignition_bringup, "launch", "create3_ignition_nodes.launch.py"]
    )
    localization_launch = PathJoinSubstitution(
        [pkg_turtlebot4_navigation, "launch", "localization.launch.py"]
    )
    slam_launch = PathJoinSubstitution(
        [pkg_turtlebot4_navigation, "launch", "slam.launch.py"]
    )
    nav2_launch = PathJoinSubstitution(
        [pkg_turtlebot4_navigation, "launch", "nav2.launch.py"]
    )
    rviz_launch = PathJoinSubstitution(
        [pkg_turtlebot4_viz, "launch", "view_robot.launch.py"]
    )

    param_file_cmd = DeclareLaunchArgument(
        "param_file",
        default_value=PathJoinSubstitution(
            [pkg_turtlebot4_ignition_bringup, "config", "turtlebot4_node.yaml"]
        ),
        description="Turtlebot4 Robot param file",
    )

    namespace = LaunchConfiguration("namespace")
    use_sim_time = LaunchConfiguration("use_sim_time")
    world = LaunchConfiguration("world")
    x = LaunchConfiguration("x")
    y = LaunchConfiguration("y")
    z = LaunchConfiguration("z")
    yaw = LaunchConfiguration("yaw")
    model = LaunchConfiguration("model")
    turtlebot4_node_yaml_file = LaunchConfiguration("param_file")

    robot_name = GetNamespacedName(namespace, "turtlebot4")

    # 1. Ignition Gazebo simulation en el mundo seleccionado (sin dock)
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([ignition_launch]),
        launch_arguments=[
            ("world", world),
        ],
    )

    # 2. Spawn del robot directamente en el suelo plano (z=0.0) sin docking station
    spawn_robot_group_action = GroupAction(
        [
            PushRosNamespace(namespace),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([robot_description_launch]),
                launch_arguments=[("model", model), ("use_sim_time", use_sim_time)],
            ),
            Node(
                package="ros_ign_gazebo",
                executable="create",
                arguments=[
                    "-name",
                    robot_name,
                    "-x",
                    x,
                    "-y",
                    y,
                    "-z",
                    z,
                    "-Y",
                    yaw,
                    "-topic",
                    "robot_description",
                ],
                output="screen",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([turtlebot4_ros_ign_bridge_launch]),
                launch_arguments=[
                    ("model", model),
                    ("robot_name", robot_name),
                    ("dock_name", "standard_dock"),
                    ("namespace", namespace),
                    ("world", world),
                ],
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([turtlebot4_node_launch]),
                launch_arguments=[
                    ("model", model),
                    ("param_file", turtlebot4_node_yaml_file),
                ],
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([create3_nodes_launch]),
                launch_arguments=[("namespace", namespace)],
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([create3_ignition_nodes_launch]),
                launch_arguments=[
                    ("robot_name", robot_name),
                    ("dock_name", "standard_dock"),
                ],
            ),
            Node(
                name="rplidar_stf",
                package="tf2_ros",
                executable="static_transform_publisher",
                output="screen",
                arguments=[
                    "0",
                    "0",
                    "0",
                    "0",
                    "0",
                    "0.0",
                    "rplidar_link",
                    [robot_name, "/rplidar_link/rplidar"],
                ],
                remappings=[
                    ("/tf", "tf"),
                    ("/tf_static", "tf_static"),
                ],
            ),
            Node(
                name="camera_stf",
                package="tf2_ros",
                executable="static_transform_publisher",
                output="screen",
                arguments=[
                    "0",
                    "0",
                    "0",
                    "1.5707",
                    "-1.5707",
                    "0",
                    "oakd_rgb_camera_optical_frame",
                    [robot_name, "/oakd_rgb_camera_frame/rgbd_camera"],
                ],
                remappings=[
                    ("/tf", "tf"),
                    ("/tf_static", "tf_static"),
                ],
            ),
        ]
    )

    def setup_localization(context, *args, **kwargs):
        loc_val = LaunchConfiguration("localization").perform(context)
        if loc_val.lower() not in ("true", "1"):
            return []

        world_val = LaunchConfiguration("world").perform(context)
        map_path = os.path.join(pkg_turtlebot4_navigation, "maps", f"{world_val}.yaml")
        if os.path.isfile(map_path):
            return [
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource([localization_launch]),
                    launch_arguments=[
                        ("namespace", namespace),
                        ("use_sim_time", use_sim_time),
                        ("map", map_path),
                    ],
                )
            ]
        # Si el mundo no dispone de mapa YAML (ej. empty, wall), no lanzar AMCL
        return []

    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([slam_launch]),
        launch_arguments=[("namespace", namespace), ("use_sim_time", use_sim_time)],
        condition=IfCondition(LaunchConfiguration("slam")),
    )

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([nav2_launch]),
        launch_arguments=[("namespace", namespace), ("use_sim_time", use_sim_time)],
        condition=IfCondition(LaunchConfiguration("nav2")),
    )

    rviz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([rviz_launch]),
        launch_arguments=[("namespace", namespace), ("use_sim_time", use_sim_time)],
        condition=IfCondition(LaunchConfiguration("rviz")),
    )

    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(param_file_cmd)
    ld.add_action(gazebo)
    ld.add_action(spawn_robot_group_action)
    ld.add_action(OpaqueFunction(function=setup_localization))
    ld.add_action(slam)
    ld.add_action(nav2)
    ld.add_action(rviz)
    return ld
