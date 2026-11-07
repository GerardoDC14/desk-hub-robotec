import http.client
import io
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
import zipfile
from unittest.mock import Mock
from PIL import Image
from phone_server import PhoneAccess,PhoneServer
from phone_html import HTML
from test_dashboard import hub
from test_photo_library import FakeCamera
from photo_library import PhotoLibrary


class PhoneTests(unittest.TestCase):
    def test_pair_single_use_expiry_and_rotation(self):
        now=[0];a=PhoneAccess(clock=lambda:now[0]);pin=a.begin()
        self.assertIsNone(a.exchange('wrong'));token=a.exchange(pin)
        self.assertTrue(a.valid(token));self.assertIsNone(a.exchange(pin))
        now[0]=901;self.assertFalse(a.valid(token))
        old=a.begin();a.begin();self.assertIsNone(a.exchange(old))
        pin=a.begin();now[0]+=61;self.assertIsNone(a.exchange(pin))

    def test_http_origin_auth_body_and_revocation(self):
        owner=[True];calls=[]
        server=PhoneServer(lambda a,d,t:(calls.append(a) or 200,{'ok':True},'application/json'),lambda:owner[0],HTML,port=0)
        self.addCleanup(server.close);self.assertIsNone(server.server)
        url=server.begin('127.0.0.1');pair=url.split('#pair=')[1]
        def request(path,method='GET',data=None,headers=None):
            c=http.client.HTTPConnection('127.0.0.1',server.port,timeout=3)
            c.request(method,path,body=json.dumps(data) if data is not None else None,headers=headers or {})
            r=c.getresponse();body=r.read();status=r.status;c.close();return status,body
        self.assertEqual(request('/')[0],200)
        self.assertEqual(request('/api/photos')[0],401)
        self.assertEqual(request('/api/pair','POST',{'pair':pair},{'Origin':'https://outside.invalid'})[0],403)
        status,body=request('/api/pair','POST',{'pair':pair});self.assertEqual(status,200)
        token=json.loads(body)['session'];headers={'Authorization':'Bearer '+token}
        self.assertEqual(request('/api/pair','POST',{'pair':pair})[0],401)
        self.assertEqual(request('/api/state',headers=headers)[0],200)
        self.assertEqual(request('/api/command',headers=headers)[0],404)
        self.assertEqual(request('/api/command','POST',{'blob':'x'*5000},headers)[0],413)
        self.assertEqual(request('/api/state',headers={**headers,'Host':'outside.invalid'})[0],403)
        owner[0]=False;self.assertEqual(request('/api/photos',headers=headers)[0],401)
        self.assertEqual(calls,['state'])
        owner[0]=True;server.access.revoke();self.assertEqual(request('/api/state',headers=headers)[0],401)

    def panel(self):
        h=hub();h.role='owner';h.init_phone();h.phone.port=0;self.addCleanup(h.phone.close)
        h.phone.access.begin();token=h.phone.access.exchange(h.phone.access.pair)
        return h,token

    def test_queued_command_rechecks_lock_expiry_and_main_thread(self):
        h,token=self.panel();h.camera=None
        event=threading.Event();job=dict(action='command',data={'command':'timer','index':0,'operation':'start'},token=token,event=event,until=time.monotonic()+2)
        h.phone_jobs.put(job);h.poll_phone();self.assertEqual(job['result'][0],200)
        deadline=h.timer.data['deadline'];h.unlocked=False;job['data']['operation']='reset'
        h.phone_jobs.put(job);h.poll_phone();self.assertEqual(job['result'][0],401);self.assertEqual(h.timer.data['deadline'],deadline)
        h.unlocked=True;job['until']=0;h.phone_jobs.put(job);h.poll_phone();self.assertEqual(h.timer.data['deadline'],deadline)
        h.role='guest';self.assertEqual(h.phone_dispatch('photos',{},token)[0],401)
        h.navigate('phone');self.assertEqual(h.screen,'home')

    def test_original_download_thumbnail_and_path_boundary(self):
        h,token=self.panel();tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        h.camera=FakeCamera(tmp.name);h.photos=PhotoLibrary(h.camera);self.addCleanup(h.photos.close)
        path=h.camera.directory/'foto-prueba.jpg';Image.new('RGB',(640,360),'red').save(path)
        raw=path.read_bytes();self.assertEqual(h.phone_dispatch('photos',{},token)[1]['photos'],[path.name])
        self.assertEqual(h.phone_dispatch('photo',{'name':path.name},token),(200,raw,'image/jpeg'))
        thumb=h.phone_dispatch('thumb',{'name':path.name},token)[1]
        with Image.open(io.BytesIO(thumb)) as image:self.assertEqual(image.size,(320,180))
        with self.assertRaises(ValueError):h.phone_dispatch('photo',{'name':'../state.sqlite3'},token)
        self.assertEqual(path.read_bytes(),raw)
        status,archive,kind=h.phone_dispatch('archive',{'names':[path.name]},token)
        self.assertEqual((status,kind),(200,'application/zip'))
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            self.assertEqual(zipped.namelist(),[path.name]);self.assertEqual(zipped.read(path.name),raw)
        with self.assertRaises(ValueError):h.phone_dispatch('archive',{'names':[path.name]*7},token)
        h.unlocked=False;self.assertEqual(h.phone_dispatch('photo',{'name':path.name},token)[0],401)

    def test_camera_lease_and_explicit_actions(self):
        h,token=self.panel();h.camera=Mock();h.camera.snapshot.return_value={'timelapse':False}
        h.phone_command({'command':'camera','operation':'start'});self.assertTrue(h._live_on)
        h.phone_frame_seen=time.monotonic()-11;h.poll_phone();self.assertFalse(h._live_on);h.camera.stop_preview.assert_called()
        h.phone_command({'command':'camera','operation':'capture'});self.assertIsNotNone(h._shot_due)
        with self.assertRaises(ValueError):h.phone_command({'command':'timer','index':True,'operation':'reset'})
        with self.assertRaises(ValueError):h.phone_command({'command':'music','operation':'volume','value':101})

    def test_real_request_rechecks_access_after_data_completes(self):
        owner=[True]
        def dispatch(*args):owner[0]=False;return 200,b'private photo','image/jpeg'
        s=PhoneServer(dispatch,lambda:owner[0],HTML,port=0);self.addCleanup(s.close)
        s.begin('127.0.0.1');token=s.access.exchange(s.access.pair)
        c=http.client.HTTPConnection('127.0.0.1',s.port,timeout=3)
        c.request('GET','/api/photo?name=foto-test.jpg',headers={'Authorization':'Bearer '+token})
        r=c.getresponse();self.assertEqual(r.status,401);self.assertNotIn(b'private photo',r.read());c.close()


if __name__=='__main__':unittest.main()
