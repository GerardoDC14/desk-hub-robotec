# Arquitectura y límites

```mermaid
flowchart LR
    N[Nextion 800 × 480] <-->|UART 8N1| U[USB–TTL CH340G]
    U <-->|USB| P[Raspberry Pi / robotec.py]
    P <--> D[(SQLite local)]
    P --> W[Open-Meteo]
    P --> G[GitHub público]
    P <-->|CLI local| S[Spotify Soloist]
    S --> A[PulseAudio / jack / parlantes]
```

## Componentes

- `editorial_views.py`: composición visual y avisos públicos, clima integrado en Inicio y QR de GitHub.
- `nextion_link.py`: normalización de texto, límites de paquetes y barrera de ejecución UART.
- `robotec.py`: vistas, zonas táctiles, bloqueo, cronómetro, portadas y ciclo de vida de Spotify.
- `desk_hub.py`: puerto serial, parser de tramas, cuenta regresiva, SQLite y consultas de red.
- `soft_ui.py`: paneles, iconos, reloj analógico y barras actualizadas por diferencias.
- `font_metrics.py`: anchos reales de las fuentes del HMI; actualízalos si sustituyes esas fuentes.
- `dashboard_views.py` y `dashboard_state.py`: herramientas de tiempo, alarma persistente, avisos y sonido local.
- `music_client.py` y `music_state.py`: suscripción local a eventos, estado musical y posición interpolada con reloj monotónico.
- `settings.py`: rutas relativas al clon y variables de configuración.
- `pin_setup.py`: registro local PBKDF2-HMAC-SHA256, con sal aleatoria y comparación de tiempo constante.
- `spotify_inicio.py`: comprueba la autorización temporal y lanza Soloist con la credencial privada.
- `lock_cleanup.py`: elimina autorización y detiene Spotify al iniciar/detener el servicio del panel.

Las operaciones de red e imágenes se ejecutan en hilos. El dibujo usa un solo escritor UART y comandos terminados en `FF FF FF`; se reciben coordenadas al soltar mediante `sendxy=1`.

Los paquetes de dibujo, incluida su barrera, no superan 256 bytes. Con `bkcmd=2`, cada lote se completa con `get sys0`: el siguiente espera la respuesta numérica y recoge los errores de las instrucciones precedentes. Los toques recibidos durante esa espera quedan pendientes para el ciclo principal. Un error o tiempo agotado interrumpe el proceso; systemd aplica el cierre del receptor y reinicia bloqueado. La barrera confirma procesamiento, no es una captura visual ni una suma de comprobación del texto dibujado.

El texto externo elimina controles, comillas dobles, barras inversas y el byte `FF`, y se limita a 160 caracteres antes de codificar. La caché considera contenido, posición, fuente y colores. Los títulos se ajustan al ancho medido y se distribuyen en dos líneas; el excedente se abrevia. El botón de acceso ocupa una zona independiente de la cuenta, el QR y los proyectos.

Las portadas se convierten a 48 × 48 píxeles con una paleta reducida y se dibujan ampliadas a 192 × 192 por bloques. Primero se transmite una vista de 12 × 12 y luego el detalle de 48 × 48. Se fusionan rectángulos iguales contiguos y se omiten píxeles ya correctos. Una caché en memoria conserva ocho portadas. El tiempo depende del contenido y UART; no se transmite vídeo ni una portada de resolución nativa completa. El indicador musical representa actividad, no un análisis del espectro de audio.

La paleta utiliza fondo grafito, texto principal blanco y texto secundario claro; la navegación y las instrucciones de acceso emplean fuentes más grandes. El brillo normal se ajusta al 100 % y el ambiental al porcentaje configurado, entre 20 y 100 %; el valor ambiental inicial es 60 %. Los cambios de brillo se envían al entrar o salir de la vista ambiental, con el mismo escritor UART. La paleta no modifica el acabado del cristal ni elimina los reflejos de la iluminación.

## Datos y temporización

