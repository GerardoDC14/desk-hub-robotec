#!/usr/bin/env python3
"""Desk Hub Robotec: vistas tactiles y portadas para Nextion Enhanced."""
import argparse
from collections import deque, OrderedDict
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
from soft_ui import SoftUI
from dashboard_state import Alarm, AlertSound
from dashboard_views import DashboardViews
from music_client import MusicClient
from music_state import position_ms, control_ready
from nextion_link import NextionLink
from editorial_views import EditorialViews, PIN_X, PIN_Y, PIN_DX, PIN_DY
from experience import Experience
from friendly_ui import FriendlyUI

def rgb(hexcolor):
    r,g,b=bytes.fromhex(hexcolor)
    return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)

BG,CARD,INK,MUTED,MINT,BUTTON=[rgb(v) for v in ('171A1D','252A2E','FFFFFF','DCE3E8','7AE0BC','38434B')]
BLUE,GOLD,CORAL,LILAC=[rgb(v) for v in ('9FD4FF','FFD66F','FFB18D','D3D8C0')]
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
    im = Image.open(io.BytesIO(raw)).convert('RGB').resize((48,48), Image.Resampling.LANCZOS)
    im = im.quantize(colors=96).convert('RGB')
    return [((r>>3)<<11)|((g>>2)<<5)|(b>>3) for r,g,b in im.getdata()]

def image_commands(pixels,x,y,size,underlay=None):
    grid=math.isqrt(len(pixels))
    if grid*grid != len(pixels) or not grid:
        raise ValueError('La imagen debe ser una cuadricula cuadrada')
    active={}; rectangles=[]
    for row in range(grid):
        current={}; start=0
        while start<grid:
            color=pixels[row*grid+start]
            if underlay is not None and color==underlay[row*grid+start]:
                start+=1; continue
            end=start+1
            while end<grid and pixels[row*grid+end]==color and (underlay is None or color!=underlay[row*grid+end]): end+=1
            key=(start,end,color)
            if key in active:
                rect=active.pop(key);rect[3]=row+1
            else: rect=[start,row,end,row+1,color]
            current[key]=rect; start=end
        rectangles.extend(active.values());active=current
    rectangles.extend(active.values())
    commands=[]
    for left,top,right,bottom,color in sorted(rectangles,key=lambda r:(r[1],r[0])):
        xx,yy=round(left*size/grid),round(top*size/grid)
        w,h=round(right*size/grid)-xx,round(bottom*size/grid)-yy
        if w>0 and h>0: commands.append(f'fill {x+xx},{y+yy},{w},{h},{color}')
    return commands

