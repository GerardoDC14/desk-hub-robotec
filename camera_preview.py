"""Encuadres MJPEG en memoria: búfer acotado y sin grabación ni servidor."""
import os
import select
import time

MAX_FRAME_BYTES = 2 * 1024 * 1024


class JpegFrames:
    def __init__(self): self.buffer=bytearray()

    def feed(self, data):
        self.buffer.extend(data); newest=None
        while True:
            start=self.buffer.find(b'\xff\xd8')
            if start<0:
                self.buffer[:]=self.buffer[-1:] if self.buffer.endswith(b'\xff') else b''
                break
            if start: del self.buffer[:start]
            end=self.buffer.find(b'\xff\xd9',2)
            if end<0:
                if len(self.buffer)>MAX_FRAME_BYTES:
                    self.buffer.clear(); raise ValueError('Encuadre demasiado grande')
                break
            if end+2>MAX_FRAME_BYTES:
                self.buffer.clear(); raise ValueError('Encuadre demasiado grande')
            newest=bytes(self.buffer[:end+2]); del self.buffer[:end+2]
        return newest


def preview_command(executable):
    return [str(executable),'--nopreview','--timeout','0','--codec','mjpeg',
            '--width','640','--height','360','--framerate','4','--quality','85','-o','-']


def read_mjpeg(process, cancelled, clock=time.monotonic):
    """Lee sin bloquear la cancelación; no almacena una cola de fotogramas."""
    parser=JpegFrames(); last=clock(); started=last; seen=False
    descriptor=process.stdout.fileno()
    while not cancelled():
        ready,_,_=select.select([descriptor],[],[],.15)
        if not ready:
            if clock()-last>(4 if seen else 8): raise TimeoutError('Cámara sin encuadres')
            continue
        data=os.read(descriptor,65536)
        if not data:
            if cancelled(): return
            raise OSError('Se interrumpió el encuadre')
        frame=parser.feed(data)
        if frame:
            last=clock(); seen=True
            # Dejar estabilizar exposición y balance antes de enseñar la primera imagen.
            if last-started>=.5 and not cancelled(): yield frame
