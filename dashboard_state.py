"""Alarma local de una sola ejecución y sonido breve por PulseAudio."""
import datetime as dt
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import time
import wave


class Alarm:
    def __init__(self, data=None, clock=time.time):
        self.clock = clock
        self.data = dict(hour=9, minute=0, enabled=False, deadline=None)
        if data:
            self.data.update(data)

    def adjust(self, hours=0, minutes=0):
        total = (self.data['hour']*60+self.data['minute']+hours*60+minutes) % 1440
        self.data.update(hour=total//60, minute=total%60)
        if self.data['enabled']:
            self.arm()

    def arm(self):
        now = dt.datetime.fromtimestamp(self.clock())
        target = now.replace(hour=self.data['hour'], minute=self.data['minute'], second=0, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        self.data.update(enabled=True, deadline=target.timestamp())

    def cancel(self):
        self.data.update(enabled=False, deadline=None)

    def snooze(self, minutes=5):
        deadline = self.clock()+minutes*60
        target = dt.datetime.fromtimestamp(deadline)
        self.data.update(enabled=True, deadline=deadline, hour=target.hour, minute=target.minute)

    def poll(self):
        if not self.data['enabled'] or self.data['deadline'] is None:
            return None
        delay = self.clock()-self.data['deadline']
        if delay < 0:
            return None
        self.cancel()
        return 'ring' if delay <= 300 else 'missed'


class AlertSound:
    def __init__(self, directory, stop):
        self.stop = stop
        self.pending = threading.Event()
        self.cancel = threading.Event()
        self.path = Path(directory)/'alert.wav'
        threading.Thread(target=self.worker, daemon=True).start()

    def play(self):
        self.cancel.clear()
        self.pending.set()

    def silence(self):
        self.cancel.set()
        self.pending.clear()

    def worker(self):
        while not self.stop.is_set():
            if not self.pending.wait(.2):
                continue
            self.pending.clear()
            if not shutil.which('paplay'):
                print('Aviso: paplay no disponible', flush=True)
                continue
            try:
                if not self.path.exists():
                    samples = bytearray()
                    rate = 22050
                    for frequency in (523.25, 659.25, 783.99):
                        for i in range(int(rate*.34)):
                            t = i/rate
                            envelope = min(1,t/.015)*max(0,1-t/.34)**2
                            samples.extend(struct.pack('<h',round(4000*envelope*math.sin(2*math.pi*frequency*t))))
                        samples.extend(b'\0\0'*int(rate*.08))
                    with wave.open(str(self.path),'wb') as file:
                        file.setnchannels(1); file.setsampwidth(2); file.setframerate(rate)
                        file.writeframes(samples)
                env = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
                with subprocess.Popen(['paplay',str(self.path)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
                    deadline = time.monotonic()+5
                    while process.poll() is None:
                        if self.cancel.wait(.03) or self.stop.is_set() or time.monotonic()>deadline:
                            process.terminate()
                            break
            except (OSError,subprocess.SubprocessError) as error:
                print('Aviso de audio:',type(error).__name__,flush=True)
