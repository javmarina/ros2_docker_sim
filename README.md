# ROS 2 Jazzy Simulation Launcher

Herramienta de simulación y navegación con **ROS 2 Jazzy**, **Gazebo Sim** y **Navigation2 (Nav2)** para la asignatura de **Sistemas de Navegación** (La Salle URL).

Construida con **PySide6 (Qt6)** para una interfaz moderna, nítida y desacoplada de dependencias locales.

---

## 🚀 Opciones de Ejecución

### Opción A. Ejecutable Independiente (Recomendada para Estudiantes)
No requiere tener instalado Python ni librerías locales:
1. Descarga el archivo **`ros2_sim_launcher.exe`** desde la sección [Releases de GitHub](https://github.com/javmarina/ros2_docker_sim/releases/latest).
2. Asegúrate de tener **Docker Desktop** iniciado.
3. Haz doble clic en `ros2_sim_launcher.exe`.
4. El launcher comprobará y descargará automáticamente nuevas versiones con un solo clic.

### Opción B. Ejecución desde Código Fuente (Modo Desarrollo)
1. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```
2. Inicia el launcher:
   ```bash
   python launch_simulation.py
   ```

---

## 🔨 Compilación Local del Ejecutable (.exe)

Para empaquetar el launcher en un único ejecutable independiente con PyInstaller:
```bash
pip install -r requirements.txt
pyinstaller --clean ros2_sim_launcher.spec
```
El archivo resultante se generará en la carpeta `dist/ros2_sim_launcher.exe`.

---

## 🔄 Integración Continua y Releases Automáticas (CI/CD)

El repositorio incluye un flujo de trabajo de **GitHub Actions** (`.github/workflows/build_and_release.yml`) que:
1. Se dispara automáticamente en cada `push` a la rama `main` o al crear etiquetas `v*`.
2. Compila el binario `ros2_sim_launcher.exe` en un entorno limpio de Windows.
3. Publica automáticamente el ejecutable en la release `latest`:
   `https://github.com/javmarina/ros2_docker_sim/releases/latest/download/ros2_sim_launcher.exe`
4. El actualizador integrado (`updater.py`) detecta la nueva versión en GitHub y permite al estudiante actualizar el ejecutable y reiniciarlo con un solo clic.

---

## 📁 Características del Launcher
- **Interfaz moderna PySide6**: Diseño estilo Slate con tarjetas, selección de robots (TurtleBot 4, PAL Robotics TIAGo), mundos y escenarios de simulación.
- **Espacio de Trabajo Persistente**: Monta automáticamente la carpeta de desarrollo de Windows en `/ros2_ws/src` dentro del contenedor con validación visual.
- **Consola con Colores ANSI**: Salida de logs de ROS 2 en vivo con auto-scroll inteligente y soporte completo de secuencias de escape ANSI.
- **Terminal Docker Nativa**: Abre Windows Terminal o PowerShell interactivo conectado al contenedor con el entorno ROS 2 listo para teleoperación.
- **Escritorio Web Virtual (noVNC)**: Visualización completa de Gazebo Sim y RViz2 en el navegador web (`http://localhost:6080/vnc.html`) sin servidores X11.
- **Mantenimiento y Comandos Rápidos**: Atajos para inspección (`ros2 topic list`, `ros2 node list`), compilación de paquetes con `colcon build` y gestión de caché de Docker.
