#!/usr/bin/env python3
"""Carga serial de un TFT mediante protocolo oficial Nextion, bloques de 4096 bytes."""
import argparse
import hashlib
import os
from pathlib import Path
import select
import termios
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('tft')
p.add_argument('--port',default='/dev/serial/by-id/usb-1a86_USB2.0-Serial-if00-port0')
p.add_argument('--sha256',required=True)
a=p.parse_args()
data=Path(a.tft).read_bytes()
if hashlib.sha256(data).hexdigest().lower()!=a.sha256.lower():
    raise SystemExit('SHA256 diferente: carga cancelada')
fd=os.open(a.port,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
original=termios.tcgetattr(fd)
def configure(baud):
    c=termios.tcgetattr(fd)
    c[0]=c[1]=c[3]=0
    c[2]=termios.CS8|termios.CREAD|termios.CLOCAL
    c[4]=c[5]=baud
    c[6][termios.VMIN]=c[6][termios.VTIME]=0
    termios.tcsetattr(fd,termios.TCSANOW,c)
def write(packet):
    packet=memoryview(packet)
    while packet:
        _,w,_=select.select([],[fd],[],3)
        if not w: raise TimeoutError('UART sin escritura')
        packet=packet[os.write(fd,packet):]
    termios.tcdrain(fd)
def read(seconds,expected=None):
    received=bytearray(); deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        r,_,_=select.select([fd],[],[],max(0,deadline-time.monotonic()))
        if r:
            received.extend(os.read(fd,4096))
            if expected and expected in received: break
    return bytes(received)
try:
    configure(termios.B9600)
    termios.tcflush(fd,termios.TCIOFLUSH)
    write(b'\xff\xff\xff'); time.sleep(.2); read(.2)
    write(b'connect\xff\xff\xff')
    identification=read(2)
    if b'NX8048K070_011' not in identification or b'comok' not in identification:
        raise RuntimeError('Modelo esperado no identificado: '+repr(identification))
    print('Modelo confirmado:',repr(identification),flush=True)
    write(f'whmi-wri {len(data)},115200,0'.encode()+b'\xff\xff\xff')
    time.sleep(.05)
    configure(termios.B115200)
    if b'\x05' not in read(3,b'\x05'): raise RuntimeError('No se recibio ACK inicial')
    for offset in range(0,len(data),4096):
        write(data[offset:offset+4096])
        response=read(5,b'\x05')
        if b'\x05' not in response:
            raise RuntimeError(f'Sin ACK en bloque {offset}: {response.hex()}')
        if offset%32768==0 or offset+4096>=len(data):
            print('Carga',min(offset+4096,len(data)),'/',len(data),flush=True)
    time.sleep(2)
    configure(termios.B9600)
    print('Arranque:',read(5).hex(' '),flush=True)
    write(b'\xff\xff\xff'); time.sleep(.2);read(.2)
    write(b'connect\xff\xff\xff')
    print('Verificacion:',repr(read(2)),flush=True)
finally:
    termios.tcsetattr(fd,termios.TCSANOW,original)
    os.close(fd)
