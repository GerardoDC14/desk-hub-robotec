"""Galería privada y filtros locales; cada exportación conserva la foto original."""
from collections import OrderedDict
import heapq
import os
from pathlib import Path
import re
import stat
import threading
import time
import uuid

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import camera_tools as limits


FILTERS = ('Original', 'B/N', 'Sepia', 'Negativo', 'Pop', 'Espejo', 'Boceto')
PHOTO_NAME = re.compile(r'(?:foto|efecto)-[A-Za-z0-9][A-Za-z0-9_-]{0,95}\.jpg\Z')
PREVIEW_SIZE = (96, 54)
MAX_PREVIEWS = 8
MAX_DECODE_PIXELS = 16_000_000


def apply_filter(image, name):
    """Devuelve una imagen RGB nueva del mismo tamaño, sin alterar ``image``."""
    if name not in FILTERS:
        raise ValueError('Filtro no disponible')
    source = image.convert('RGB')
    if name == 'Original': return source
    if name == 'B/N': return ImageOps.grayscale(source).convert('RGB')
    if name == 'Sepia':
        return ImageOps.colorize(ImageOps.grayscale(source), '#362317', '#fff1cf').convert('RGB')
    if name == 'Negativo': return ImageOps.invert(source)
    if name == 'Pop':
        return ImageEnhance.Contrast(ImageEnhance.Color(source).enhance(1.6)).enhance(1.15)
    if name == 'Espejo': return ImageOps.mirror(source)
    edges = ImageOps.grayscale(source).filter(ImageFilter.FIND_EDGES)
    return ImageOps.autocontrast(ImageOps.invert(edges)).convert('RGB')


