"""Negociación reversible; baud es volátil y nunca escribe bauds/EEPROM."""
import time


def negotiate_speed(set_rate, send, receive, target=921600, clock=time.monotonic, sleep=time.sleep):
    if target not in (115200,230400,921600): raise ValueError('Velocidad UART no admitida')
    rates=list(dict.fromkeys((target,115200,9600,230400,921600)))
    def probe(rate):
        set_rate(rate)
        # Un sondeo a otra velocidad puede dejar bytes incompletos en Nextion.
        # Vaciar con el terminador y repetir en la MISMA velocidad antes de
        # descartarla; no volver a cambiar baud entre estos dos intentos.
        for _ in range(2):
            send(''); send('sendme')
            deadline=clock()+.65; raw=b''
            while clock()<deadline:
                raw=(raw+receive(.03))[-4096:]
                if b'\x66\x00\xff\xff\xff' in raw: return True
        return False
    found=next((rate for rate in rates if probe(rate)),None)
    if found is None: raise RuntimeError('Pantalla sin respuesta a las velocidades admitidas')
    if found==target: return found
    send('baud='+str(target)); sleep(.12)
    if probe(target): return target
    # La orden pudo rechazarse o la nueva velocidad resultar inestable.
    for rate in list(dict.fromkeys((found,115200,9600,230400,921600))):
        if not probe(rate): continue
        if rate==115200: return rate
        send('baud=115200'); sleep(.12)
        if probe(115200): return 115200
    raise RuntimeError('No se pudo recuperar la comunicación UART')
