"""Configuración de instalación mediante variables de entorno."""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SOLOIST = str(APP_DIR / 'spotify' / 'soloist')
GITHUB_USER = os.environ.get('DESK_HUB_GITHUB_USER', 'GerardoDC14')
LOCATION = os.environ.get('DESK_HUB_LOCATION', 'Zapopan')
LATITUDE = float(os.environ.get('DESK_HUB_LATITUDE', '20.72'))
LONGITUDE = float(os.environ.get('DESK_HUB_LONGITUDE', '-103.39'))
TIMEZONE = os.environ.get('DESK_HUB_TIMEZONE', 'America/Mexico_City')
DEVICE_NAME = os.environ.get('DESK_HUB_DEVICE_NAME', 'Desk Hub Robotec')
