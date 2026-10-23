#!/usr/bin/env python3
"""Genera unidades systemd para el usuario y la ruta actuales, sin instalarlas."""
import getpass
import os
from pathlib import Path
import re


def render(template, username, uid, home, app_dir):
    values = {'USERNAME': username, 'UID': str(uid), 'HOME': str(home), 'APP_DIR': str(app_dir)}
    for key, value in values.items():
        if not value or re.search(r'[\s"\\%\x00-\x1f]', value):
            raise ValueError(f'{key}: utiliza un usuario y rutas sin espacios ni caracteres especiales')
        template = template.replace('@' + key + '@', value)
    return template


if __name__ == '__main__':
    if not hasattr(os, 'getuid') or os.getuid() == 0:
        raise SystemExit('Ejecuta este script en Linux como usuario normal, sin sudo.')
    root = Path(__file__).resolve().parent.parent
    output = root / 'build'
    output.mkdir(exist_ok=True)
    for source in (root / 'systemd').glob('*.service.in'):
        target = output / source.name.removesuffix('.in')
        target.write_text(render(source.read_text(), getpass.getuser(), os.getuid(), Path.home(), root))
        print(target)
