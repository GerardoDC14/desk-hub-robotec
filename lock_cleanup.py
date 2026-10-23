#!/usr/bin/env python3
"""Cierra Spotify y elimina la autorizacion local al detener Desk Hub."""
import os
from pathlib import Path
import subprocess

runtime=Path('/run/user')/str(os.getuid())
(runtime/'desk-hub.unlocked').unlink(missing_ok=True)
env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
subprocess.run(['systemctl','--user','stop','desk-hub-spotify'],env=env,timeout=8,check=False)
