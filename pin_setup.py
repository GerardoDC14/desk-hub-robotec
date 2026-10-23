#!/usr/bin/env python3
"""Configura el PIN local sin guardarlo en texto plano."""
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets

def verify_pin(pin,record):
    if not pin.isdigit() or len(pin)!=6: return False
    value=hashlib.pbkdf2_hmac('sha256',pin.encode(),bytes.fromhex(record['salt']),record['iterations']).hex()
    return secrets.compare_digest(value,record['hash'])

if __name__=='__main__':
    pin=getpass.getpass('PIN de seis digitos: ')
    if len(pin)!=6 or not pin.isdigit(): raise SystemExit('Se requieren seis digitos.')
    if getpass.getpass('Repite el PIN: ')!=pin: raise SystemExit('Los PIN no coinciden.')
    directory=Path.home()/'.config/desk-hub'; directory.mkdir(parents=True,exist_ok=True); directory.chmod(0o700)
    salt=secrets.token_bytes(16); iterations=120000
    record=dict(salt=salt.hex(),iterations=iterations,hash=hashlib.pbkdf2_hmac('sha256',pin.encode(),salt,iterations).hex())
    path=directory/'lock.json'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as file: json.dump(record,file)
    path.chmod(0o600)
    print('PIN configurado en archivo privado.')
