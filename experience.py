"""Vista ambiental, ajustes directos y estado local del Desk Hub."""
from collections import Counter
import datetime as dt
import json
import socket
import subprocess
import time
from music_state import connection_label, control_ready, position_ms

AWAY_LABELS=('Estoy fuera','En reunion','En el laboratorio')


def album_colors(pixels):
    # El fondo conserva luminancia baja; el acento queda claro sobre él.
    if not pixels: return None
    bins=Counter(((p>>11)//4,((p>>5)&63)//8,(p&31)//4) for p in pixels)
    choices=[(count,key) for key,count in bins.items() if max(key)-min(key)>=2 and max(key)>=2]
    key=max(choices or [(count,key) for key,count in bins.items()])[1]
    source=[(v+.5)/8 for v in key]
    def color(channels):
        r,g,b=[max(0,min(255,round(v))) for v in channels]
        return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)
    bg=color([12+v*20 for v in source])
    accent=color([165+v*85 for v in source])
    card=color([27+v*27 for v in source])
    return dict(bg=bg,mint=accent,card=card,button=card)


def probe_system():
    result=dict(network='Sin conexion',address='',audio='Sin salida',audio_stream=False)
    def run(*args): return subprocess.run(args,capture_output=True,check=True,timeout=2).stdout
    try:
        routes=json.loads(run('ip','-j','route','show','default'))
        dev=next((r['dev'] for r in routes if r.get('dev')),None)
        if dev:
            result['network']='Wi-Fi' if dev.startswith('wl') else 'Ethernet'
            addresses=json.loads(run('ip','-j','address','show','dev',dev))
            result['address']=next((a['local'] for d in addresses for a in d.get('addr_info',[]) if a.get('family')=='inet'),'')
    except (OSError,ValueError,subprocess.SubprocessError,StopIteration): pass
    try:
        import os
        env=dict(os.environ,XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
        sinks=json.loads(subprocess.run(['pactl','--format=json','list','sinks'],env=env,capture_output=True,check=True,timeout=2).stdout)
        inputs=json.loads(subprocess.run(['pactl','--format=json','list','sink-inputs'],env=env,capture_output=True,check=True,timeout=2).stdout)
        result['audio']='Salida silenciada' if sinks and all(s.get('mute') for s in sinks) else 'Jack / disponible' if sinks else 'Sin salida'
        result['audio_stream']=any(s.get('properties',{}).get('application.process.binary')=='soloist' and not s.get('corked') and not s.get('mute') for s in inputs)
    except (OSError,ValueError,subprocess.SubprocessError,AttributeError): pass
    return result


class Experience:
    def init_experience(self):
        self.init_friendly()
        self.init_idle()
        self.ambient_enabled=True; self.ambient_return='home'; self.away_label=0
        self.away_pending=False; self.away_return=None; self.last_activity=time.monotonic()
        self.duration_edit=None; self.duration_digits=''; self.duration_error=''
        self.music_session=0; self.music_revision=0
        self.music_refresh=__import__('threading').Event(); self.spotify_restart=False
        self.system_info=dict(network='Comprobando...',address='',audio='Comprobando...',audio_stream=False)
        self.theme=dict(type(self).theme); self.palette_key=None

    def system_worker(self):
        self.ready.wait()
        while not self.stop.is_set():
            info=probe_system()
            with self.lock: self.system_info=info
            self.stop.wait(5)

    def prepare_experience(self):
        # Único escritor de pantalla: los hilos de red sólo publican datos.
        self.check_inactivity(show_ambient=True)
        self.set_display_brightness()
        base=dict(type(self).theme)
        if self.screen in ('music','ambient'):
            with self.lock: image=self.images.get('music')
            key=image[0] if image else None
            if image and getattr(self,'palette_key',None)!=key:
                self.palette_key=key; self.palette=album_colors(image[1])
            base.update(getattr(self,'palette',None) or {})
        if self.theme!=base:
            self.theme=base; self.dirty=True; self.cache.clear(); self.artwork.clear(); self.art_key=None

    def draw_connection_badge(self):
        c=self.theme; info=getattr(self,'system_info',{})
        good=info.get('network') in ('Wi-Fi','Ethernet')
        if self.cache.get('connectiondot')!=good:
            self.send(f"cirs 239,32,4,{c['mint'] if good else c['gold']}")
            self.cache['connectiondot']=good
        self.text_action('connection',256,12,216,40,'Estado / red local' if good else 'Estado / revisar',False,2)

    def music_label(self,music):
        label=connection_label(music,getattr(self,'music_stream_online',False) or time.monotonic()-getattr(self,'last_music_seen',0)<8)
        info=getattr(self,'system_info',{})
        if label=='Reproduciendo aqui' and not info.get('audio_stream',True):
            label=('Sin audio / abre Estado' if time.monotonic()-music.get('_active_since',time.monotonic())>10 else 'Comprobando salida de audio')
        return label

    def scrolling_title(self,key,value,width,font=0):
        if self.text_width(value,font)<=width: return value
        now=time.monotonic(); record=self.cache.get('scroll:'+key)
        if not record or record[0]!=value:
            record=(value,now); self.cache['scroll:'+key]=record
        offset=max(0,int((now-record[1]-2)/.6))
        maximum=len(value)
        while maximum>0 and self.text_width(value[maximum:],font)<width: maximum-=1
        maximum+=1
        phase=offset%(maximum*2+6)
        start=min(maximum,max(0,phase)) if phase<=maximum+3 else max(0,2*maximum+3-phase)
        visible=''
        for character in value[start:]:
            if self.text_width(visible+character,font)>width-4: break
            visible+=character
        return visible

    def open_duration(self,target):
        self.duration_edit=target; self.duration_digits=''; self.duration_error=''
        self.navigate('duration')

    def draw_duration(self):
        c=self.theme
        self.text('durationtitle',32,84,340,48,0,'¿Cuantos minutos?',c['ink'],c['bg'])
        self.digital('durationnumber',32,151,330,92, self.duration_digits or '0',1,c['mint'],c['bg'])
        self.paragraph('durationhint',32,260,330,self.duration_error or 'De 1 a 1440 minutos. Guardar prepara la cuenta.',3,0)
        for row,keys in enumerate([['1','2','3'],['4','5','6'],['7','8','9'],['Borrar','0','Guardar']]):
            for col,label in enumerate(keys):
                self.soft_button('durationkey'+label,416+col*112,116+row*70,104,62,label,label=='Guardar',0 if label.isdigit() else 2)
        self.text_action('durationcancel',32,416,330,44,'Cancelar',False,0)

    def touch_experience(self,x,y):
        self.last_activity=time.monotonic()
        if self.screen=='ambient':
            if (x-608)**2+(y-399)**2<=28**2:
                with self.lock: playing=self.music.get('status')=='playing'
                self.queue_music(['pause' if playing else 'play']); return True
            self.navigate(getattr(self,'ambient_return','home')); return True
        if self.screen=='duration':
            if 416<=y<460 and 32<=x<362:
                self.navigate('away' if self.duration_edit=='away' else 'time'); return True
            if 416<=x<752 and 116<=y<396:
                col=(x-416)//112; row=(y-116)//70
                if (x-416)%112>=104 or (y-116)%70>=62: return True
                key=[['1','2','3'],['4','5','6'],['7','8','9'],['Borrar','0','Guardar']][row][col]
                if key=='Borrar': self.duration_digits=self.duration_digits[:-1]
                elif key=='Guardar':
                    value=int(self.duration_digits or '0')
                    if not 1<=value<=1440: self.duration_error='Elige entre 1 y 1440 minutos.'
                    else:
                        if self.duration_edit=='away': self.timer.data=dict(mode='away',duration=value*60,remaining=value*60,deadline=None)
                        else: self.set_duration(value*60)
                        self.save(); self.navigate('away' if self.duration_edit=='away' else 'time')
                elif len(self.duration_digits)<4:
                    self.duration_digits=(self.duration_digits+key).lstrip('0'); self.duration_error=''
            return True
        if self.screen=='status':
            if 632<=x<768 and 12<=y<52: self.navigate('home')
            elif 294<=y<330 and 32<=x<768:
                self.open_display()
            elif 350<=y<406 and 32<=x<408:
                with self.lock: playing=self.music.get('is_active') and self.music.get('status') in ('playing','buffering')
                if playing: self.navigate('confirm_reconnect')
                else: self.reconnect_music()
            elif 350<=y<406 and 432<=x<768:
                self.ambient_return='home'; self.navigate('ambient')
            elif y>=424:
                self.navigate(['home','time','away','music'][min(3,x//200)])
            return True
        if not self.compact and 224<=x<480 and 12<=y<52 and self.screen not in ('lock','power'):
            self.navigate('status'); return True
        if self.screen in ('time','away') and not self.compact:
            if self.screen=='away' and 128<=y<164 and 32<=x<768:
                self.away_label=(getattr(self,'away_label',0)+1)%len(AWAY_LABELS); self.save(); return True
            if 280<=x<520 and 165<=y<247 and (self.screen=='away' or self.time_mode=='timer'):
                self.open_duration('away' if self.screen=='away' else 'timer'); return True
        return False

    def draw_ambient(self,now,music):
        c=self.theme; self.art('music',488,120,240)
        self.text('ambientdate',40,66,400,40,0,now.strftime('%d / %m'),c['muted'],c['bg'])
        self.digital('ambientclock',24,120,412,152,now.strftime('%H:%M'),3,c['ink'],c['bg'])
        self.paragraph('ambienttitle',40,292,392,music['title'] if music.get('is_active') else 'Tu espacio. A tu ritmo.',2,0)
        self.text('ambientartist',40,381,392,30,2,self.fit(('Temporizador / '+self.countdown()) if self.timer.data['deadline'] is not None and self.timer.data['mode']!='away' else ('Cronometro / '+self.hms(self.elapsed())) if self.watch['started'] is not None else music['artist'] if music.get('is_active') else 'Desk Hub Robotec',392),c['muted'],c['bg'])
        self.text('ambienthint',40,436,688,28,2,self.ambient_footer(),c['muted'],c['bg'],1)
        self.icon_button('ambienttoggle',608,399,26,'pause' if music.get('status')=='playing' else 'play',True)

    def draw_status(self):
        c=self.theme; info=getattr(self,'system_info',{}); music=self.music
        self.text('statustitle',32,76,736,48,0,'Conexiones del Hub',c['ink'],c['bg'])
        rows=[('Red',info.get('network','Comprobando...')+'  '+info.get('address','')),
              ('Audio',info.get('audio','Comprobando...')),
              ('Spotify',self.music_label(music)),
              ('Pantalla','Conectada / 115200' if getattr(self,'online',False) else 'Esperando pantalla')]
        for i,(label,value) in enumerate(rows):
            y=136+i*38
            self.text('statuslabel'+str(i),32,y,152,34,2,label,c['muted'],c['bg'])
            self.text('statusvalue'+str(i),192,y,576,34,0 if self.text_width(value,0)<576 else 2,value,c['ink'],c['bg'])
        self.text_action('ambientsetting',32,294,736,36,'Pantalla y bloqueo / ajustar tiempos y brillo',True)
        self.soft_button('reconnect',32,350,376,56,'Reconectar Spotify',False,0)
        self.soft_button('ambientnow',432,350,336,56,'Vista ambiental',True,0)
