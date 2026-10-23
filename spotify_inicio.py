#!/usr/bin/env python3
"""Inicia Spotify Soloist leyendo una clave privada local."""
import os
from pathlib import Path

from settings import SOLOIST, DEVICE_NAME
if not (Path('/run/user')/str(os.getuid())/'desk-hub.unlocked').is_file():
    raise SystemExit('Desk Hub bloqueado: Spotify no autorizado.')
keyfile = Path.home()/'.config/desk-hub/soloist.key'
if not keyfile.is_file():
    raise SystemExit('Falta ~/.config/desk-hub/soloist.key; genere su clave en Spotify for Developers.')
if keyfile.stat().st_mode & 0o077:
    raise SystemExit('La clave debe tener permisos 600.')
key = keyfile.read_text().strip()
if not key:
    raise SystemExit('La clave esta vacia.')
binary = SOLOIST
os.execv(binary,[binary,'--device-name',DEVICE_NAME,'--api-key',key,
                 '--ws','127.0.0.1:9090','--cache-size','100','--initial-volume','30'])
