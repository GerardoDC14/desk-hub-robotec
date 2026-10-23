#!/usr/bin/env python3
"""Diagnóstico Nextion a 9600 baudios, sin dependencias externas."""
import argparse
import os
import select
import termios
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', default='/dev/serial0')
parser.add_argument('--seconds', type=float, default=30, help='Tiempo para pulsar PROBAR')
args = parser.parse_args()
end = b'\xff\xff\xff'
fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
original = termios.tcgetattr(fd)
pending = bytearray()


def receive(seconds):
    frames = []
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        ready, _, _ = select.select([fd], [], [], max(0, until - time.monotonic()))
        if not ready:
            break
        data = os.read(fd, 4096)
        if not data:
            continue
        print('RX:', data.hex(' ').upper(), flush=True)
        pending.extend(data)
        while end in pending:
            cut = pending.index(end)
            frame = bytes(pending[:cut])
            del pending[:cut + 3]
            frames.append(frame)
            if frame.startswith(b'comok'):
                print('Identificación:', frame.decode('ascii', errors='replace'), flush=True)
            elif len(frame) == 2 and frame[0] == 0x66:
                print('Página:', frame[1], flush=True)
            elif len(frame) == 4 and frame[0] == 0x65:
                print(f'Evento: página={frame[1]}, componente={frame[2]}, estado={frame[3]}', flush=True)
            elif frame == b'\x01':
                print('Comando aceptado.', flush=True)
    return frames


def send(command):
    print('TX:', command, flush=True)
    packet = memoryview(command.encode('ascii') + end)
    while packet:
        _, ready, _ = select.select([], [fd], [], 2)
        if not ready:
            raise TimeoutError('UART no disponible para escritura')
        packet = packet[os.write(fd, packet):]
    termios.tcdrain(fd)
    return receive(1.5)


try:
    config = termios.tcgetattr(fd)
    config[0] = 0
    config[1] = 0
    config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    config[3] = 0
    config[4] = termios.B9600
    config[5] = termios.B9600
    config[6][termios.VMIN] = 0
    config[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, config)
    receive(0.3)
    identification = send('connect')
    page = send('sendme')
    if not any(frame.startswith(b'comok') for frame in identification):
        print('No se recibió identificación comok.')
    if b'\x66\x00' not in page:
        print('No se confirmó page0.')
    send('t0.txt="PI CONECTADA"')
    send('ref t0')
    send('get t0.txt')
    print(f'Comprueba PI CONECTADA en la pantalla y pulsa PROBAR durante los próximos {args.seconds:g} segundos.', flush=True)
    events = receive(args.seconds)
    if b'\x65\x00\x02\x00' in events:
        print('CONFIRMADO: evento de b0 al soltar.')
    else:
        print('No se recibió el evento esperado de b0 al soltar.')
    if pending:
        print('Bytes sin terminador:', pending.hex(' ').upper())
finally:
    termios.tcsetattr(fd, termios.TCSANOW, original)
    os.close(fd)
