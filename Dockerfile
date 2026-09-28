# Dockerfile for University Course on Navigation and ROS 2 Jazzy
FROM osrf/ros:jazzy-desktop-full

ENV DEBIAN_FRONTEND=noninteractive
ENV RCUTILS_COLORIZED_OUTPUT=1

# Install Navigation2, SLAM Toolbox, TurtleBot4, TIAGo dependencies, and Gazebo (ros_gz)
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

# Pre-descarga de modelos 3D de Gazebo Fuel para mundos de simulacion (Warehouse, Depot)
RUN /bin/bash -c "source /opt/ros/jazzy/setup.bash && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Warehouse' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Depot' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/MovAi/models/pallet_box_mobile' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/MovAi/models/shelf' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/MovAi/models/shelf_big' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Chair' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/CoffeeTable' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/FemaleVisitorSit' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/Jersey Barrier' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/MaleVisitorOnPhone' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/foldable_chair' || true && \
    gz fuel download -u 'https://fuel.gazebosim.org/1.0/plateau/models/Casual female' || true"

EXPOSE 6080
WORKDIR /ros2_ws

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc \
    && echo "if [ -f /ros2_ws/install/setup.bash ]; then source /ros2_ws/install/setup.bash; fi" >> /root/.bashrc

LABEL org.nav_course.dockerfile_hash="81d2493f0f8d6e63"

CMD ["/bin/bash"]
