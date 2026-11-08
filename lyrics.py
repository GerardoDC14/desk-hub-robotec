"""Letras sincronizadas bajo demanda; red aislada del dibujo y del audio."""
from bisect import bisect_right
from collections import OrderedDict
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


@dataclass(frozen=True)
class Lyrics:
    status: str
    rows: tuple = ()
    times: tuple = ()


class Backoff(Exception):
    def __init__(self,seconds): self.seconds=seconds


def retry_delay(value):
    try:
        seconds=float(value)
        return max(1,seconds) if math.isfinite(seconds) else 60
    except (ValueError,TypeError):
        try: return max(1,parsedate_to_datetime(value).timestamp()-time.time())
        except (ValueError,TypeError,OverflowError): return 60


def parse_lrc(value,duration):
    if not isinstance(value,str) or len(value)>100_000: return Lyrics('unsynced')
    offset=re.search(r'\[offset:([+-]?\d+)\]',value,re.I)
    offset=int(offset[1]) if offset else 0
    rows={}
    for line in value.splitlines()[:2000]:
        stamps=re.findall(r'\[(\d{1,3}):([0-5]\d)(?:[.:](\d{1,3}))?\]',line)
        text=re.sub(r'\[[^\]]*\]','',line).strip()[:300]
        for minute,second,fraction in stamps:
            at=max(0,(int(minute)*60+int(second))*1000+int((fraction or '0').ljust(3,'0'))-offset)
            if at>duration+10_000: continue
            if at not in rows: rows[at]=text
            elif text and text!=rows[at]: rows[at]=(rows[at]+' / '+text)[:300]
    result=tuple(sorted(rows.items()))
    if not any(text for _,text in result):return Lyrics('unsynced')
    return Lyrics('synced',result,tuple(at for at,_ in result))


