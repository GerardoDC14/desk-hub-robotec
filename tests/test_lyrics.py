import io
import datetime as dt
import json
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch
from test_dashboard import hub
from lyrics import Lyrics, LyricsClient, Backoff, fetch_lyrics, parse_lrc, three_lines, retry_delay


SONG=dict(uri='spotify:track:example',title='Prueba',artist='Robotec',album='Pruebas',duration=60000)
LRC='[00:01.00]Primera frase de prueba\n[00:03.500]Segunda frase de prueba\n[00:06.00]\n[00:08.00]Última frase de prueba'


class LyricsTests(unittest.TestCase):
    def client(self,fetch):
        client=LyricsClient(fetch)
        self.addCleanup(client.close)
        return client

    def ready(self,client,music=SONG):
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            result=client.request(music)
            if result.status!='loading':return result
            time.sleep(.01)
        self.fail('worker did not complete')

    def test_lrc_boundaries_gaps_seek_back_and_offsets(self):
        result=parse_lrc(LRC,60000)
        self.assertEqual(three_lines(result,0),('','','Primera frase de prueba'))
        self.assertEqual(three_lines(result,3500)[1],'Segunda frase de prueba')
        self.assertEqual(three_lines(result,6500)[1],'')
        self.assertEqual(three_lines(result,1000)[1],'Primera frase de prueba')
        multi=parse_lrc('[offset:100]\n[00:02.1][00:04.20]Prueba',60000)
        self.assertEqual(multi.times,(2000,4100))
        self.assertEqual(parse_lrc('[ar:Robotec]\nSin tiempos',60000).status,'unsynced')

    def test_fetch_duration_instrumental_missing_and_size_limits(self):
        def response(**data):return io.BytesIO(json.dumps(dict(duration=60,**data)).encode())
        with patch('urllib.request.urlopen',return_value=response(syncedLyrics=LRC)) as request:
            self.assertEqual(fetch_lyrics(('Prueba','Robotec','Pruebas',60000)).status,'synced')
            self.assertEqual(request.call_args.kwargs['timeout'],3)
        with patch('urllib.request.urlopen',return_value=response(instrumental=True)):
            self.assertEqual(fetch_lyrics(('a','b','c',60000)).status,'instrumental')
        with patch('urllib.request.urlopen',return_value=response(syncedLyrics=LRC)):
            self.assertEqual(fetch_lyrics(('a','b','c',70000)).status,'missing')
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'x'*262145)):
            self.assertEqual(fetch_lyrics(('a','b','c',60000)).status,'unavailable')
        error=urllib.error.HTTPError('https://lrclib.net',429,'limited',{'Retry-After':'120'},None)
        with patch('urllib.request.urlopen',side_effect=error):
            with self.assertRaises(Backoff) as caught:fetch_lyrics(('a','b','c',60000))
            self.assertEqual(caught.exception.seconds,120)
        self.assertEqual(retry_delay('NaN'),60)

    def test_slow_network_never_blocks_request_and_cancel_discards_response(self):
        entered=threading.Event(); release=threading.Event()
        def fetch(track):entered.set(); release.wait(2); return parse_lrc(LRC,60000)
        client=self.client(fetch)
        self.assertEqual(client.request(SONG).status,'loading'); self.assertTrue(entered.wait(1))
        started=time.monotonic()
        for _ in range(100):self.assertEqual(client.request(SONG).status,'loading')
        self.assertLess(time.monotonic()-started,.2)
        client.cancel(); release.set()
        client.close(); client._thread.join(1)
        self.assertEqual(client._result.status,'empty'); self.assertFalse(client._cache)

    def test_track_switch_rejects_late_song_and_caches_success(self):
        entered=threading.Event(); release=threading.Event(); calls=[]
        def fetch(track):
            calls.append(track[0])
            if track[0]=='Prueba':entered.set(); release.wait(1)
            return parse_lrc('[00:00]'+track[0],60000)
        client=self.client(fetch); client.request(SONG); self.assertTrue(entered.wait(1))
        second=dict(SONG,uri='spotify:track:second',title='Otra')
        client.request(second); release.set()
        self.assertEqual(self.ready(client,second).rows[0][1],'Otra')
        client.cancel(); self.assertEqual(client.request(second).status,'synced')
        self.assertEqual(calls,['Prueba','Otra'])

    def test_rate_limit_applies_across_song_changes(self):
        calls=[]
        def fetch(track):calls.append(track); raise Backoff(120)
        client=self.client(fetch); self.assertEqual(self.ready(client).status,'limited')
        client.request(dict(SONG,uri='spotify:track:second',title='Otra'))
        time.sleep(.06)
        self.assertEqual(len(calls),1)
        self.assertGreater(client._not_before-time.monotonic(),119)

    def test_unchanged_phrase_sends_nothing_and_change_updates_only_three_lines(self):
        app=hub(); app.screen='lyrics'; app.music.update(SONG)
        app.music.update(status='paused',position={'position_ms':1500,'speed':0})
        result=parse_lrc(LRC,60000)
        class Client:
            def request(self,*a):return result
            def cancel(self):pass
        app.lyrics=Client(); sent=[]; app.send=sent.append
        app.draw_lyrics(app.music); sent.clear()
        app.draw_lyrics(app.music); self.assertEqual(sent,[])
        app.music['position']['position_ms']=4000; app.draw_lyrics(app.music)
        self.assertEqual(len(sent),3)
        self.assertTrue(all(c.startswith('xstr ') and len(c.encode('latin-1'))+3<=240 for c in sent))

    def test_button_return_footer_and_locked_access(self):
        app=hub(); app.screen='music'; app.last_touch=0; app.touch(710,77)
        self.assertEqual(app.screen,'lyrics')
        app.last_touch=0; app.touch(700,32); self.assertEqual(app.screen,'music')
        app.screen='lyrics'; app.last_touch=0; app.touch(40,450); self.assertEqual(app.screen,'home')
        app.unlocked=False; app.navigate('lyrics'); self.assertEqual(app.screen,'lock')

    def test_controls_in_both_views_keep_view_and_respect_readiness(self):
        for view in ('lyrics','ambient'):
            app=hub(); app.screen=view
            for action,x,y,r in app.music_control_bounds(view=='ambient'):
                app.last_touch=0;app.touch(x,y)
                self.assertEqual(app.music_commands.get_nowait()['command'],['play' if action=='toggle' else action])
                self.assertEqual(app.screen,view)
            app.music['status']='playing';app.last_touch=0
            app.touch(608,348) if view=='ambient' else app.touch(552,374)
            self.assertEqual(app.music_commands.get_nowait()['command'],['pause'])
            app.music['_ready']=False;app.last_touch=0
            app.touch(688,348) if view=='ambient' else app.touch(696,374)
            self.assertTrue(app.music_commands.empty());self.assertEqual(app.screen,view)

    def test_ambient_only_current_phrase_updates_and_return_preserves_request(self):
        app=hub(); app.screen='ambient';app.music.update(SONG)
        app.music.update(status='paused',position={'position_ms':1500,'speed':0})
        result=parse_lrc(LRC,60000); cancelled=[]
        class Client:
            def request(self,*a):return result
            def cancel(self):cancelled.append(True)
        app.lyrics=Client();sent=[];app.send=sent.append
        now=dt.datetime(2026,11,8,13,0)
        app.draw_ambient(now,app.music);sent.clear()
        app.draw_ambient(now,app.music);self.assertEqual(sent,[])
        app.music['position']['position_ms']=4000;app.draw_ambient(now,app.music)
        self.assertEqual(len(sent),1);self.assertTrue(sent[0].startswith('xstr 40,382,'))
        app.navigate('lyrics');app.navigate('ambient');self.assertEqual(cancelled,[])
        app.navigate('home');self.assertEqual(len(cancelled),1)

    def test_cover_and_controls_regions_do_not_cover_three_lines(self):
        app=hub(); app.screen='lyrics';app.music.update(SONG)
        app.lyrics=type('Client',(),{'request':lambda *a:parse_lrc(LRC,60000)})()
        app.images['music']=('cover',[123]*9216)
        sent=[];app.send=sent.append;app.draw_lyrics(app.music)
        rows=[c for c in sent if c.startswith('xstr 312,')]
        self.assertEqual(len(rows),3)
        for row in rows:
            x,y,w,h=map(int,row.split(' ',1)[1].split(',')[:4])
            self.assertGreaterEqual(x,272);self.assertLessEqual(y+h,304)
        self.assertTrue(app.artwork)


if __name__=='__main__':unittest.main()
