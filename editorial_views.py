"""Composición del panel con contraste alto y controles discretos."""
import datetime as dt
import math
import time
from nextion_link import safe_text
from settings import GITHUB_USER, LOCATION
from music_state import position_ms, control_ready
from experience import AWAY_LABELS

from navigation import TABS,tab_bounds
PIN_X, PIN_Y, PIN_DX, PIN_DY = 416,116,112,70


class EditorialViews:
    def fit(self,value,width,font=2):
        value=safe_text(value)
        if self.text_width(value,font)<=width: return value
        while value and self.text_width(value+'...',font)>width: value=value[:-1]
        return value+'...'

    def paragraph(self,key,x,y,w,value,lines=3,font=2,color=None,bg=None):
        c=self.theme; height={0:40,1:76,2:25,3:140}[font]
        words=safe_text(value).split(); result=[]; line=''
        for word in words:
            candidate=(line+' '+word).strip()
            if line and self.text_width(candidate,font)>w:
                result.append(self.fit(line,w,font)); line=word
            else: line=candidate
        if line: result.append(self.fit(line,w,font))
        if len(result)>lines: result[lines-1]=self.fit(result[lines-1]+' ...',w,font)
        for i in range(lines):
            self.text(key+str(i),x,y+i*height,w,height,font,result[i] if i<len(result) else '',color if color is not None else c['ink'],bg if bg is not None else c['bg'])

    def draw_base(self):
        c=self.theme; self.send(f"cls {c['bg']}")
        if self.notice: self.dirty=False; return
        if self.screen=='videos':
            self.soft_button('videoback',632,12,136,40,'Volver')
            self.dirty=False;return
        if self.screen=='notion':
            self.soft_button('notionrefresh',496,12,120,40,'Actualizar')
            self.soft_button('notionback',632,12,136,40,'Inicio')
            self.dirty=False; return
        if self.screen in ('gallery','gallery_grid','viewfinder','photo_show'):
            self.text('brand',32,14,178,32,2,'ROBOTEC / AYUDA',c['ink'],c['bg'])
            self.draw_connection_badge()
            if getattr(self,'_photo_action',None):
                self.soft_button('galleryback',632,12,136,40,'Volver')
                self.dirty=False; return
            self.soft_button('galleryback',632,12,136,40,{'gallery':'Álbum','gallery_grid':'Cámara','viewfinder':'Inicio','photo_show':'Álbum'}[self.screen])
            if self.screen=='gallery_grid': self.soft_button('showstart',496,12,120,40,'Presentar')
            if self.screen=='gallery':self.soft_button('photooptions',496,12,120,40,'Opciones')
            self.dirty=False; return
        if not self.compact and self.screen not in ('lock','power','ambient','duration','help','confirm_reconnect','display_settings'):
            self.text('brand',32,14,178,32,2,'ROBOTEC / AYUDA',c['ink'],c['bg'])
            self.draw_connection_badge()
            if self.screen=='status': self.soft_button('statusback',632,12,136,40,'Volver')
            elif self.screen=='camera':
                self.soft_button('videoopen',496,12,120,40,'Vídeos')
                self.soft_button('cameraback',632,12,136,40,'Volver')
            elif self.screen=='home':
                self.soft_button('lockmanual',504,12,120,40,'Bloquear')
                self.soft_button('power',648,12,120,40,'Apagar')
            elif self.screen in ('music','music_options'):
                self.soft_button('musicoptions',632,12,136,40,'Volver' if self.screen=='music_options' else 'Opciones')
                if self.screen=='music': self.soft_button('libraryopen',496,12,120,40,'Guardadas')
            elif self.screen in ('library','focus','camera'):
                self.soft_button('subpageback',632,12,136,40,'Volver')
            elif self.screen=='time':
                self.soft_button('timersopen',496,12,120,40,'Ver todos')
                self.soft_button('focusopen',632,12,136,40,'Sesiones')
            elif self.screen=='timers': self.soft_button('timersback',632,12,136,40,'Volver')
            else: self.text('local',550,14,218,32,2,LOCATION,c['muted'],c['bg'],2)
            if self.screen=='status': self.soft_button('cameraopen',496,12,120,40,'Cámara')
            for i,(view,title) in enumerate(TABS):
                selected=view==self.screen or (view=='music' and self.screen in ('music_options','library')) or (view=='time' and self.screen=='focus')
                left,right=tab_bounds(i)
                if selected:
                    self.panel('navpill'+view,left+6,430,right-left-12,46,c['card'],18)
                self.text('nav'+view,left+14,433,right-left-28,40,0,title,c['mint'] if selected else c['muted'],c['card'] if selected else c['bg'],1)
        if self.screen=='home':
            self.panel('homeweathercard',448,72,320,344,c['card'],24)
            self.fill(32,268,364,1,c['button'])
        if self.compact and self.screen=='away':
            self.panel('project',410,80,358,308,c['card'],24)
        self.dirty=False

    def draw_lock(self,now):
        c=self.theme
        self.text('lockbrand',32,20,352,32,2,'ROBOTEC  /  DESK HUB',c['mint'],c['bg'])
        self.soft_button('lockhelp',624,12,144,40,'Ayuda',False,0)
        self.text('locktitle',32,91,352,48,0,'Bienvenido.',c['ink'],c['bg'])
        self.digital('lockclock',32,151,330,90,now.strftime('%H:%M'),1,c['ink'],c['bg'])
        self.paragraph('lockhint',32,250,324,'Espera '+str(max(0,math.ceil(self.pin_wait-time.monotonic())))+' segundos' if time.monotonic()<self.pin_wait else self.pin_message,2,0,color=c['ink'])
        self.paragraph('lockspotify',32,330,320,'Spotify se activa al desbloquear.',2,0,color=c['muted'])
        if self.cache.get('pindots')!=len(self.pin_entry):
            self.fill(416,65,328,32,c['bg'])
            for i in range(6): self.send(f"cirs {440+i*52},81,5,{c['mint'] if i<len(self.pin_entry) else c['button']}")
            self.cache['pindots']=len(self.pin_entry)
        for row,values in enumerate([['1','2','3'],['4','5','6'],['7','8','9'],['Borrar','0','Entrar']]):
            for col,title in enumerate(values):
                self.soft_button('pin'+title,PIN_X+col*PIN_DX,PIN_Y+row*PIN_DY,104,62,title,title=='Entrar',0 if title.isdigit() else 2)
        if self.away_timer.data['mode']=='away' and (self.away_timer.data['deadline'] is not None or getattr(self,'away_pending',False)):
            self.soft_button('backaway',32,420,324,44,'Ver aviso de regreso')

    def draw_home(self,now,network,music,kind):
        c=self.theme
        days=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
        months=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']
        self.text('date',32,77,364,38,0,f'{days[now.weekday()]}, {now.day} {months[now.month-1]}',c['ink'],c['bg'])
        self.digital('clock',24,112,380,145,now.strftime('%H:%M'),3,c['ink'],c['bg'])
        weather=network['weather']
        if '°' not in weather: weather='--°'
        weather=weather.replace(' °C','°')
        if self.cache.get('homeweatherlayout')!=(weather,kind):
            self.fill(464,88,288,80,c['card'])
            self.cache.pop('weathericon',None); self.cache.pop('temperature',None)
            self.cache['homeweatherlayout']=(weather,kind)
        width=self.text_width(weather,1)+8; group=64+16+width; left=464+(288-group)//2
        self.weather_icon('weathericon',left,96,kind,64,c['card'],c['gold'],c['blue'],c['blue'])
        self.text('temperature',left+80,88,width,80,1,weather,c['ink'],c['card'],1)
        condition=network['condition'].split(' / ')[0]
        font=0 if self.text_width(condition,0)<=288 else 2
        self.text('condition',464,174,288,40,font,self.fit(condition,288,font),c['ink'],c['card'],1)
        rows,forecast=self.home_weather_rows(network)
        available=any(row['at']>time.time() for row in network.get('forecast',[])) and not network.get('weather_stale')
        weatherhint='Próximas horas / lluvia %' if forecast else LOCATION+(' / ver pronóstico' if available else ' / sin pronóstico')
        self.text('weatherlocation',464,216,288,26,2,self.fit(weatherhint,288),c['muted'],c['card'],1)
        for i,(title,value) in enumerate(rows):
            y=260+i*44
            self.text('weatherlabel'+str(i),472,y,112,40,2,self.fit(title,112),c['muted'],c['card'])
            self.text('weathervalue'+str(i),584,y,160,40,0,self.fit(value,160,0),c['ink'],c['card'],2)
        self.text('musiceyebrow',32,282,364,26,2,'TU MÚSICA' if music['status']=='playing' and music.get('is_active',False) else 'SPOTIFY CONNECT',c['mint'],c['bg'])
        self.text('homesong',32,316,364,48,0,self.fit(music['title'] if music['status']=='playing' and music.get('is_active',False) else 'Un poco de música.',364,0),c['ink'],c['bg'])
        self.draw_home_activity(music)

    def draw_away(self,repos):
        c=self.theme; deadline=self.away_timer.data['deadline'] or getattr(self,'away_return',None) or time.time()
        pending=self.away_timer.data['deadline'] is None
        self.text('awayheading',32,13,512,40,0,AWAY_LABELS[getattr(self,'away_label',0)]+'.',c['ink'],c['bg'])
        self.text('awaystatus',560,18,208,30,2,'Spotify activo' if self.unlocked else 'Spotify desactivado',c['muted'],c['bg'],2)
        self.text('awayreturnlabel',32,90,350,32,2,'REGRESO PENDIENTE' if pending else 'VUELVO A LAS',c['mint'],c['bg'])
        self.digital('awayreturn',24,132,366,142,dt.datetime.fromtimestamp(deadline).strftime('%H:%M'),3,c['ink'],c['bg'])
        remaining='Hora prevista' if pending else 'Faltan '+self.countdown(away=True)
        self.text('awaycount',32,287,224,40,0 if self.text_width(remaining,0)<=224 else 2,remaining,c['mint'],c['bg'])
        self.progress('awayprogress',32,345,216,1-self.away_timer.remaining()/max(1,self.away_timer.data['duration']),c['mint'])
        self.text('awayprofile',32,362,224,28,2,'github.com/'+GITHUB_USER,c['muted'],c['bg'])
        if 'profileqr' not in self.images:
            try:
                import qrcode
                qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,border=4)
                qr.add_data('https://github.com/'+GITHUB_USER); qr.make(fit=True)
                self.images['profileqr']=[0 if cell else 65535 for row in qr.get_matrix() for cell in row]
            except ImportError: pass
        if 'profileqr' in self.images: self.art('profileqr',270,276,111)
        self.text('projecteyebrow',430,94,318,26,2,'EXPLORA MI GITHUB',c['mint'],c['card'])
        if repos:
            index=(self.repo_index+int((time.monotonic()-self.carousel_started)//18))%len(repos)
            repo=repos[index]
            language=repo.get('language') or 'Proyecto público'
            stats=language+' / '+str(repo.get('stargazers_count',0))+' estrellas'
            number=f'{index+1} de {len(repos)}'
        else:
            repo=dict(name='GitHub',description='Los proyectos públicos aparecen al conectar con GitHub.')
            stats='Solo información publica'; number='Sin proyectos'
        self.paragraph('awayrepo',430,137,316,repo['name'],2,0,bg=c['card'])
        self.paragraph('awaydescription',430,225,316,repo.get('description') or 'Código y documentación de este proyecto en GitHub.',3,2,c['muted'],c['card'])
        self.text('awaystats',430,311,318,25,2,self.fit(stats,318),c['mint'],c['card'])
        self.soft_button('projectprev',430,343,70,32,'<')
        self.text('projectnumber',506,345,168,28,2,number,c['muted'],c['card'],1)
        self.soft_button('projectnext',680,343,68,32,'>')
        if self.unlocked: self.soft_button('awayhome',32,416,208,44,'Volver al inicio')
        else: self.text('awayprivacy',32,413,480,27,2,'Proyectos públicos. El panel sigue bloqueado.',c['muted'],c['bg'])
        self.soft_button('awayunlock',552,416,216,44,'Bloquear' if self.unlocked else 'Desbloquear',True,0)

    def draw_away_setup(self):
        c=self.theme; away=self.away_timer.data['mode']=='away'
        seconds=self.away_timer.remaining() if away else 1800
        self.text('awaytitle',32,78,736,45,0,'¿En cuánto tiempo vuelves?',c['ink'],c['bg'],1)
        self.soft_button('awayreason',224,124,352,32,AWAY_LABELS[getattr(self,'away_label',0)]+' / cambiar')
        self.duration_picker('away',seconds,[(15,'15 min'),(30,'30 min'),(60,'1 hora')])
        self.soft_button('awaystart',240,342,320,56,'Estoy fuera',True,0)
        self.text('return',32,400,736,23,2,'Aviso de regreso · panel bloqueado · Spotify detenido',c['muted'],c['bg'],1)

    def draw_output_meter(self,active):
        c=self.theme; meter=getattr(self,'output_meter',None)
        levels=meter.snapshot() if active and meter else (0.0,)*16
        for i,level in enumerate(levels):
            height=max(2,min(20,round(level*20)))
            key='soundbar'+str(i); old=self.cache.get(key,0)
            x=416+i*22
            if height>old:self.fill(x,246-height,12,height-old,c['mint'] if active else c['button'])
            elif height<old:self.fill(x,246-old,12,old-height,c['bg'])
            # El color también cambia al pausar, sin borrar el panel.
            if self.cache.get('soundactive')!=active:self.fill(x,246-height,12,height,c['mint'] if active else c['button'])
            self.cache[key]=height
        self.cache['soundactive']=active

    def draw_music(self,music):
        c=self.theme; self.art('music',32,72,344)
        ready=control_ready(music); active=ready and music['status']=='playing'
        self.text('playing',416,72,352,24,2,self.fit(self.music_label(music),352),c['mint'],c['bg'])
        title=music['title']; big=self.text_width(title,1)<=352
        if self.cache.get('titlelayout')!=big:
            self.fill(416,96,352,80,c['bg'])
            for key in ('musictitlebig','musictitle0','musictitle1'):self.cache.pop(key,None)
            self.cache['titlelayout']=big
        if big:self.text('musictitlebig',416,96,352,80,1,title,c['ink'],c['bg'])
        else:self.paragraph('musictitle',416,96,352,title,2,0)
        self.text('musicartist',416,178,352,22,2,self.fit(music['artist'],352),c['ink'],c['bg'])
        self.text('musicalbum',416,202,352,22,2,self.fit(music.get('album') or '',352),c['muted'],c['bg'])
        self.draw_output_meter(active)
        ms=position_ms(music); duration=music.get('duration',0)
        if self.cache.get('musicassiststate')!=active:
            self.fill(416,250,352,52,c['bg'])
            for key in ('elapsed','tracklength','delta:trackprogress','button:musichelp','musichelp'):self.cache.pop(key,None)
            self.cache['musicassiststate']=active
        if active:
            self.text('elapsed',416,250,128,24,2,f'{int(ms)//60000}:{int(ms)//1000%60:02}',c['muted'],c['bg'])
            self.text('tracklength',640,250,128,24,2,f'{duration//60000}:{duration//1000%60:02}',c['muted'],c['bg'],2)
            self.progress('trackprogress',416,280,352,ms/max(1,duration),c['mint'])
        else:
            title='Conectando...' if getattr(self,'music_pending',None) else 'Escuchar aquí'
            self.soft_button('musichelp',416,258,352,44,title,True,0)
        for key,x,icon,selected in [('prev',472,'prev',False),('toggle',592,'pause' if music['status']=='playing' else 'play',True),('next',712,'next',False)]:
            self.icon_button(key,x,342,34 if selected else 26,icon,selected and ready,ready)
        self.text('volumelabel',416,384,32,32,2,'Vol.',c['muted'],c['bg'])
        self.progress('volumeprogress',456,396,232,music['volume']/100,c['mint'])
        self.text('volume',704,384,64,32,2,str(music['volume'])+'%',c['ink'],c['bg'],2)

    def draw_music_options(self,music):
        c=self.theme; options=music.get('options',{}); repeat=options.get('repeat','off')
        self.text('optiontitle',48,86,704,48,0,'Tu reproducción',c['ink'],c['bg'])
        for i,(label,value) in enumerate([('Aleatorio','Activado' if options.get('shuffle') else 'Desactivado'),('Repetir',{'off':'No','context':'Lista','track':'Canción'}.get(repeat,'No'))]):
            y=159+i*72
            self.text('optionlabel'+str(i),48,y,360,52,0,label,c['ink'],c['bg'])
            self.soft_button('optionvalue'+str(i),488,y,264,52,value,False,0)
        self.text('displayshortcut',48,287,704,26,2,'Vista ambiental y PIN según la inactividad',c['mint'],c['bg'])
        self.soft_button('displaysettings',48,314,704,42,'Pantalla y bloqueo',False,0)
        self.text('nextlabel',48,365,704,24,2,'A CONTINUACIÓN',c['mint'],c['bg'])
        self.text('nexttrack',48,391,704,30,2,self.fit(music.get('next_title') or 'La cola se controla desde Spotify',704),c['ink'],c['bg'])
