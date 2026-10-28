"""Cámara local: fotos y timelapse explícitos, sin servidor ni captura al arrancar."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid
from font_metrics import text_width

INTERVALS = (10, 30, 60)
COUNTS = (12, 30, 60)
MAX_PHOTOS = 100
MAX_STORAGE_BYTES = 250 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
PROCESS_TIMEOUT = 20


def camera_command(executable, output=None):
    """Argumentos sin shell. ``output=None`` sólo enumera cámaras."""
    if output is None:
        return [str(executable), '--list-cameras']
    return [str(executable), '--nopreview', '-t', '1000', '--width', '1280',
            '--height', '720', '-o', str(output)]


def camera_present(output):
    return bool(re.search(r'^\s*\d+\s*:\s*\S+', output or '', re.MULTILINE))


class CameraController:
    """Un único trabajador serializa sondeos y capturas.

    Las peticiones requieren ``unlocked=True``; el propietario debe llamar
    ``lock()`` al bloquear el panel. Ninguna sesión se persiste ni se reanuda.
    """
    def __init__(self, directory, popen=subprocess.Popen, which=shutil.which,
                 clock=time.monotonic, wall_clock=time.time):
        self.directory = Path(directory) / 'camera'
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink():
            raise ValueError('La carpeta de cámara no puede ser un enlace.')
        os.chmod(self.directory, 0o700)
        self.executable = which('rpicam-still') or which('libcamera-still')
        self._popen = popen; self._clock = clock; self._wall_clock = wall_clock
        self._cv = threading.Condition(threading.RLock())
        self._closed = False; self._job = None; self._busy = False; self._process = None; self._editing = False
        self._generation = 0; self._sequence = None; self._next_due = None
        self._connected = None; self._last_filename = ''; self._error = ''
        self._completed = 0; self._requested = 0; self._usage_cache = None
        self._status = 'Cámara sin comprobar' if self.executable else 'Faltan herramientas de cámara'
        self._thread = threading.Thread(target=self._worker, name='desk-hub-camera', daemon=True)
        self._thread.start()

    def snapshot(self):
        with self._cv:
            now = self._clock()
            cached = self._usage_cache
            if cached is None or now-cached[0] >= 1 or now < cached[0]:
                cached = (now, *self._usage())
                self._usage_cache = cached
            _, files, size = cached
            return dict(status=self._status, connected=self._connected,
                        available=bool(self.executable), busy=self._busy or self._job is not None or self._editing,
                        timelapse=self._sequence is not None, completed=self._completed,
                        requested=self._requested, last_filename=self._last_filename,
                        error=self._error, photo_count=files, storage_bytes=size,
                        next_seconds=max(0, int(self._next_due-self._clock())) if self._next_due else 0)

    def _usage(self):
        files = 0; size = 0
        for item in self.directory.iterdir():
            try:
                if item.is_file() and not item.is_symlink():
                    size += item.stat().st_size
                    if item.suffix.lower() in ('.jpg', '.jpeg'): files += 1
            except FileNotFoundError:
                pass
        return files, size

    def _room(self):
        files, size = self._usage()
        return files < MAX_PHOTOS and size + MAX_FILE_BYTES <= MAX_STORAGE_BYTES

    def _enqueue(self, kind, unlocked):
        with self._cv:
            if not unlocked or self._closed or self._busy or self._job or self._sequence or self._editing:
                return False
            if not self.executable:
                self._status = 'Instala rpicam-apps para usar la cámara'; return False
            self._error = ''; self._job = (kind, self._generation)
            self._cv.notify_all()
            return True

    def probe(self, unlocked=False):
        return self._enqueue('probe', unlocked)

    def capture(self, unlocked=False):
        return self._enqueue('capture', unlocked)

    def start_timelapse(self, interval=30, count=12, unlocked=False):
        if interval not in INTERVALS or count not in COUNTS: return False
        with self._cv:
            if not unlocked or self._closed or self._busy or self._job or self._sequence or self._editing:
                return False
            if not self.executable:
                self._status = 'Instala rpicam-apps para usar la cámara'; return False
            self._completed = 0; self._requested = count; self._error = ''
            self._sequence = dict(interval=interval, count=count)
            self._next_due = self._clock()
            self._status = 'Timelapse iniciado'
            self._cv.notify_all()
            return True

    def _cancel(self, status):
        with self._cv:
            self._generation += 1; self._sequence = None; self._next_due = None; self._job = None
            process = self._process
            self._status = status
            self._cv.notify_all()
        if process is not None:
            try: process.terminate()
            except (OSError, ProcessLookupError): pass

    def stop_timelapse(self):
        self._cancel('Captura detenida')

    def lock(self):
        self._cancel('Cámara detenida / panel bloqueado')

    def close(self):
        with self._cv:
            if self._closed: return
            self._closed = True
        self._cancel('Cámara detenida')
        self._thread.join(timeout=2)

    def _worker(self):
        while True:
            with self._cv:
                if self._closed: return
                if self._job is None and self._sequence and not self._busy:
                    if self._clock() >= self._next_due:
                        self._job = ('capture', self._generation)
                        self._next_due = self._clock()+self._sequence['interval']
                if self._job is None:
                    self._cv.wait(timeout=0.25); continue
                kind, generation = self._job; self._job = None; self._busy = True
                self._status = 'Buscando cámara…' if kind == 'probe' else 'Tomando foto…'
            try:
                self._execute(kind, generation)
            except Exception:
                # El hilo sigue disponible aunque una herramienta o unidad falle.
                with self._cv:
                    if generation == self._generation:
                        self._error = 'No se pudo completar la operación de cámara'
                        self._status = self._error; self._sequence = None; self._next_due = None
            finally:
                with self._cv:
                    self._busy = False; self._process = None; self._cv.notify_all()

    def _execute(self, kind, generation):
        temporary = None
        try:
            with self._cv:
                if self._closed or generation != self._generation: return
                if kind == 'capture':
                    if not self._room():
                        self._status = 'Almacenamiento lleno / retira fotos de la Pi'
                        self._error = self._status; self._sequence = None; self._next_due = None
                        return
                    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(self._wall_clock()))
                    token = uuid.uuid4().hex[:8]
                    filename = 'foto-'+stamp+'-'+token+'.jpg'
                    destination = self.directory / filename
                    temporary = self.directory / ('.capture-'+token+'.jpg')
                    # El archivo existe con permisos privados antes de abrir la cámara.
                    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.close(descriptor)
                command = camera_command(self.executable, temporary)
                process = self._popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, shell=False)
                self._process = process
            deadline = self._clock()+PROCESS_TIMEOUT
            while True:
                with self._cv:
                    cancelled = self._closed or generation != self._generation
                if cancelled:
                    self._terminate(process); return
                if self._clock() >= deadline:
                    self._terminate(process)
                    raise TimeoutError('La cámara no respondió a tiempo')
                try:
                    output, _ = process.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
            with self._cv:
                if self._closed or generation != self._generation: return
                if process.returncode:
                    self._error = 'No se pudo abrir la cámara / revisa el cable con la Pi apagada'
                    self._status = self._error; self._connected = False
                    self._sequence = None; self._next_due = None
                    return
                if kind == 'probe':
                    self._connected = camera_present(output)
                    self._status = ('OV5647 lista' if 'ov5647' in (output or '').lower() else 'Cámara lista') if self._connected else 'No se detectó cámara'
                    return
                size = temporary.stat().st_size
                files, total = self._usage()
                if size <= 0 or size > MAX_FILE_BYTES or files > MAX_PHOTOS or total > MAX_STORAGE_BYTES:
                    self._error = 'Foto vacía o límite de almacenamiento alcanzado'
                    self._status = self._error; self._sequence = None; self._next_due = None
                    return
                os.chmod(temporary, 0o600)
                temporary.replace(destination)
                self._usage_cache = None
                self._last_filename = filename; self._connected = True
                if self._sequence:
                    self._completed += 1
                    self._status = f'Timelapse / {self._completed} de {self._requested} fotos'
                    if self._completed >= self._requested:
                        self._sequence = None; self._next_due = None; self._status = 'Timelapse terminado'
                else:
                    self._status = 'Foto guardada en la Raspberry'
        finally:
            if temporary is not None:
                try: temporary.unlink(missing_ok=True)
                except OSError: pass
                with self._cv: self._usage_cache = None

    @staticmethod
    def _terminate(process):
        try:
            process.terminate()
            process.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            try: process.kill(); process.communicate(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired): pass
        except (OSError, ProcessLookupError): pass


class CameraViews:
    """Controles de cámara manual; no transmite vídeo ni toma fotos al entrar."""
    def draw_camera(self):
        c = self.theme; camera = getattr(self, 'camera', None)
        self.text('cameratitle',32,76,736,48,0,'Cámara de laboratorio',c['ink'],c['bg'])
        if camera is None:
            self.text('camerastatus',32,140,736,60,0,'Cámara no disponible',c['ink'],c['bg'])
            return
        state = camera.snapshot()
        status = state['status']; status_font = 0 if text_width(status,0)<=736 else 2
        if text_width(status,status_font)>736:
            while status and text_width(status+'...',status_font)>736: status=status[:-1]
            status += '...'
        self.text('camerastatus',32,128,736,32,status_font,status,c['mint'],c['bg'])
        self.text('cameraprivate',32,166,736,26,2,'1280 x 720 / fotos privadas en la Raspberry',c['muted'],c['bg'])
        self.soft_button('cameracapture',32,204,344,52,'Tomando…' if state['busy'] else 'Tomar foto',True,0)
        self.soft_button('cameraprobe',408,204,360,52,'Probar cámara',False,0)
        interval = getattr(self, '_camera_interval', 30); count = getattr(self, '_camera_count', 12)
        self.text('cameraintervallabel',32,272,112,36,2,'Intervalo',c['ink'],c['bg'])
        for i, value in enumerate(INTERVALS):
            self.soft_button('camerainterval'+str(value),148+i*96,272,88,36,str(value)+' s',interval==value,2)
        self.text('cameracountlabel',450,272,80,36,2,'Fotos',c['ink'],c['bg'])
        for i,value in enumerate(COUNTS):
            self.soft_button('cameracount'+str(value),532+i*80,272,76,36,str(value),count==value,2)
        self.soft_button('cameratimelapse',32,326,344,52,'Detener timelapse' if state['timelapse'] else 'Iniciar timelapse',state['timelapse'],0)
        self.soft_button('cameragallery',408,326,360,52,'Galería / '+str(state['photo_count'])+' fotos',False,0)
        detail = str(state['photo_count'])+'/100 fotos / '+str(round(state['storage_bytes']/1048576,1))+' de 250 MiB'
        self.text('camerastorage',32,392,736,28,2,detail,c['muted'],c['bg'],1)

    def touch_camera(self,x,y):
        camera = getattr(self,'camera',None)
        if not getattr(self,'unlocked',False) or camera is None: return False
        state = camera.snapshot(); changed = False
        if 204<=y<256:
            if 32<=x<376: changed = camera.capture(unlocked=True)
            elif 408<=x<768: changed = camera.probe(unlocked=True)
        elif 272<=y<308 and not state['timelapse'] and not state['busy']:
            for i,value in enumerate(INTERVALS):
                if 148+i*96<=x<236+i*96: self._camera_interval=value; changed=True
            for i,value in enumerate(COUNTS):
                if 532+i*80<=x<608+i*80: self._camera_count=value; changed=True
        elif 326<=y<378:
            if 408<=x<768:
                self.navigate('gallery'); return True
            if 32<=x<376:
                if state['timelapse']:
                    camera.stop_timelapse(); changed=True
                else:
                    changed = camera.start_timelapse(getattr(self,'_camera_interval',30),getattr(self,'_camera_count',12),unlocked=True)
        if changed: self.navigate('camera')
        return changed
