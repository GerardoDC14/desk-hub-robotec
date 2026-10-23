# Instalación y servicios

## Sistema y conexiones

Prepara Raspberry Pi OS Lite de 64 bits con SSH y red. `sudo nmtui` permite configurar Wi-Fi; no guardes contraseñas en este repositorio. Comprueba acceso por la IP Wi-Fi antes de retirar Ethernet.

```sh
sudo timedatectl set-timezone America/Mexico_City
```

Con las fuentes desconectadas, conecta:

| Nextion | Destino |
|---|---|
| TX | RX del USB–TTL |
| RX | TX del USB–TTL |
| GND | GND del adaptador y tierra común con la fuente de pantalla |
| +5 V | Fuente externa de pantalla de 5 V / 2 A |

Enchufa el adaptador al USB de la Pi. No alimentes la pantalla desde el pin VCC del TTL ni unas dos salidas de 5 V. Comprueba etiquetas y niveles del adaptador; el color del cable no determina su señal. Este procedimiento usa USB–TTL y no necesita modificar el UART GPIO ni `/boot/firmware`.

## Código, puerto y PIN

Ejecuta el bloque de instalación del README y después, como usuario normal:

```sh
sudo usermod -aG dialout "$USER"
ls -l /dev/serial/by-id/
mkdir -p ~/.config/desk-hub
chmod 700 ~/.config/desk-hub
cp .env.example ~/.config/desk-hub/environment
chmod 600 ~/.config/desk-hub/environment
nano ~/.config/desk-hub/environment
python3 pin_setup.py
```

Cierra sesión y vuelve a entrar para aplicar el grupo dialout. Selecciona el puerto real en `environment`: `/dev/ttyUSB0` puede cambiar. El PIN se pide dos veces sin mostrarlo, se almacena con sal y PBKDF2 y permisos 600. Reinicia el panel después de cambiarlo.

Configura `DESK_HUB_GITHUB_USER`, `DESK_HUB_LOCATION`, latitud, longitud y zona horaria del clima. La hora visible usa la zona horaria de Linux: ajústala también. El archivo `environment` lo leen los servicios; si ejecutas Python manualmente, exporta esas variables en tu terminal. No contiene contraseñas ni claves.

## Arranque automático

Prepara el firmware y, si vas a usar música, sigue [Spotify](SPOTIFY.md). Desde el repositorio, sin sudo:

```sh
python3 scripts/render_services.py
mkdir -p ~/.config/systemd/user
cp build/desk-hub-spotify.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user disable --now desk-hub-spotify.service
sudo loginctl enable-linger "$USER"
sudo cp build/desk-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now desk-hub.service
```

El generador utiliza el usuario, UID y ruta actuales. Utiliza rutas sin espacios; si mueves el clon, regenera las unidades. Spotify debe quedar **deshabilitado para el arranque**: el panel lo inicia al desbloquear y lo detiene al bloquear. Sin Soloist, las demás funciones siguen disponibles y la música queda no disponible.

```sh
systemctl is-active desk-hub
journalctl -u desk-hub -n 30 --no-pager
systemctl --user is-active desk-hub-spotify
```

Al arrancar debe aparecer PIN y Spotify debe estar inactivo. Al desbloquear, el receptor se activa; al iniciar Fuera se detiene. El teclado y las cuentas funcionan sin internet. El estado se guarda en `~/.local/share/desk-hub/state.sqlite3`.

## Permiso opcional de apagado

El botón ejecuta `sudo -n /usr/bin/systemctl poweroff`. Un administrador puede habilitarlo con `sudo visudo -f /etc/sudoers.d/desk-hub-poweroff`, añadiendo esta línea con el usuario local correcto:

```text
USUARIO_LOCAL ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff
```

Esto permite a ese usuario apagar sin contraseña. No concedas `NOPASSWD: ALL`. Sin ese permiso, utiliza SSH para apagar; el botón mostrará el fallo y volverá al bloqueo.
