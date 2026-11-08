import io
import threading
import unittest
from unittest.mock import patch
from PIL import Image
from test_dashboard import hub
from robotec import image_pixels


def item(cover):
    return {'uri':cover,'decorations':{'visual_identity':{'cover':[{'url':cover}]}}}


class CoverPrefetchTests(unittest.TestCase):
    def app(self):
        app=hub(); app.screen='music'; app.music_session=1
        app.music['cover']='current'; app.cover_cache['current']=[1]*9216
        app.images['music']=('current',app.cover_cache['current'])
        app.accept_music({'type':'queue_changed','upcoming':[{'item':item('next')}]})
        return app

    def test_next_track_ready_without_downloading_or_displaying_future_art(self):
        app=self.app(); pixels=[2]*9216; calls=[]
        app.decode_image=lambda url,**kw: calls.append((url,kw)) or pixels
        self.assertTrue(app.prefetch_cover())
        self.assertEqual(app.images['music'][0],'current')
        self.assertFalse(app.prefetch_cover())
        app.accept_music({'type':'track_changed','item':item('next')})
        self.assertIs(app.images['music'][1],pixels)
        self.assertTrue(app.image_jobs.empty())
        self.assertEqual(calls,[('next',{'timeout':2})])

    def test_lock_new_session_and_replaced_queue_discard_inflight_results(self):
        for change in ('lock','session','queue'):
            with self.subTest(change=change):
                app=self.app()
                def decode(*args,**kw):
                    if change=='lock': app.unlocked=False
                    elif change=='session': app.music_session+=1
                    else: app.music['next_cover']='different'
                    return [9]
                app.decode_image=decode
                self.assertFalse(app.prefetch_cover())
                self.assertNotIn('next',app.cover_cache)
                self.assertEqual(app.images['music'][0],'current')

    def test_camera_drawing_or_current_download_defer_optional_work(self):
        for reason in ('camera','drawing','current','locked'):
            with self.subTest(reason=reason):
                app=self.app()
                if reason=='camera':
                    app.camera=type('Camera',(),{'snapshot':lambda _:dict(busy=True,timelapse=False)})()
                elif reason=='drawing': app.artwork.append('fill')
                elif reason=='current': app.cover_cache.clear()
                else: app.unlocked=False
                app.decode_image=lambda *a,**kw: self.fail('optional download started')
                self.assertFalse(app.prefetch_cover())

    def test_failure_backs_off_but_current_request_is_not_blocked(self):
        app=self.app(); calls=[]
        def fail(*a,**kw): calls.append(1); raise TimeoutError()
        app.decode_image=fail
        self.assertFalse(app.prefetch_cover()); self.assertFalse(app.prefetch_cover())
        self.assertEqual(len(calls),1)
        app.accept_music({'type':'track_changed','item':item('next')})
        self.assertEqual(app.image_jobs.get_nowait(),'next')

    def test_slow_prefetch_does_not_hold_lock_or_block_current_worker(self):
        app=self.app(); entered=threading.Event(); release=threading.Event()
        app.stop=threading.Event()
        def decode(url,**kw):
            if url=='next': entered.set(); release.wait(2); return [2]
            app.stop.set(); return [3]
        app.decode_image=decode
        worker=threading.Thread(target=app.prefetch_cover); worker.start()
        try:
            self.assertTrue(entered.wait(1))
            app.accept_music({'type':'track_changed','item':item('chosen')})
            app.cover_worker()
            self.assertEqual(app.images['music'],('chosen',[3]))
        finally: release.set(); worker.join(2)
        self.assertNotIn('next',app.cover_cache)

    def test_cache_bounded_and_pixels_identical_to_normal_decoder(self):
        raw=io.BytesIO(); Image.effect_noise((200,200),50).convert('RGB').save(raw,'PNG')
        with patch('urllib.request.urlopen',side_effect=lambda *a,**kw:io.BytesIO(raw.getvalue())):
            normal=image_pixels('https://example.com/cover')
            anticipated=image_pixels('https://example.com/cover',timeout=2)
        self.assertEqual(normal,anticipated); self.assertEqual(len(normal),96*96)
        app=self.app(); app.decode_image=lambda *a,**kw:anticipated
        for n in range(12):
            app.music['next_cover']=str(n)
            app.cover_cache.move_to_end('current')
            self.assertTrue(app.prefetch_cover())
        self.assertEqual(len(app.cover_cache),8)


if __name__=='__main__': unittest.main()
