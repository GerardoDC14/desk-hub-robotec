# Desk Hub Robotec

Panel táctil con **Raspberry Pi 3 B y Nextion Enhanced de 7 pulgadas**: hora, clima, temporizadores, proyectos públicos de GitHub y música por Spotify Connect.

La Pi mantiene el estado, consulta internet y reproduce audio por su jack. Nextion dibuja la interfaz y envía toques mediante un adaptador USB–TTL CH340G.

![Inicio con tarjetas redondeadas](docs/images/home.png)

Vista reconstruida desde los comandos de dibujo, con datos de demostración y tipografía aproximada. La tipografía física es la incorporada en el HMI.

## Funciones

- **Inicio:** reloj, fecha, temperatura e icono del clima.
- **Tiempo:** Temporizador con presets de Enfoque/Descanso, Cronómetro con reloj analógico y vueltas, y Alarma local de una ejecución.
- **Fuera:** duración, hora de regreso y carrusel de repositorios públicos. Al iniciar, bloquea y detiene Spotify.
- **Spotify:** portada progresiva, canción, artista, contexto, siguiente tema, avance al tocar la barra, aleatorio, repetición y volumen directo. Controles con tipografía estable y animación por cambios parciales.
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

En **Tiempo**, elige Temporizador, Cronómetro o Alarma. El temporizador reúne presets de 5 minutos de descanso, 25 de enfoque, 45 y 60 minutos, además de ajustes −5, −1, +1 y +5. Iniciar amplía la cuenta; Pausar o Reiniciar regresa a los ajustes. Tiempo y Fuera comparten una cuenta regresiva: elegir una duración nueva sustituye la anterior. El cronómetro es independiente y conserva las cinco últimas vueltas.

La **Alarma** se activa para la próxima ocurrencia de una hora local y suena una vez. Puedes probar el sonido, desactivarla o posponer cinco minutos cuando aparece el aviso. El temporizador también avisa al finalizar. Los avisos no desbloquean el panel ni activan Spotify. La Pi debe estar encendida y el servicio activo; no es un despertador que arranque la Pi apagada. Consulta [Tiempo y avisos](docs/TIEMPO.md).

En **Fuera**, selecciona duración y pulsa Estoy fuera. Permanecen visibles la cuenta, hora de regreso y proyectos públicos. Se detiene Spotify y el acceso vuelve a exigir PIN. Una persona de confianza puede desbloquear mientras la cuenta continúa. Terminar la cuenta no desbloquea automáticamente.

Para escuchar música, desbloquea y selecciona **Desk Hub Robotec** en Dispositivos disponibles de Spotify. Toca la barra para saltar a una posición, y usa Aleatorio o Repetir según prefieras. El nombre de la lista y el siguiente tema aparecen cuando Soloist los proporciona. Controla desde teléfono o pantalla. Bloquear, iniciar Fuera o perder comunicación con la pantalla detiene el receptor.

Para desconectar, pulsa **Apagar** y confirma si habilitaste el permiso opcional, o ejecuta `sudo systemctl poweroff` por SSH. Espera al apagado antes de quitar energía; no cortes alimentación durante una carga TFT o escritura en microSD.

## Configuración y funcionamiento

`.env.example` permite seleccionar puerto serial, perfil público de GitHub, ubicación del clima y nombre del receptor. La configuración real, PIN, claves y SQLite permanecen fuera del repositorio. El PIN restringe el panel y la disponibilidad de Spotify; no sustituye la seguridad de SSH y de la red.

- [Arquitectura y límites](docs/ARQUITECTURA.md)
- [Diagnóstico](docs/DIAGNOSTICO.md)
- [Nextion: edición y actualización](docs/NEXTION.md)

`soft_ui.py` aporta tarjetas redondeadas, iconos nativos y actualizaciones por diferencias. `dashboard_views.py` y `dashboard_state.py` gestionan herramientas y alarmas. `music_client.py` recibe eventos de Soloist. `robotec.py` dibuja las vistas y procesa coordenadas de toque; `desk_hub.py` aporta UART, temporización, persistencia y consultas. El HMI editable y el TFT compilado están en `nextion/`. Modifica dibujo y zonas táctiles conjuntamente.

## Comprobaciones

```sh
python3 -m compileall -q .
python3 robotec.py --self-test
python3 -m unittest discover -s tests -v
```

Los tests cubren temporización, restauración, tramas UART, PIN, bloqueo, alarmas, posposición, avance musical, vueltas, conservación de píxeles al actualizar barras e imágenes y estabilización de la tipografía. El hardware de referencia validó UART a 115200, controles, reproducción y bloqueo de Spotify. Las rutas y servicios configurables requieren prueba de instalación en el equipo destino; los tests no verifican apagado físico ni ventilación.

El clima procede de [Open-Meteo](https://open-meteo.com/) y los proyectos de la API pública de GitHub. [Spotify Soloist](https://developer.spotify.com/documentation/soloist/reference/downloads-and-updates) se descarga por separado y conserva sus propios términos; no se incluyen ejecutables ni credenciales.
