"""Composición del panel con contraste alto y controles discretos."""
import datetime as dt
import math
import time
from nextion_link import safe_text
from settings import GITHUB_USER, LOCATION
from music_state import position_ms, control_ready
from experience import AWAY_LABELS

TABS = [('home','Inicio'),('time','Tiempo'),('away','Fuera'),('music','Spotify')]
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
        if self.screen=='gallery':
            self.text('brand',32,14,178,32,2,'ROBOTEC / AYUDA',c['ink'],c['bg'])
            self.draw_connection_badge()
            self.soft_button('galleryback',632,12,136,40,'Cámara')
            self.dirty=False; return
        if not self.compact and self.screen not in ('lock','power','ambient','duration','help','confirm_reconnect','display_settings'):
            self.text('brand',32,14,178,32,2,'ROBOTEC / AYUDA',c['ink'],c['bg'])
            self.draw_connection_badge()
            if self.screen=='status': self.soft_button('statusback',632,12,136,40,'Volver')
            elif self.screen=='home':
                self.soft_button('lockmanual',504,12,120,40,'Bloquear')
                self.soft_button('power',648,12,120,40,'Apagar')
            elif self.screen in ('music','music_options'):
                self.soft_button('musicoptions',632,12,136,40,'Volver' if self.screen=='music_options' else 'Opciones')
                if self.screen=='music': self.soft_button('libraryopen',496,12,120,40,'Guardadas')
            elif self.screen in ('library','focus','camera'):
                self.soft_button('subpageback',632,12,136,40,'Volver')
            elif self.screen=='time': self.soft_button('focusopen',632,12,136,40,'Sesiones')
            else: self.text('local',550,14,218,32,2,LOCATION,c['muted'],c['bg'],2)
            if self.screen=='status': self.soft_button('cameraopen',496,12,120,40,'Cámara')
            self.fill(32,426,736,1,c['button'])
            for i,(view,title) in enumerate(TABS):
                selected=view==self.screen or (view=='music' and self.screen in ('music_options','library')) or (view=='time' and self.screen=='focus')
                self.text('nav'+view,i*200+24,431,152,40,0,title,c['mint'] if selected else c['ink'],c['bg'],1)
                if selected: self.fill(i*200+78,473,44,3,c['mint'])
        if self.screen=='home':
            self.fill(428,82,1,308,c['button'])
            self.fill(32,268,364,1,c['button'])
        if self.compact and self.screen=='away':
            self.fill(32,59,736,1,c['button'])
            self.panel('project',410,80,358,308,c['card'],6)
            self.fill(32,400,736,1,c['button'])
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
        if self.timer.data['mode']=='away' and (self.timer.data['deadline'] is not None or getattr(self,'away_pending',False)):
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
            self.fill(464,78,304,88,c['bg'])
            self.cache.pop('weathericon',None); self.cache.pop('temperature',None)
            self.cache['homeweatherlayout']=(weather,kind)
        width=self.text_width(weather,1)+8; group=64+16+width; left=464+(304-group)//2
        self.weather_icon('weathericon',left,89,kind,64,c['bg'],c['gold'],c['blue'],c['blue'])
        self.text('temperature',left+80,78,width,86,1,weather,c['ink'],c['bg'],1)
        condition=network['condition'].split(' / ')[0]
        font=0 if self.text_width(condition,0)<=304 else 2
        self.text('condition',464,173,304,40,font,self.fit(condition,304,font),c['ink'],c['bg'],1)
        rows,forecast=self.home_weather_rows(network)
        available=any(row['at']>time.time() for row in network.get('forecast',[])) and not network.get('weather_stale')
        weatherhint='Próximas horas / lluvia %' if forecast else LOCATION+(' / ver pronóstico' if available else ' / sin pronóstico')
        self.text('weatherlocation',464,216,304,26,2,weatherhint,c['muted'],c['bg'],1)
        for i,(title,value) in enumerate(rows):
            y=260+i*44
            self.text('weatherlabel'+str(i),464,y,136,40,2,title,c['muted'],c['bg'])
            self.text('weathervalue'+str(i),600,y,168,40,0,self.fit(value,168,0),c['ink'],c['bg'],2)
        self.text('musiceyebrow',32,282,364,26,2,'TU MÚSICA' if music['status']=='playing' and music.get('is_active',False) else 'SPOTIFY CONNECT',c['mint'],c['bg'])
        self.text('homesong',32,316,364,48,0,self.fit(music['title'] if music['status']=='playing' and music.get('is_active',False) else 'Un poco de música.',364,0),c['ink'],c['bg'])
        self.draw_home_activity(music)

    def draw_away(self,repos):
        c=self.theme; deadline=self.timer.data['deadline'] or getattr(self,'away_return',None) or time.time()
        pending=self.timer.data['deadline'] is None
        self.text('awayheading',32,13,512,40,0,AWAY_LABELS[getattr(self,'away_label',0)]+'.',c['ink'],c['bg'])
        self.text('awaystatus',560,18,208,30,2,'SPOTIFY ACTIVO' if self.unlocked else 'SPOTIFY DESACTIVADO',c['muted'],c['bg'],2)
        self.text('awayreturnlabel',32,83,350,40,0,'REGRESO PENDIENTE' if pending else 'VUELVO A LAS',c['coral'],c['bg'])
        self.digital('awayreturn',24,132,366,142,dt.datetime.fromtimestamp(deadline).strftime('%H:%M'),3,c['ink'],c['bg'])
        remaining='Hora prevista' if pending else 'Faltan '+self.countdown()
        self.text('awaycount',32,287,224,40,0 if self.text_width(remaining,0)<=224 else 2,remaining,c['coral'],c['bg'])
        self.progress('awayprogress',32,345,216,1-self.timer.remaining()/max(1,self.timer.data['duration']),c['coral'])
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
        self.paragraph('awaydescription',430,225,316,repo.get('description') or 'Código y documentación de este proyecto en GitHub.',2,0,c['ink'],c['card'])
        self.text('awaystats',430,311,318,25,2,self.fit(stats,318),c['mint'],c['card'])
        self.soft_button('projectprev',430,343,70,32,'<')
        self.text('projectnumber',506,345,168,28,2,number,c['muted'],c['card'],1)
        self.soft_button('projectnext',680,343,68,32,'>')
        if self.unlocked: self.soft_button('awayhome',32,416,208,44,'Volver al inicio')
        else: self.text('awayprivacy',32,413,480,27,2,'Proyectos públicos. El panel sigue bloqueado.',c['muted'],c['bg'])
        self.soft_button('awayunlock',552,416,216,44,'Bloquear' if self.unlocked else 'Desbloquear',True,0)

    def draw_away_setup(self):
        c=self.theme; away=self.timer.data['mode']=='away'
        seconds=self.timer.remaining() if away else 1800
        self.text('awaytitle',32,78,736,45,0,'¿En cuánto tiempo vuelves?',c['ink'],c['bg'],1)
        self.text_action('awayreason',32,124,736,32,AWAY_LABELS[getattr(self,'away_label',0)]+' / cambiar',True)
        self.duration_picker('away',seconds,[(15,'15 min'),(30,'30 min'),(60,'1 hora')])
        self.soft_button('awaystart',240,342,320,56,'Estoy fuera',True,0)
        self.text('return',32,400,736,23,2,'Aviso de regreso · panel bloqueado · Spotify detenido',c['muted'],c['bg'],1)

    def draw_music(self,music):
        c=self.theme; self.art('music',40,80,240)
        title=self.scrolling_title('music',music['title'],448,0)
        self.text('musictitle',320,80,448,72,0,title,c['ink'],c['bg'])
        self.text('musicartist',320,166,448,38,0,self.fit(music['artist'],448,0),c['muted'],c['bg'])
        self.text('musiccontext',320,209,448,24,2,self.fit(music.get('context') or 'Spotify Connect',448),c['mint'],c['bg'])
        ms=position_ms(music); duration=music.get('duration',0)
        self.text('elapsed',320,238,140,24,2,f'{int(ms)//60000}:{int(ms)//1000%60:02}',c['muted'],c['bg'])
        self.text('tracklength',628,238,140,24,2,f'{duration//60000}:{duration//1000%60:02}',c['muted'],c['bg'],2)
        self.progress('trackprogress',320,267,448,ms/max(1,duration),c['mint'])
        for key,x,icon,selected in [('prev',434,'prev',False),('toggle',544,'pause' if music['status']=='playing' else 'play',True),('next',654,'next',False)]:
            self.icon_button(key,x,319,34 if selected else 26,icon,selected and control_ready(music),control_ready(music))
        self.text('playing',32,331,256,42,2,self.fit(self.music_label(music),256),c['mint'],c['bg'],1)
        ready=control_ready(music)
        assist=(ready,music.get('logged_in',False),bool(getattr(self,'music_pending',None)))
        if self.cache.get('musicassiststate')!=assist:
            self.fill(32,374,256,44,c['bg']); self.cache.pop('activity:music',None)
            self.cache.pop('button:musichelp',None); self.cache.pop('musichelp',None); self.cache['musicassiststate']=assist
        if ready: self.activity('music',113,387,music['status']=='playing',c['mint'],c['bg'])
        else:
            title='Conectando...' if assist[2] else 'Escuchar aquí' if assist[1] else '¿Cómo conectar?'
            font=0 if self.text_width(title,0)<=228 else 2
            self.soft_button('musichelp',32,374,256,44,title,True,font)
        self.text('volumelabel',320,373,84,30,2,'Volumen',c['muted'],c['bg'])
        self.progress('volumeprogress',410,384,258,music['volume']/100,c['muted'])
        self.text('volume',680,369,88,38,0,str(music['volume'])+'%',c['ink'],c['bg'],2)

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
