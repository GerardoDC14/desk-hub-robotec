# Compartir el Hub con invitados

El código de invitado permite usar música, temporizadores, cronómetro y sesiones de enfoque. No permite abrir fotos, cámara, tareas de Notion, ajustes de pantalla, apagado ni gestión de accesos. El PIN del anfitrión se conserva por separado.

## Crear un acceso

1. Desbloquea con el PIN del anfitrión y entra en **Estado → Invitados**.
2. Elige **Crear / 1 hora** o **Crear / 8 horas**.
3. Comparte el código de seis cifras que aparece. Se muestra sólo en esa vista; al salir se oculta. Si lo necesitas de nuevo, genera otro.
4. Pulsa Volver y bloquea el panel. El invitado introduce el código en el mismo teclado del PIN.

El encabezado muestra **Modo invitado**. La portada ofrece **Salir**, que bloquea el panel y detiene Spotify. El invitado puede volver a entrar mientras el código siga vigente. La vista ambiental y el bloqueo por inactividad mantienen sus tiempos configurados.

Al vencer el código, la sesión de invitado se bloquea y Spotify se detiene. Para revocarlo antes, desbloquea con el PIN del anfitrión, abre Invitados y pulsa **Revocar**. Crear un código nuevo invalida el anterior. El vencimiento se conserva si se reinicia la Pi; se necesita una hora local correcta.

## Durante una ausencia

Entrar como invitado no termina el aviso de regreso. Puede escuchar música y usar los temporizadores; al salir o caducar el código vuelve el aviso público de ausencia. El PIN del anfitrión sí termina la salida y permite preparar otra. Ninguno de estos cambios cancela las cuentas independientes que estén en marcha.

El código de invitado no es una cuenta de Spotify ni cambia la cuenta conectada al receptor. La conexión musical se realiza desde Spotify después de desbloquear el Hub.

Los códigos no se guardan en texto legible. El estado local conserva una derivación PBKDF2 con sal y fecha de vencimiento. El teclado limita los intentos incorrectos tanto para invitados como para el anfitrión.
