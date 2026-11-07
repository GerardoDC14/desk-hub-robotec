import io
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
from PIL import Image
from camera_preview import JpegFrames, MAX_FRAME_BYTES, preview_command
from camera_tools import CameraController
from gallery_pixels import stable_pixels
from uart_speed import negotiate_speed
from nextion_link import NextionLink, END
from desk_hub import Frames
from test_dashboard import hub
from visual_assets import player_symbol, player_commands


class SerialSimulation:
    def __init__(self, device=9600, supported=(115200,230400,921600), deaf=False):
        self.device=device; self.host=None; self.supported=supported; self.now=0
        self.commands=[]; self.reply=b''; self.deaf=deaf
    def set_rate(self,rate): self.host=rate; self.reply=b''
    def send(self,command):
        self.commands.append(command)
        if self.host!=self.device or self.deaf:return
        if command=='sendme': self.reply=b'\x66\x00'+END
        if command.startswith('baud=') and int(command[5:]) in self.supported:self.device=int(command[5:])
    def receive(self,timeout):
        self.now+=timeout; response=self.reply; self.reply=b''; return response
    def negotiate(self,target=921600):
        return negotiate_speed(self.set_rate,self.send,self.receive,target,lambda:self.now,lambda s:None)


class SerialPerformanceTests(unittest.TestCase):
    def test_power_on_and_service_only_restart_are_both_detected(self):
        for speed in (9600,115200,230400,921600):
            sim=SerialSimulation(speed); self.assertEqual(sim.negotiate(),921600)
            self.assertFalse(any(c.startswith('bauds=') for c in sim.commands))
    def test_rejected_fast_speed_falls_back(self):
        sim=SerialSimulation(115200,supported=(115200,))
        self.assertEqual(sim.negotiate(),115200)
    def test_conservative_recovery_can_find_panel_left_at_fast_speed(self):
        sim=SerialSimulation(921600)
        self.assertEqual(sim.negotiate(115200),115200)
    def test_missing_panel_fails_in_bounded_time(self):
        sim=SerialSimulation(deaf=True)
        with self.assertRaises(RuntimeError):sim.negotiate()
        self.assertLess(sim.now,4)
    def test_fast_packets_reserve_rx_headroom_and_keep_touches(self):
        packets=[]; touch=bytes.fromhex('670100010000')
        link=NextionLink(packets.append,lambda t:touch+END+b'\x71\0\0\0\0'+END,Frames(),max_batch=960)
        link.send(['fill 0,0,10,10,65535']*100)
        self.assertTrue(all(len(p)<=971 for p in packets))
        self.assertGreater(max(map(len,packets)),800)
        self.assertEqual(len(link.pending),len(packets))
    def test_display_failure_locks_and_clears_pending_images(self):
        v=hub(); v.marker=Mock();v.spotify_wake=Mock();v.camera=Mock();v.photos=Mock()
        v.artwork.append('fill 0,0,10,10,0');v.online=True;v.link=Mock()
        v.display_failed()
        self.assertFalse(v.unlocked);self.assertFalse(v.online);self.assertIsNone(v.link)
        self.assertEqual(v.uart_target,115200);self.assertFalse(v.artwork);v.camera.lock.assert_called_once()


class StreamTests(unittest.TestCase):
    def test_fragmented_frames_keep_only_newest_complete_frame(self):
        p=JpegFrames(); self.assertIsNone(p.feed(b'noise\xff'))
        self.assertIsNone(p.feed(b'\xd8abc\xff'))
        self.assertEqual(p.feed(b'\xd9\xff\xd8new\xff\xd9\xff'),b'\xff\xd8new\xff\xd9')
        self.assertEqual(p.feed(b'\xd8tail\xff\xd9'),b'\xff\xd8tail\xff\xd9')
    def test_oversized_and_garbage_buffers_are_bounded(self):
        p=JpegFrames();p.feed(b'a'*MAX_FRAME_BYTES);self.assertEqual(len(p.buffer),0)
        with self.assertRaises(ValueError):p.feed(b'\xff\xd8'+b'a'*MAX_FRAME_BYTES)
        self.assertEqual(len(p.buffer),0)
    def test_stream_is_local_and_does_not_write_a_file(self):
        command=preview_command('rpicam-vid');self.assertEqual(command[-2:],['-o','-'])
        self.assertIn('mjpeg',command);self.assertIn('--nopreview',command)
    def test_one_process_delivers_multiple_frames_and_lock_discards_late_frame(self):
        out=io.BytesIO();Image.new('RGB',(320,180),'orange').save(out,format='JPEG')
        frame=out.getvalue();first=threading.Event();finish=threading.Event();calls=[]
        process=Mock();process.communicate.return_value=(b'',b'')
        def popen(*a,**k):calls.append(a);return process
        def reader(proc,cancelled):
            yield frame;yield frame;first.set();finish.wait(2);yield frame
        with tempfile.TemporaryDirectory() as temp:
            c=CameraController(temp,popen=popen,which=lambda n:n,stream_reader=reader)
            try:
                self.assertFalse(c.preview());self.assertTrue(c.preview(unlocked=True))
                self.assertTrue(first.wait(2));self.assertEqual(c.snapshot()['preview_id'],2)
                self.assertTrue(c.snapshot()['streaming']);self.assertEqual(len(calls),1)
                c.lock();finish.set();c._thread.join(.1)
                self.assertIsNone(c.snapshot()['preview']);self.assertEqual(list(c.directory.iterdir()),[])
            finally:finish.set();c.close()
        process.terminate.assert_called()


class VisualQualityTests(unittest.TestCase):
    def test_noise_threshold_does_not_accumulate_drift(self):
        original=(10<<11)|(20<<5)|10
        small=(11<<11)|(22<<5)|11
        large=(15<<11)|(30<<5)|15
        shown=stable_pixels((small,),(original,));self.assertEqual(shown,(original,))
        self.assertEqual(stable_pixels((large,),shown),(large,))
        self.assertEqual(stable_pixels((large,),None),(large,))
    def test_antialiased_symbols_have_intermediate_colors_and_match_geometry(self):
        for name in ('play','pause','prev','next'):
            side,values=player_symbol(26,name,65535,0,0)
            self.assertEqual(len(values),side*side);self.assertGreater(len(set(values)),10)
            for cmd in player_commands(100,100,26,name,65535,0,0):
                x,y,w,h,col=map(int,cmd[5:].split(','))
                self.assertGreaterEqual(x,73);self.assertGreaterEqual(y,73)
                self.assertLessEqual(x+w,128);self.assertLessEqual(y+h,128)


if __name__=='__main__':unittest.main()
