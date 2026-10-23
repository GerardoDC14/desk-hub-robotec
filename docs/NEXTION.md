# Interfaz Nextion

## Proyecto y modelo

`nextion/desk_hub_robotec.HMI` es el proyecto editable para Nextion Editor. `nextion/desk_hub_robotec.tft` es el compilado de referencia para **NX8048K070_011C**, Enhanced, 800 × 480 horizontal. Se compiló con Nextion Editor 1.68.2 sin errores ni advertencias.

El TFT mide **463.552 bytes** y su SHA-256 es:

```text
4A6C20061794F2846FC709900DD85C4E477963F4BF54BD55B027616881A26F14
```

El HMI incorpora las fuentes con IDs 0/1/2/3, de 32/64/16/128 píxeles. El arranque fija UART a 9600; Postinitialize oculta los componentes de diagnóstico, dibuja BLOQUEADO, activa `sendxy=1` y emite `sendme`. Su texto está en `robotec_page0.txt`. La Pi negocia 115200 durante la ejecución y dibuja las vistas sobre la misma page0.

Para editar, descarga [Nextion Editor oficial](https://nextion.tech/nextion-editor/), abre el HMI y conserva modelo y orientación. Compila, revisa errores y usa **File > TFT file output**. No renombres un HMI a TFT. Si cambias fuentes, IDs o resolución, adapta también Python.

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
