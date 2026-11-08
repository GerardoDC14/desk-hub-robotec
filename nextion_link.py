"""Texto seguro y envío UART con barrera de ejecución entre paquetes."""
from collections import deque
import time
import unicodedata

END = b'\xff\xff\xff'
ERRORS = {0x00,0x02,0x03,0x04,0x05,0x11,0x12,0x1a,0x1b,0x1c,0x1d,0x1e,0x1f,0x20,0x23,0x24}
# Sólo se repiten operaciones de dibujo: nunca páginas, ajustes ni acciones.
REPLAYABLE_DRAWING = {b'fill',b'xstr',b'cirs',b'cir',b'line',b'draw',b'cls'}


def drawing_summary(batch):
    """Diagnóstico sin títulos, texto de tareas, PIN ni píxeles de fotografías."""
    commands=batch.split(END)[:-1]
    operations=sorted({c.partition(b' ')[0] for c in commands})
    names=','.join(op.decode('ascii','replace') if op in REPLAYABLE_DRAWING else 'otra' for op in operations)
    return f'operaciones={names}; instrucciones={len(commands)}; bytes={len(batch)}'


def safe_text(value, limit=160):
    """Nunca permitir comillas, controles ni un terminador dentro de xstr."""
    value = unicodedata.normalize('NFKC', str(value))
    value = value.translate(str.maketrans({'"':"'",'\\':'/','“':"'",'”':"'",'’':"'",'—':'-','–':'-','…':'...'}))
    value = ''.join(' ' if unicodedata.category(c).startswith('C') or c.isspace() else c for c in value)
    value = value.encode('latin-1', 'replace').decode('latin-1').replace('\xff','?')
    return ' '.join(value.split())[:limit]


class NextionLink:
    """Un escritor; cada lote espera get sys0 antes de enviar el siguiente.

    bkcmd=2 informa errores. La respuesta numérica de get sys0 confirma que
    Nextion consumió las instrucciones anteriores. Los toques se conservan.
    """
    def __init__(self, write, receive, parser, clock=time.monotonic, max_batch=240):
        if max_batch not in (240,960): raise ValueError('Tamaño de lote no admitido')
        self.max_batch=max_batch
        self.write, self.receive, self.parser, self.clock = write, receive, parser, clock
        self.pending = deque()
        # Sólo una barrera de ejecución confirmada acredita actividad del panel.
        self.last_confirmed = None

    def send(self, commands):
        packets = []
        for command in commands:
            packet = command.encode('latin-1', errors='strict') + END
            if END in packet[:-3] or len(packet)>240:
                raise ValueError('Instrucción Nextion inválida o demasiado larga')
            packets.append(packet)
        # También se cuentan los bytes de la barrera; mantener holgura de RX.
        batch = b''
        for packet in packets:
            if len(batch)+len(packet)>self.max_batch:
                self._flush(batch); batch=b''
            batch += packet
        if batch: self._flush(batch)

    def _flush(self, batch, allow_replay=True):
        if not batch: return
        self.write(batch+b'get sys0'+END)
        deadline = self.clock()+1.5
        errors=[]
        while self.clock()<deadline:
            raw = self.receive(min(.05,max(0,deadline-self.clock())))
            confirmed=False
            for frame in self.parser.feed(raw):
                if frame in (b'\x88',b'\x00\x00\x00'):
                    raise OSError('Nextion reiniciada durante el dibujo')
                if len(frame)==1 and frame[0] in ERRORS: errors.append(frame[0])
                elif len(frame)==5 and frame[0]==0x71:
                    confirmed=True
                else: self.pending.append(frame)
            if confirmed:
                if errors:
                    codes=','.join(f'{e:02x}' for e in errors)
                    commands=batch.split(END)[:-1]
                    if (allow_replay and set(errors)<={0x1e,0x24} and
                            all(c.partition(b' ')[0] in REPLAYABLE_DRAWING for c in commands)):
                        # La barrera llegó: el lote terminó, pero parte del dibujo
                        # fue rechazado. Rehacerlo una sola vez, orden por orden.
                        # Un timeout, reinicio o segundo rechazo se propaga.
                        self.max_batch=240
                        for command in commands: self._flush(command+END,allow_replay=False)
                        print(f'UART: dibujo recuperado; codigos={codes}; {drawing_summary(batch)}',flush=True)
                        return
                    raise OSError('Nextion rechazó dibujo: '+codes+'; '+drawing_summary(batch))
                self.last_confirmed = self.clock()
                return
        raise TimeoutError('Nextion no confirmó el lote de dibujo')