class Robotec(FriendlyUI, Experience, EditorialViews, DashboardViews, MusicClient, SoftUI, Hub):
    decode_image=staticmethod(image_pixels)
    theme=dict(bg=BG,card=CARD,ink=INK,muted=MUTED,mint=MINT,lilac=LILAC,coral=CORAL,button=BUTTON,blue=BLUE,gold=GOLD)
    def __init__(self,port,directory):
        self.init_experience()
        self.ready = threading.Event()
        self.images = {}
        self.cover_cache=OrderedDict()
        self.cover_requested=None
        self.music_stream_online=False
        self.music_event_process=None
        self.notice=None
        self.alarm=Alarm()
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
        self.time_mode = 'timer'
        self.repo_index = 0
        self.repos = []
        self.compact = False
        self.carousel_started = time.monotonic()
        super().__init__(port,directory)
        row = self.db.execute("SELECT value FROM state WHERE key='stopwatch'").fetchone()
        if row:
            self.watch = json.loads(row[0])
        row=self.db.execute("SELECT value FROM state WHERE key='alarm'").fetchone()
        if row: self.alarm=Alarm(json.loads(row[0]))
        row=self.db.execute("SELECT value FROM state WHERE key='experience'").fetchone()
        if row:
            preferences=json.loads(row[0])
            self.ambient_enabled=preferences.get('ambient_enabled',True)
            self.away_label=preferences.get('away_label',0)%3
            self.away_pending=preferences.get('away_pending',False)
            self.away_return=preferences.get('away_return')
        if self.timer.data['mode']=='away' and self.timer.data['deadline'] is not None:
            self.away_pending=True; self.away_return=self.timer.data['deadline']
        row=self.db.execute("SELECT value FROM state WHERE key='friendly'").fetchone()
        if row: self.session_deadline=json.loads(row[0]).get('session_deadline')
        self.music.update(is_active=False,logged_in=False,_ready=False,_epoch=0)
        self.alert_sound=AlertSound(self.directory,self.stop)
        if self.watch['started'] is not None: self.time_mode='watch'
        self.ready.set()
        threading.Thread(target=self.music_events,daemon=True).start()
        threading.Thread(target=self.cover_worker,daemon=True).start()
        threading.Thread(target=self.spotify_lifecycle,daemon=True).start()
        threading.Thread(target=self.system_worker,daemon=True).start()
        self.lock_hub(away=self.away_pending,keep_schedule=True)

    def save(self):
        super().save()
        self.db.execute("INSERT OR REPLACE INTO state VALUES ('stopwatch',?)",(json.dumps(self.watch),))
        self.db.execute("INSERT OR REPLACE INTO state VALUES ('alarm',?)",(json.dumps(self.alarm.data),))
        self.db.execute("INSERT OR REPLACE INTO state VALUES ('experience',?)",(json.dumps(dict(ambient_enabled=self.ambient_enabled,away_label=self.away_label,away_pending=self.away_pending,away_return=self.away_return)),))
        self.db.execute("INSERT OR REPLACE INTO state VALUES ('friendly',?)",(json.dumps(dict(session_deadline=self.session_deadline)),))
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

    def spotify_lifecycle(self):
        env=dict(os.environ,XDG_RUNTIME_DIR=str(self.runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(self.runtime/'bus'))
        while not self.stop.is_set():
            self.spotify_wake.wait(.5)
            if not self.spotify_wake.is_set(): continue
            self.spotify_wake.clear()
            desired=self.spotify_desired
            restart=self.spotify_restart; self.spotify_restart=False
            try:
                if restart and desired:
                    subprocess.run(['systemctl','--user','stop','desk-hub-spotify'],env=env,timeout=8,capture_output=True)
                desired=self.spotify_desired
                result=subprocess.run(['systemctl','--user','start' if desired else 'stop','desk-hub-spotify'],env=env,timeout=8,capture_output=True)
                print('Spotify:',('habilitado' if desired else 'detenido') if result.returncode==0 else 'servicio no disponible',flush=True)
            except (OSError,subprocess.SubprocessError): print('Spotify: servicio no disponible',flush=True)
            if desired!=self.spotify_desired: self.spotify_wake.set()

    def lock_hub(self,away=False,keep_schedule=False):
        if not keep_schedule and getattr(self,'session_deadline',None) is not None:
            self.session_deadline=None; self.save()
        self.unlocked=False
        self.reset_music_session()
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
            if self.timer.data['mode']=='away':
                self.timer.reset()
                self.away_pending=False; self.away_return=None
                self.save()
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
        # Textos sobre tarjetas: margen interior preserva sus esquinas.
        if key.startswith('pin') and key!='pindots':
            self.soft_button(key,x,y,w,h,value,value=='Entrar',font)
        elif bg==CARD:
            self.panel(key,x,y,w,h,bg,12)
            self.text(key,x+12,y+3,max(1,w-24),max(1,h-6),font,value,color,bg,align)
        else:
            self.text(key,x,y,w,h,font,value,color,bg,align)

    def soft_button(self,key,x,y,w,h,value,selected=False,font=2):
        c=self.theme; fill=c['mint'] if selected else c['button']
        style=(x,y,w,h,selected,font,fill,c['ink'],c['bg'])
        if self.cache.get('button:'+key)!=style:
            self.rounded(x,y,w,h,min(6,h//2-1),fill)
            self.cache['button:'+key]=style
            self.cache.pop(key,None)
        inset=min(14,max(3,h//4))
        self.text(key,x+inset,y+(2 if h>=24 else 0),w-2*inset,h-4 if h>=24 else h,font,value,c['bg'] if selected else c['ink'],fill,1)

    def button(self,key,x,y,w,h,value,selected=False):
        font=0 if h>=52 and self.text_width(value,0)<w-32 else 2
        self.soft_button(key,x,y,w,h,value,selected,font)

    def navigate(self,view):
        if not self.unlocked and view not in ('lock','away','help'): view='lock'
        self.screen=view
        self.compact=(view=='away' and self.timer.data['mode']=='away' and (self.timer.data['deadline'] is not None or getattr(self,'away_pending',False))) or (view=='time' and (self.watch['started'] is not None if self.time_mode=='watch' else self.time_mode!='alarm' and self.timer.data['deadline'] is not None and self.timer.data['mode']!='away'))
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
        self.last_touch=now; self.last_activity=now
        if self.notice:
            self.touch_notice(x,y); return
        if self.touch_friendly(x,y): return
        if self.screen=='lock':
            if time.monotonic()<self.pin_wait: return
            if 420<=y<464 and 32<=x<356 and self.timer.data['mode']=='away' and (self.timer.data['deadline'] is not None or getattr(self,'away_pending',False)):
                self.navigate('away'); return
            if PIN_Y<=y<PIN_Y+4*PIN_DY and PIN_X<=x<PIN_X+3*PIN_DX:
                row=(y-PIN_Y)//PIN_DY; col=(x-PIN_X)//PIN_DX
                if (x-PIN_X)%PIN_DX>=104 or (y-PIN_Y)%PIN_DY>=62: return
                keys=[['1','2','3'],['4','5','6'],['7','8','9'],['Borrar','0','Entrar']]
                key=keys[row][col]
                if key=='Borrar': self.pin_entry=self.pin_entry[:-1]
                elif key=='Entrar': self.unlock_hub()
                elif len(self.pin_entry)<6: self.pin_entry+=key
            return
        if self.screen=='away' and self.compact:
            if 416<=y<460 and 552<=x<768:
                if self.unlocked: self.lock_hub(away=True)
                else: self.navigate('lock')
            elif self.unlocked and 416<=y<460 and 32<=x<240: self.navigate('home')
            elif 343<=y<375 and (430<=x<500 or 680<=x<748):
                with self.lock: count=len(self.repos)
                if count:
                    index=(self.repo_index+int((time.monotonic()-self.carousel_started)//18))%count
                    self.repo_index=(index+(-1 if x<500 else 1))%count
                    self.carousel_started=time.monotonic()
            return
        if not self.unlocked:
            return
        if self.touch_experience(x,y): return
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
        if self.screen=='home' and 648<=x<768 and 12<=y<52:
            self.navigate('power'); return
        if self.screen=='home' and 504<=x<624 and 12<=y<52:
            self.lock_hub(); return
        if self.screen in ('music','music_options') and 632<=x<768 and 12<=y<52:
            self.navigate('music_options' if self.screen=='music' else 'music'); return
        if self.compact and self.screen in ('time','away'):
            if self.screen=='time' and self.time_mode=='watch' and 412<=y<448:
                self.lap(); return
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
            if 32<=x<396 and 280<=y<424: self.navigate('music')
        elif self.screen=='time':
            self.touch_time(x,y)
        elif self.screen=='away':
            seconds=None
            if 178<=y<236 and (209<=x<267 or 533<=x<591):
                remaining=self.timer.remaining() if self.timer.data['mode']=='away' else 1800
                seconds=max(60,min(86400,remaining+(-60 if x<400 else 60)))
            elif 283<=y<323 and 194<=x<614:
                seconds=[900,1800,3600][min(2,(x-194)//140)]
            if seconds is not None:
                self.timer.data=dict(mode='away',duration=seconds,remaining=seconds,deadline=None)
                self.save()
            elif 342<=y<398 and 240<=x<560:
                if self.timer.data['mode']!='away':
                    self.timer.data=dict(mode='away',duration=1800,remaining=1800,deadline=None)
                self.timer.toggle(); self.away_pending=True; self.away_return=self.timer.data['deadline']; self.save(); self.carousel_started=time.monotonic()
                self.lock_hub(away=True)
        elif self.screen in ('music','music_options'):
            with self.lock: m=self.music.copy()
            if not control_ready(m): return
            command=None
            if self.screen=='music_options':
                options=m.get('options',{})
                if 488<=x<752 and 159<=y<211: command=['shuffle','off' if options.get('shuffle') else 'on']
                elif 488<=x<752 and 231<=y<283: command=['repeat',{'off':'context','context':'track','track':'off'}.get(options.get('repeat','off'),'off')]
            elif 255<=y<279 and 320<=x<768:
                if m.get('duration',0): command=['seek',str(round((x-320)/448*m['duration']))]
            elif 285<=y<353:
                for cx,action in [(434,'prev'),(544,'pause' if m['status']=='playing' else 'play'),(654,'next')]:
                    if (x-cx)**2+(y-319)**2<=(34 if cx==544 else 28)**2: command=[action]
            elif 365<=y<409 and 410<=x<668:
                value=max(0,min(100,round((x-410)/258*100)))
                command=['volume',str(value)]
            if command: self.queue_music(command)
        elif self.screen=='github' and 346 <= y < 394:
            with self.lock: count=len(self.repos)
            if count:
                self.repo_index=(self.repo_index+(-1 if x < 520 else 1))%count
                self.navigate('github')

    def elapsed(self):
        return self.watch['elapsed']+(time.time()-self.watch['started'] if self.watch['started'] is not None else 0)

    def base(self):
        self.draw_base()

    def art(self,key,x,y,size):
        with self.lock: data=self.images.get(key)
        ident=(key,data[0] if key=='music' and data else bool(data))
        if ident==self.art_key: return
        self.art_key=ident; self.artwork.clear()
        self.fill(x,y,size,size,self.theme['button'])
        if data:
            pixels=data[1] if key=='music' else data
            if key=='music' and len(pixels)==48*48:
                coarse=[pixels[(row*4+2)*48+column*4+2] for row in range(12) for column in range(12)]
                self.artwork.extend(image_commands(coarse,x,y,size))
                underlay=[coarse[(row//4)*12+column//4] for row in range(48) for column in range(48)]
                self.artwork.extend(image_commands(pixels,x,y,size,underlay))
            else: self.artwork.extend(image_commands(pixels,x,y,size))
            self.art_started=time.monotonic(); self.art_total=len(self.artwork)
        else:
            self.label('noart'+key,x,y,size,size,'ROBOTEC',0,self.theme['mint'],self.theme['button'],1)

    def flush_artwork(self):
        if not self.artwork: return
        batch=[]; count=0
        while self.artwork:
            command=self.artwork[0]
            if batch and count+len(command)+3>256: break
            batch.append(self.artwork.popleft()); count+=len(command)+3
        self.send_batch(batch)
        if not self.artwork:
            print(f'Imagen: {self.art_total} comandos / {time.monotonic()-self.art_started:.2f} s',flush=True)

    @staticmethod
    def marquee(value,limit):
        if len(value)<=limit: return value
        source=value+'   '
        offset=int(time.monotonic()/2)%len(source)
        return (source+source)[offset:offset+limit]

    def countdown(self):
        n=self.timer.remaining()
        return f'{n//3600:02}:{n//60%60:02}:{n%60:02}' if n>=3600 else f'{n//60:02}:{n%60:02}'

    def progress(self,key,x,y,w,ratio,color=MINT):
        self.delta_progress(key,x,y,w,ratio,color,self.theme['button'])

    def send(self,command):
        drawing=getattr(self,'drawing',None)
        if drawing is not None: drawing.append(command)
        else: super().send(command)

    def render(self):
        commands=[]; self.drawing=commands
        try: self.render_view()
        finally: self.drawing=None
        if commands: self.send_batch(commands)

    def render_view(self):
        self.poll_tools()
        self.prepare_experience()
        if self.dirty: self.base()
        if self.notice:
            self.render_notice(); return
        with self.lock:
            n=self.network.copy(); m=self.music.copy(); repos=self.repos.copy()
        now=dt.datetime.now()
        if not self.compact and self.screen not in ('lock','power','ambient','duration','help','confirm_reconnect'):
            self.draw_connection_badge()
        if self.screen=='help': self.draw_help(); return
        if self.screen=='confirm_reconnect': self.draw_reconnect_confirm(); return
        if self.screen=='duration': self.draw_duration(); return
        if self.screen=='ambient': self.draw_ambient(now,m); return
        if self.screen=='status': self.draw_status(); return
        if self.screen=='lock':
            self.draw_lock(now); return
        if self.screen=='power':
            self.label('powertitle',24,80,752,120,'¿Apagar la Raspberry Pi?',0,INK,BG,1)
            self.label('powerhint',24,200,752,40,'Luego espera 30 s y retira la alimentacion de ambos equipos',2,MUTED,BG,1)
            self.button('powercancel',124,270,266,60,'Cancelar')
            self.button('powerconfirm',410,270,266,60,'Apagar Pi',True)
            return
        if self.compact and self.screen=='time':
            self.render_running(); return
        if self.compact and self.screen=='away':
            self.draw_away(repos); return
        if self.screen=='home':
            self.draw_home(now,n,m,weather_kind(n.get('weather_code',3)))
        elif self.screen=='time':
            self.render_time()
        elif self.screen=='away':
            self.draw_away_setup()
        elif self.screen=='music':
            self.draw_music(m)
        elif self.screen=='music_options':
            self.draw_music_options(m)

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
                    self.link=None
                    self.frames=Frames()
                    self.negotiate(); self.send('bkcmd=2'); self.send('page 0')
                    self.link=NextionLink(self.write_packet,self.receive_bytes,self.frames)
                    self.send('dim=100')
                    self.send('sendme')
                    self.next_retry=time.monotonic()+3
                except (RuntimeError,OSError):
                    self.next_retry=time.monotonic()+3
                    print('Esperando pantalla',flush=True)
            self.poll_tools()
            frames=list(self.link.pending) if self.link else []
            if self.link: self.link.pending.clear()
            frames.extend(self.frames.feed(self.receive_bytes(.005)))
            for frame in frames:
                if frame==b'\x66\x00':
                    self.last_seen=time.monotonic()
                    if not self.online:
                        self.online=True; self.dirty=True; self.cache.clear(); self.art_key=None
                elif len(frame)==6 and frame[0]==0x67 and frame[5]==0:
                    self.touch(int.from_bytes(frame[1:3],'big'),int.from_bytes(frame[3:5],'big'))
                elif frame==b'\x88':
                    self.lock_hub(); self.online=False; self.next_retry=0
                elif frame and frame[0] in (0,3,4,5,0x1a): print('UART error:',frame.hex(),flush=True)
            if self.online and time.monotonic()-self.last_tick >= .10:
                self.render(); self.last_tick=time.monotonic()
            if self.online: self.flush_artwork()
            if self.online and time.monotonic()>=self.next_heartbeat:
                self.send('sendme'); self.next_heartbeat=time.monotonic()+2
            if self.online and time.monotonic()-self.last_seen>6:
                self.lock_hub(); self.online=False; self.next_retry=0

def selftest():
    from desk_hub import selftest as original
    original()
    hub=Robotec.__new__(Robotec)
    hub.init_experience(); hub.lock=threading.Lock(); hub.music={}
    hub.timer=Timer(); hub.save=lambda:None
    hub.change(-3600); assert hub.timer.remaining()==0
    hub.change(60); assert hub.timer.remaining()==60
    hub.timer.toggle(); hub.change(-30); assert 29<=hub.timer.remaining()<=30
    hub.change(1000000); assert hub.timer.remaining()<=86400
    assert len(image_commands([123]*1024,24,88,224))==1
    hub.watch={'elapsed':12,'started':None}; assert hub.elapsed()==12
    hub.timer=Timer(); hub.time_mode='timer'; hub.screen='time'; hub.compact=False; hub.unlocked=True; hub.notice=None; hub.alarm=Alarm()
    hub.marker=type('Marker',(),{'unlink':lambda *a,**k:None})()
    hub.spotify_wake=threading.Event(); hub.music_commands=queue.Queue()
    hub.last_touch=0; hub.cache={}; hub.artwork=deque(); hub.art_key=None
    hub.touch(400,370); assert hub.compact and hub.timer.data['deadline'] is not None
    hub.last_touch=0; hub.touch(200,350)
    assert not hub.compact and hub.timer.data['deadline'] is None
    hub.screen='away'; hub.last_touch=0; hub.touch(400,300)
    assert hub.timer.remaining()==1800
    hub.last_touch=0; hub.touch(400,370); assert hub.compact and not hub.unlocked
    assert hub.spotify_desired is False and hub.timer.data['deadline'] is not None
    hub.last_touch=0; hub.touch(650,435); assert hub.screen=='lock'
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
            hub.stop.set()
            if hub.music_event_process and hub.music_event_process.poll() is None:
                hub.music_event_process.terminate()
            hub.alert_sound.silence(); hub.alert_sound.thread.join(3); hub.db.close(); os.close(hub.fd)
