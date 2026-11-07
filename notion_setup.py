"""Configura lectura de Notion sin poner la clave en el historial de comandos."""
import getpass
import re
from pathlib import Path
from notion_board import write_private


def main():
    source=input('ID de la fuente de tareas (data source): ').strip()
    if not re.fullmatch(r'[a-fA-F0-9-]{32,36}',source):raise SystemExit('ID no válido')
    token=getpass.getpass('Token de Notion (no se muestra): ').strip()
    if not token or '\n' in token or '\r' in token:raise SystemExit('Token no válido')
    path=Path.home()/'.config/desk-hub/notion.json'
    write_private(path,dict(data_source=source,token=token))
    print('Conexión guardada. En Estado → Tareas Robotec, pulsa Actualizar.')


if __name__=='__main__':main()
