# Temporizador, cronómetro y alarma

## Temporizador

Elige 5 minutos de descanso, 25 de enfoque o una hora con los accesos bajo la cifra central. Los botones − y + ajustan un minuto por toque, entre 1 minuto y 24 horas. Iniciar presenta una vista de cuenta grande. Pausar conserva lo restante; Continuar reanuda la cuenta y Reiniciar devuelve la duración configurada. Al pausar se muestran también los segundos restantes. El temporizador comparte estado con Fuera: definir una nueva duración sustituye la cuenta anterior.

Al terminar aparece Tiempo cumplido y el aviso se repite hasta pulsar Detener, durante un máximo de treinta segundos. El sonido utiliza `paplay` de PulseAudio, no Spotify. Funciona sin red si el audio y servicio están disponibles.

## Cronómetro

La cuenta y el reloj analógico representan tiempo transcurrido. El reloj pequeño no es la hora local. Puedes marcar vueltas sin detenerlo; se conservan las cinco últimas en SQLite y se muestra la más reciente. Pausar conserva el tiempo; Reiniciar borra cuenta y vueltas.

El cronómetro iniciado conserva el tiempo transcurrido durante un reinicio. El reloj de Linux debe ser correcto: una corrección brusca de hora puede afectar temporizadores basados en instantes guardados.

## Alarma

Toca las horas o los minutos para seleccionar qué ajustar; la parte seleccionada aparece en verde. Usa −/+ y pulsa Activar alarma. Si esa hora ya pasó, se programa para el día siguiente. La programación es de una sola ejecución: debes activarla de nuevo si la necesitas otro día.

La barra Volumen del aviso ajusta un nivel de 20 a 100 %, independiente del volumen de Spotify. El nivel general de la salida y el control físico de los parlantes también afectan lo que se escucha. Probar sonido reproduce el aviso durante cinco segundos sin programar la alarma.

Cuando llega la hora, las tres notas se repiten con una pausa corta entre secuencias. Detener silencia el aviso; Posponer 5 min lo silencia y programa otro para cinco minutos después. La repetición tiene un límite de tres minutos y el aviso visual permanece hasta atenderlo. Ambos controles funcionan con el panel bloqueado, pero no desbloquean ni activan Spotify.

La programación se conserva en SQLite. Si el servicio se recupera hasta cinco minutos después de la hora, reproduce el aviso. Si pasó más tiempo, presenta Alarma vencida sin sonido. No enciende la Raspberry Pi apagada y no sustituye un despertador autónomo: requiere Pi encendida, servicio activo, hora correcta y salida de audio operativa. Si la conexión USB–TTL impide arrancar el servicio, tampoco puede gestionar avisos hasta recuperarse.

![Alarma](images/alarm.png)

![Cronómetro](images/stopwatch.png)

Vistas reconstruidas con datos de demostración y tipografía aproximada; no son fotografías de la pantalla.
