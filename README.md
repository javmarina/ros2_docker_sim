# ROS 2 Jazzy Simulation Launcher

Herramienta de simulación y navegación con **ROS 2 Jazzy**, **Gazebo Sim** y **Navigation2 (Nav2)** para la asignatura de **Sistemas de Navegación**.

---

## 🚀 Requisitos Previos
1. **Python 3.10 o superior** (incluido en Windows).
2. **Docker Desktop** instalado y en ejecución con backend WSL 2.

---

## 💻 Inicio Rápido
Ejecuta en tu terminal (PowerShell, CMD o Terminal de Linux/macOS):

```bash
python launch_simulation.py
```

---

## 📁 Características
- **Interfaz moderna por tarjetas**: Configuración intuitiva de robots (TurtleBot 4, PAL Robotics TIAGo), mundos y modos de navegación (Nav2, SLAM Toolbox, teleoperación).
- **Espacio de Trabajo Persistente**: Monta tu carpeta de Windows automáticamente en `/ros2_ws/src` dentro del contenedor para desarrollar y compilar paquetes localmente.
- **Terminal Docker Nativa**: Acceso con un solo clic a la consola interactiva del contenedor con el entorno ROS 2 ya cargado (`source /opt/ros/jazzy/setup.bash`).
- **Escritorio Web Virtual (noVNC)**: Visualización fluida de Gazebo y RViz2 directamente desde el navegador web (`http://localhost:6080/vnc.html`) sin necesidad de configurar servidores X11.
- **Actualizaciones Automáticas**: Detección y descarga de nuevas versiones directamente desde GitHub.
