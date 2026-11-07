# Diseño y respuesta del panel

El panel utiliza seis destinos principales: Inicio, Spotify, Tiempo, Fuera, Tareas y Cámara. La navegación inferior conserva su posición y destaca el destino actual con una superficie redondeada. La acción principal usa verde claro; las acciones secundarias utilizan una superficie oscura. Los controles de duración admiten ajuste por pasos, valores frecuentes y entrada directa al tocar la cifra.

[Archivo editable en Figma](https://www.figma.com/design/haO2a7ZleMYs7osOep2Ycr/Desk-Hub-Robotec-%E2%80%94-simplificar-y-pulir) en la página **02 · Reproductor y accesos**, con las composiciones de 800 × 480. Contiene capas de texto y vectores editables. Inter sirve como referencia en Figma; la pantalla utiliza las fuentes incorporadas en el HMI. Las imágenes de esta guía reconstruyen los comandos de dibujo con datos de demostración y tipografía aproximada.

## Legibilidad y controles

- Fondo grafito, texto claro y acento verde suave; la portada no cambia la paleta del reproductor.
- El reproductor sitúa la portada de 272 × 272 a la derecha y la información a la izquierda. El título utiliza la fuente grande cuando cabe y dos líneas de tamaño normal cuando necesita más espacio. Reproducción y volumen comparten una franja inferior. El estado del receptor se expresa con texto, sin simular niveles de audio.
- Las zonas táctiles deben conservar la geometría de los controles visibles. Al modificar un control, revisa tanto su dibujo como su manejo del toque.
- La vista ambiental puede utilizar colores derivados de la portada. Un toque vuelve al panel antes del bloqueo; después se requiere el PIN.

## Actualización por diferencias

Los textos, iconos, superficies y progreso se conservan en caché. Solo se envían los cambios mediante UART; cambiar la portada no borra toda la vista del reproductor. Los iconos incluyen sus colores en la clave de caché para que un cambio de paleta no conserve píxeles anteriores.

Las pruebas de `tests/test_essential.py` verifican que una reproducción con estado y posición constantes no genera órdenes de dibujo repetidas; también comprueban que una portada nueva no repinta los controles, que los cambios de color actualizan los iconos y que toda la superficie de Pantalla y bloqueo responde al toque. Esto comprueba tráfico y comportamiento del código, no una frecuencia de imagen física garantizada.

Tareas y Cámara se abren directamente desde la barra inferior. Ambas requieren desbloquear el panel; entrar en Cámara no inicia una captura ni activa la vista previa. Su botón Inicio vuelve a la portada.

Para validar en el equipo, abre los seis destinos, ajusta una duración, cambia de canción y comprueba título, portada, progreso y respuesta táctil. La legibilidad final depende también del brillo, los reflejos y el ángulo de observación.

Las pruebas de `tests/test_player_layout.py` cubren los accesos directos, la protección con PIN, el ajuste de etiquetas a las fuentes del HMI, la separación de zonas de reproducción y volumen y la limpieza de títulos al cambiar de canción.
