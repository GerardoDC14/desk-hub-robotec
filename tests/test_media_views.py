import io
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from camera_tools import CameraController
from photo_library import PhotoLibrary
from test_dashboard import hub
from test_gallery_views import FakePhotos
from font_metrics import text_width


def wait_for(test, condition):
    end=time.monotonic()+4
    while time.monotonic()<end:
        if condition(): return
        time.sleep(.01)
    test.fail('No terminó el trabajo asíncrono')


class PreviewProcess:
    def __init__(self, output): self.output=output; self.returncode=0
    def communicate(self, timeout): return self.output,None
    def terminate(self): self.returncode=-15


class MediaBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.calls=[]
        out=io.BytesIO(); Image.new('RGB',(320,180),'orange').save(out,format='JPEG')
        self.jpeg=out.getvalue()
        def popen(args,**kwargs):
            self.calls.append((args,kwargs)); return PreviewProcess(self.jpeg)
        self.camera=CameraController(self.temp.name,popen=popen,which=lambda name:name)
        self.photos=PhotoLibrary(self.camera)

    def tearDown(self): self.photos.close(); self.camera.close(); self.temp.cleanup()

    def test_preview_requires_unlock_and_never_writes_photos(self):
        self.assertFalse(self.camera.preview())
        self.assertTrue(self.camera.preview(unlocked=True))
        wait_for(self,lambda:self.camera.snapshot()['preview'] is not None)
        state=self.camera.snapshot(); self.assertEqual(state['preview'][:2],(48,27))
        self.assertEqual(list(self.camera.directory.iterdir()),[])
        self.assertEqual(self.calls[0][0][-2:],['-o','-'])
        self.assertFalse(self.calls[0][1]['text'])
        self.camera.lock(); self.assertIsNone(self.camera.snapshot()['preview'])

    def test_lock_discards_late_camera_frame(self):
        started=threading.Event(); gate=threading.Event()
        class Process(PreviewProcess):
            def communicate(inner,timeout):
                started.set(); gate.wait(2); return self.jpeg,None
            def terminate(inner): gate.set()
        self.camera._popen=lambda *a,**k:Process(self.jpeg)
        self.camera.preview(unlocked=True); self.assertTrue(started.wait(1))
        self.camera.lock(); gate.set()
        wait_for(self,lambda:not self.camera.snapshot()['busy'])
        self.assertIsNone(self.camera.snapshot()['preview'])
        self.assertEqual(list(self.camera.directory.iterdir()),[])

    def test_stop_preview_does_not_cancel_timelapse(self):
        with self.camera._cv:
            self.camera._sequence=dict(interval=60,count=12)
            self.camera._next_due=time.monotonic()+60
        self.camera.stop_preview(); self.assertTrue(self.camera.snapshot()['timelapse'])

    def test_grid_is_paginated_cached_and_private(self):
        for i in range(8):
            (self.camera.directory/f'foto-test{i}.jpg').write_bytes(self.jpeg)
        state=self.photos.grid(0,unlocked=True)
        self.assertEqual(state['count'],8); self.assertEqual(state['pages'],2)
        self.assertEqual(len(state['items']),6)
        wait_for(self,lambda:all(i['preview'] for i in self.photos.grid(0,unlocked=True)['items']))
        keys=[i['key'] for i in self.photos.grid(0,unlocked=True)['items']]
        self.assertEqual(len(self.photos.grid(99,unlocked=True)['items']),2)
        self.assertEqual(self.photos.grid(99,unlocked=True)['page'],1)
        self.assertEqual(len(set(keys)),6)
        self.photos.lock(); self.assertEqual(self.photos.grid()['items'],[])
        self.assertFalse(self.photos._thumbs)

    def test_corrupt_thumbnail_is_reported_without_retry_loop(self):
        (self.camera.directory/'foto-broken.jpg').write_bytes(b'bad')
        wait_for(self,lambda:self.photos.grid(unlocked=True)['items'][0]['error'])
        state=self.photos.grid(unlocked=True); self.assertIsNone(state['items'][0]['preview'])

    def test_late_thumbnail_cannot_repopulate_cache_after_lock(self):
        (self.camera.directory/'foto-test.jpg').write_bytes(self.jpeg)
        original=self.photos._read_image; started=threading.Event(); gate=threading.Event()
        def read(key): started.set(); gate.wait(2); return original(key)
        self.photos._read_image=read
        self.photos.grid(unlocked=True); self.assertTrue(started.wait(1))
        self.photos.lock(); gate.set()
        wait_for(self,lambda:self.photos._working is None)
        self.assertFalse(self.photos._thumbs)


