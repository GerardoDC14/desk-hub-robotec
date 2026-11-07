import io
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PIL import Image
from camera_tools import CameraController
from photo_library import PhotoLibrary
from photobooth import Photobooth,compose
from test_camera_tools import Clock,FakeRunner
from test_dashboard import hub


class BoothTests(unittest.TestCase):
    def setup_booth(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        out=io.BytesIO();Image.new('RGB',(1280,720),'teal').save(out,format='JPEG');raw=out.getvalue()
        clock=Clock();runner=FakeRunner(image=raw)
        c=CameraController(temp.name,popen=runner,which=lambda n:n if n=='rpicam-still' else None,clock=clock)
        self.addCleanup(c.close);p=PhotoLibrary(c);self.addCleanup(p.close)
        b=Photobooth(c,p,clock);self.addCleanup(b.cancel)
        return b,c,p,clock,raw

    def settle(self,c):
        until=time.monotonic()+3
        while time.monotonic()<until:
            with c._cv:
                if not c._busy and not c._job:return
            time.sleep(.01)
        self.fail('Captura no terminó')

    def four(self,b,c,clock):
        for _ in range(4):
            clock.advance(3.1);b.poll(True);self.settle(c);b.poll(True)

    def test_four_originals_and_collage_without_overwrite(self):
        b,c,p,clock,raw=self.setup_booth()
        self.assertFalse(b.start());self.assertTrue(b.start(unlocked=True))
        self.assertFalse(c.capture(unlocked=True));self.assertFalse(c.start_timelapse(unlocked=True))
        b.poll(True);self.assertEqual(list(c.directory.iterdir()),[])
        self.four(b,c,clock);b.thread.join(3)
        self.assertTrue(b.result);self.assertEqual(len(b.names),4)
        for name in b.names:self.assertEqual((c.directory/name).read_bytes(),raw)
        with Image.open(c.directory/b.result) as image:self.assertEqual(image.size,(1352,844))
        self.assertEqual(p.snapshot(unlocked=True)['count'],5)
        self.assertFalse(c._booth_active);self.assertFalse(c._booth_working)

    def test_cancel_preserves_completed_capture_and_never_resumes(self):
        b,c,p,clock,raw=self.setup_booth();b.start(unlocked=True)
        clock.advance(4);b.poll(True);self.settle(c);b.poll(True)
        self.assertEqual(len(b.names),1);b.poll(False)
        clock.advance(100);b.poll(True);self.assertFalse(b.active)
        self.assertEqual(list(c.directory.glob('foto-*.jpg'))[0].read_bytes(),raw)
        self.assertEqual(len(list(c.directory.glob('*.jpg'))),1)

    def test_lock_during_composition_does_not_publish_partial_image(self):
        b,c,p,clock,raw=self.setup_booth();entered=threading.Event();release=threading.Event()
        def slow(*args):entered.set();release.wait(3);return compose(*args)
        with patch('photobooth.compose',slow):
            b.start(unlocked=True);self.four(b,c,clock);self.assertTrue(entered.wait(1))
            b.cancel();self.assertFalse(c.capture(unlocked=True));release.set();b.thread.join(3)
        self.assertEqual(b.result,'');self.assertEqual(len(list(c.directory.glob('foto-*.jpg'))),4)
        self.assertEqual(list(c.directory.glob('efecto-*.jpg')),[])
        self.assertEqual(list(c.directory.glob('*.tmp')),[])

    def test_layouts_filters_and_storage_gate(self):
        images=[Image.new('RGB',(80,45),color) for color in ('red','green','blue','yellow')]
        before=[im.tobytes() for im in images]
        result=compose(images,'Tira','B/N','Menta');self.assertEqual(result.size,(688,1612))
        for pos,color in zip(((30,30),(30,420),(30,800),(30,1200)),images):
            r,g,b=result.getpixel(pos);self.assertEqual(r,g);self.assertEqual(g,b)
        self.assertEqual(before,[im.tobytes() for im in images])
        b,c,p,clock,raw=self.setup_booth()
        with patch.object(c,'_usage',return_value=(96,100)):self.assertFalse(b.start(unlocked=True))

    def test_native_controls_start_countdown_and_cancel(self):
        b,c,p,clock,raw=self.setup_booth();h=hub();h.role='owner';h.camera=c;h.photos=p;h.booth=b
        h.navigate('viewfinder');h.last_touch=0;h.touch(550,30);self.assertEqual(h.screen,'booth')
        h.last_touch=0;h.touch(600,165);self.assertEqual(h._booth_layout,'Tira')
        h.last_touch=0;h.touch(180,425);self.assertTrue(b.active);h.render();self.assertTrue(b.active)
        self.assertEqual(h.cache['booth-layout'],True)
        h.last_touch=0;h.touch(380,425);h.render();self.assertFalse(b.active);self.assertEqual(h.cache['booth-layout'],False)
        h.role='guest';h.navigate('booth');self.assertEqual(h.screen,'home')


if __name__=='__main__':unittest.main()
