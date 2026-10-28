"""Integración Soloist por eventos locales, con consulta de respaldo y caché de portadas."""
import json
import os
import queue
import select
import subprocess
import time
from music_state import apply_event, control_ready
from settings import SOLOIST


class MusicClient:
    def reset_music_session(self):
        with self.lock:
            self.music_session=getattr(self,'music_session',0)+1
            self.music.update(is_active=False,logged_in=False,_ready=False,_epoch=self.music.get('_epoch',0)+1)
            self.music_stream_online=False
        while not self.music_commands.empty():
            try: self.music_commands.get_nowait()
            except queue.Empty: break

    def queue_music(self,command):
        with self.lock:
            if not self.unlocked or not control_ready(self.music): return False
            envelope=dict(command=command,created=time.monotonic(),session=getattr(self,'music_session',0),epoch=self.music.get('_epoch',0),uri=self.music.get('uri',''))
        self.music_commands.put(envelope)
        return True

    def command_current(self,envelope):
        with self.lock:
            return (self.unlocked and control_ready(self.music) and time.monotonic()-envelope['created']<2
                    and envelope['session']==getattr(self,'music_session',0) and envelope['epoch']==self.music.get('_epoch',0)
                    and (envelope['command'][0] not in ('seek','next','prev','play','pause') or envelope['uri']==self.music.get('uri','')))

    def music_connection_lost(self,session):
        with self.lock:
            if session!=getattr(self,'music_session',0): return False
            if self.music_stream_online:
                self.music['_ready']=False
                self.music['_epoch']=self.music.get('_epoch',0)+1
                self.music_revision=getattr(self,'music_revision',0)+1
            self.music_stream_online=False
            if hasattr(self,'music_refresh'): self.music_refresh.set()
        return True

    def accept_music(self,event,token=None,session=None):
        with self.lock:
            if session is not None and session!=getattr(self,'music_session',0): return False
            if token is not None and token!=getattr(self,'music_revision',0): return False
            if event.get('type') in ('auth_state','device_changed') and hasattr(self,'music_refresh'):
                self.music_refresh.set()
            self.last_music_seen=time.monotonic()
            if event.get('type')!='queue_changed': self.music_revision=getattr(self,'music_revision',0)+1
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
            session=getattr(self,'music_session',0)
            try:
                process = subprocess.Popen([SOLOIST,'ctl','-w','127.0.0.1:9090','trace'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                self.music_event_process = process
                buffer = b''
                while not self.stop.is_set() and self.unlocked and session==getattr(self,'music_session',0) and process.poll() is None:
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
                        with self.lock:
                            if session==getattr(self,'music_session',0): self.music_stream_online=True
                        self.accept_music(event,session=session)
            except (OSError,ValueError):
                pass
            finally:
                self.music_connection_lost(session)
                if self.music_event_process is process: self.music_event_process=None
                if process and process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
            self.stop.wait(1)

    def music_worker(self):
        self.ready.wait()
        next_poll=next_queue=0
        while not self.stop.is_set():
            try: envelope=self.music_commands.get(timeout=.1)
            except queue.Empty: envelope=None
            if not self.unlocked: continue
            try:
                if envelope and self.command_current(envelope):
                    subprocess.run([SOLOIST,'ctl','-w','127.0.0.1:9090',*envelope['command']],timeout=3,capture_output=True,check=True)
                    # La confirmacion de la orden no equivale al cambio de reproduccion.
                    if not self.music_stream_online: next_poll=0
                next_poll,next_queue=self.music_observations(next_poll,next_queue)
            except (OSError,subprocess.SubprocessError,ValueError):
                next_poll=time.monotonic()+3; next_queue=time.monotonic()+15

    def music_observations(self,next_poll,next_queue):
        # Los toques pendientes preceden a consultas opcionales. Una lectura
        # tampoco debe ocupar los dos segundos de validez de la siguiente orden.
        if self.stop.is_set() or not self.music_commands.empty(): return next_poll,next_queue
        refresh=getattr(self,'music_refresh',None)
        if refresh and refresh.is_set(): refresh.clear(); next_poll=0
        if time.monotonic()>=next_poll:
            with self.lock:
                token=getattr(self,'music_revision',0); session=getattr(self,'music_session',0)
            result=subprocess.run([SOLOIST,'ctl','-w','127.0.0.1:9090','now','--json'],timeout=1,capture_output=True,check=True)
            self.accept_music(json.loads(result.stdout),token=token,session=session)
            with self.lock: ready=control_ready(self.music)
            next_poll=time.monotonic()+(15 if self.music_stream_online and ready else 1)
        if (not self.stop.is_set() and self.music_commands.empty()
                and self.screen in ('music','music_options') and time.monotonic()>=next_queue):
            with self.lock:
                token=getattr(self,'music_revision',0); session=getattr(self,'music_session',0)
            result=subprocess.run([SOLOIST,'ctl','-w','127.0.0.1:9090','queue','1','--json'],timeout=1,capture_output=True,check=True)
            event=json.loads(result.stdout); event['type']='queue_changed'
            self.accept_music(event,token=token,session=session)
            next_queue=time.monotonic()+15
        return next_poll,next_queue

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
