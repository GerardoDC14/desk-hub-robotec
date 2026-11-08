# Diagnóstico

## La pantalla no responde

Comprueba primero alimentación, GND común, TX/RX cruzados y existencia del puerto. Detén el servicio antes de abrir el puerto manualmente. El TFT arranca a 9600 y el panel negocia hasta 921600 (o 115200 en recuperación); reiniciar solo el servicio no reinicia la velocidad de Nextion.

```sh
ls -l /dev/serial/by-id/
id
systemctl status desk-hub
journalctl -u desk-hub -n 40 --no-pager
```

Si falta `dialout`, corrige el grupo y vuelve a iniciar sesión. Para aislar UART y lógica, utiliza el firmware y script de [diagnóstico mínimo](NEXTION.md). Un loopback requiere desconectar Nextion y unir TX/RX del adaptador con las fuentes apagadas antes de cambiar cables; no unas alimentación con señales.

## Texto extraño o dibujo incompleto

Comprueba que solo `desk-hub.service` abre el puerto. Detén el servicio antes de ejecutar un diagnóstico serial; dos procesos sobre el mismo puerto pueden mezclar comandos o consumir respuestas del otro.

La aplicación espera una respuesta de Nextion entre lotes. El log `Nextion rechazó dibujo` incluye el código hexadecimal de error; `Nextion no confirmó el lote de dibujo` indica que falta la respuesta esperada. Revisa alimentación, USB, conectores y GND común antes de volver a iniciar el servicio. No cambies cables con alimentación conectada.

```sh
sudo systemctl restart desk-hub
journalctl -u desk-hub -n 40 --no-pager
```

Después del reinicio debe aparecer el teclado de PIN. En Fuera, comprueba que Desbloquear permanece legible mientras cambia la cuenta y usa las flechas para verificar el cambio de proyecto. Los cambios de composición realizados en Python no requieren volver a cargar el TFT.

## Spotify no aparece o no suena

Desbloquea primero. Comprueba el ejecutable, clave local con permisos 600, unidad del usuario, red y salida de audio. El receptor debe estar inactivo mientras el panel está bloqueado. Consulta [Spotify y audio](SPOTIFY.md). Revisa el log si el reproductor requiere actualización; no publiques claves ni sesiones al pedir ayuda.

## Vuelve al PIN durante música o cámara

Comprueba primero los tiempos de **Estado → Pantalla y bloqueo**. La música no desactiva el bloqueo por inactividad. Si ocurre mientras estás usando la pantalla, consulta:

```sh
systemctl show desk-hub.service -p NRestarts -p ExecMainStartTimestamp -p Result
journalctl -u desk-hub.service --since '30 minutes ago' --no-pager
journalctl -k --since '30 minutes ago' --no-pager
uptime
```

`NRestarts` cuenta reinicios automáticos del servicio, no todos los reinicios posibles. Compara también su hora de inicio y el tiempo encendida de la Pi.

- **UART: recuperando enlace…** indica recuperación de la comunicación con Nextion. Incluye motivo, vista, baudios, segundos desde la última confirmación y número de instrucciones de imagen pendientes. No registra el contenido de fotos, PIN ni claves.
- **Nextion no confirmó el lote de dibujo** significa que faltó la confirmación de ejecución durante 1,5 segundos después de enviar un lote. **Nextion rechazó dibujo** incluye el código de rechazo.
- **UART: pantalla reiniciada** indica que Nextion envió su aviso de arranque.
- **Under-voltage detected** en el registro del kernel indica una caída de alimentación detectada por la Pi. Revisa también el cable y sus conexiones, aunque la fuente tenga el voltaje nominal correcto.

Las confirmaciones de cada lote de dibujo cuentan como actividad de la pantalla: una imagen que tarde más de seis segundos no debe provocar por sí sola el regreso al PIN. Si se pierde realmente la comunicación, se bloquea el Hub, se detiene Spotify y se intenta recuperar el enlace a 115200 baudios. A esa velocidad las imágenes tardan más. Tras revisar alimentación y conexiones, reinicia el servicio para negociar nuevamente la velocidad configurada. El bloqueo mantiene privadas la cámara y la galería; los temporizadores conservan su estado.

Para comprobar estabilidad, alterna varias canciones, abre Cámara, activa y pausa la vista, toma una foto y vuelve a Spotify. Revisa que no haya nuevos mensajes de recuperación ni reinicios automáticos. Una prueba sin fallos no descarta una interrupción eléctrica intermitente.

## Fuente, temperatura y red

```sh
vcgencmd get_throttled
vcgencmd measure_temp
timedatectl
nmcli device status
```

Compara los indicadores de alimentación con la [documentación oficial de Raspberry Pi](https://www.raspberrypi.com/documentation/computers/os.html). Bajo voltaje puede afectar estabilidad incluso si la interfaz parece funcionar. Utiliza una fuente y cable adecuados, ventilación y apagado ordenado.

Si solo fallan clima/GitHub, revisa conectividad, DNS y configuración; no necesitas reflashear Nextion. Si la hora es incorrecta, corrige la zona horaria y sincronización de Linux.

## Lectura bajo iluminación intensa

El panel configura brillo al 100 % y utiliza contraste alto. Comprueba la lectura desde el ángulo habitual y evita que la luminaria se refleje directamente en el cristal. Cambiar colores no elimina reflejos ni aumenta la luminosidad máxima del hardware. Si los textos grandes se leen y los pequeños no, identifica la vista y el texto concreto para ajustar su tamaño sin reducir el resto de la información.

## La canción aparece, pero no suena

1. En Spotify del teléfono, selecciona Desk Hub Robotec como dispositivo de salida.
2. Espera a que el panel deje de indicar sincronización o carga.
3. Abre Estado y revisa Audio y Spotify. Una salida disponible y un flujo abierto no detectan un jack desconectado ni parlantes apagados.
4. Si el traspaso queda detenido, pulsa Reconectar Spotify y selecciona el Hub nuevamente desde el teléfono.
5. Comprueba el volumen de Spotify, el nivel general de PulseAudio y los parlantes. El nivel del aviso de alarma es independiente.

No es necesario reiniciar la Pi para reconectar el receptor. Reconectar interrumpe la reproducción del Hub y mantiene la protección por PIN.
