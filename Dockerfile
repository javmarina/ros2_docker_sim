# Dockerfile for University Course on Navigation and ROS 2 Jazzy
FROM osrf/ros:jazzy-desktop-full

ENV DEBIAN_FRONTEND=noninteractive
ENV RCUTILS_COLORIZED_OUTPUT=1

# Install Navigation2, SLAM Toolbox, TurtleBot4 dependencies, and Gazebo (ros_gz)
RUN echo "=== [1/3] Actualizando repositorios APT ===" && \
    apt-get update && \
    echo "=== [2/3] Instalando dependencias de ROS 2 y utilidades del sistema ===" && \
    apt-get install -y --no-install-recommends \
        --verbose-versions \
        -o Dpkg::Use-Pty=0 \
        ros-jazzy-navigation2 \
        ros-jazzy-nav2-bringup \
        ros-jazzy-slam-toolbox \
        ros-jazzy-robot-localization \
        ros-jazzy-turtlebot4-simulator \
        ros-jazzy-turtlebot4-gz-bringup \
        ros-jazzy-turtlebot4-gz-gui-plugins \
        ros-jazzy-turtlebot4-gz-toolbox \
        ros-jazzy-turtlebot4-navigation \
        ros-jazzy-turtlebot4-description \
        ros-jazzy-turtlebot4-viz \
        ros-jazzy-irobot-create-nodes \
        ros-jazzy-ros-gz \
        ros-jazzy-ros-gz-bridge \
        ros-jazzy-ros-gz-sim \
        ros-jazzy-ros-gz-interfaces \
        ros-jazzy-teleop-twist-keyboard \
        ros-jazzy-joint-state-publisher-gui \
        ros-jazzy-xacro \
        ros-jazzy-twist-mux \
        ros-jazzy-controller-manager \
        ros-jazzy-ros2-control \
        ros-jazzy-ros2-controllers \
        python3-colcon-common-extensions \
        python3-rosdep \
        x11-apps \
        mesa-utils \
        libgl1 \
        libglx-mesa0 \
        libgl1-mesa-dri \
        novnc \
        websockify \
        xvfb \
        x11vnc \
        openbox \
        nano \
        gedit \
        git \
        wget \
        curl \
        net-tools \
    && echo "=== [3/3] Limpiando cache de APT ===" \
    && rm -rf /var/lib/apt/lists/*

ENV ROBOT_MODEL=turtlebot4

# Launch file sin dock, mundos (SDF) y mapas (YAML/PNG) de la asignatura
COPY turtlebot4_nodock.launch.py /opt/ros/jazzy/share/turtlebot4_gz_bringup/launch/
COPY worlds/ /opt/ros/jazzy/share/turtlebot4_gz_bringup/worlds/
COPY maps/ /opt/ros/jazzy/share/turtlebot4_navigation/maps/
# Optimizaciones y parches para simulación:
# 1. Eliminar panel HMI innecesario en la GUI de Gazebo
# 2. Aumentar timeout del gestor de controladores a 120s para arranques pesados
# 3. Remapear /cmd_vel a Twist sin estampar (geometry_msgs/msg/Twist) para compatibilidad
#    directa con teleop estándar y nodos de alumnos (slalom_node, etc.)
RUN sed -i '/<plugin filename=.*Hmi/,/<\/plugin>/d' /opt/ros/jazzy/share/turtlebot4_gz_bringup/gui/*/gui.config && \
    sed -i "s/'--controller-manager-timeout', '30'/'--controller-manager-timeout', '120'/g" /opt/ros/jazzy/share/irobot_create_control/launch/include/control.py && \
    python3 -c "import pathlib; \
p1=pathlib.Path('/opt/ros/jazzy/share/irobot_create_common_bringup/launch/create3_nodes.launch.py'); \
p1.write_text(p1.read_text().replace(\"('/tf_static', 'tf_static')\", \"('/tf_static', 'tf_static'), ('cmd_vel', 'cmd_vel_stamped'), ('cmd_vel_unstamped', 'cmd_vel')\")); \
p2=pathlib.Path('/opt/ros/jazzy/share/irobot_create_gz_bringup/launch/create3_ros_gz_bridge.launch.py'); \
p2.write_text(p2.read_text().replace(\"([namespace, '/cmd_vel'], 'cmd_vel')\", \"([namespace, '/cmd_vel'], 'cmd_vel_stamped')\")); \
p3=pathlib.Path('/opt/ros/jazzy/share/turtlebot4_navigation/config/nav2.yaml'); \
p3.write_text(p3.read_text().replace('enable_stamped_cmd_vel: true', 'enable_stamped_cmd_vel: false'))"
LABEL org.nav_course.assets_digest="6cfabf7e6facf7c9"

EXPOSE 6080
WORKDIR /ros2_ws

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc \
    && echo "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi" >> /root/.bashrc

LABEL org.nav_course.dockerfile_hash="5f992a62221271a6"

CMD ["/bin/bash"]
