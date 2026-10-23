# Desk Hub Robotec

Panel táctil con **Raspberry Pi 3 B y Nextion Enhanced de 7 pulgadas**: hora, clima, temporizadores, proyectos públicos de GitHub y música por Spotify Connect.

La Pi mantiene el estado, consulta internet y reproduce audio por su jack. Nextion dibuja la interfaz y envía toques mediante un adaptador USB–TTL CH340G.

## Funciones

- **Inicio:** reloj, fecha, temperatura e icono del clima.
- **Tiempo:** enfoque, descanso, temporizador ajustable y cronómetro; vista de cuenta grande con Pausar y Reiniciar.
- **Fuera:** duración, hora de regreso y carrusel de repositorios públicos. Al iniciar, bloquea y detiene Spotify.
- **Spotify:** portada, canción, artista, progreso, anterior/siguiente, pausa y volumen en pasos directos de diez puntos.
- **PIN:** seis dígitos configurados localmente; tres intentos fallidos suspenden el teclado treinta segundos.
- **Persistencia:** SQLite conserva las cuentas entre reinicios.

## Requisitos

| Elemento | Configuración de referencia |
|---|---|
| Raspberry Pi | Pi 3 Model B, Raspberry Pi OS Lite 64 bits, Debian Trixie |
| Pantalla | Nextion Enhanced **NX8048K070_011C**, 800 × 480 horizontal |
| Serial | USB–TTL CH340G, UART 8N1 sin control de flujo |
| Audio | Parlantes amplificados al jack de 3,5 mm de la Pi |
| Energía | Pi con fuente adecuada; Nextion con fuente externa de 5 V / 2 A y tierra común |
| Red | Wi-Fi o Ethernet para las integraciones |
| Música | Spotify Premium y credencial propia de Spotify Soloist |

El TFT incluido corresponde al modelo identificado **NX8048K070_011C**. Nextion Editor presenta la familia NX8048K070_011. No cargar en otra serie o resolución.

## Instalación

```sh
git clone https://github.com/GerardoDC14/desk-hub-robotec.git ~/desk-hub
cd ~/desk-hub
sudo apt update
sudo apt install python3 python3-pil pulseaudio pulseaudio-utils alsa-utils
python3 pin_setup.py
python3 robotec.py --self-test
```

Continúa con [Instalación y servicios](docs/INSTALACION.md), [Firmware Nextion](docs/NEXTION.md) y [Spotify y audio](docs/SPOTIFY.md). Esas guías cubren conexiones, permisos y arranque automático.

## Uso

Al encender aparece BLOQUEADO. Introduce tu PIN y pulsa Entrar; no se distribuye un PIN predeterminado. El panel reintenta la conexión si enciendes Nextion después de la Pi.

En **Tiempo**, selecciona Enfoque, Descanso, Temporizador o Cronómetro. Ajusta las cuentas con −5, −1, +1 o +5 minutos, entre cero y 24 horas. Iniciar amplía la cuenta; Pausar o Reiniciar regresa a los ajustes. Tiempo y Fuera comparten una cuenta regresiva: elegir una duración nueva sustituye la anterior. El cronómetro es independiente. No hay alarma sonora al terminar.

En **Fuera**, selecciona duración y pulsa Estoy fuera. Permanecen visibles la cuenta, hora de regreso y proyectos públicos. Se detiene Spotify y el acceso vuelve a exigir PIN. Una persona de confianza puede desbloquear mientras la cuenta continúa. Terminar la cuenta no desbloquea automáticamente.

Para escuchar música, desbloquea y selecciona **Desk Hub Robotec** en Dispositivos disponibles de Spotify. Controla desde teléfono o pantalla. Bloquear, iniciar Fuera o perder comunicación con la pantalla detiene el receptor.

Para desconectar, pulsa **Apagar** y confirma si habilitaste el permiso opcional, o ejecuta `sudo systemctl poweroff` por SSH. Espera al apagado antes de quitar energía; no cortes alimentación durante una carga TFT o escritura en microSD.

## Configuración y funcionamiento

`.env.example` permite seleccionar puerto serial, perfil público de GitHub, ubicación del clima y nombre del receptor. La configuración real, PIN, claves y SQLite permanecen fuera del repositorio. El PIN restringe el panel y la disponibilidad de Spotify; no sustituye la seguridad de SSH y de la red.

- [Arquitectura y límites](docs/ARQUITECTURA.md)
- [Diagnóstico](docs/DIAGNOSTICO.md)
- [Nextion: edición y actualización](docs/NEXTION.md)

`robotec.py` dibuja las vistas y procesa coordenadas de toque; `desk_hub.py` aporta UART, temporización, persistencia y consultas. El HMI editable y el TFT compilado están en `nextion/`. Modifica dibujo y zonas táctiles conjuntamente.

## Comprobaciones

```sh
python3 -m compileall -q .
python3 robotec.py --self-test
```

Los tests cubren temporización, restauración, tramas UART fragmentadas, bloqueo de Fuera, PIN y espera por intentos fallidos. El hardware de referencia validó UART a 115200, controles, reproducción y bloqueo de Spotify. Las rutas y servicios configurables requieren prueba de instalación en el equipo destino; los tests no verifican apagado físico ni ventilación.

El clima procede de [Open-Meteo](https://open-meteo.com/) y los proyectos de la API pública de GitHub. [Spotify Soloist](https://developer.spotify.com/documentation/soloist/reference/downloads-and-updates) se descarga por separado y conserva sus propios términos; no se incluyen ejecutables ni credenciales.
