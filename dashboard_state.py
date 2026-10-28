"""Alarma local y avisos repetidos, cancelables y con volumen propio."""
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
from audio_focus import MusicDuck


class Alarm:
    def __init__(self, data=None, clock=time.time):
        self.clock = clock
        self.data = dict(hour=9, minute=0, enabled=False, deadline=None, volume=80)
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
    MAX_SECONDS=180
    REPEAT_GAP=.65

    def __init__(self, directory, stop):
        self.stop=stop
        self.wake=threading.Event()
        self.lock=threading.Lock()
        self.request=None
        self.path=Path(directory)/'alert-v3-alarm.wav'
        self.duck=MusicDuck()
        self.thread=threading.Thread(target=self.worker,daemon=True)
        self.thread.start()

    def play(self,seconds=180,volume=80,kind="alarm"):
        with self.lock:
            self.request=(object(),time.monotonic()+max(.1,min(self.MAX_SECONDS,seconds)),max(0,min(100,volume)),"timer" if kind=="timer" else "alarm")
        self.wake.set()

    def silence(self):
        with self.lock: self.request=None
        self.wake.set()

    def active(self,request):
        with self.lock: current=self.request is request
        return current and not self.stop.is_set() and time.monotonic()<request[1]

    def make_wave(self,kind="alarm"):
        path=self.path.with_name("alert-v3-"+kind+".wav")
        samples=bytearray(); rate=22050
        for frequency in ((880,660) if kind=="timer" else (523.25,659.25,783.99)):
            for i in range(int(rate*.34)):
                t=i/rate
                envelope=min(1,t/.02,(.34-t)/.04)
                samples.extend(struct.pack('<h',round(16000*envelope*math.sin(2*math.pi*frequency*t))))
            samples.extend(b'\0\0'*int(rate*.12))
        with wave.open(str(path),'wb') as file:
            file.setnchannels(1); file.setsampwidth(2); file.setframerate(rate)
            file.writeframes(samples)

    def worker(self):
        while not self.stop.is_set():
            self.wake.wait(.2); self.wake.clear()
            with self.lock: request=self.request
            if request is None: continue
            if not shutil.which('paplay'):
                print('Aviso: paplay no disponible',flush=True)
                with self.lock:
                    if self.request is request: self.request=None
                continue
            try:
                path=self.path.with_name("alert-v3-"+request[3]+".wav")
                if not path.exists(): self.make_wave(request[3])
                env=dict(os.environ,XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
                while self.active(request):
                    self.duck.update()
                    volume=str(round(65536*request[2]/100))
                    with subprocess.Popen(['paplay','--volume='+volume,str(path)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as process:
                        deadline=time.monotonic()+5
                        while process.poll() is None:
                            self.duck.update()
                            if not self.active(request) or time.monotonic()>deadline:
                                process.terminate()
                                try: process.wait(timeout=1)
                                except subprocess.TimeoutExpired: process.kill()
                                break
                            self.wake.wait(.03); self.wake.clear()
                    if not self.active(request): break
                    self.wake.wait(self.REPEAT_GAP); self.wake.clear()
            except (OSError,subprocess.SubprocessError) as error:
                print('Aviso de audio:',type(error).__name__,flush=True)
            self.duck.restore()
            with self.lock:
                if self.request is request: self.request=None