def preview_pixels(image):
    """Miniatura 16:9 de 96 colores, devuelta como píxeles RGB565 inmutables."""
    canvas = Image.new('RGB', PREVIEW_SIZE, (12, 18, 24))
    thumbnail = ImageOps.contain(image, PREVIEW_SIZE, Image.Resampling.LANCZOS)
    canvas.paste(thumbnail, ((canvas.width-thumbnail.width)//2, (canvas.height-thumbnail.height)//2))
    canvas = canvas.quantize(colors=96, method=Image.Quantize.MEDIANCUT).convert('RGB')
    raw = canvas.tobytes()
    pixels = tuple(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
                   for r, g, b in zip(raw[::3], raw[1::3], raw[2::3]))
    return (*PREVIEW_SIZE, pixels)


class PhotoLibrary:
    """Un trabajador procesa vistas y copias; no toma fotos ni abre servidores.

    El propietario debe pasar ``unlocked=True`` sólo con el panel desbloqueado,
    y llamar ``lock()`` antes de bloquearlo. Cámara y galería comparten ``_cv``;
    ``camera._editing`` reserva el almacenamiento mientras se exporta una copia.
    """
    def __init__(self, camera):
        self.camera = camera
        self.directory = Path(camera.directory)
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise ValueError('La galería requiere una carpeta privada regular')
        self._root = self.directory.resolve(strict=True)
        self._cv = camera._cv
        self._clock = getattr(camera, '_clock', time.monotonic)
        self._closed = False; self._unlocked = False; self._access = 0; self._generation = 0
        self._photos = []; self._selected = ''; self._index = 0; self._filter = FILTERS[0]
        self._listed_at = float('-inf'); self._capture_seen = None
        self._preview = None; self._preview_key = None; self._original_size = None
        self._cache = OrderedDict(); self._failed_key = None
        self._preview_job = None; self._save_job = None; self._working = None
        self._saving = False; self._message = ''; self._error = ''; self._last_saved = ''
        self._thread = threading.Thread(target=self._worker, name='desk-hub-photo-library', daemon=True)
        self._thread.start()

    def _root_valid(self):
        try:
            return (not self.directory.is_symlink() and self.directory.is_dir()
                    and self.directory.resolve(strict=True) == self._root)
        except OSError:
            return False

    @staticmethod
    def _signature(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    def _file_info(self, filename):
        if not isinstance(filename, str) or not PHOTO_NAME.fullmatch(filename) or not self._root_valid():
            raise ValueError('Nombre de foto no válido')
        path = self.directory / filename
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('La foto debe ser un archivo regular')
        return path, info

    def _refresh_locked(self, force=False):
        now = self._clock()
        capture = getattr(self.camera, '_last_filename', '')
        if not force and capture == self._capture_seen and 0 <= now-self._listed_at < 1:
            return
        self._listed_at = now; self._capture_seen = capture
        old = next((entry for entry in self._photos if entry[0] == self._selected), None)
        entries = []
        if self._root_valid():
            def candidates():
                for path in self.directory.iterdir():
                    if not PHOTO_NAME.fullmatch(path.name): continue
                    try:
                        _, info = self._file_info(path.name)
                        yield path.name, self._signature(info)
                    except (OSError, ValueError):
                        continue
            try:
                entries = heapq.nlargest(limits.MAX_PHOTOS, candidates(), key=lambda item: (item[1][3], item[0]))
            except OSError:
                self._error = 'No se pudo leer la carpeta de fotos'
        self._photos = entries
        names = [entry[0] for entry in entries]
        if self._selected in names: self._index = names.index(self._selected)
        else:
            self._index = max(0, min(self._index, len(names)-1))
            self._selected = names[self._index] if names else ''
        current = next((entry for entry in entries if entry[0] == self._selected), None)
        if current != old:
            self._changed_locked()

    def _allowed_locked(self, unlocked):
        if unlocked is not True:
            self.lock(); return False
        if self._closed or getattr(self.camera, '_closed', False): return False
        self._unlocked = True
        return True

    def _valid_locked(self, access):
        return (not self._closed and self._unlocked and access == self._access
                and not getattr(self.camera, '_closed', False))

    def _changed_locked(self):
        self._generation += 1
        self._preview = self._preview_key = self._original_size = None
        self._preview_job = None; self._failed_key = None
        self._error = ''; self._message = ''

    def _key_locked(self):
        entry = next((entry for entry in self._photos if entry[0] == self._selected), None)
        return (entry[0], entry[1], self._filter) if entry else None

    def _queue_preview_locked(self):
        key = self._key_locked()
        if not key or not self._unlocked or self._failed_key == key: return
        public_key = (self._selected, self._filter, self._generation)
        if self._preview_key == public_key: return
        if key in self._cache:
            self._preview, self._original_size = self._cache[key]
            self._cache.move_to_end(key); self._preview_key = public_key
            return
        job = ('preview', key, self._generation, self._access)
        if self._preview_job == job or self._working == job: return
        self._preview_job = job
        self._cv.notify_all()

    def snapshot(self, unlocked=False):
        with self._cv:
            allowed = self._allowed_locked(unlocked)
            if allowed:
                self._refresh_locked(); self._queue_preview_locked()
            if not allowed:
                return dict(status='Galería bloqueada', busy=False, saving=False, ready=False,
                            count=0, index=0, filename='', filter=self._filter, filters=FILTERS,
                            preview=None, preview_key=None, original_size=None, error='', last_saved='')
            busy = bool(self._working or self._preview_job or self._save_job)
            status = ('Guardando copia…' if self._saving else self._error or self._message or
                      ('No hay fotos guardadas' if not self._photos else
                       'Preparando vista…' if self._preview is None else 'Fotos privadas en la Raspberry'))
            return dict(status=status, busy=busy, saving=self._saving, ready=self._preview is not None,
                        count=len(self._photos), index=self._index, filename=self._selected,
                        filter=self._filter, filters=FILTERS, preview=self._preview,
                        preview_key=self._preview_key, original_size=self._original_size,
                        error=self._error, last_saved=self._last_saved)

    def select(self, selection, unlocked=False):
        with self._cv:
            if not self._allowed_locked(unlocked): return False
            self._refresh_locked(force=True)
            if isinstance(selection, str):
                names = [entry[0] for entry in self._photos]
                if selection not in names: return False
                index = names.index(selection)
            elif isinstance(selection, int) and not isinstance(selection, bool):
                if not self._photos: return False
                index = max(0, min(selection, len(self._photos)-1))
            else: return False
            name = self._photos[index][0]
            if name != self._selected:
                self._selected = name; self._index = index; self._changed_locked()
            self._queue_preview_locked()
            return True

    def move(self, step, unlocked=False):
        with self._cv:
            if not self._allowed_locked(unlocked) or not isinstance(step, int) or isinstance(step, bool): return False
            self._refresh_locked(force=True)
            return self.select(self._index+step, unlocked=True)

    def set_filter(self, name, unlocked=False):
        with self._cv:
            if not self._allowed_locked(unlocked) or name not in FILTERS: return False
            self._refresh_locked()
            if name != self._filter:
                self._filter = name; self._changed_locked()
            self._queue_preview_locked()
            return True

    def save_copy(self, unlocked=False):
        with self._cv:
            if not self._allowed_locked(unlocked): return False
            self._refresh_locked(force=True)
            if not self._selected:
                self._message = 'Primero toma una foto'; return False
            if self._filter == 'Original':
                self._message = 'Elige un filtro para guardar una copia'; return False
            if self._saving: return False
            if (self.camera._busy or self.camera._job is not None or self.camera._sequence is not None
                    or getattr(self.camera, '_editing', False)):
                self._message = 'Espera a que termine la cámara'; return False
            files, size = self.camera._usage()
            if files >= limits.MAX_PHOTOS or size+limits.MAX_FILE_BYTES > limits.MAX_STORAGE_BYTES:
                self._message = 'Almacenamiento lleno / retira fotos de la Pi'; return False
            self._error = ''; self._message = ''; self._saving = True
            self.camera._editing = True
            self._save_job = ('save', self._key_locked(), self._generation, self._access)
            self._cv.notify_all()
            return True

    def lock(self):
        with self._cv:
            if self._unlocked or self._preview_job or self._save_job or self._preview is not None or self._cache:
                self._access += 1; self._generation += 1
            self._unlocked = False
            self._preview_job = self._save_job = None
            self._preview = self._preview_key = self._original_size = None
            self._cache.clear(); self._failed_key = None; self._message = self._error = ''
            if not self._working or self._working[0] != 'save':
                self._saving = False; self.camera._editing = False
            self._cv.notify_all()

    def close(self):
        with self._cv:
            if self._closed: return
            self._closed = True
            self.lock(); self._cv.notify_all()
        self._thread.join(timeout=2)

    def _read_image(self, key):
        filename, signature, _ = key
        with self._cv:
            path, info = self._file_info(filename)
            if self._signature(info) != signature:
                raise ValueError('La foto cambió')
            descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or self._signature(info) != signature
                    or not 0 < info.st_size <= limits.MAX_FILE_BYTES):
                raise ValueError('Archivo de foto no válido')
            with Image.open(stream) as source:
                if source.format != 'JPEG' or source.width*source.height > MAX_DECODE_PIXELS:
                    raise ValueError('Formato o tamaño de foto no válido')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGB')
            if self._signature(os.fstat(stream.fileno())) != signature:
                raise ValueError('La foto cambió durante la lectura')
            return image

    def _worker(self):
        while True:
            with self._cv:
                if self._closed: return
                job = self._save_job or self._preview_job
                if job is None:
                    self._cv.wait(timeout=.25); continue
                if job[0] == 'save': self._save_job = None
                else: self._preview_job = None
                self._working = job
            try:
                if job[0] == 'save': self._export(job)
                else: self._make_preview(job)
            except Exception:
                with self._cv:
                    if self._valid_locked(job[3]):
                        if job[0] == 'save': self._error = 'No se pudo guardar la copia'
                        elif job[1] == self._key_locked() and job[2] == self._generation:
                            self._failed_key = job[1]; self._error = 'No se pudo abrir esta foto'
            finally:
                with self._cv:
                    if job[0] == 'save':
                        self._saving = False; self.camera._editing = False
                        self.camera._usage_cache = None
                    self._working = None; self._cv.notify_all()

    def _make_preview(self, job):
        _, key, generation, access = job
        with self._cv:
            if not self._valid_locked(access) or generation != self._generation or key != self._key_locked(): return
        image = self._read_image(key)
        size = image.size
        pixels = preview_pixels(apply_filter(image, key[2]))
        with self._cv:
            if not self._valid_locked(access) or generation != self._generation or key != self._key_locked(): return
            self._cache[key] = (pixels, size); self._cache.move_to_end(key)
            while len(self._cache) > MAX_PREVIEWS: self._cache.popitem(last=False)
            self._preview = pixels; self._original_size = size
            self._preview_key = (key[0], key[2], generation)
            self._error = ''

    def _export(self, job):
        _, key, _, access = job
        temporary = None; destination = None; reservation = None
        try:
            with self._cv:
                if not self._valid_locked(access): return
            image = apply_filter(self._read_image(key), key[2])
            token = uuid.uuid4().hex
            with self._cv:
                if not self._valid_locked(access) or not self._root_valid(): return
                temporary = self.directory / ('.efecto-'+token+'.tmp')
                descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0), 0o600)
            with os.fdopen(descriptor, 'wb') as output:
                image.save(output, format='JPEG', quality=92, optimize=True)
                output.flush(); os.fsync(output.fileno())
            with self._cv:
                if not self._valid_locked(access) or not self._root_valid(): return
                size = temporary.stat().st_size
                files, total = self.camera._usage()
                if not 0 < size <= limits.MAX_FILE_BYTES or files >= limits.MAX_PHOTOS or total > limits.MAX_STORAGE_BYTES:
                    self._message = 'Almacenamiento lleno / retira fotos de la Pi'; return
                os.chmod(temporary, 0o600)
                stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(getattr(self.camera, '_wall_clock', time.time)()))
                for _ in range(12):
                    filename = 'efecto-'+stamp+'-'+uuid.uuid4().hex[:12]+'.jpg'
                    candidate = self.directory / filename
                    try:
                        descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                        try: reservation = self._signature(os.fstat(descriptor))
                        finally: os.close(descriptor)
                        destination = candidate
                        break
                    except FileExistsError:
                        continue
                else:
                    raise OSError('No se pudo reservar un nombre de copia')
                if self._signature(destination.lstat()) != reservation or destination.is_symlink():
                    raise OSError('El nombre reservado cambió')
                # Se sustituye sólo el archivo vacío recién reservado, nunca una foto.
                os.replace(temporary, destination); temporary = None; destination = None
                self._last_saved = filename; self._message = 'Copia guardada en la Raspberry'
                self._listed_at = float('-inf'); self.camera._usage_cache = None
        finally:
            if destination is not None:
                try:
                    if self._signature(destination.lstat()) == reservation and not destination.is_symlink():
                        destination.unlink()
                except OSError: pass
            if temporary is not None:
                try: temporary.unlink(missing_ok=True)
                except OSError: pass
            with self._cv: self.camera._usage_cache = None
