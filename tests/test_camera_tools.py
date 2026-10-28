import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camera_tools import CameraController, CameraViews, camera_command, camera_present
from font_metrics import text_width


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class FakeRunner:
    def __init__(self, blocked=False, code=0, image=b'jpeg-data', ignore_terminate=False):
        self.calls = []; self.code = code; self.image = image; self.ignore_terminate = ignore_terminate
        self.started = threading.Event(); self.gate = threading.Event()
        self.active = 0; self.max_active = 0
        if not blocked: self.gate.set()

    def __call__(self, args, **options):
        self.calls.append((args, options)); self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.started.set()
        runner = self
        class Process:
            returncode = None
            terminated = False
            complete = False
            def communicate(self, timeout):
                if not runner.gate.wait(timeout):
                    raise subprocess.TimeoutExpired(args, timeout)
                if not self.complete:
                    self.complete = True; runner.active -= 1
                    self.returncode = -15 if self.terminated else runner.code
                    if '-o' in args and self.returncode == 0:
                        Path(args[args.index('-o')+1]).write_bytes(runner.image)
                output = 'Available cameras\n0 : ov5647 [2592x1944]\n' if '--list-cameras' in args else ''
                return output, None
            def terminate(self):
                if not runner.ignore_terminate: self.terminated = True; runner.gate.set()
            def kill(self): self.terminate()
        return Process()


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent); self.controllers = []

    def tearDown(self):
        for controller in self.controllers: controller.close()
        self.temp.cleanup()

    def controller(self, runner=None, **kwargs):
        runner = runner or FakeRunner()
        kwargs.setdefault('which', lambda name: '/usr/bin/'+name if name == 'rpicam-still' else None)
        controller = CameraController(self.temp.name, popen=runner, **kwargs)
        self.controllers.append(controller)
        return controller, runner

    def wait_for(self, condition):
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            if condition(): return
            threading.Event().wait(0.01)
        self.fail('La operación de cámara no terminó')

    def idle(self, controller):
        self.wait_for(lambda: not controller.snapshot()['busy'])

    def test_commands_are_generated_without_shell_or_preview(self):
        self.assertEqual(camera_command('/usr/bin/rpicam-still'), ['/usr/bin/rpicam-still', '--list-cameras'])
        args = camera_command('/usr/bin/rpicam-still', Path('/private/photo.jpg'))
        self.assertIn('--nopreview', args)
        self.assertEqual(args[args.index('-t')+1], '1000')
        self.assertEqual(args[args.index('--width')+1], '1280')
        self.assertEqual(args[args.index('--height')+1], '720')
        self.assertEqual(args[args.index('-o')+1], str(Path('/private/photo.jpg')))
        self.assertTrue(camera_present('Available cameras\n0 : ov5647 [2592x1944]\n'))
        self.assertFalse(camera_present('No cameras available!'))

    def test_boot_and_locked_requests_never_start_a_process(self):
        controller, runner = self.controller()
        self.assertEqual(runner.calls, [])
        self.assertFalse(controller.capture())
        self.assertFalse(controller.probe())
        self.assertFalse(controller.start_timelapse())
        self.assertEqual(runner.calls, [])
        self.assertEqual(list(controller.directory.iterdir()), [])

    def test_probe_is_readonly_and_detects_sensor(self):
        controller, runner = self.controller()
        self.assertTrue(controller.probe(unlocked=True))
        self.idle(controller)
        self.assertEqual(len(runner.calls), 1)
        self.assertIn('--list-cameras', runner.calls[0][0])
        self.assertFalse(runner.calls[0][1]['shell'])
        self.assertTrue(controller.snapshot()['connected'])
        self.assertIn('OV5647', controller.snapshot()['status'])
        self.assertEqual(list(controller.directory.iterdir()), [])

    def test_fallback_and_missing_tools(self):
        controller, runner = self.controller(which=lambda name: '/usr/bin/libcamera-still' if name=='libcamera-still' else None)
        controller.probe(unlocked=True); self.idle(controller)
        self.assertEqual(runner.calls[0][0][0], '/usr/bin/libcamera-still')
        controller.close()
        other, calls = self.controller(which=lambda name: None)
        self.assertFalse(other.capture(unlocked=True))
        self.assertFalse(other.start_timelapse(unlocked=True))
        self.assertFalse(other.snapshot()['available'])
        self.assertEqual(calls.calls, [])

    def test_photo_is_private_and_keeps_only_generated_filename(self):
        controller, runner = self.controller()
        self.assertTrue(controller.capture(unlocked=True)); self.idle(controller)
        result = controller.snapshot()
        path = controller.directory/result['last_filename']
        self.assertEqual(path.read_bytes(), b'jpeg-data')
        self.assertEqual(result['photo_count'], 1)
        self.assertEqual(result['storage_bytes'], len(b'jpeg-data'))
        self.assertEqual(len(list(controller.directory.iterdir())), 1)
        self.assertRegex(path.name, r'^foto-\d{8}-\d{6}-[0-9a-f]{8}\.jpg$')
        if os.name != 'nt':
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(controller.directory.stat().st_mode & 0o777, 0o700)

    def test_requests_do_not_overlap_and_lock_removes_partial_photo(self):
        controller, runner = self.controller(FakeRunner(blocked=True))
        controller.capture(unlocked=True)
        self.assertTrue(runner.started.wait(1))
        self.assertFalse(controller.capture(unlocked=True))
        self.assertFalse(controller.probe(unlocked=True))
        self.assertFalse(controller.start_timelapse(unlocked=True))
        controller.lock(); self.idle(controller)
        self.assertEqual(runner.max_active, 1)
        self.assertEqual(list(controller.directory.iterdir()), [])
        self.assertEqual(controller.snapshot()['last_filename'], '')
        self.assertFalse(controller.snapshot()['timelapse'])

    def test_photo_completed_after_lock_is_discarded_even_if_process_ignores_terminate(self):
        controller, runner = self.controller(FakeRunner(blocked=True,ignore_terminate=True))
        controller.capture(unlocked=True)
        self.assertTrue(runner.started.wait(1))
        controller.lock(); runner.gate.set(); self.idle(controller)
        self.assertEqual(controller.snapshot()['last_filename'], '')
        self.assertEqual(controller.snapshot()['photo_count'], 0)
        self.assertEqual(list(controller.directory.iterdir()), [])

    def test_render_storage_usage_is_cached_for_one_second_and_capture_invalidates_it(self):
        clock=Clock(); controller, runner=self.controller(clock=clock)
        with patch.object(controller,'_usage',wraps=controller._usage) as usage:
            for _ in range(20): controller.snapshot()
            self.assertEqual(usage.call_count,1)
            clock.advance(1.1); controller.snapshot()
            self.assertEqual(usage.call_count,2)
            controller.capture(unlocked=True); self.idle(controller)
            self.assertEqual(controller.snapshot()['photo_count'],1)
            before=usage.call_count
            for _ in range(20): controller.snapshot()
            self.assertEqual(usage.call_count,before)

    def test_explicit_timelapse_finishes_selected_count_without_overlapping(self):
        clock = Clock(); controller, runner = self.controller(clock=clock)
        self.assertTrue(controller.start_timelapse(interval=10, count=12, unlocked=True))
        for expected in range(1,13):
            self.wait_for(lambda: controller.snapshot()['completed'] == expected)
            self.idle(controller)
            if expected < 12:
                self.assertTrue(controller.snapshot()['timelapse'])
                clock.advance(10)
                with controller._cv: controller._cv.notify_all()
        result = controller.snapshot()
        self.assertFalse(result['timelapse'])
        self.assertEqual(result['completed'], 12)
        self.assertEqual(result['photo_count'], 12)
        self.assertEqual(len(runner.calls), 12)
        self.assertEqual(runner.max_active, 1)

    def test_lock_and_reopen_never_resume_a_timelapse(self):
        clock = Clock(); controller, runner = self.controller(clock=clock)
        controller.start_timelapse(interval=10, count=12, unlocked=True)
        self.wait_for(lambda: controller.snapshot()['completed'] == 1)
        self.idle(controller); controller.lock()
        clock.advance(10000)
        with controller._cv: controller._cv.notify_all()
        controller.close()
        reopened, calls = self.controller(clock=clock)
        self.assertFalse(reopened.snapshot()['timelapse'])
        self.assertEqual(reopened.snapshot()['completed'], 0)
        self.assertEqual(calls.calls, [])
        self.assertEqual(len(runner.calls), 1)

    def test_only_fixed_timelapse_presets_are_accepted(self):
        controller, runner = self.controller()
        for interval,count in [(1,12),(11,30),(10,100),(30,-1),('30',12)]:
            self.assertFalse(controller.start_timelapse(interval,count,unlocked=True))
        self.assertEqual(runner.calls, [])

    def test_photo_count_cap_refuses_to_open_camera(self):
        controller, runner = self.controller()
        for i in range(100): (controller.directory/f'photo-{i}.jpg').write_bytes(b'x')
        controller.capture(unlocked=True); self.idle(controller)
        self.assertEqual(runner.calls, [])
        self.assertEqual(controller.snapshot()['photo_count'], 100)
        self.assertIn('Almacenamiento', controller.snapshot()['status'])

    def test_disk_cap_reserves_space_before_capture(self):
        controller, runner = self.controller()
        with patch('camera_tools.MAX_STORAGE_BYTES', 8*1024*1024-1):
            controller.capture(unlocked=True); self.idle(controller)
        self.assertEqual(runner.calls, [])
        self.assertEqual(list(controller.directory.iterdir()), [])

    def test_oversize_or_empty_result_is_discarded(self):
        controller, runner = self.controller(FakeRunner(image=b'four'))
        with patch('camera_tools.MAX_FILE_BYTES',3):
            controller.capture(unlocked=True); self.idle(controller)
        self.assertEqual(controller.snapshot()['photo_count'], 0)
        self.assertEqual(list(controller.directory.iterdir()), [])
        runner.image=b''
        controller.capture(unlocked=True); self.idle(controller)
        self.assertEqual(list(controller.directory.iterdir()), [])

    def test_failure_and_timeout_remove_temp_file_and_leave_worker_usable(self):
        controller, runner = self.controller(FakeRunner(code=1))
        controller.capture(unlocked=True); self.idle(controller)
        self.assertFalse(controller.snapshot()['connected'])
        self.assertEqual(list(controller.directory.iterdir()), [])
        runner.code=0; runner.gate.clear()
        with patch('camera_tools.PROCESS_TIMEOUT',0.05):
            controller.capture(unlocked=True); self.idle(controller)
        self.assertEqual(list(controller.directory.iterdir()), [])
        controller.capture(unlocked=True); self.idle(controller)
        self.assertEqual(controller.snapshot()['photo_count'], 1)

    def test_close_cancels_pending_and_running_requests(self):
        controller, runner = self.controller(FakeRunner(blocked=True))
        controller.capture(unlocked=True); self.assertTrue(runner.started.wait(1))
        controller.close()
        self.assertFalse(controller._thread.is_alive())
        self.assertFalse(controller.capture(unlocked=True))
        self.assertEqual(list(controller.directory.iterdir()), [])


