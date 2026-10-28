"""Filtros no destructivos, almacenamiento privado y cancelación de la galería."""
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import photo_library
from photo_library import FILTERS, PhotoLibrary, apply_filter, preview_pixels


class FakeCamera:
    def __init__(self, root):
        self.directory = Path(root) / 'camera'; self.directory.mkdir(mode=0o700)
        self._cv = threading.Condition(threading.RLock())
        self._clock = time.monotonic; self._wall_clock = lambda: 1793116800
        self._busy = False; self._job = None; self._sequence = None; self._closed = False
        self._editing = False; self._last_filename = ''; self._usage_cache = ('cached',)

    def _usage(self):
        files = size = 0
        for item in self.directory.iterdir():
            if item.is_file() and not item.is_symlink():
                size += item.stat().st_size
                if item.suffix.lower() in ('.jpg', '.jpeg'): files += 1
        return files, size


class FilterTests(unittest.TestCase):
    def test_all_seven_filters_are_deterministic_rgb_same_size_and_non_destructive(self):
        image = Image.new('RGB', (24, 16))
        image.putdata([(x*9 % 256, x*31 % 256, x*7 % 256) for x in range(24*16)])
        original = image.tobytes()
        self.assertEqual(FILTERS, ('Original', 'B/N', 'Sepia', 'Negativo', 'Pop', 'Espejo', 'Boceto'))
        for name in FILTERS:
            with self.subTest(name=name):
                result = apply_filter(image, name)
                self.assertEqual(result.mode, 'RGB'); self.assertEqual(result.size, image.size)
                self.assertEqual(result.tobytes(), apply_filter(image, name).tobytes())
                self.assertEqual(image.tobytes(), original); self.assertIsNot(result, image)
        self.assertEqual(apply_filter(image, 'Original').tobytes(), original)
        with self.assertRaises(ValueError): apply_filter(image, '../outside')

    def test_mirror_negative_and_grayscale_have_expected_pixel_meaning(self):
        image = Image.new('RGB', (2, 1)); image.putdata([(10, 50, 90), (200, 120, 20)])
        def pixels(name):
            result = apply_filter(image, name)
            return [result.getpixel((x, 0)) for x in range(2)]
        self.assertEqual(pixels('Espejo'), [(200, 120, 20), (10, 50, 90)])
        self.assertEqual(pixels('Negativo'), [(245, 205, 165), (55, 135, 235)])
        self.assertTrue(all(r == g == b for r, g, b in pixels('B/N')))

    def test_preview_is_a_bounded_immutable_rgb565_grid(self):
        image = Image.new('RGB', (80, 160), (23, 180, 90))
        preview = preview_pixels(image)
        self.assertEqual(preview[:2], (96, 54)); self.assertEqual(len(preview[2]), 96*54)
        self.assertIsInstance(preview[2], tuple)
        self.assertTrue(all(0 <= value <= 65535 for value in preview[2]))
        self.assertLessEqual(len(set(preview[2])), 96)
        self.assertEqual(preview, preview_pixels(image))


class PhotoLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary.cleanup)
        self.camera = FakeCamera(self.temporary.name)
        self.library = None

    def start(self):
        if self.library is None:
            self.library = PhotoLibrary(self.camera); self.addCleanup(self.library.close)
        return self.library

    def photo(self, name='foto-original.jpg', color=(180, 50, 25), size=(64, 36), stamp=None, exif=None):
        path = self.camera.directory / name
        image = Image.new('RGB', size, color)
        image.save(path, 'JPEG', **({'exif': exif} if exif is not None else {}))
        os.chmod(path, 0o600)
        if stamp is not None: os.utime(path, ns=(stamp*1_000_000_000, stamp*1_000_000_000))
        return path

    def wait(self, predicate, timeout=4):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            result = predicate()
            if result: return result
            time.sleep(.005)
        self.fail('El trabajador de galería no terminó a tiempo')

    def ready(self):
        library = self.start()
        return self.wait(lambda: (state if (state := library.snapshot(unlocked=True))['ready'] else None))

    def idle(self):
        def check():
            with self.library._cv:
                return self.library._working is None and self.library._save_job is None and self.library._preview_job is None
        self.wait(check)

    def effects(self):
        return list(self.camera.directory.glob('efecto-*.jpg'))

    def test_starts_locked_without_loading_images_or_taking_photos(self):
        self.photo()
        with patch('photo_library.Image.open', side_effect=AssertionError('Lectura no autorizada')):
            library = self.start(); state = library.snapshot()
            self.assertEqual(state['count'], 0); self.assertIsNone(state['preview'])
            self.assertFalse(library.select(0)); self.assertFalse(library.move(1))
            self.assertFalse(library.set_filter('Sepia')); self.assertFalse(library.save_copy())
        self.assertEqual(len(list(self.camera.directory.glob('*.jpg'))), 1)

    def test_newest_first_selection_stays_on_filename_and_indices_clamp(self):
        old = self.photo('foto-old.jpg', stamp=10); new = self.photo('foto-new.jpg', stamp=20)
        library = self.start(); self.assertEqual(self.ready()['filename'], new.name)
        library.select(old.name, unlocked=True); self.assertEqual(self.ready()['index'], 1)
        newest = self.photo('foto-newest.jpg', stamp=30)
        self.camera._last_filename = newest.name
        state = library.snapshot(unlocked=True)
        self.assertEqual(state['filename'], old.name); self.assertEqual(state['index'], 2)
        library.move(-1000, unlocked=True); self.assertEqual(self.ready()['filename'], newest.name)
        library.select(1000, unlocked=True); self.assertEqual(self.ready()['filename'], old.name)
        old.unlink(); library.select(1000, unlocked=True)
        self.assertEqual(self.ready()['filename'], new.name)

    def test_list_is_cached_for_one_second_but_capture_filename_refreshes_immediately(self):
        now = [20.0]; self.camera._clock = lambda: now[0]
        self.photo('foto-one.jpg'); library = self.start(); self.ready()
        with self.camera._cv, patch.object(library, '_file_info', wraps=library._file_info) as info:
            for _ in range(30): library.snapshot(unlocked=True)
            info.assert_not_called()
            self.photo('foto-two.jpg'); self.camera._last_filename = 'foto-two.jpg'
            self.assertEqual(library.snapshot(unlocked=True)['count'], 2)
            self.assertGreater(info.call_count, 0)
            info.reset_mock(); now[0] += 1.01
            library.snapshot(unlocked=True); self.assertGreater(info.call_count, 0)

    def test_traversal_unsupported_names_and_non_regular_paths_are_excluded(self):
        good = self.photo('foto-good.jpg')
        for name in ('private.jpg', 'foto-bad.jpeg', 'foto-space here.jpg'):
            self.photo(name)
        if os.name != 'nt': self.photo('foto-quote".jpg')
        (self.camera.directory / 'foto-folder.jpg').mkdir()
        library = self.start(); state = self.ready()
        self.assertEqual(state['count'], 1); self.assertEqual(state['filename'], good.name)
        for name in ('../foto-good.jpg', str(good.resolve()), 'foto-folder.jpg', 'private.jpg', 'foto-quote".jpg'):
            self.assertFalse(library.select(name, unlocked=True), name)
        self.assertFalse(library.select(True, unlocked=True)); self.assertFalse(library.move('1', unlocked=True))

    def test_symlinks_and_hardlinks_to_other_files_are_not_loaded(self):
        good = self.photo('foto-good.jpg')
        outside = Path(self.temporary.name) / 'outside.jpg'; Image.new('RGB', (20, 20)).save(outside)
        try:
            (self.camera.directory / 'foto-link.jpg').symlink_to(outside)
        except OSError:
            pass  # Algunas cuentas de Windows no tienen permiso para crear symlinks.
        try: os.link(outside, self.camera.directory / 'foto-hardlink.jpg')
        except OSError: pass
        library = self.start(); state = self.ready()
        self.assertEqual(state['count'], 1); self.assertEqual(state['filename'], good.name)
        self.assertFalse(library.select('foto-link.jpg', unlocked=True))
        self.assertFalse(library.select('foto-hardlink.jpg', unlocked=True))

    def test_corrupt_and_oversized_files_fail_without_killing_worker(self):
        broken = self.camera.directory / 'foto-corrupt.jpg'; broken.write_bytes(b'not a jpeg')
        library = self.start(); library.snapshot(unlocked=True)
        self.wait(lambda: library.snapshot(unlocked=True)['error'])
        self.assertFalse(library.snapshot(unlocked=True)['ready'])
        good = self.photo('foto-good.jpg'); library.select(good.name, unlocked=True)
        self.assertEqual(self.ready()['filename'], good.name)
        with patch('camera_tools.MAX_FILE_BYTES', 1):
            library.set_filter('Negativo', unlocked=True)
            self.wait(lambda: library.snapshot(unlocked=True)['error'])
            self.assertFalse(library.snapshot(unlocked=True)['ready'])

    def test_exif_orientation_is_applied_and_not_copied_to_saved_image(self):
        exif = Image.Exif(); exif[274] = 6
        original = self.photo(size=(40, 20), exif=exif)
        before = original.read_bytes(); library = self.start()
        self.assertEqual(self.ready()['original_size'], (20, 40))
        library.set_filter('Espejo', unlocked=True); self.ready()
        self.assertTrue(library.save_copy(unlocked=True)); self.wait(lambda: self.effects())
        self.idle()
        with Image.open(self.effects()[0]) as image:
            self.assertEqual(image.size, (20, 40)); self.assertEqual(len(image.getexif()), 0)
        self.assertEqual(original.read_bytes(), before)

    def test_export_is_full_size_private_unique_and_preserves_original(self):
        original = self.photo(size=(1280, 720)); digest = hashlib.sha256(original.read_bytes()).hexdigest()
        library = self.start(); self.ready()
        self.assertFalse(library.save_copy(unlocked=True))
        self.assertIn('Elige un filtro', library.snapshot(unlocked=True)['status'])
        library.set_filter('Sepia', unlocked=True); self.ready()
        for expected in (1, 2):
            self.assertTrue(library.save_copy(unlocked=True))
            self.wait(lambda: len(self.effects()) == expected); self.idle()
        self.assertEqual(len({path.name for path in self.effects()}), 2)
        for copy in self.effects():
            self.assertRegex(copy.name, r'^efecto-\d{8}-\d{6}-[a-f0-9]{12}\.jpg$')
            with Image.open(copy) as image:
                self.assertEqual(image.format, 'JPEG'); self.assertEqual(image.size, (1280, 720))
                self.assertEqual(image.mode, 'RGB')
            if os.name != 'nt': self.assertEqual(stat.S_IMODE(copy.stat().st_mode), 0o600)
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), digest)
        self.assertIsNone(self.camera._usage_cache); self.assertFalse(self.camera._editing)
        self.assertFalse(list(self.camera.directory.glob('.efecto-*')))

    def test_export_creation_is_private_and_existing_effect_name_is_not_overwritten(self):
        self.photo(stamp=20)
        stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(self.camera._wall_clock()))
        existing = self.photo('efecto-'+stamp+'-'+'a'*12+'.jpg', stamp=10)
        previous = existing.read_bytes(); library = self.start(); self.ready()
        library.set_filter('Negativo', unlocked=True); self.ready()
        tokens = [SimpleNamespace(hex=letter*32) for letter in ('b', 'a', 'c')]
        real_open = os.open
        with patch('photo_library.uuid.uuid4', side_effect=tokens), patch('photo_library.os.open', wraps=real_open) as opened:
            self.assertTrue(library.save_copy(unlocked=True)); self.idle()
        self.assertEqual(len(self.effects()), 2); self.assertEqual(existing.read_bytes(), previous)
        creates = [call.args for call in opened.call_args_list if call.args[1] & os.O_CREAT]
        self.assertGreaterEqual(len(creates), 2)
        self.assertTrue(all(args[1] & os.O_EXCL and args[2] == 0o600 for args in creates))

    def test_save_rejects_camera_jobs_timelapse_and_existing_export_reservation(self):
        self.photo(); library = self.start(); self.ready(); library.set_filter('Pop', unlocked=True); self.ready()
        for attribute, value in (('_busy', True), ('_job', ('capture', 1)), ('_sequence', {}), ('_editing', True)):
            with self.subTest(attribute=attribute):
                setattr(self.camera, attribute, value)
                self.assertFalse(library.save_copy(unlocked=True))
                self.assertIn('Espera', library.snapshot(unlocked=True)['status'])
                setattr(self.camera, attribute, False if attribute in ('_busy', '_editing') else None)
        self.assertEqual(self.effects(), [])

    def test_count_cap_and_reserved_bytes_include_capture_temporary_files(self):
        self.photo(); library = self.start(); self.ready(); library.set_filter('B/N', unlocked=True); self.ready()
        with patch.object(self.camera, '_usage', return_value=(100, 1000)):
            self.assertFalse(library.save_copy(unlocked=True))
        self.assertIn('Almacenamiento lleno', library.snapshot(unlocked=True)['status'])
        pending = self.camera.directory / '.capture-left.jpg'; pending.write_bytes(b'x'*300)
        files, size = self.camera._usage(); self.assertEqual(files, 2)
        with patch('camera_tools.MAX_STORAGE_BYTES', size+photo_library.limits.MAX_FILE_BYTES-1):
            self.assertFalse(library.save_copy(unlocked=True))
        self.assertFalse(self.camera._editing); self.assertEqual(self.effects(), [])

    def test_list_is_limited_to_newest_hundred_files(self):
        for index in range(105):
            path = self.camera.directory / ('foto-'+str(index)+'.jpg'); path.write_bytes(b'not a jpeg')
            os.utime(path, ns=((index+1)*1_000_000_000, (index+1)*1_000_000_000))
        library = self.start(); state = library.snapshot(unlocked=True)
        self.assertEqual(state['count'], 100); self.assertEqual(state['filename'], 'foto-104.jpg')
        self.assertFalse(library.select('foto-0.jpg', unlocked=True))

    def test_old_preview_cannot_be_published_as_new_selection(self):
        self.photo('foto-red.jpg', color=(200, 0, 0), stamp=20)
        self.photo('foto-blue.jpg', color=(0, 0, 200), stamp=10)
        library = self.start(); entered = threading.Event(); release = threading.Event()
        self.addCleanup(release.set)
        real_filter = apply_filter
        def delayed(image, name):
            if not entered.is_set():
                entered.set(); release.wait(3)
            return real_filter(image, name)
        with patch('photo_library.apply_filter', side_effect=delayed):
            library.snapshot(unlocked=True); self.assertTrue(entered.wait(2))
            library.select('foto-blue.jpg', unlocked=True)
            self.assertIsNone(library.snapshot(unlocked=True)['preview'])
            release.set(); state = self.ready()
        self.assertEqual(state['filename'], 'foto-blue.jpg')
        self.assertEqual(state['preview_key'][:2], ('foto-blue.jpg', 'Original'))
        pixel = state['preview'][2][27*96+48]
        self.assertGreater(pixel & 31, pixel >> 11)

    def test_lock_discards_inflight_preview_and_clears_all_preview_memory(self):
        self.photo(); library = self.start(); self.ready()
        self.assertTrue(library._cache)
        entered = threading.Event(); release = threading.Event(); self.addCleanup(release.set)
        real_filter = apply_filter
        def delayed(image, name):
            entered.set(); release.wait(3); return real_filter(image, name)
        with patch('photo_library.apply_filter', side_effect=delayed):
            library.set_filter('Negativo', unlocked=True); self.assertTrue(entered.wait(2))
            library.lock(); release.set(); self.idle()
        state = library.snapshot()
        self.assertIsNone(state['preview']); self.assertEqual(state['filename'], '')
        self.assertFalse(library._cache); self.assertIsNone(library._preview_job)

    def test_lock_during_jpeg_encoding_cancels_commit_and_removes_private_temporary(self):
        self.photo(); library = self.start(); self.ready(); library.set_filter('Sepia', unlocked=True); self.ready()
        entered = threading.Event(); release = threading.Event(); self.addCleanup(release.set)
        real_save = Image.Image.save
        def delayed(image, output, *args, **kwargs):
            entered.set(); release.wait(3); return real_save(image, output, *args, **kwargs)
        with patch.object(Image.Image, 'save', delayed):
            self.assertTrue(library.save_copy(unlocked=True)); self.assertTrue(entered.wait(2))
            self.assertTrue(self.camera._editing)
            self.assertFalse(library.save_copy(unlocked=True))
            library.lock(); release.set(); self.idle()
        self.assertEqual(self.effects(), []); self.assertFalse(self.camera._editing)
        self.assertFalse(list(self.camera.directory.glob('.efecto-*')))
        self.assertIsNone(self.camera._usage_cache); self.assertIsNone(library.snapshot()['preview'])

    def test_export_rechecks_count_cap_at_commit_after_external_files_appear(self):
        self.photo(); library = self.start(); self.ready(); library.set_filter('Sepia', unlocked=True); self.ready()
        entered = threading.Event(); release = threading.Event(); self.addCleanup(release.set)
        real_filter = apply_filter
        def delayed(image, name):
            entered.set(); release.wait(3); return real_filter(image, name)
        with patch('photo_library.apply_filter', side_effect=delayed):
            self.assertTrue(library.save_copy(unlocked=True)); self.assertTrue(entered.wait(2))
            for index in range(99):
                (self.camera.directory / ('foto-external'+str(index)+'.jpg')).write_bytes(b'file')
            release.set(); self.idle()
        self.assertEqual(self.effects(), []); self.assertFalse(self.camera._editing)
        self.assertFalse(list(self.camera.directory.glob('.efecto-*')))

    def test_export_rechecks_encoded_file_size_before_commit(self):
        self.photo(); library = self.start(); self.ready(); library.set_filter('Sepia', unlocked=True); self.ready()
        entered = threading.Event(); release = threading.Event(); self.addCleanup(release.set)
        real_filter = apply_filter
        def delayed(image, name):
            entered.set(); release.wait(3); return real_filter(image, name)
        with patch('photo_library.apply_filter', side_effect=delayed):
            self.assertTrue(library.save_copy(unlocked=True)); self.assertTrue(entered.wait(2))
            with patch('camera_tools.MAX_FILE_BYTES', 80):
                release.set(); self.idle()
        self.assertEqual(self.effects(), []); self.assertFalse(self.camera._editing)
        self.assertFalse(list(self.camera.directory.glob('.efecto-*')))

    def test_lock_cancels_a_save_waiting_behind_preview(self):
        self.photo(); library = self.start(); self.ready()
        entered = threading.Event(); release = threading.Event(); self.addCleanup(release.set)
        real_filter = apply_filter
        def delayed(image, name):
            entered.set(); release.wait(3); return real_filter(image, name)
        with patch('photo_library.apply_filter', side_effect=delayed):
            library.set_filter('B/N', unlocked=True); self.assertTrue(entered.wait(2))
            self.assertTrue(library.save_copy(unlocked=True)); self.assertTrue(self.camera._editing)
            library.lock(); self.assertFalse(self.camera._editing)
            release.set(); self.idle()
        self.assertEqual(self.effects(), []); self.assertFalse(library._cache)

    def test_preview_cache_is_bounded_and_identical_filter_requests_do_not_reload(self):
        self.photo('foto-one.jpg', stamp=20); self.photo('foto-two.jpg', stamp=10)
        library = self.start(); self.ready()
        with patch.object(library, '_read_image', wraps=library._read_image) as read:
            for _ in range(20):
                library.set_filter('Original', unlocked=True); library.snapshot(unlocked=True)
            self.idle(); read.assert_not_called()
        for filename in ('foto-one.jpg', 'foto-two.jpg'):
            library.select(filename, unlocked=True)
            for name in FILTERS:
                library.set_filter(name, unlocked=True); self.ready()
                self.assertLessEqual(len(library._cache), 8)
        self.assertEqual(len(library._cache), 8)

    def test_preview_changes_do_not_cancel_or_starve_an_explicit_save(self):
        self.photo(); library = self.start(); self.ready(); library.set_filter('B/N', unlocked=True); self.ready()
        entered = threading.Event(); release = threading.Event(); self.addCleanup(release.set)
        real_filter = apply_filter
        def delayed(image, name):
            if not entered.is_set(): entered.set(); release.wait(3)
            return real_filter(image, name)
        with patch('photo_library.apply_filter', side_effect=delayed):
            library.set_filter('Pop', unlocked=True); self.assertTrue(entered.wait(2))
            self.assertTrue(library.save_copy(unlocked=True))
            for name in FILTERS: library.set_filter(name, unlocked=True)
            self.assertFalse(library.save_copy(unlocked=True))
            release.set(); self.wait(lambda: self.effects()); self.idle()
        self.assertEqual(len(self.effects()), 1); self.assertFalse(self.camera._editing)
        self.assertEqual(self.ready()['filter'], 'Boceto')


if __name__ == '__main__': unittest.main()
