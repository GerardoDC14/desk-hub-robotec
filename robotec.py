#!/usr/bin/env python3
"""Desk Hub Robotec: vistas tactiles y portadas para Nextion Enhanced."""
import argparse
from collections import deque
import datetime as dt
import io
import json
import math
import os
from pathlib import Path
import queue
import select
import subprocess
import threading
import time
import urllib.request
from desk_hub import Hub, Timer, Frames, fetch, BG, CARD, INK, MUTED, MINT, BUTTON, PORT
from pin_setup import verify_pin
from settings import GITHUB_USER, SOLOIST

def rgb(hexcolor):
    r,g,b=bytes.fromhex(hexcolor)
    return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)

BG,CARD,INK,MUTED,MINT,BUTTON=[rgb(v) for v in ('202638','30394D','FFF3DF','BBC7D6','73DCCB','47536A')]
BLUE,GOLD,CORAL,LILAC=[rgb(v) for v in ('82BDF5','F4C66D','F29A86','C3A5ED')]
TABS = [('home','Inicio'),('time','Tiempo'),('away','Fuera'),('music','Spotify')]
COUNT_FONT=3

def weather_pixels(kind):
    from PIL import Image,ImageDraw
    im=Image.new('RGB',(32,32),'#202638'); d=ImageDraw.Draw(im)
    if kind in ('sun','cloud'):
        d.ellipse((5,4,20,19),fill='#F4C66D')
        for a,b in [((12,0),(12,2)),((12,21),(12,24)),((1,12),(3,12)),((23,12),(26,12)),((2,2),(5,5)),((21,2),(23,0))]: d.line((a,b),fill='#F4C66D',width=2)
    if kind!='sun':
        d.ellipse((3,12,17,24),fill='#DFE7F1');d.ellipse((10,8,25,24),fill='#DFE7F1');d.ellipse((20,14,30,24),fill='#DFE7F1');d.rectangle((8,18,25,24),fill='#DFE7F1')
    if kind=='rain':
        for x in (8,17,26): d.line((x,26,x-2,30),fill='#82BDF5',width=2)
    elif kind=='storm': d.polygon([(17,22),(12,27),(17,27),(14,31),(23,25),(18,25)],fill='#F4C66D')
    elif kind=='snow':
        for x in (8,18,27): d.line((x,26,x,30),fill='#82BDF5');d.line((x-2,28,x+2,28),fill='#82BDF5')
    elif kind=='fog':
        for y in (27,30): d.line((4,y,29,y),fill='#BBC7D6')
    return [((r>>3)<<11)|((g>>2)<<5)|(b>>3) for r,g,b in im.getdata()]

def weather_kind(code):
    if code==0: return 'sun'
    if code in (45,48): return 'fog'
    if 71<=code<=77 or code in (85,86): return 'snow'
    if code>=95: return 'storm'
    if 51<=code<=67 or 80<=code<=82: return 'rain'
    return 'cloud'

def image_pixels(url):
    from PIL import Image
    req = urllib.request.Request(url,headers={'User-Agent':'DeskHubRobotec/2.0'})
    with urllib.request.urlopen(req,timeout=6) as r:
        raw = r.read(2_000_000)
    im = Image.open(io.BytesIO(raw)).convert('RGB').resize((32,32))
    im = im.quantize(colors=48).convert('RGB')
    return [((r>>3)<<11)|((g>>2)<<5)|(b>>3) for r,g,b in im.getdata()]

def image_commands(pixels,x,y,size):
    step = size//32
    commands = []
    for row in range(32):
        start = 0
        while start < 32:
            color = pixels[row*32+start]
            end = start+1
            while end < 32 and pixels[row*32+end] == color:
                end += 1
            commands.append(f'fill {x+start*step},{y+row*step},{(end-start)*step},{step},{color}')
            start = end
    return commands