class CameraViewTests(unittest.TestCase):
    class Camera:
        def __init__(self): self.calls=[]; self.running=False
        def snapshot(self):
            return dict(status='Cámara lista',busy=False,timelapse=self.running,last_filename='',photo_count=0,storage_bytes=0)
        def capture(self,**kwargs): self.calls.append(('capture',kwargs)); return True
        def probe(self,**kwargs): self.calls.append(('probe',kwargs)); return True
        def start_timelapse(self,*args,**kwargs): self.calls.append(('start',args,kwargs)); self.running=True; return True
        def stop_timelapse(self): self.calls.append(('stop',)); self.running=False
    class View(CameraViews):
        def __init__(self):
            self.theme=dict(ink=1,bg=0,mint=2,muted=3); self.commands=[]; self.routes=[]
            self.camera=CameraViewTests.Camera(); self.unlocked=True
        def text(self,*args): self.commands.append(('text',args))
        def soft_button(self,*args): self.commands.append(('button',args))
        def navigate(self,route): self.routes.append(route)

    def test_draw_stays_inside_page_and_has_filled_actions(self):
        view=self.View(); view.draw_camera()
        for kind,args in view.commands:
            key,x,y,w,h=args[:5]
            self.assertGreaterEqual(x,0); self.assertLessEqual(x+w,800)
            self.assertGreaterEqual(y,76); self.assertLessEqual(y+h,424)
        self.assertEqual(len([c for c in view.commands if c[0]=='button']),9)

    def test_long_status_uses_smaller_font_and_fits_without_clipping(self):
        view=self.View()
        original=view.camera.snapshot
        def snapshot():
            state=original(); state['status']='No se pudo abrir la cámara / revisa el cable con la Pi apagada'
            return state
        view.camera.snapshot=snapshot; view.draw_camera()
        args=next(args for kind,args in view.commands if args[0]=='camerastatus')
        self.assertEqual(args[5],2)
        self.assertLessEqual(text_width(args[6],args[5]),args[3])

    def test_locked_and_missing_controller_never_capture(self):
        view=self.View(); view.unlocked=False
        self.assertFalse(view.touch_camera(50,220)); self.assertEqual(view.camera.calls,[])
        view.camera=None; view.unlocked=True
        self.assertFalse(view.touch_camera(50,220)); view.draw_camera()

    def test_presets_and_actions_match_hit_areas(self):
        view=self.View()
        self.assertTrue(view.touch_camera(50,220))
        self.assertTrue(view.touch_camera(450,220))
        view.touch_camera(160,280); view.touch_camera(700,280)
        self.assertTrue(view.touch_camera(50,340))
        self.assertEqual(view.camera.calls[-1],('start',(10,60),dict(unlocked=True)))
        self.assertTrue(view.touch_camera(50,340))
        self.assertEqual(view.camera.calls[-1],('stop',))


if __name__=='__main__': unittest.main()
