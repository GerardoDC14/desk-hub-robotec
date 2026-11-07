# Tareas de Robotec en el Hub

Abre **Estado → Tareas Robotec** con el panel desbloqueado. Cada tarjeta muestra el nombre de una tarea, su estado y su fecha. Tócala para leer el siguiente paso; **Volver a tareas** regresa a la lista. Anterior y Siguiente recorren las páginas. No se modifican tareas desde el Hub.

El encabezado indica la última consulta. **Copia guardada / conexión pendiente** significa que hay información guardada pero no se ha configurado la actualización autónoma. **Sincronizado** confirma una consulta completada. Si falla Internet, se conserva la última consulta con su fecha. Las tareas no aparecen en Fuera ni en la vista ambiental.

## Configurar la actualización automática

Se requiere una conexión interna de Notion con acceso a la base original de tareas. El acceso de una aplicación de chat no proporciona automáticamente credenciales a la Raspberry.

1. En el [portal de desarrolladores de Notion](https://app.notion.com/profile/integrations), crea una conexión interna en el espacio del equipo. Configúrala con **Read content**; no necesita insertar ni actualizar contenido ni leer información de usuarios.
2. En Notion, abre la base original de tareas. En su menú **••• → Add connections**, añade la conexión. Compartir únicamente una página con vistas enlazadas puede no dar acceso a la base original.
3. Obtén el identificador **data source** de esa base. El identificador de la página del planner o de una vista no lo sustituye.
4. En la Raspberry, ejecuta desde la carpeta del programa:

   ```bash
   python3 notion_setup.py
   ```

   Introduce el identificador y pega el token cuando lo solicite. El token no se muestra y se guarda en `~/.config/desk-hub/notion.json` con permisos `0600`. No lo escribas como argumento de un comando ni lo publiques en el repositorio.
5. En el Hub, pulsa **Actualizar**. Cuando aparezca **Sincronizado**, verifica las tareas y la fecha de consulta. No hace falta reiniciar el servicio.

La base debe contener `Tarea` (título), `Estado` (selección), `Fecha límite` (fecha), `Siguiente paso` (texto) y, opcionalmente, `Prioridad` (selección). Se excluyen los estados Terminada y Cancelada. El cliente consulta cada cinco minutos y limita las solicitudes manuales a una cada treinta segundos. Admite hasta 500 tareas abiertas; si hay más, conserva la última consulta completa en lugar de reemplazarla por una lista parcial.

La caché se guarda en `~/.local/share/desk-hub/notion-tasks.json` con permisos `0600`. No la incluyas en Git ni en paquetes públicos. Para desconectar, retira el acceso de la conexión en Notion y elimina su archivo de configuración de la Pi. La copia local sigue disponible hasta que se elimine también su archivo de caché y se reinicie el Hub.

Referencias: [autorización y acceso a páginas](https://developers.notion.com/guides/authorization/overview), [capacidades de sólo lectura](https://developers.notion.com/reference/capabilities) y [consulta de fuentes de datos](https://developers.notion.com/reference/query-a-data-source).
