import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from PIL import Image
from photo_library import PhotoLibrary
from video_export import VideoExporter,video_command
from test_photo_library import FakeCamera


class VideoTests(unittest.TestCase):
    def setup_video(self,popen=None,which=lambda n:n):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        c=FakeCamera(temp.name);p=PhotoLibrary(c);self.addCleanup(p.close)
        ident=p.catalog.begin('timelapse',10)
        for i in range(6):
            path=c.directory/f'foto-video-{i}.jpg';Image.new('RGB',(640,360),(i*35,100,130)).save(path);p.catalog.record(ident,path.name)
        p.catalog.record(ident,state='terminada')
        kwargs={'which':which}
        if popen:kwargs['popen']=popen
        v=VideoExporter(temp.name,p,**kwargs);self.addCleanup(v.close)
        return v,p,c,ident

    def fake(self,blocked=False,code=0):
        gate=threading.Event();started=threading.Event()
        if not blocked:gate.set()
        def popen(args,**kwargs):
            class Process:
                stdin=io.BytesIO();returncode=None
                def communicate(self,timeout):
                    started.set()
                    if not gate.wait(timeout):raise subprocess.TimeoutExpired(args,timeout)
                    if self.returncode is None:self.returncode=code
                    if not self.returncode:Path(args[-1]).write_bytes(b'fake-test-video')
                    return None,None
                def poll(self):return self.returncode
                def terminate(self):self.returncode=-15;gate.set()
                def kill(self):self.returncode=-9;gate.set()
            return Process()
        return popen,started,gate

    def test_export_preserves_sources_private_index_and_no_shell_arguments(self):
        runner,started,gate=self.fake();v,p,c,ident=self.setup_video(runner)
        originals={f.name:f.read_bytes() for f in c.directory.glob('*.jpg')}
        self.assertFalse(v.start(ident));self.assertTrue(v.start(ident,12,True));v.thread.join(3)
        self.assertFalse(v.busy);self.assertTrue(v.result);self.assertEqual(v.completed,6);self.assertEqual(len(v.entries()),1)
        self.assertEqual(originals,{f.name:f.read_bytes() for f in c.directory.glob('*.jpg')})
        restored=VideoExporter(c.directory.parent,p,which=lambda n:n);self.addCleanup(restored.close)
        self.assertEqual(restored.entries()[0]['frames'],6)
        args=video_command('ffmpeg','out.mp4',12);self.assertIn('pipe:0',args);self.assertIn('libx264',args)
        self.assertEqual(args[args.index('-threads')+1],'1')

    def test_cancel_and_encoder_failure_leave_no_published_video(self):
        runner,started,gate=self.fake(blocked=True);v,p,c,ident=self.setup_video(runner)
        self.assertTrue(v.start(ident,6,True));self.assertTrue(started.wait(2));self.assertTrue(c._video_working)
        v.cancel();v.thread.join(3);self.assertFalse(v.busy);self.assertFalse(c._video_working)
        self.assertEqual(v.entries(),[]);self.assertEqual(list(v.directory.iterdir()),[])
        runner,_,_=self.fake(code=1);v.popen=runner;v.start(ident,12,True);v.thread.join(3)
        self.assertEqual(v.entries(),[]);self.assertEqual(len(list(c.directory.glob('*.jpg'))),6)

    def test_busy_missing_and_path_gates(self):
        runner,_,_=self.fake();v,p,c,ident=self.setup_video(runner)
        c._sequence={'active':True};self.assertFalse(v.start(ident,12,True));c._sequence=None
        (c.directory/'foto-video-0.jpg').unlink();self.assertFalse(v.start(ident,12,True))
        self.assertIn('Faltan fotos',v.message)
        with self.assertRaises(ValueError):v.file('../state.sqlite3')
        self.assertFalse(v.start(ident,0,True))

    def test_unavailable_storage_view_keeps_navigation(self):
        from test_dashboard import hub
        h=hub();h.role='owner';h.videos=None
        h.navigate('videos');h.render();h.last_touch=0
        h.touch(680,30)
        self.assertEqual(h.screen,'camera')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Requiere FFmpeg instalado')
    def test_real_mp4_frame_count_duration_resolution_and_sources(self):
        v,p,c,ident=self.setup_video(which=shutil.which)
        original={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in c.directory.glob('*.jpg')}
        self.assertTrue(v.start(ident,6,True));v.thread.join(45);self.assertFalse(v.busy);self.assertTrue(v.result,v.message)
        path,_=v.file(v.result)
        result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,nb_frames,r_frame_rate,duration','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=10)
        stream=json.loads(result.stdout)['streams'][0]
        self.assertEqual((stream['width'],stream['height']),(1280,720));self.assertEqual(int(stream['nb_frames']),6)
        self.assertEqual(stream['r_frame_rate'],'6/1');self.assertAlmostEqual(float(stream['duration']),1,places=2)
        self.assertEqual(original,{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in c.directory.glob('*.jpg')})


if __name__=='__main__':unittest.main()

