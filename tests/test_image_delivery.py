"""Píxeles exactos, entrega acotada y encuadres preparados bajo demanda."""
from collections import deque
import io
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from test_dashboard import hub
from test_gallery_pixels import paint, reference
from camera_tools import CameraController
from photo_library import preview_pixels


class ImageDeliveryTests(unittest.TestCase):
    def view(self):
        v=hub(); v.screen='music'; v.packets=[]; v.commands=[]
        v.link=SimpleNamespace(max_batch=240,pending=deque())
        v.send=v.commands.append
        v.send_batch=lambda batch:v.packets.append(list(batch))
        return v

    def finish(self,v):
        while v.artwork:v.flush_artwork()
        result=v.commands+[c for batch in v.packets for c in batch]
        v.commands.clear();v.packets.clear()
        return result

    def test_completed_cover_delta_preserves_exact_odd_pixel_edges(self):
        v=self.view(); pixels=[(r//4+c//4)%3 for r in range(48) for c in range(48)]
        v.images['music']=('a',pixels);v.art('music',32,72,53)
        canvas=paint(self.finish(v))
        self.assertEqual(canvas,reference(pixels,48,48,32,72,53,53))
        changed=list(pixels);changed[77]=65535
        v.images['music']=('b',changed);v.art('music',32,72,53)
        self.assertLess(len(v.artwork),5);self.assertFalse(v.commands)
        canvas=paint(self.finish(v),canvas)
        self.assertEqual(canvas,reference(changed,48,48,32,72,53,53))
        v.images['music']=('new-url-same-image',changed);v.art('music',32,72,53)
        self.assertFalse(v.artwork);self.assertFalse(v.commands)

    def test_interrupted_cover_or_new_page_cannot_reuse_a_partial_image(self):
        v=self.view(); pixels=[i%5 for i in range(48*48)]
        v.images['music']=('a',pixels);v.art('music',32,72,53);self.finish(v)
        changed=[7+i%13 if i%2 else c for i,c in enumerate(pixels)]
        v.images['music']=('b',changed);v.art('music',32,72,53);v.flush_artwork()
        self.assertTrue(v.artwork)
        v.images['music']=('c',changed);v.art('music',32,72,53)
        self.assertTrue(v.commands)  # Full redraw clears the incomplete cover.
        self.assertEqual(paint(self.finish(v)),reference(changed,48,48,32,72,53,53))
        v.navigate('home');v.navigate('music');v.art('music',32,72,53)
        self.assertTrue(v.artwork)

    def test_small_batches_preserve_order_and_yield_for_touch(self):
        v=self.view();commands=[f'fill {i},10,1,1,65535' for i in range(100)]
        v.artwork.extend(commands);v.art_total=len(commands);v.art_started=time.monotonic()
        def send(batch):v.packets.append(list(batch));v.link.pending.append(b'touch')
        v.send_batch=send;v.flush_artwork()
        self.assertEqual(len(v.packets),1);self.assertTrue(v.artwork)
        v.link.pending.clear();v.send_batch=lambda b:v.packets.append(list(b))
        while v.artwork:v.flush_artwork()
        self.assertEqual([c for batch in v.packets for c in batch],commands)
        self.assertTrue(all(sum(len(c)+3 for c in batch)<=240 for batch in v.packets))

    def test_failed_transmission_does_not_commit_cover_baseline(self):
        v=self.view();v.images['music']=('a',[1]*2304);v.art('music',32,72,53)
        v.send_batch=Mock(side_effect=TimeoutError('No ACK'))
        with self.assertRaises(TimeoutError):v.flush_artwork()
        self.assertIsNone(getattr(v,'_music_painted',None))

    def test_next_live_frame_is_requested_once_near_end(self):
        v=self.view();v.screen='viewfinder';v._live_on=True;v.camera=Mock()
        v.art_key=('live',3);v.artwork.extend(['fill 1,1,1,1,1']*50)
        v.art_total=50;v.art_started=time.monotonic()
        while v.artwork:v.flush_artwork()
        v.camera.request_preview_frame.assert_called_once()


class PacedPreviewTests(unittest.TestCase):
    def test_skips_unused_conversion_and_delivers_new_frame_on_request(self):
        out=io.BytesIO();Image.new('RGB',(80,45),'orange').save(out,format='JPEG');frame=out.getvalue()
        ready=threading.Event();advance=threading.Event();done=threading.Event();finish=threading.Event()
        process=Mock();process.communicate.return_value=(b'',b'')
        def reader(proc,cancelled):
            for _ in range(5):yield frame
            ready.set();advance.wait(3)
            yield frame;done.set();finish.wait(3)
        with tempfile.TemporaryDirectory() as temp,patch('photo_library.preview_pixels',wraps=preview_pixels) as convert:
            c=CameraController(temp,popen=lambda *a,**k:process,which=lambda name:name,stream_reader=reader)
            try:
                self.assertTrue(c.preview(unlocked=True,paced=True));self.assertTrue(ready.wait(2))
                self.assertEqual(c.snapshot()['preview_id'],1);self.assertEqual(convert.call_count,1)
                c.request_preview_frame();advance.set();self.assertTrue(done.wait(2))
                self.assertEqual(c.snapshot()['preview_id'],2);self.assertEqual(convert.call_count,2)
                self.assertEqual(list(c.directory.iterdir()),[])
                c.lock();self.assertIsNone(c.snapshot()['preview']);self.assertIsNone(c._latest_jpeg)
            finally:advance.set();finish.set();c.close()


if __name__=='__main__':unittest.main()