class Robotec(Hub):
    def __init__(self,port,directory):
        self.ready = threading.Event()
        self.images = {}
        self.image_jobs = queue.Queue()
        self.artwork = deque()
        self.art_key = None
        self.dirty = True
        self.screen = 'lock'
        self.unlocked=False
        self.pin_entry=''
        self.pin_failures=0
        self.pin_wait=0
        self.pin_message='Introduce tu PIN'
        self.spotify_desired=False
        self.spotify_wake=threading.Event()
        self.last_seen=0
        self.next_heartbeat=0
        self.runtime=Path('/run/user')/str(os.getuid())
        self.marker=self.runtime/'desk-hub.unlocked'
        self.pin_record=None
        try:
            pinfile=Path.home()/'.config/desk-hub/lock.json'
            if pinfile.stat().st_mode & 0o077: raise ValueError('Permisos del PIN')
            self.pin_record=json.loads(pinfile.read_text())
        except (OSError,ValueError): self.pin_message='PIN sin configurar / usa SSH'
        self.watch = {'elapsed':0.0,'started':None}
        self.time_mode = 'focus'
        self.repo_index = 0
        self.repos = []
        self.compact = False
        self.carousel_started = time.monotonic()
        super().__init__(port,directory)
        row = self.db.execute("SELECT value FROM state WHERE key='stopwatch'").fetchone()
        if row:
            self.watch = json.loads(row[0])
        if self.timer.data['mode'] in ('focus','break','timer'): self.time_mode=self.timer.data['mode']
        if self.watch['started'] is not None: self.time_mode='watch'
        self.ready.set()
        threading.Thread(target=self.cover_worker,daemon=True).start()
        threading.Thread(target=self.spotify_lifecycle,daemon=True).start()
        self.lock_hub()

    def save(self):
        super().save()
        self.db.execute("INSERT OR REPLACE INTO state VALUES ('stopwatch',?)",(json.dumps(self.watch),))
        self.db.commit()

    def worker(self):
        self.ready.wait()
        threading.Thread(target=self.github_worker,daemon=True).start()
        super().worker()

    def github_worker(self):
        while not self.stop.is_set():
            try:
                repos = fetch(f'https://api.github.com/users/{GITHUB_USER}/repos?sort=updated&per_page=20')
                with self.lock:
                    self.repos = [r for r in repos if not r.get('private')]
                profile = fetch(f'https://api.github.com/users/{GITHUB_USER}')
                pixels = image_pixels(profile['avatar_url'])
                with self.lock:
                    self.images['github'] = pixels
            except Exception as e:
                print('Perfil publico:',type(e).__name__,flush=True)
            self.stop.wait(600)

    def music_worker(self):
        self.ready.wait()
        binary=SOLOIST
        next_poll=0
        last_cover=None
        while not self.stop.is_set():
            try:
                command=self.music_commands.get(timeout=.1)
            except queue.Empty:
                command=None
            try:
                if command and self.unlocked:
                    subprocess.run([binary,'ctl','-w','127.0.0.1:9090',*command],timeout=3,capture_output=True,check=True)
                    next_poll=0
                if time.monotonic() >= next_poll:
                    result=subprocess.run([binary,'ctl','-w','127.0.0.1:9090','now','--json'],timeout=3,capture_output=True,check=True)
                    state=json.loads(result.stdout)
                    decor=(state.get('item') or {}).get('decorations',{})
                    artist=', '.join(c.get('entity',{}).get('decorations',{}).get('identity',{}).get('name','') for c in decor.get('creators',[]))
                    covers=decor.get('visual_identity',{}).get('cover',[])
                    cover=covers[0]['url'] if covers else None
                    with self.lock:
                        self.music.update(title=decor.get('identity',{}).get('name') or 'Selecciona Desk Hub Robotec',artist=artist or 'Spotify Connect',status=state.get('status','paused'),position=state.get('position',{}),duration=decor.get('playback',{}).get('duration_ms',0),cover=cover)
                        self.music['volume']=state.get('volume',30)
                    if cover != last_cover:
                        last_cover=cover
                        with self.lock:
                            self.images.pop('music',None)
                        if cover: self.image_jobs.put(cover)
                    next_poll=time.monotonic()+1
            except (OSError,subprocess.SubprocessError,ValueError):
                next_poll=time.monotonic()+3

    def cover_worker(self):
        while not self.stop.is_set():
            try: cover=self.image_jobs.get(timeout=.5)
            except queue.Empty: continue
            try:
                pixels=image_pixels(cover)
                with self.lock:
                    if self.music.get('cover')==cover: self.images['music']=(cover,pixels)
            except Exception as e:
                print('Portada:',type(e).__name__,flush=True)

    def spotify_lifecycle(self):
        env=dict(os.environ,XDG_RUNTIME_DIR=str(self.runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(self.runtime/'bus'))
        while not self.stop.is_set():
            self.spotify_wake.wait(.5)
            if not self.spotify_wake.is_set(): continue
            self.spotify_wake.clear()
            desired=self.spotify_desired
            try:
                result=subprocess.run(['systemctl','--user','start' if desired else 'stop','desk-hub-spotify'],env=env,timeout=8,capture_output=True)
                print('Spotify:',('habilitado' if desired else 'detenido') if result.returncode==0 else 'servicio no disponible',flush=True)
            except (OSError,subprocess.SubprocessError): print('Spotify: servicio no disponible',flush=True)
            if desired!=self.spotify_desired: self.spotify_wake.set()

    def lock_hub(self,away=False):
        self.unlocked=False
        self.spotify_desired=False
        self.marker.unlink(missing_ok=True)
        while not self.music_commands.empty():
            try: self.music_commands.get_nowait()
            except queue.Empty: break
        self.spotify_wake.set()
        self.pin_entry=''
        self.navigate('away' if away else 'lock')

    def unlock_hub(self):
        if time.monotonic()<self.pin_wait or not self.pin_record: return
        if verify_pin(self.pin_entry,self.pin_record):
            self.marker.touch(mode=0o600)
            self.unlocked=True; self.pin_entry=''; self.pin_failures=0
            self.spotify_desired=True; self.spotify_wake.set()
            self.navigate('home')
        else:
            self.pin_entry=''; self.pin_failures+=1
            self.pin_message='PIN incorrecto'
            if self.pin_failures>=3:
                self.pin_wait=time.monotonic()+30; self.pin_failures=0

    def fill(self,x,y,w,h,color):
        self.send(f'fill {x},{y},{w},{h},{color}')

    def label(self,key,x,y,w,h,value,font=2,color=INK,bg=CARD,align=0):
        self.text(key,x,y,w,h,font,value,color,bg,align)

    def button(self,key,x,y,w,h,value,selected=False):
        self.label(key,x,y,w,h,value,2,BG if selected else INK,MINT if selected else BUTTON,1)

    def navigate(self,view):
        if not self.unlocked and view not in ('lock','away'): view='lock'
        self.screen=view
        self.compact=(view=='away' and self.timer.data['mode']=='away' and self.timer.data['deadline'] is not None) or (view=='time' and (self.watch['started'] is not None if self.time_mode=='watch' else self.timer.data['deadline'] is not None and self.timer.data['mode']!='away'))
        self.dirty=True
        self.cache.clear()
        self.artwork.clear()
        self.art_key=None
        print('Vista:',view,flush=True)

    def change(self,seconds):
        left=max(0,min(24*3600,self.timer.remaining()+seconds))
        self.timer.data['remaining']=left
        self.timer.data['duration']=max(1,min(24*3600,self.timer.data['duration']+seconds))
        if self.timer.data['deadline'] is not None:
            self.timer.data['deadline']=time.time()+left
        self.save()

    def touch(self,x,y):
        now=time.monotonic()
        if now-self.last_touch < .15: return
        self.last_touch=now
        if self.screen=='lock':
            if time.monotonic()<self.pin_wait: return
            if 96<=y<376 and 220<=x<580:
                row=(y-96)//70; col=(x-220)//120
                keys=[['1','2','3'],['4','5','6'],['7','8','9'],['Borrar','0','Entrar']]
                key=keys[row][col]
                if key=='Borrar': self.pin_entry=self.pin_entry[:-1]
                elif key=='Entrar': self.unlock_hub()
                elif len(self.pin_entry)<6: self.pin_entry+=key
            return
        if not self.unlocked:
            if self.screen=='away' and 342<=y<400: self.navigate('lock')
            return
        if self.screen=='power':
            if 260<=y<330:
                if x<400: self.navigate('home')
                else:
                    self.save(); self.lock_hub(); self.send(f'cls {BG}')
                    self.label('shutdown',24,100,752,200,'Apagando la Pi... espera 30 segundos antes de retirar alimentacion',0,INK,BG,1)
                    os.sync()
                    result=subprocess.run(['sudo','-n','/usr/bin/systemctl','poweroff'],timeout=5,capture_output=True)
                    if result.returncode: self.pin_message='No se pudo apagar / usa SSH'; self.navigate('lock')
            return
        if self.screen=='home' and 650<=x<776 and 12<=y<52:
            self.navigate('power'); return
        if self.screen=='home' and 512<=x<776 and 408<=y<428:
            self.lock_hub(); return
        if self.compact and self.screen in ('time','away'):
            if 332<=y<400:
                if x<390:
                    if self.screen=='time' and self.time_mode=='watch':
                        self.watch['elapsed']=self.elapsed(); self.watch['started']=None
                    else: self.timer.toggle()
                else:
                    if self.screen=='time' and self.time_mode=='watch': self.watch={'elapsed':0.0,'started':None}
                    else: self.timer.reset()
                self.save(); self.compact=False; self.navigate(self.screen)
            return
        if y >= 424:
            i=x//200
            if 0 <= i < 4: self.navigate(TABS[i][0])
            return
        if self.screen=='home':
            if 512 <= x < 776:
                if 80 <= y < 180: self.navigate('time')
                elif 196 <= y < 296: self.navigate('away')
                elif 312 <= y < 408: self.navigate('music')
        elif self.screen=='time':
            if 80 <= y < 124:
                modes=['focus','break','timer','watch']
                i=(x-24)//188
                if 0 <= i < 4:
                    self.time_mode=modes[i]
                    if self.time_mode!='watch': self.timer.mode(self.time_mode)
                    self.save(); self.navigate('time')
            elif 252 <= y < 312:
                if x < 390:
                    if self.time_mode=='watch':
                        if self.watch['started'] is None: self.watch['started']=time.time()
                        else:
                            self.watch['elapsed']=self.elapsed()
                            self.watch['started']=None
                    else:
                        if self.timer.data['mode']!=self.time_mode: self.timer.mode(self.time_mode)
                        self.timer.toggle()
                else:
                    if self.time_mode=='watch': self.watch={'elapsed':0.0,'started':None}
                    else: self.timer.reset()
                self.save()
                self.navigate('time')
            elif 338 <= y < 390 and self.time_mode!='watch':
                i=(x-24)//188
                if 0 <= i < 4: self.change([-300,-60,60,300][i])
        elif self.screen=='away':
            if 82 <= y < 130:
                i=(x-24)//150
                if 0 <= i < 5:
                    seconds=[5,15,30,60,120][i]*60
                    self.timer.data=dict(mode='away',duration=seconds,remaining=seconds,deadline=None)
                    self.save()
            elif 256 <= y < 308:
                if x < 390:
                    if self.timer.data['mode']!='away': self.timer.mode('away'); self.timer.data['deadline']=None
                    self.timer.toggle()
                else: self.timer.reset()
                self.save()
                self.carousel_started=time.monotonic()
                self.navigate('away')
                if self.timer.data['deadline'] is not None: self.lock_hub(away=True)
            elif 334 <= y < 386:
                if self.timer.data['mode']=='away': self.change([-300,-60,60,300][max(0,min(3,(x-24)//188))])
        elif self.screen=='music':
            with self.lock: m=self.music.copy()
            command=None
            if 276 <= y < 330:
                i=(x-280)//165
                if 0 <= i < 3: command=[['prev'],['pause' if m['status']=='playing' else 'play'],['next']][i]
            elif 350 <= y < 400:
                delta=-10 if 280 <= x < 410 else 10 if 646 <= x < 776 else 0
                if delta:
                    with self.lock:
                        value=max(0,min(100,self.music['volume']+delta))
                        self.music['volume']=value
                        command=['volume',str(value)]
            if command: self.music_commands.put(command)
        elif self.screen=='github' and 346 <= y < 394:
            with self.lock: count=len(self.repos)
            if count:
                self.repo_index=(self.repo_index+(-1 if x < 520 else 1))%count
                self.navigate('github')

    def elapsed(self):
        return self.watch['elapsed']+(time.time()-self.watch['started'] if self.watch['started'] is not None else 0)

    def base(self):
        self.send(f'cls {BG}')
        if not self.compact and self.screen not in ('lock','power'):
            self.label('brand',24,12,560,38,'Desk Hub Robotec',0,INK,BG)
            if self.screen=='home': self.button('power',650,12,126,40,'Apagar')
            else: self.label('local',602,22,174,22,'ZAPOPAN / WI-FI',2,MINT,BG,2)
            for i,(view,title) in enumerate(TABS):
                self.button('nav'+view,i*200+8,432,184,40,title,view==self.screen)
        self.dirty=False

    def art(self,key,x,y,size):
        with self.lock: data=self.images.get(key)
        ident=(key,data[0] if key=='music' and data else bool(data))
        if ident!=self.art_key:
            self.art_key=ident
            self.artwork.clear()
            self.fill(x,y,size,size,BUTTON)
            if data:
                pixels=data[1] if key=='music' else data
                self.artwork.extend(image_commands(pixels,x,y,size))
            else:
                self.label('noart'+key,x,y,size,size,'ROBOTEC',0,MINT,BUTTON,1)
        for _ in range(min(20,len(self.artwork))): self.send(self.artwork.popleft())

    def countdown(self):
        n=self.timer.remaining()
        return f'{n//3600:02}:{n//60%60:02}:{n%60:02}' if n>=3600 else f'{n//60:02}:{n%60:02}'

    def progress(self,key,x,y,w,ratio,color=MINT):
        value=max(0,min(w,round(w*ratio)))
        if self.cache.get(key)!=value:
            self.fill(x,y,w,6,BUTTON)
            if value: self.fill(x,y,value,6,color)
            self.cache[key]=value

    def render(self):
        if self.timer.data['deadline'] is not None and self.timer.remaining()==0:
            self.timer.data.update(deadline=None,remaining=0); self.save()
            if self.compact: self.compact=False; self.navigate(self.screen if self.unlocked else 'lock')
        if self.dirty: self.base()
        with self.lock:
            n=self.network.copy(); m=self.music.copy(); repos=self.repos.copy()
        now=dt.datetime.now()
        if self.screen=='lock':
            self.label('locktitle',24,8,752,40,'Desk Hub Robotec / Bloqueado',0,LILAC,BG,1)
            self.label('pindots',24,48,752,42,'*'*len(self.pin_entry) or '------',0,INK,BG,1)
            keys=[['1','2','3'],['4','5','6'],['7','8','9'],['Borrar','0','Entrar']]
            for row,values in enumerate(keys):
                for col,key in enumerate(values): self.label('pin'+key,220+col*120,96+row*70,112,62,key,0 if key.isdigit() else 2,BG if key=='Entrar' else INK,MINT if key=='Entrar' else BUTTON,1)
            left=max(0,math.ceil(self.pin_wait-time.monotonic()))
            self.label('lockhint',24,390,752,38,f'Espera {left} segundos' if left else self.pin_message,2,MUTED,BG,1)
            self.label('lockspotify',24,437,752,30,'Spotify desactivado hasta desbloquear',2,MINT,BG,1)
            return
        if self.screen=='power':
            self.label('powertitle',24,80,752,120,'¿Apagar la Raspberry Pi?',0,INK,BG,1)
            self.label('powerhint',24,200,752,40,'Luego espera 30 s y retira la alimentacion de ambos equipos',2,MUTED,BG,1)
            self.button('powercancel',124,270,266,60,'Cancelar')
            self.button('powerconfirm',410,270,266,60,'Apagar Pi',True)
            return
        if self.compact and self.screen=='time':
            watch=self.time_mode=='watch'
            title={'focus':'Un momento para enfocarte','break':'Es hora de descansar','timer':'Tu tiempo, a tu ritmo','watch':'Cronometro en marcha'}.get(self.time_mode,'Cuenta en marcha')
            self.label('runningtitle',24,85,752,48,title,0,LILAC,BG,1)
            elapsed=int(self.elapsed())
            value=f'{elapsed//3600:02}:{elapsed//60%60:02}:{elapsed%60:02}' if watch else self.countdown()
            self.label('runningtime',24,145,752,155,value,COUNT_FONT,INK,BG,1)
            if not watch: self.progress('runbar',124,309,552,1-self.timer.remaining()/max(1,self.timer.data['duration']),CORAL)
            self.button('runpause',124,342,266,58,'Pausar',True)
            self.button('runreset',410,342,266,58,'Reiniciar')
            return
        if self.compact and self.screen=='away':
            self.label('awayintro',24,66,752,32,'Estoy fuera / mientras vuelvo, visita mi GitHub',2,LILAC,BG,1)
            self.label('awaycount',24,106,240,94,self.countdown(),1,GOLD,BG,1)
            deadline=self.timer.data['deadline']
            self.label('awayreturn',24,207,240,30,'Vuelvo a las '+dt.datetime.fromtimestamp(deadline).strftime('%H:%M'),2,MUTED,BG,1)
            self.art('github',48,252,64)
            self.label('handle',120,252,140,64,GITHUB_USER,2,MINT,BG)
            if repos:
                index=int((time.monotonic()-self.carousel_started)//12)%len(repos)
                repo=repos[index]
                self.label('awayrepo',292,110,484,76,repo['name'][:32],0,INK,CARD)
                self.label('awaydescription',292,190,484,90,(repo.get('description') or 'Explora este proyecto publico en GitHub')[:130],2,MUTED,CARD)
                self.label('awaystats',292,284,484,32,f"{repo.get('language') or 'Proyecto'} / {repo['stargazers_count']} estrellas / {index+1} de {len(repos)}",2,MINT,CARD)
            else: self.label('awaypending',292,110,484,170,'GitHub / consultando proyectos publicos',0,INK,CARD)
            if self.unlocked:
                self.button('awaypause',124,342,266,58,'Pausar',True)
                self.button('awayreset',410,342,266,58,'Reiniciar')
            else:
                self.button('awayunlock',124,342,552,58,'Desbloquear con PIN',True)
            return
        if self.screen=='home':
            self.label('clock',24,100,464,104,now.strftime('%H:%M'),1,INK,BG,1)
            days=['Lunes','Martes','Miercoles','Jueves','Viernes','Sabado','Domingo']
            self.label('date',24,211,464,30,f'{days[now.weekday()]} / {now:%d.%m.%Y}',2,MUTED,BG,1)
            kind=weather_kind(n.get('weather_code',3))
            if self.cache.get('weathericon')!=kind:
                for command in image_commands(weather_pixels(kind),100,258,96): self.send(command)
                self.cache['weathericon']=kind
            self.label('weather',204,266,224,58,n['weather'],0,GOLD,BG,1)
            self.label('condition',24,350,464,26,n['condition'],2,MUTED,BG,1)
            self.label('seconds',24,375,464,24,now.strftime('%H:%M:%S'),2,MUTED,BG,1)
            for key,y,title,detail in [('shortcut',80,'TIEMPO',self.countdown()+' / '+{'focus':'Enfoque','break':'Descanso','away':'Fuera','timer':'Timer'}[self.timer.data['mode']]),('awaycard',196,'ESTOY FUERA','Elige cuando vuelves'),('songcard',312,'SPOTIFY',m['title'][:22])]:
                self.label(key+'title',512,y,264,44,{'shortcut':'Tiempo','awaycard':'Estoy fuera','songcard':'Spotify'}[key],0,{'shortcut':LILAC,'awaycard':CORAL,'songcard':MINT}[key],CARD,1)
                self.label(key+'detail',512,y+44,264,50,detail,2,INK,CARD,1)
            self.button('lockmanual',512,408,264,20,'Bloquear')
        elif self.screen=='time':
            for i,(mode,title) in enumerate([('focus','Enfoque'),('break','Descanso'),('timer','Temporizador'),('watch','Cronometro')]):
                self.button('mode'+mode,24+i*188,80,180,44,title,self.time_mode==mode)
            watch=self.time_mode=='watch'
            elapsed=int(self.elapsed())
            value=f'{elapsed//3600:02}:{elapsed//60%60:02}:{elapsed%60:02}' if watch else self.countdown()
            self.label('timevalue',24,143,752,90,value,1,MINT,BG,1)
            running=self.watch['started'] is not None if watch else self.timer.data['deadline'] is not None
            self.button('start',24,252,366,60,'Pausar' if running else 'Iniciar',True)
            self.button('reset',410,252,366,60,'Reiniciar')
            if not watch:
                for i,v in enumerate(['-5 min','-1 min','+1 min','+5 min']): self.button('adjust'+str(i),24+i*188,338,180,52,v)
                self.progress('timerbar',24,238,752,1-self.timer.remaining()/max(1,self.timer.data['duration']))
            else: self.label('watchhint',24,340,752,48,'Cuenta independiente / puedes cambiar de vista',2,MUTED,BG,1)
        elif self.screen=='away':
            for i,v in enumerate([5,15,30,60,120]): self.button('preset'+str(i),24+i*150,82,144,48,str(v)+' min')
            away=self.timer.data['mode']=='away'
            self.label('awaytitle',24,145,752,32,'ESTOY FUERA / VUELVO EN' if away else 'ELIGE TU TIEMPO DE REGRESO',2,MUTED,BG,1)
            self.label('awaytime',24,184,752,64,self.countdown() if away else '--:--',1,GOLD,BG,1)
            self.button('awaystart',24,256,366,52,'Pausar' if away and self.timer.data['deadline'] is not None else 'Estoy fuera',True)
            self.button('awayreset',410,256,366,52,'Reiniciar')
            for i,v in enumerate(['-5 min','-1 min','+1 min','+5 min']): self.button('awayadjust'+str(i),24+i*188,334,180,52,v)
            deadline=self.timer.data['deadline'] if away else None
            self.label('return',24,392,752,24,'Regreso estimado: '+dt.datetime.fromtimestamp(deadline).strftime('%H:%M') if deadline else 'Selecciona duracion y pulsa Estoy fuera',2,MUTED,BG,1)
        elif self.screen=='music':
            self.art('music',24,88,224)
            self.label('musictitle',280,88,496,74,m['title'][:30],0,INK,BG)
            self.label('musicartist',280,170,496,42,m['artist'][:44],2,MUTED,BG)
            position=m.get('position',{})
            ms=position.get('position_ms',0)+(time.time()*1000-position.get('timestamp_ms',time.time()*1000))*position.get('speed',0)
            dur=m.get('duration',0)
            ms=max(0,min(dur,ms))
            self.label('tracktime',280,225,496,28,f'{int(ms)//60000}:{int(ms)//1000%60:02} / {dur//60000}:{dur//1000%60:02}',2,MUTED,BG)
            self.progress('trackprogress',280,259,496,ms/max(1,dur),BLUE)
            for i,title in enumerate(['Anterior','Pausar' if m['status']=='playing' else 'Reproducir','Siguiente']): self.button('music'+str(i),280+i*165,276,156,54,title,i==1)
            self.button('volminus',280,350,130,50,'Vol -')
            self.label('volume',420,350,216,50,str(m['volume'])+' %',0,INK,BG,1)
            self.button('volplus',646,350,130,50,'Vol +')
            self.label('playing',24,334,224,48,'REPRODUCIENDO' if m['status']=='playing' else 'EN PAUSA',2,MINT,BG,1)
        elif self.screen=='github':
            self.art('github',24,88,192)
            self.label('profile',24,300,192,38,GITHUB_USER,2,MINT,BG,1)
            if repos:
                repo=repos[self.repo_index%len(repos)]
                self.label('reponame',248,88,528,70,repo['name'][:32],0,INK,BG)
                self.label('repodesc',248,168,528,76,(repo.get('description') or 'Repositorio publico')[:100],2,MUTED,BG)
                self.label('repoinfo',248,262,528,34,f"{repo.get('language') or 'Proyecto'} / {repo['stargazers_count']} estrellas",2,MINT,BG)
                self.label('updated',248,307,528,28,'Actualizado: '+repo['updated_at'][:10],2,MUTED,BG)
                self.button('repoprev',248,346,254,48,'Anterior')
                self.button('reponext',522,346,254,48,'Siguiente')
            else: self.label('githubpending',248,90,528,90,n['github_detail'],0,INK,BG)

    def negotiate(self):
        for speed in (self.termios.B115200,self.termios.B9600):
            c=self.termios.tcgetattr(self.fd); c[4]=c[5]=speed
            self.termios.tcsetattr(self.fd,self.termios.TCSANOW,c)
            self.termios.tcflush(self.fd,self.termios.TCIOFLUSH)
            self.send('')
            self.send('sendme')
            end=time.monotonic()+1
            received=b''
            while time.monotonic()<end:
                r,_,_=select.select([self.fd],[],[],.1)
                if r: received+=os.read(self.fd,4096)
                if b'\x66\x00\xff\xff\xff' in received:
                    if speed!=self.termios.B115200:
                        self.send('baud=115200'); time.sleep(.15)
                        c[4]=c[5]=self.termios.B115200
                        self.termios.tcsetattr(self.fd,self.termios.TCSANOW,c)
                    print('UART 115200 validado',flush=True)
                    return
        raise RuntimeError('Pantalla sin respuesta a 9600/115200')

    def run(self):
        while True:
            if not self.online and time.monotonic()>=self.next_retry:
                try:
                    self.negotiate(); self.send('bkcmd=0'); self.send('page 0')
                    self.next_retry=time.monotonic()+3
                except (RuntimeError,OSError):
                    self.next_retry=time.monotonic()+3
                    print('Esperando pantalla',flush=True)
            r,_,_=select.select([self.fd],[],[],.02)
            if r:
                for frame in self.frames.feed(os.read(self.fd,4096)):
                    if frame==b'\x66\x00':
                        self.last_seen=time.monotonic()
                        if not self.online:
                            self.online=True; self.dirty=True; self.cache.clear(); self.art_key=None
                    elif len(frame)==6 and frame[0]==0x67 and frame[5]==0:
                        self.touch(int.from_bytes(frame[1:3],'big'),int.from_bytes(frame[3:5],'big'))
                    elif frame==b'\x88':
                        self.lock_hub(); self.online=False; self.next_retry=0
                    elif frame and frame[0] in (0,3,4,5,0x1a): print('UART error:',frame.hex(),flush=True)
            if self.online and time.monotonic()-self.last_tick >= .12:
                self.render(); self.last_tick=time.monotonic()
            if self.online and time.monotonic()>=self.next_heartbeat:
                self.send('sendme'); self.next_heartbeat=time.monotonic()+2
            if self.online and time.monotonic()-self.last_seen>6:
                self.lock_hub(); self.online=False; self.next_retry=0

def selftest():
    from desk_hub import selftest as original
    original()
    hub=Robotec.__new__(Robotec)
    hub.timer=Timer(); hub.save=lambda:None
    hub.change(-3600); assert hub.timer.remaining()==0
    hub.change(60); assert hub.timer.remaining()==60
    hub.timer.toggle(); hub.change(-30); assert 29<=hub.timer.remaining()<=30
    hub.change(1000000); assert hub.timer.remaining()<=86400
    assert len(image_commands([123]*1024,24,88,224))==32
    hub.watch={'elapsed':12,'started':None}; assert hub.elapsed()==12
    hub.timer=Timer(); hub.time_mode='focus'; hub.screen='time'; hub.compact=False; hub.unlocked=True
    hub.marker=type('Marker',(),{'unlink':lambda *a,**k:None})()
    hub.spotify_wake=threading.Event(); hub.music_commands=queue.Queue()
    hub.last_touch=0; hub.cache={}; hub.artwork=deque(); hub.art_key=None
    hub.touch(100,280); assert hub.compact and hub.timer.data['deadline'] is not None
    hub.last_touch=0; hub.touch(200,350)
    assert not hub.compact and hub.timer.data['deadline'] is None
    hub.screen='away'; hub.last_touch=0; hub.touch(330,100)
    assert hub.timer.remaining()==1800
    hub.last_touch=0; hub.touch(100,280); assert hub.compact and not hub.unlocked
    assert hub.spotify_desired is False and hub.timer.data['deadline'] is not None
    hub.last_touch=0; hub.touch(500,350); assert hub.screen=='lock'
    assert hub.timer.data['deadline'] is not None
    assert weather_kind(61)=='rain' and weather_kind(0)=='sun' and weather_kind(95)=='storm'
    import hashlib
    test_record=dict(salt='ab'*16,iterations=120000)
    test_record['hash']=hashlib.pbkdf2_hmac('sha256',b'123456',bytes.fromhex(test_record['salt']),120000).hex()
    assert verify_pin('123456',test_record) and not verify_pin('654321',test_record)
    hub.pin_record=test_record; hub.pin_wait=0; hub.pin_failures=0
    for _ in range(3): hub.pin_entry='654321'; hub.unlock_hub()
    assert not hub.unlocked and hub.pin_wait>time.monotonic()
    print('OK: cuentas, Fuera bloqueado, continuidad, PIN y limite de intentos')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default=PORT)
    parser.add_argument('--state-dir',default=str(Path.home()/'.local/share/desk-hub'))
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test: selftest()
    else:
        hub=Robotec(args.port,args.state_dir)
        try: hub.run()
        finally:
            hub.stop.set(); hub.db.close(); os.close(hub.fd)
