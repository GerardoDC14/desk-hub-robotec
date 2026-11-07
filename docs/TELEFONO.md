# Usar el Hub desde el teléfono

El panel local permite controlar Spotify, ajustar las tres cuentas independientes, descargar fotos originales y ver el encuadre de la cámara por Wi‑Fi. No requiere instalar una aplicación.

## Enlazar

1. Conecta el teléfono a la misma red que la Raspberry. La red debe permitir comunicación entre sus dispositivos.
2. Desbloquea el Hub con el PIN del anfitrión.
3. Abre **Estado → Invitados → Teléfono → Generar QR**.
4. Escanea el QR con el teléfono y abre el enlace. El QR vence en 60 segundos y sólo se utiliza una vez.
5. Elige **Música**, **Cuentas**, **Fotos** o **Cámara**.

La sesión dura 15 minutos. Generar otro QR invalida el enlace anterior. **Cerrar enlace**, bloquear el Hub o reiniciarlo revoca el acceso. Recargar o cerrar la página pierde la sesión y requiere otro QR: el navegador no guarda la credencial. Los invitados no pueden generar este enlace, porque permite acceder a las fotos y a la cámara del anfitrión.

El bloqueo por inactividad sigue vigente. Las acciones explícitas cuentan como actividad; consultar el estado o recibir encuadres automáticamente no mantiene el Hub desbloqueado. Ajusta los tiempos en **Estado → Pantalla y bloqueo** según la sesión de trabajo.

## Música y cuentas

Selecciona **Desk Hub Robotec** en Spotify antes de usar los controles del panel local. Puedes reproducir, pausar, cambiar de canción y ajustar el volumen. Las respuestas indican si la orden se envió o si primero hace falta conectar Spotify.

Cada cuenta tiene su propia duración y controles para iniciar, pausar y reiniciar. Para cambiar la duración, pausa primero e introduce de 1 a 1440 minutos. Las cuentas continúan al cerrar la página y se conservan en la Raspberry.

## Fotos y cámara

**Fotos** muestra seis miniaturas por página. **Descargar** entrega el JPEG original, sin reducirlo ni modificarlo. Pulsa **Actualizar** después de una captura. La papelera se gestiona desde la pantalla del Hub.

En **Cámara**, pulsa **Activar cámara** para ver el encuadre. La captura continua es de 640 × 360 píxeles y hasta cuatro encuadres por segundo; la velocidad efectiva depende de la red y la carga de la Pi. La Nextion conserva su vista optimizada para el enlace serie. La vista en directo no guarda fotos.

**Tomar foto** detiene el encuadre y guarda una foto de 1280 × 720 en la Raspberry. Abre Fotos y pulsa Actualizar para descargarla. **Pausar vista**, cambiar de sección, ocultar la página o bloquear el Hub detiene la vista iniciada desde el teléfono. Si el teléfono deja de pedir encuadres, la Pi la detiene después de unos diez segundos. Una captura o un timelapse en curso no se reemplaza por una nueva vista.

## Red y privacidad

El servidor sólo se abre al generar un QR y utiliza el puerto TCP 8765. No se configura acceso desde Internet ni reenvío de puertos. Usa una red local de confianza: esta versión emplea HTTP, sin cifrado de transporte, y no debe exponerse a Internet ni utilizarse en redes públicas o no confiables. Quien escanee el QR vigente tendrá acceso temporal de anfitrión a estas funciones.

La credencial se entrega en el fragmento del enlace, se retira de la barra del navegador y permanece sólo en memoria. Las peticiones posteriores requieren una sesión válida; el servidor verifica también el estado desbloqueado, limita tamaños y concurrencia y no registra las credenciales en sus accesos. No proporciona acceso a rutas arbitrarias, claves de Spotify, PIN, archivos de configuración ni datos de Notion.

Si el enlace no abre, verifica que ambos dispositivos compartan red y que ésta no tenga aislamiento de clientes. Si el QR venció o el Hub se bloqueó, desbloquea y genera uno nuevo.
