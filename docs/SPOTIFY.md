# Spotify Connect y audio

## Instalar Soloist

La integración utiliza Spotify Soloist, descargado por separado desde la [página oficial](https://developer.spotify.com/documentation/soloist/reference/downloads-and-updates). Para Raspberry Pi OS de 64 bits selecciona Linux AArch64. Extrae el ejecutable como `spotify/soloist` dentro del clon y dale permiso de ejecución:

```sh
mkdir -p spotify
chmod 700 spotify
chmod +x spotify/soloist
spotify/soloist --version
```

No subas el binario, sus archivos de sesión ni su caché al repositorio. Consulta dependencias y condiciones de uso en la documentación del proveedor. La integración de referencia se probó con Soloist 1.3.8.105; si cambia la CLI o su JSON, revisa `robotec.py`.

## Credencial local

Genera tu credencial en el [dashboard de Spotify Soloist](https://developer.spotify.com/dashboard/soloist). Para guardarla sin escribirla en el historial, desde la Pi ejecuta:

```sh
python3 - <<'PY'
import getpass, os
from pathlib import Path
directory = Path.home()/'.config/desk-hub'
directory.mkdir(parents=True, exist_ok=True)
directory.chmod(0o700)
key = getpass.getpass('Credencial Soloist: ').strip()
if not key:
    raise SystemExit('Credencial vacía')
path = directory/'soloist.key'
fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as file:
    file.write(key)
path.chmod(0o600)
PY
```

El lanzador comprueba permisos y la autorización temporal del panel. La API local escucha solo en `127.0.0.1:9090`; no abras ese puerto a la red. El nombre del receptor se configura con `DESK_HUB_DEVICE_NAME`.

## Jack y PulseAudio

Conecta parlantes amplificados al jack de la Pi. Inicia el audio del usuario y consulta las salidas:

```sh
systemctl --user enable --now pulseaudio.socket
pactl info
pactl list short sinks
```

Selecciona la salida analógica que exista realmente:

```sh
pactl set-default-sink NOMBRE_REAL_DE_LA_SALIDA
pactl set-sink-volume @DEFAULT_SINK@ 80%
```

No confundas ese nivel con el volumen de Spotify. Si no aparece el jack, comprueba la configuración de audio de Raspberry Pi OS y que esté habilitado `dtparam=audio=on`. Utiliza `alsamixer` para revisar silencios. El sonido debe estar disponible en la sesión del mismo usuario que ejecuta el receptor.

## Escuchar música

Con las unidades instaladas, desbloquea el panel y selecciona Desk Hub Robotec en Spotify desde un teléfono o PC en la misma red. Inicia una canción y entra en la pestaña Spotify de Nextion. Al bloquear o activar Fuera, el receptor se detiene y corta la reproducción. Puede tardar unos segundos en desaparecer de la lista de dispositivos del teléfono.

El PIN habilita el receptor completo, no una autorización por persona de Spotify Connect. Una vez desbloqueado, las conexiones se rigen por Spotify y la red local. Comparte el PIN solo con personas de confianza.

Para revisar problemas:

```sh
systemctl --user status desk-hub-spotify
journalctl --user -u desk-hub-spotify -n 30 --no-pager
spotify/soloist ctl -w 127.0.0.1:9090 now --json
```

La consulta CLI requiere el panel desbloqueado y Soloist activo. Si la compilación del reproductor ha expirado, actualízala siguiendo al proveedor. No reinicies manualmente el receptor para saltarte el bloqueo.

## Controles y presentación

Pausar y Reproducir utilizan el mismo tamaño de fuente. La barra es táctil para avanzar o retroceder; Aleatorio activa/desactiva mezcla, y Repetir recorre No, Lista y Tema. El indicador de barras es decorativo y no mide el sonido real. La posición se interpola localmente entre eventos; no requiere consultar Spotify por cada movimiento visual.

La portada usa vista rápida, refinamiento y caché en memoria. Volver a una canción conocida evita descargarla de nuevo, pero todavía hay que dibujarla en Nextion. El color y resolución son reducidos por el enlace UART. La API pública de [Soloist](https://developer.spotify.com/documentation/soloist/reference/websocket-api) no documenta letras de canciones; esta integración no las presenta.
