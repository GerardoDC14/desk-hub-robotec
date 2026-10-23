# Diagnóstico

## La pantalla no responde

Comprueba primero alimentación, GND común, TX/RX cruzados y existencia del puerto. Detén el servicio antes de abrir el puerto manualmente. El TFT arranca a 9600 y el panel lo cambia a 115200; reiniciar solo el servicio no reinicia la velocidad de Nextion.

```sh
ls -l /dev/serial/by-id/
id
systemctl status desk-hub
journalctl -u desk-hub -n 40 --no-pager
```

Si falta `dialout`, corrige el grupo y vuelve a iniciar sesión. Para aislar UART y lógica, utiliza el firmware y script de [diagnóstico mínimo](NEXTION.md). Un loopback requiere desconectar Nextion y unir TX/RX del adaptador con las fuentes apagadas antes de cambiar cables; no unas alimentación con señales.

## Spotify no aparece o no suena

Desbloquea primero. Comprueba el ejecutable, clave local con permisos 600, unidad del usuario, red y salida de audio. El receptor debe estar inactivo mientras el panel está bloqueado. Consulta [Spotify y audio](SPOTIFY.md). Revisa el log si el reproductor requiere actualización; no publiques claves ni sesiones al pedir ayuda.

## Fuente, temperatura y red

```sh
vcgencmd get_throttled
vcgencmd measure_temp
timedatectl
nmcli device status
```

Compara los indicadores de alimentación con la [documentación oficial de Raspberry Pi](https://www.raspberrypi.com/documentation/computers/os.html). Bajo voltaje puede afectar estabilidad incluso si la interfaz parece funcionar. Utiliza una fuente y cable adecuados, ventilación y apagado ordenado.

Si solo fallan clima/GitHub, revisa conectividad, DNS y configuración; no necesitas reflashear Nextion. Si la hora es incorrecta, corrige la zona horaria y sincronización de Linux.
