"""Integración Soloist por eventos locales, con consulta de respaldo y caché de portadas."""
import json
import os
import queue
import select
import subprocess
import time
from music_state import apply_event
from settings import SOLOIST


class MusicClient:
    def accept_music(self,event):
        with self.lock:
            previous = self.music.get('cover')
            apply_event(self.music,event)
            cover = self.music.get('cover')
            if cover != previous:
                self.images.pop('music',None)
            if cover and cover in self.cover_cache:
                self.images['music'] = (cover,self.cover_cache[cover])
                self.cover_cache.move_to_end(cover)
                self.cover_requested = None
                return
            if not cover:
                self.cover_requested = None
                return
            if cover == self.cover_requested:
                return
            self.cover_requested = cover
        while not self.image_jobs.empty():
            try: self.image_jobs.get_nowait()
            except queue.Empty: break
        self.image_jobs.put(cover)

    def music_events(self):
        self.ready.wait()
        while not self.stop.is_set():
            if not self.unlocked:
                self.stop.wait(.2)
                continue
            process = None
            try:
                process = subprocess.Popen([SOLOIST,'ctl','-w','127.0.0.1:9090','trace'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                self.music_event_process = process
                buffer = b''
                while not self.stop.is_set() and self.unlocked and process.poll() is None:
                    if not select.select([process.stdout],[],[],.15)[0]:
                        continue
                    chunk = os.read(process.stdout.fileno(),65536)
                    if not chunk: break
                    buffer += chunk
                    if len(buffer)>2_000_000: raise ValueError('Evento demasiado grande')
                    while b'\n' in buffer:
                        line,buffer = buffer.split(b'\n',1)
                        start = line.find(b'{')
                        if start<0: continue
                        try: event = json.loads(line[start:])
                        except ValueError: continue
                        self.music_stream_online = True
                        self.accept_music(event)
            except (OSError,ValueError):
                pass
            finally:
                self.music_stream_online = False
                self.music_event_process = None
                if process and process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
            self.stop.wait(1)

    def music_worker(self):
        self.ready.wait()
        next_poll = next_queue = 0
        while not self.stop.is_set():
            try: command = self.music_commands.get(timeout=.1)
            except queue.Empty: command = None
            if not self.unlocked:
                continue
            try:
                if command:
                    subprocess.run([SOLOIST,'ctl','-w','127.0.0.1:9090',*command],timeout=3,capture_output=True,check=True)
                    if not self.music_stream_online: next_poll = 0
                if time.monotonic()>=next_poll:
                    result = subprocess.run([SOLOIST,'ctl','-w','127.0.0.1:9090','now','--json'],timeout=3,capture_output=True,check=True)
                    self.accept_music(json.loads(result.stdout))
                    next_poll = time.monotonic()+(30 if self.music_stream_online else 1)
                if self.screen=='music' and time.monotonic()>=next_queue:
                    result = subprocess.run([SOLOIST,'ctl','-w','127.0.0.1:9090','queue','1','--json'],timeout=3,capture_output=True,check=True)
                    event = json.loads(result.stdout)
                    event['type'] = 'queue_changed'
                    self.accept_music(event)
                    next_queue = time.monotonic()+15
            except (OSError,subprocess.SubprocessError,ValueError):
                next_poll = time.monotonic()+3
                next_queue = time.monotonic()+15

    def cover_worker(self):
        while not self.stop.is_set():
            try: cover = self.image_jobs.get(timeout=.5)
            except queue.Empty: continue
            with self.lock:
                if cover != self.music.get('cover'): continue
            try:
                pixels = self.decode_image(cover)
                with self.lock:
                    self.cover_cache[cover] = pixels
                    self.cover_cache.move_to_end(cover)
                    while len(self.cover_cache)>8: self.cover_cache.popitem(last=False)
                    if self.music.get('cover')==cover: self.images['music'] = (cover,pixels)
            except Exception as error:
                with self.lock:
                    if self.cover_requested == cover: self.cover_requested = None
                print('Portada:',type(error).__name__,flush=True)
