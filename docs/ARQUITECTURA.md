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

Las operaciones de red e imágenes se ejecutan en hilos. El dibujo transmite comandos Nextion terminados en `FF FF FF` y evita reenviar textos sin cambios. Se reciben coordenadas al soltar mediante `sendxy=1`. Las portadas y el avatar se convierten a 48 × 48 píxeles con una paleta reducida y se dibujan ampliados por bloques; no son imágenes de alta resolución. La portada se muestra a 192 × 192 píxeles. Primero se transmite una vista de 12 × 12 y luego el detalle de 48 × 48; los rectángulos iguales contiguos se fusionan y los píxeles ya correctos no se vuelven a enviar. Se conserva una caché en memoria de ocho portadas. Los paquetes de dibujo se limitan a unos 256 bytes y se intercalan con lectura táctil; el tiempo depende del contenido y UART. No se transmite vídeo ni una portada de resolución nativa completa. El indicador musical animado representa actividad, no un análisis del espectro del audio. Los títulos largos se desplazan cada dos segundos.

## Datos y temporización

La cuenta guarda un instante final y se resta del reloj de Linux. El cronómetro conserva el inicio, el tiempo acumulado y las cinco últimas vueltas. La alarma de una sola ejecución guarda su siguiente instante y se desactiva al dispararse. Si se recupera hasta cinco minutos tarde, se presenta el aviso; más tarde se informa que venció sin reproducir sonido. Un reinicio puede incluir el tiempo que la Pi estuvo apagada; un cambio brusco de hora de Linux puede afectar esas cuentas. Los cambios se guardan en SQLite, no hay escritura por cada refresco. Las barras y la animación musical dibujan solo sus diferencias. Las cifras grandes se actualizan por carácter; el reloj analógico borra y repone únicamente las agujas, lejos de las marcas de la esfera.

Clima y GitHub se consultan aproximadamente cada diez minutos. Un proceso `soloist ctl trace` entrega eventos musicales en tiempo real; una consulta cada treinta segundos mantiene una referencia de respaldo. Si el stream no está disponible, se vuelve a consultar aproximadamente cada segundo. La cola se refresca cuando llegan eventos y con una consulta de respaldo mientras la vista musical está abierta. Los límites y errores de las APIs pueden conservar información anterior o mostrar indisponibilidad. Las cuentas locales siguen funcionando sin internet.

## Bloqueo y recuperación

El servicio arranca bloqueado. El PIN correcto crea una autorización temporal en `/run/user/UID/desk-hub.unlocked`; bloquear la elimina y solicita detener el receptor. Iniciar Fuera mantiene la cuenta visible y bloquea; terminarla no autoriza Spotify.

Se consulta presencia de Nextion cada dos segundos. Se solicita bloqueo tras seis segundos sin respuesta; una desconexión USB que termine el proceso es recuperada por systemd. Un reinicio detectado de la pantalla bloquea y obliga a renegociar UART. El tiempo total de detección/recuperación depende también de operaciones de serial en curso. La pantalla puede presentar el aviso nativo de bloqueo mientras espera al servicio.

Tres PIN incorrectos producen treinta segundos de espera. Esa espera reside en memoria y se reinicia al reiniciar el proceso. El PIN protege el uso del panel: una cuenta con acceso a los archivos o comandos del mismo usuario Linux puede alterar la aplicación. No equivale a autenticación del sistema ni a aislamiento entre usuarios de Spotify Connect.

## Alcance de validación

Los autotests comprueban lógica y parser sin hardware. El apagado físico, la secuencia de alimentación, tolerancias de fuentes y la instalación en otra Pi requieren comprobación real. El proyecto usa servicios de usuario y systemd de Linux; Windows se utiliza para editar y compilar el HMI, no para ejecutar el panel conectado.
