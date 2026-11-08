# Interfaz Nextion

## Proyecto y modelo

`nextion/desk_hub_robotec.HMI` es el proyecto editable para Nextion Editor. `nextion/desk_hub_robotec.tft` es el compilado de referencia para **NX8048K070_011C**, Enhanced, 800 × 480 horizontal. Se compiló con Nextion Editor 1.68.2 sin errores ni advertencias.

El TFT mide **463.552 bytes** y su SHA-256 es:

```text
4A6C20061794F2846FC709900DD85C4E477963F4BF54BD55B027616881A26F14
```

El HMI incorpora las fuentes con IDs 0/1/2/3, de 32/64/16/128 píxeles. El arranque fija UART a 9600; Postinitialize oculta los componentes de diagnóstico, dibuja BLOQUEADO, activa `sendxy=1` y emite `sendme`. Su texto está en `robotec_page0.txt`. La Pi negocia **921600 baudios** durante la ejecución y dibuja las vistas sobre la misma page0. Detecta también 9600, 115200 y 230400 para recuperarse de reinicios o de un cambio de velocidad. Solo usa `baud`, que es volátil; no modifica el ajuste persistente `bauds`.

Las tarjetas redondeadas, los iconos meteorológicos nativos y el rediseño visual se generan desde Python y son compatibles con este mismo TFT. No necesitan volver a cargar firmware si las fuentes y el modelo permanecen iguales.

Para editar, descarga [Nextion Editor oficial](https://nextion.tech/nextion-editor/), abre el HMI y conserva modelo y orientación. Compila, revisa errores y usa **File > TFT file output**. No renombres un HMI a TFT. Si cambias fuentes, IDs o resolución, adapta también Python.

## Transporte y calidad de imagen

El modo rápido agrupa hasta **960 bytes** de instrucciones más una barrera de ejecución de 11 bytes. Cada lote espera una respuesta del panel antes del siguiente; los eventos táctiles recibidos durante la espera se conservan. Los modos conservadores usan lotes de 240 bytes. No abras simultáneamente el puerto con otro programa.

Si falla la confirmación de un lote durante el dibujo, el Hub bloquea el panel y reintenta el enlace a **115200**. Para mantener esa velocidad desde el arranque, configura `Environment=DESK_HUB_BAUD=115200` en un override de `desk-hub.service`, recarga systemd y reinicia el servicio. Se admiten 115200, 230400 y 921600. Un reinicio de la pantalla vuelve a la velocidad definida por el TFT y la aplicación la negocia otra vez.

Si 921600 no es estable durante música y cámara, puedes seleccionar **230400** como velocidad intermedia. No cambia la resolución ni los archivos de las fotos; aumenta el tiempo de transmisión de las imágenes. Ejecuta `sudo systemctl edit desk-hub.service` y añade:

```ini
[Service]
Environment=DESK_HUB_BAUD=230400
```

Después ejecuta `sudo systemctl daemon-reload` y `sudo systemctl restart desk-hub.service`. Comprueba que el registro indique `UART 230400 validado` y prueba música, encuadre y captura juntos. Si ya defines `DESK_HUB_BAUD` en `~/.config/desk-hub/environment`, cambia ese valor también: un `EnvironmentFile` tiene prioridad sobre `Environment`. Reducir la velocidad no corrige una alimentación defectuosa ni conexiones flojas.

La detección prueba dos veces cada velocidad antes de descartarla, para permitir que el terminador vacíe bytes incompletos de un sondeo anterior. La segunda consulta repite únicamente la identificación de página y no acciones del panel.

## Actualización de imágenes

Las imágenes se envían en lotes de hasta 240 bytes, con confirmación independiente de cada lote. El bucle agrupa como máximo cuatro lotes y cede al detectar un toque pendiente o alcanzar su presupuesto de 25 ms; una respuesta lenta puede alargar ese intervalo hasta el límite de espera del enlace. Se conservan la recuperación de errores y el bloqueo cuando se pierde la comunicación.

Mientras permanece abierta la vista de Spotify, una portada completamente dibujada sirve de referencia para enviar únicamente los píxeles que cambian. Un cambio de página, geometría o un envío incompleto obliga a dibujarla de nuevo. Esto reduce el trabajo cuando las portadas coinciden total o parcialmente; la primera carga y las imágenes muy distintas siguen limitadas por el enlace serial.

La vista de cámara solicita el siguiente encuadre cuando está terminando de enviar el actual. Evita convertir fotogramas que la pantalla no puede mostrar y mantiene un único encuadre pendiente, sin guardar imágenes automáticamente. Conserva resolución, paleta y calidad de las fotos. La velocidad visible depende del detalle y del movimiento de la escena; no equivale a una pantalla de vídeo conectada por HDMI.

Las portadas de música se procesan a **96 × 96**, con hasta 192 colores; primero aparece una vista rápida y después el detalle. Los iconos de reproducción usan bordes suavizados a su tamaño nativo. El contenido cambia por regiones para mantener disponibles los controles táctiles. La resolución física del panel sigue siendo 800 × 480; la conexión UART limita el detalle y la frecuencia de las imágenes dinámicas.

## Cargar con microSD

1. Identifica una tarjeta de diagnóstico independiente, FAT32, compatible con Nextion. **No utilices ni borres la microSD de Linux de la Pi.**
2. Copia solo el TFT correspondiente al modelo a la raíz; debe haber un único `.tft`.
3. Expulsa de forma segura. Apaga Nextion, inserta la tarjeta y enciende.
4. Espera confirmación de actualización satisfactoria, sin interrumpir energía.
5. Apaga, retira la tarjeta y vuelve a encender. El firmware reemplaza la interfaz anterior.

## Cargar desde la Pi por UART

Detén el servicio y apaga/enciende solo la pantalla para restaurar 9600 antes de usar el cargador. No ejecutes dos procesos sobre el mismo puerto.

```sh
sudo systemctl stop desk-hub
sha256sum nextion/desk_hub_robotec.tft
python3 scripts/cargar_nextion.py nextion/desk_hub_robotec.tft \
  --port /dev/serial/by-id/usb-1a86_USB2.0-Serial-if00-port0 \
  --sha256 4A6C20061794F2846FC709900DD85C4E477963F4BF54BD55B027616881A26F14
sudo systemctl start desk-hub
```

Sustituye el puerto por el real. El cargador valida el hash y la identificación de la familia antes de escribir, transmite a 115200 con ACK por bloque de 4096 bytes y consulta identificación al terminar. La comprobación de familia no sustituye seleccionar el TFT correcto para la variante. Si recompilas, utiliza el hash nuevo, no el de referencia.

## Diagnóstico mínimo

`diagnostics/diagnostico_nextion.HMI` y `.tft` presentan LISTO y PROBAR. Cargarlos sustituye temporalmente Desk Hub. Para consultar identificación y recibir el botón:

```sh
sudo systemctl stop desk-hub
python3 diagnostics/probar_uart.py --port /dev/serial/by-id/usb-1a86_USB2.0-Serial-if00-port0
```

El diagnóstico trabaja a 9600 y actualiza el texto a PI CONECTADA. Pulsa PROBAR durante la escucha y revisa las tramas recibidas. Después restaura el TFT Desk Hub y el servicio.