La cuenta guarda un instante final y se resta del reloj de Linux. El cronómetro conserva el inicio, el tiempo acumulado y las cinco últimas vueltas. La alarma de una sola ejecución guarda su siguiente instante y se desactiva al dispararse. Si se recupera hasta cinco minutos tarde, se presenta el aviso; más tarde se informa que venció sin reproducir sonido. Un reinicio puede incluir el tiempo que la Pi estuvo apagada; un cambio brusco de hora de Linux puede afectar esas cuentas. Los cambios se guardan en SQLite, no hay escritura por cada refresco. Las barras y la animación musical dibujan solo sus diferencias. Las cifras grandes se actualizan por carácter; el reloj analógico borra y repone únicamente las agujas, lejos de las marcas de la esfera.

Clima y GitHub se consultan aproximadamente cada diez minutos. Inicio integra sensación térmica en °C, humedad en % y viento en km/h bajo el reloj y la temperatura. El estado sin actualizar permite reconocer un fallo de consulta conservando los últimos datos disponibles. Fuera rota repositorios cada 18 segundos y permite avanzar o retroceder manualmente. Su QR se genera localmente con python3-qrcode, apunta al perfil público configurado y no contiene credenciales. Un proceso `soloist ctl trace` entrega eventos musicales en tiempo real; una consulta cada quince segundos cuando el receptor está activo mantiene una referencia de respaldo. Si el stream no está disponible, se vuelve a consultar aproximadamente cada segundo. La cola se refresca cuando llegan eventos y con una consulta de respaldo mientras la vista musical está abierta. Los límites y errores de las APIs pueden conservar información anterior o mostrar indisponibilidad. Las cuentas locales siguen funcionando sin internet.

## Bloqueo y recuperación

El servicio arranca bloqueado. El PIN correcto crea una autorización temporal en `/run/user/UID/desk-hub.unlocked`; bloquear la elimina y solicita detener el receptor. Iniciar Fuera mantiene la cuenta visible y bloquea; terminarla no autoriza Spotify. Un PIN válido indica el regreso: restablece la duración de Fuera, elimina su instante final y guarda el estado antes de activar el receptor. Un PIN incorrecto, abrir el teclado o volver al aviso público no termina la salida. Desbloquear conserva un temporizador normal en curso y el cronómetro independiente.

Se consulta presencia de Nextion cada dos segundos. Se solicita bloqueo tras seis segundos sin respuesta; una desconexión USB que termine el proceso es recuperada por systemd. Un reinicio detectado de la pantalla bloquea y obliga a renegociar UART. El tiempo total de detección/recuperación depende también de operaciones de serial en curso. La pantalla puede presentar el aviso nativo de bloqueo mientras espera al servicio.

Tres PIN incorrectos producen treinta segundos de espera. Esa espera reside en memoria y se reinicia al reiniciar el proceso. El PIN protege el uso del panel: una cuenta con acceso a los archivos o comandos del mismo usuario Linux puede alterar la aplicación. No equivale a autenticación del sistema ni a aislamiento entre usuarios de Spotify Connect.

## Alcance de validación

Los autotests comprueban lógica y parser sin hardware. El apagado físico, la secuencia de alimentación, tolerancias de fuentes y la instalación en otra Pi requieren comprobación real. El proyecto usa servicios de usuario y systemd de Linux; Windows se utiliza para editar y compilar el HMI, no para ejecutar el panel conectado.

## Fuentes y avisos