def fetch_lyrics(track):
    title,artist,album,duration=track
    query=urllib.parse.urlencode(dict(track_name=title,artist_name=artist,album_name=album,duration=duration/1000))
    request=urllib.request.Request('https://lrclib.net/api/get?'+query,
        headers={'User-Agent':'DeskHubRobotec/2.1 (https://github.com/GerardoDC14/desk-hub-robotec)', 'Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=3) as response:
            raw=response.read(262145)
        if len(raw)>262144: return Lyrics('unavailable')
        data=json.loads(raw)
        if not isinstance(data,dict): return Lyrics('unavailable')
        # Evita sincronizar otra versión de duración distinta.
        if abs(float(data.get('duration',0))*1000-duration)>2000:return Lyrics('missing')
        if data.get('instrumental'): return Lyrics('instrumental')
        return parse_lrc(data.get('syncedLyrics'),duration)
    except urllib.error.HTTPError as error:
        if error.code==404:return Lyrics('missing')
        if error.code in (429,503):raise Backoff(retry_delay(error.headers.get('Retry-After')))
        return Lyrics('unavailable')


def three_lines(lyrics,position):
    index=bisect_right(lyrics.times,position)-1
    return tuple(lyrics.rows[n][1] if 0<=n<len(lyrics.rows) else '' for n in (index-1,index,index+1))


class LyricsClient:
    """Un trabajador, ocho resultados en RAM y ninguna llamada desde el hilo de pantalla."""
    def __init__(self,fetch=fetch_lyrics):
        self._fetch=fetch; self._cv=threading.Condition()
        self._key=None; self._wanted=None; self._generation=0; self._closed=False
        self._cache=OrderedDict(); self._result=Lyrics('empty'); self._refresh=0; self._not_before=0
        self._thread=threading.Thread(target=self._worker,name='desk-hub-lyrics',daemon=True)
        self._thread.start()

    def request(self,music,session=0):
        track=(music.get('title',''),music.get('artist',''),music.get('album',''),music.get('duration',0))
        key=(session,music.get('uri',''),track)
        with self._cv:
            if self._closed:return Lyrics('empty')
            now=time.monotonic()
            if key==self._key and now<self._refresh:return self._result
            self._key=key; self._generation+=1; self._wanted=None
            if not key[1].startswith('spotify:track:') or not track[0] or not track[1] or not 1000<=track[3]<=3_600_000:
                self._result=Lyrics('empty'); self._refresh=float('inf'); return self._result
            cached=self._cache.get(track)
            if cached and now<cached[0]:
                self._cache.move_to_end(track); self._refresh=cached[0]; self._result=cached[1]
            else:
                self._result=Lyrics('loading'); self._refresh=float('inf')
                self._wanted=(self._generation,track); self._cv.notify()
            return self._result

    def cancel(self):
        with self._cv:
            self._generation+=1; self._key=None; self._wanted=None; self._result=Lyrics('empty')
            self._cv.notify()

    def close(self):
        with self._cv: self._closed=True; self._cv.notify()

    def _worker(self):
        while True:
            with self._cv:
                while not self._closed:
                    if self._wanted and time.monotonic()>=self._not_before:break
                    self._cv.wait(min(60,max(.05,self._not_before-time.monotonic())) if self._wanted else None)
                if self._closed:return
                generation,track=self._wanted; self._wanted=None
            retry=0
            try: result=self._fetch(track)
            except Backoff as error: result=Lyrics('limited'); retry=error.seconds
            except Exception: result=Lyrics('unavailable')
            with self._cv:
                now=time.monotonic(); self._not_before=now+max(.5,retry)
                if self._closed or generation!=self._generation:continue
                ttl=1800 if result.status=='synced' else 300 if result.status in ('missing','instrumental','unsynced') else max(60,retry)
                self._result=result; self._refresh=now+ttl
                self._cache[track]=(self._refresh,result); self._cache.move_to_end(track)
                while len(self._cache)>8:self._cache.popitem(last=False)


class LyricsViews:
    def lyrics_result(self,music):
        if not getattr(self,'lyrics',None) and not str(music.get('uri','')).startswith('spotify:track:'):
            return Lyrics('empty')
        if not getattr(self,'lyrics',None):self.lyrics=LyricsClient()
        return self.lyrics.request(music,getattr(self,'music_session',0))

    def music_controls(self,music,ambient=False):
        from music_state import control_ready
        ready=control_ready(music)
        for action,x,y,r in self.music_control_bounds(ambient):
            icon=('pause' if music.get('status')=='playing' else 'play') if action=='toggle' else action
            self.icon_button('lyricscontrol'+action,x,y,r,icon,action=='toggle' and ready,ready)

    @staticmethod
    def music_control_bounds(ambient=False):
        return (('prev',528,348,22),('toggle',608,348,26),('next',688,348,22)) if ambient else (
            ('prev',408,374,26),('toggle',552,374,32),('next',696,374,26))

    def touch_music_controls(self,x,y,ambient=False):
        for action,cx,cy,r in self.music_control_bounds(ambient):
            if (x-cx)**2+(y-cy)**2<=(r+2)**2:
                with self.lock: playing=self.music.get('status')=='playing'
                self.queue_music(['pause' if playing else 'play'] if action=='toggle' else [action])
                return True
        return False

    def draw_lyrics(self,music):
        from music_state import position_ms
        c=self.theme
        result=self.lyrics_result(music)
        self.art('music',32,80,240)
        self.paragraph('lyricstitle',32,332,240,music.get('title',''),2,2,color=c['ink'])
        self.text('lyricsartist',32,388,240,26,2,self.fit(music.get('artist',''),240),c['muted'],c['bg'])
        messages={'empty':'Reproduce una canción para ver su letra','loading':'Buscando letra sincronizada…',
            'missing':'No hay letra disponible para esta versión','instrumental':'Esta canción es instrumental',
            'unsynced':'Esta versión no tiene letra sincronizada','unavailable':'No se pudo consultar la letra. Se reintentará.',
            'limited':'El servicio está ocupado. Se reintentará.'}
        rows=three_lines(result,position_ms(music)) if result.status=='synced' else ('',messages.get(result.status,''),'')
        self.panel('lyricsfocus',296,168,472,64,c['card'],18)
        for i,value in enumerate(rows):
            font=0 if self.text_width(value,0)<=440 else 2
            self.text('lyricsline'+str(i),312,96+i*72,440,60,font,self.fit(value,440,font),
                      c['mint'] if i==1 else c['muted'],c['card'] if i==1 else c['bg'],1)
        self.music_controls(music)
        status=('Sigue la reproducción en el Hub' if not music.get('is_active') else 'En pausa' if music.get('status')!='playing' else 'Sincronizada por frase')
        self.text('lyricssource',296,310,472,28,2,self.fit('LRCLIB · '+status if result.status=='synced' else 'Letras: LRCLIB',472),c['muted'],c['bg'],1)

    def ambient_lyrics(self,music):
        from music_state import position_ms
        if not music.get('is_active'):
            if getattr(self,'lyrics',None): self.lyrics.cancel()
            return ''
        result=self.lyrics_result(music)
        if result.status=='synced':
            current=three_lines(result,position_ms(music))[1]
            return current or 'Música · LRCLIB'
        return {'loading':'Buscando letra · LRCLIB','instrumental':'Instrumental',
                'unsynced':'Letra sin sincronización','missing':'Letra no disponible',
                'unavailable':'Letra no disponible por ahora','limited':'Letras en espera'}.get(result.status,'')
