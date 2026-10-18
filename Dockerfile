# Dockerfile for University Course on Navigation and ROS 2 Humble
FROM osrf/ros:humble-desktop-full

ENV DEBIAN_FRONTEND=noninteractive
ENV RCUTILS_COLORIZED_OUTPUT=1

# Install Navigation2, SLAM Toolbox, TurtleBot4 dependencies, and Ignition Gazebo
RUN echo "=== [1/3] Actualizando repositorios APT ===" && \
    apt-get update && \
    echo "=== [2/3] Instalando dependencias de ROS 2 y utilidades del sistema ===" && \
    apt-get install -y --no-install-recommends \
        --verbose-versions \
        -o Dpkg::Use-Pty=0 \
        ros-humble-navigation2 \
        ros-humble-nav2-bringup \
        ros-humble-slam-toolbox \
        ros-humble-robot-localization \
        ros-humble-turtlebot4-simulator \
        ros-humble-turtlebot4-desktop \
        ros-humble-turtlebot4-navigation \
        ros-humble-turtlebot4-description \
        ros-humble-turtlebot4-viz \
        ros-humble-irobot-create-nodes \
        ros-humble-teleop-twist-keyboard \
        ros-humble-joint-state-publisher-gui \
        ros-humble-xacro \
        ros-humble-twist-mux \
        ros-humble-controller-manager \
        ros-humble-ros2-control \
        ros-humble-ros2-controllers \
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
COPY turtlebot4_nodock.launch.py /opt/ros/humble/share/turtlebot4_ignition_bringup/launch/
COPY worlds/ /opt/ros/humble/share/turtlebot4_ignition_bringup/worlds/
COPY maps/ /opt/ros/humble/share/turtlebot4_navigation/maps/
# Eliminar panel HMI innecesario en la GUI de Gazebo
RUN sed -i '/<plugin filename=.*Hmi/,/<\/plugin>/d' /opt/ros/humble/share/turtlebot4_ignition_bringup/gui/*/gui.config
LABEL org.nav_course.assets_digest="c567857cf0cb7b52"

EXPOSE 6080
WORKDIR /ros2_ws

RUN echo "source /opt/ros/humble/setup.bash" >> /root/.bashrc \
    && echo "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi" >> /root/.bashrc

LABEL org.nav_course.dockerfile_hash="92306713d4df0faf"

CMD ["/bin/bash"]