`font_metrics.py` almacena el ancho de un byte de cada carácter de las fuentes ZI v6 incorporadas. El byte contiguo corresponde al margen izquierdo; no forma parte del ancho. El formato se contrastó con los archivos del proyecto y la [documentación del lector ZI](https://github.com/hagronnestad/nextion-font-editor/blob/master/Docs/Nextion%20Font%20Format%20Specification%20ZI%20version%206.md). La condición meteorológica utiliza una fuente menor cuando no cabe completa.

`AlertSound` ejecuta un solo proceso de audio a la vez. Cada solicitud tiene un identificador y un plazo; una solicitud nueva sustituye a la anterior, y Detener cancela también un sonido en curso. El volumen del aviso se aplica al flujo `paplay`, sin modificar la salida global. `audio_focus.py` reduce el flujo de Soloist al 22 % de su nivel mientras suena el aviso. Conserva el nivel por canal y la identidad del proceso, y sólo restaura flujos que siguen teniendo el nivel reducido; respeta cambios manuales y no aplica un nivel guardado a un identificador reutilizado por otro proceso. La forma de onda tiene picos inferiores a la mitad del rango PCM de 16 bits.

## Sesiones y presentación

Cada orden musical lleva el instante de creación, generación del receptor, época de actividad y canción de origen. Se valida antes de ejecutarla. Bloquear o reconectar invalida la generación y vacía la cola. Cada evento incrementa una revisión; una consulta sólo puede actualizar el estado si conserva esa revisión y generación. Las respuestas a órdenes son confirmaciones de envío, no confirmaciones de reproducción.

El monitor de red y PulseAudio publica datos cada cinco segundos, sin escribir al UART. Sólo el hilo de interfaz dibuja. La vista ambiental conserva la reproducción y muestra la cuenta de tiempo activa. Su entrada y el bloqueo posterior se rigen por la inactividad de la pantalla. Los ajustes de pantalla, motivo y aviso de salida se guardan en SQLite. Regreso pendiente persiste hasta un PIN válido, incluidos reinicios del servicio.

Cada refresco reúne las instrucciones de dibujo en una transacción. `NextionLink` divide esa transacción en lotes que caben en el búfer de la pantalla y espera su confirmación; conserva los eventos táctiles recibidos durante la espera. Las portadas se dibujan progresivamente entre refrescos.

## Uso compartido

`friendly_ui.py` mantiene la guía pública y los accesos a cuentas en curso. La guía no modifica la autorización del receptor ni el límite de intentos del PIN.

La política de inactividad distingue dos etapas: entrar en la vista ambiental y, después, bloquear con PIN. El valor inicial es de 60 segundos para la primera etapa y 300 segundos adicionales para la segunda. Las duraciones configuradas se guardan en SQLite; la interacción se mide con reloj monotónico. Un toque de pantalla reinicia la inactividad. Los eventos musicales, la reproducción y los controles desde el teléfono no la reinician.

La comprobación del bloqueo se ejecuta en el ciclo principal y no depende de dibujar una vista concreta. Los avisos de alarma no suspenden ese control. Al bloquear se elimina la autorización temporal y se solicita detener Spotify, conservando temporizador, cronómetro y alarmas. Entrar en Fuera mantiene su bloqueo inmediato.

La entrada automática admite 30, 60, 120 o 300 segundos, o Nunca. El retraso de PIN admite 60, 300, 900 o 1800 segundos, o Nunca. Si la entrada automática está desactivada, no se inicia automáticamente la segunda etapa; una entrada manual con Ver ahora sí usa el retraso de PIN configurado. El toque del botón de reproducción dentro de la vista ambiental reinicia ese retraso. El servicio arranca bloqueado después de reiniciar.

El pronóstico se solicita junto con el clima actual. `weather_data.py` convierte instantes Unix a la zona configurada mediante `zoneinfo`, filtra horas pasadas y conserva hasta tres filas. El renderizado nunca consulta la red. Las filas vencidas o de una consulta marcada sin actualizar no sustituyen a las condiciones actuales. En Raspberry Pi OS se utiliza la base de zonas horarias del sistema; para ejecutar las pruebas en Windows, instala también `tzdata` en tu entorno Python.

La pérdida del observador de eventos de Spotify invalida las órdenes del estado anterior y solicita una consulta inmediata. Una respuesta nueva del receptor permite recuperar los controles. Las órdenes pendientes tienen prioridad sobre consultas opcionales, con un límite de un segundo para observaciones locales. Con eventos disponibles, cada toque no provoca una consulta completa adicional.
