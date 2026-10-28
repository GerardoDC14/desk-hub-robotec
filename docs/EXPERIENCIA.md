# Uso de la experiencia del Hub

## Música y vista ambiental

Desbloquea el panel y selecciona **Desk Hub Robotec** en la aplicación Spotify del teléfono. El Hub debe estar en la misma red local. El indicador distingue espera, sincronización, carga y reproducción local. El título o la portada pueden estar disponibles antes de que el traspaso de audio haya terminado.

Usa los iconos para anterior, pausa/reproducción y siguiente. La barra superior cambia la posición; la inferior cambia el volumen. Opciones contiene aleatorio, repetición y el siguiente tema. El fondo y el acento toman un color de la portada. Un título largo comienza a desplazarse tras una pausa inicial.

La vista ambiental muestra hora, portada, canción y la cuenta activa del temporizador o cronómetro. Se abre al pasar el intervalo de inactividad configurado y después puede bloquear el Hub con PIN. Antes de ese bloqueo, un toque fuera del botón de música vuelve a la vista anterior y se consume: no activa un control que estuviera debajo. El botón circular pausa o reproduce y reinicia el plazo de bloqueo sin salir de la vista ambiental.

Abre **Estado → Pantalla y bloqueo** o **Spotify → Opciones → Pantalla y bloqueo**. Puedes elegir:

- **Entrada a la vista ambiental:** 30 segundos, 1 minuto, 2 minutos, 5 minutos o Nunca.
- **PIN después de la vista ambiental:** 1, 5, 15 o 30 minutos, o Nunca.
- **Brillo ambiental:** de 20 a 100 %, inicialmente 60 %. Las vistas normales conservan el brillo del 100 %.

Los valores iniciales son **1 minuto para la vista ambiental y 5 minutos más para pedir PIN**: 6 minutos sin tocar la pantalla. Un toque reinicia los tiempos. Los eventos y controles de Spotify en el teléfono no cuentan como interacción con la pantalla.

Al bloquear, el Hub detiene su receptor de Spotify y pide el PIN. El temporizador, cronómetro y alarmas continúan; un aviso de alarma no suspende la protección por inactividad. Para bloquear de inmediato, usa Bloquear o Fuera.

**Ver ahora** activa la vista ambiental manualmente. Aunque la entrada automática esté en Nunca, esta activación manual aplica el intervalo de PIN elegido. Con PIN en Nunca, la vista ambiental sigue accesible hasta bloquearla manualmente. Los ajustes se guardan entre reinicios; el servicio arranca bloqueado.

![Vista ambiental](images/ambient.png)

Vista reconstruida con datos de demostración y tipografía aproximada.

## Duración exacta

1. Abre Tiempo → Temporizador o la preparación de Fuera.
2. Toca la cifra central de minutos.
3. Introduce un entero entre **1 y 1440 minutos**.
4. Pulsa Guardar para preparar la duración. La cuenta comienza al pulsar Iniciar o Estoy fuera.

Borrar elimina el último dígito. Cancelar conserva la duración anterior. Los controles −/+ siguen disponibles para ajustes de un minuto.

## Aviso de salida

En la preparación de Fuera, toca el motivo para recorrer **Estoy fuera**, **En reunión** y **En el laboratorio**. Elige duración y pulsa Estoy fuera. El panel se bloquea, detiene Spotify y presenta la hora prevista de regreso junto a proyectos públicos de GitHub.

Al vencer la cuenta aparece **Regreso pendiente**: conserva la hora prevista, los proyectos públicos y el bloqueo. El PIN correcto termina la salida y permite preparar otra. Abrir el teclado o introducir un PIN incorrecto conserva el aviso. Ver aviso de regreso vuelve a la pantalla pública.

## Conexiones y recuperación

Toca **Estado** en el encabezado de una vista normal. El panel muestra el tipo de red local y su dirección IP, disponibilidad de audio, estado de Spotify y comunicación con la pantalla. El monitor se actualiza aproximadamente cada cinco segundos. El estado del flujo de audio es una comprobación del sistema operativo; no detecta parlantes apagados ni conectores físicos sueltos.

Si la reproducción queda atascada, pulsa **Reconectar Spotify**. Se reinicia el receptor, se descartan órdenes pendientes y debes seleccionarlo otra vez desde el teléfono. Esta acción mantiene la protección por PIN. Bloqueado o en Fuera, el panel no habilita el receptor.

![Estado del dispositivo](images/status.png)

Vista reconstruida con datos de demostración y tipografía aproximada.

## Avisos y música

El temporizador y la alarma tienen secuencias de tonos diferentes. Durante el aviso, el Hub reduce temporalmente el flujo de audio de Spotify al **22 % de su nivel anterior**; no modifica el nivel general de salida. Al detener, posponer o concluir el sonido restaura los niveles por canal. Si se cambia manualmente el volumen del flujo durante el aviso, conserva el cambio manual.

La alarma repite el aviso durante un máximo de tres minutos y el temporizador durante treinta segundos. Probar sonido dura cinco segundos. Los avisos funcionan con el panel bloqueado y no autorizan Spotify.

## Instalación de estas funciones

Las vistas y su lógica se ejecutan en Python en la Raspberry Pi. Se usa el HMI/TFT de referencia del repositorio; estas funciones no requieren volver a cargar la microSD de la pantalla. Mantén todos los módulos Python de la misma versión y reinicia el servicio después de actualizar el código.

## Uso compartido y ayuda

Ayuda está disponible en la pantalla del PIN y mediante ROBOTEC / AYUDA en las vistas normales. Explica Música, Tiempo, Fuera, Clima y Compartir. Funciona sin internet y mantiene el estado de bloqueo y la espera por intentos de PIN incorrectos.

Durante un temporizador o cronómetro activo, Inicio vuelve a la portada sin detener la cuenta. Su tarjeta permite recuperarla. En los avisos, Silenciar corta el sonido sin cerrar el aviso; Detener lo cierra. Las cuentas independientes siguen funcionando.

En Estado o Spotify → Opciones, Pantalla y bloqueo permite elegir cuándo entra la vista ambiental y cuánto tiempo después debe pedir PIN. Para dejar el equipo protegido de inmediato, pulsa Bloquear o inicia Fuera. Las personas de la red pueden intentar conectarse mientras el panel esté desbloqueado.

Si Spotify está reproduciendo o cargando audio en el Hub, Reconectar Spotify presenta una confirmación. Cancelar conserva la sesión.

## Pronóstico sin salir de Inicio

Toca el bloque de clima para alternar los datos actuales y las próximas tres horas. La temperatura grande sigue siendo la actual. Cada fila del pronóstico muestra hora local, temperatura en °C y probabilidad de precipitación en %. Un segundo toque recupera sensación térmica, humedad y viento. Si no hay un pronóstico vigente, se mantienen los datos actuales y se indica su indisponibilidad.

Los datos proceden del [pronóstico horario de Open-Meteo](https://open-meteo.com/en/docs) y se consultan aproximadamente cada diez minutos. El pronóstico expresa una estimación, no una medición futura.