class ViewCamera:
    def __init__(self):
        self.state=dict(status='Cámara lista',error='',busy=False,timelapse=False,last_filename='',preview=None,preview_id=0)
        self.calls=[]
    def snapshot(self): return dict(self.state)
    def preview(self,**kw): self.calls.append('preview'); self.state['busy']=True; return True
    def capture(self,**kw): self.calls.append('capture'); self.state['busy']=True; return True
    def stop_preview(self): self.calls.append('stop'); self.state['preview']=None


class MediaViewTests(unittest.TestCase):
    def view(self,screen='viewfinder'):
        v=hub(); v.screen=screen; v.camera=ViewCamera(); v.photos=FakePhotos()
        v.commands=[]; v.send=v.commands.append
        return v

    def test_entering_camera_does_not_capture_and_controls_fit(self):
        v=self.view(); buttons=[]; original=v.soft_button
        def button(*args,**kwargs): buttons.append(args); original(*args,**kwargs)
        v.soft_button=button; v.draw_viewfinder()
        self.assertFalse(v.camera.calls)
        for args in buttons:
            _,x,y,w,h,label,*extra=args
            font=extra[1] if len(extra)>1 else 2
            self.assertLessEqual(text_width(label,font),w-2*min(14,max(3,h//4)),label)
            self.assertLessEqual(y+h,480); self.assertLessEqual(x+w,800)

    def test_preview_frame_is_not_replaced_mid_transmission(self):
        v=self.view(); v.camera.state.update(preview=(2,2,(1,2,3,4)),preview_id=1)
        v.draw_viewfinder(); queued=list(v.artwork)
        v.camera.state.update(preview=(2,2,(5,6,7,8)),preview_id=2)
        v.draw_viewfinder(); self.assertEqual(list(v.artwork),queued)
        v.artwork.clear(); v.draw_viewfinder(); self.assertEqual(v.art_key,('live',2))

    def test_explicit_preview_starts_and_navigation_stops_it(self):
        v=self.view(); v.touch_media(650,220); v.draw_viewfinder()
        self.assertEqual(v.camera.calls,['preview'])
        v.navigate('ambient'); self.assertEqual(v.camera.calls[-1],'stop')
        self.assertFalse(v._live_on); self.assertIsNone(v._shot_due)
        self.assertFalse(v.artwork)

    def test_countdown_waits_for_preview_shutdown_and_captures_once(self):
        v=self.view(); v._shot_delay=3; v.camera.state['busy']=True
        with patch('media_views.time.monotonic',return_value=100):
            v.touch_media(650,130); v.draw_viewfinder()
        self.assertNotIn('capture',v.camera.calls)
        with patch('media_views.time.monotonic',return_value=104):
            v.draw_viewfinder(); self.assertNotIn('capture',v.camera.calls)
            v.camera.state['busy']=False; v.draw_viewfinder(); v.draw_viewfinder()
        self.assertEqual(v.camera.calls.count('capture'),1)
        v.navigate('home'); self.assertIsNone(v._shot_wait)

    def test_lock_blocks_all_new_routes(self):
        v=self.view(); v.unlocked=False
        for screen in ('gallery_grid','viewfinder','photo_show'):
            v.screen=screen; self.assertFalse(v.touch_media(650,130))
            v.navigate(screen); self.assertEqual(v.screen,'lock')

    def test_slideshow_waits_until_image_complete_then_eight_seconds(self):
        v=self.view('photo_show'); v.photos.select=Mock()
        with patch('media_views.time.monotonic',return_value=100):
            v.draw_photo_show(); self.assertIsNone(v._show_due)
            v.artwork.clear(); v.draw_photo_show(); self.assertEqual(v._show_due,108)
        with patch('media_views.time.monotonic',return_value=109): v.draw_photo_show()
        v.photos.select.assert_called_once_with(1,unlocked=True)

    def test_paused_slideshow_keeps_selected_photo(self):
        v=self.view('photo_show'); v.photos.select=Mock(); v._show_play=False
        v.draw_photo_show(); v.artwork.clear(); v._show_due=1; v.draw_photo_show()
        v.photos.select.assert_not_called()


if __name__=='__main__': unittest.main()
