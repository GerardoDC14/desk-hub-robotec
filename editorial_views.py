"""Composición del panel: papel cálido, espacio y controles discretos."""
import datetime as dt
import math
import time
from nextion_link import safe_text
from settings import GITHUB_USER, LOCATION
from music_state import position_ms

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
        if not self.compact and self.screen not in ('lock','power'):
            self.text('brand',32,14,440,32,2,'ROBOTEC  /  DESK HUB',c['ink'],c['bg'])
            if self.screen=='home':
                self.soft_button('lockmanual',532,12,112,36,'Bloquear')
                self.soft_button('power',656,12,112,36,'Apagar')
            else: self.text('local',550,14,218,32,2,LOCATION,c['muted'],c['bg'],2)
            self.fill(32,426,736,1,c['button'])
            for i,(view,title) in enumerate(TABS):
                selected=view==self.screen or (view=='home' and self.screen=='weather')
                self.text('nav'+view,i*200+24,431,152,40,2,title,c['mint'] if selected else c['muted'],c['bg'],1)
                if selected: self.fill(i*200+78,473,44,3,c['mint'])
        if self.screen=='home':
            self.fill(478,88,1,170,c['button'])
            self.fill(32,284,736,1,c['button'])
        if self.compact and self.screen=='away':
            self.fill(32,59,736,1,c['button'])
            self.panel('project',410,80,358,308,c['card'],6)
            self.fill(32,400,736,1,c['button'])
        self.dirty=False

    def draw_lock(self,now):
        c=self.theme
        self.text('lockbrand',32,20,352,32,2,'ROBOTEC  /  DESK HUB',c['mint'],c['bg'])
        self.text('locktitle',32,91,352,48,0,'Bienvenido.',c['ink'],c['bg'])
        self.digital('lockclock',32,151,330,90,now.strftime('%H:%M'),1,c['ink'],c['bg'])
        self.paragraph('lockhint',32,261,324,'Espera '+str(max(0,math.ceil(self.pin_wait-time.monotonic())))+' segundos' if time.monotonic()<self.pin_wait else self.pin_message,2,color=c['muted'])
        self.paragraph('lockspotify',32,329,320,'Spotify se activa al desbloquear el panel.',2,color=c['muted'])
        if self.cache.get('pindots')!=len(self.pin_entry):
            self.fill(416,65,328,32,c['bg'])
            for i in range(6): self.send(f"cirs {440+i*52},81,5,{c['mint'] if i<len(self.pin_entry) else c['button']}")
            self.cache['pindots']=len(self.pin_entry)
        for row,values in enumerate([['1','2','3'],['4','5','6'],['7','8','9'],['Borrar','0','Entrar']]):
            for col,title in enumerate(values):
                self.soft_button('pin'+title,PIN_X+col*PIN_DX,PIN_Y+row*PIN_DY,104,62,title,title=='Entrar',0 if title.isdigit() else 2)
        if self.timer.data['mode']=='away' and self.timer.data['deadline'] is not None:
            self.soft_button('backaway',32,395,324,44,'Ver aviso de regreso')

    def draw_home(self,now,network,music,kind):
        c=self.theme
        days=['Lunes','Martes','Miercoles','Jueves','Viernes','Sabado','Domingo']
        months=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']
        self.text('date',32,67,422,30,2,f'{days[now.weekday()]}, {now.day} {months[now.month-1]} {now.year}',c['muted'],c['bg'])
        self.digital('clock',24,106,430,151,now.strftime('%H:%M'),3,c['ink'],c['bg'])
        weather=network['weather']
        if '°' not in weather: weather='--°'
        weather=weather.replace(' °C','°')
        if self.cache.get('homeweatherlayout')!=(weather,kind):
            self.fill(500,90,268,86,c['bg'])
            self.cache.pop('weathericon',None); self.cache.pop('temperature',None)
            self.cache['homeweatherlayout']=(weather,kind)
        width=self.text_width(weather,1)+8; group=64+16+width; left=510+(258-group)//2
        self.weather_icon('weathericon',left,102,kind,64,c['bg'],c['gold'],c['blue'],c['blue'])
        self.text('temperature',left+80,94,width,82,1,weather,c['ink'],c['bg'],1)
        condition=network['condition'].split(' / ')[0]
        self.text('condition',504,184,264,30,2,self.fit(condition,264),c['ink'],c['bg'],1)
        self.text('weatherlocation',504,218,264,26,2,LOCATION+' / ver clima',c['muted'],c['bg'],1)
        self.text('nowlabel',32,302,736,24,2,'AHORA SUENA' if music['status']=='playing' else 'TU MUSICA',c['mint'],c['bg'])
        self.text('homesong',32,332,736,40,0,self.fit(music['title'],736,0),c['ink'],c['bg'])
        detail=music['artist'] if music['status']=='playing' else 'Abre Spotify y elige Desk Hub Robotec'
        if self.timer.data['deadline'] is not None:
            detail=('Fuera / regreso '+dt.datetime.fromtimestamp(self.timer.data['deadline']).strftime('%H:%M')) if self.timer.data['mode']=='away' else 'Temporizador / '+self.countdown()
        elif self.alarm.data['enabled']: detail='Alarma / '+dt.datetime.fromtimestamp(self.alarm.data['deadline']).strftime('%H:%M')
        self.text('homedetail',32,379,736,28,2,self.fit(detail,736),c['muted'],c['bg'])

    def draw_weather(self,network,kind):
        c=self.theme
        self.text('weatherheading',32,74,736,46,0,'El tiempo en '+LOCATION,c['ink'],c['bg'])
        self.weather_icon('forecasticon',66,151,kind,96,c['bg'],c['gold'],c['blue'],c['blue'])
        self.text('forecasttemp',190,145,320,100,1,network['weather'],c['ink'],c['bg'])
        self.text('forecastcondition',64,254,688,36,0,self.fit(network['condition'].split(' / ')[0],688,0),c['ink'],c['bg'])
        for i,(title,value) in enumerate([('Sensacion',network.get('feels','--')),('Humedad',network.get('humidity','--')),('Viento',network.get('wind','--'))]):
            x=32+i*254
            self.text('forecastlabel'+str(i),x,316,236,26,2,title,c['muted'],c['bg'],1)
            self.text('forecastvalue'+str(i),x,348,236,44,0,value,c['ink'],c['bg'],1)
        self.text('forecastsource',32,397,736,22,2,'Open-Meteo / '+network.get('weather_updated','sin actualizar'),c['muted'],c['bg'])

    def draw_away(self,repos):
        c=self.theme; deadline=self.timer.data['deadline']
        self.text('awayheading',32,13,512,40,0,'Estoy fuera.',c['ink'],c['bg'])
        self.text('awaystatus',560,18,208,30,2,'SPOTIFY ACTIVO' if self.unlocked else 'SPOTIFY DESACTIVADO',c['muted'],c['bg'],2)
        self.text('awayreturnlabel',32,92,350,30,2,'VUELVO A LAS',c['coral'],c['bg'])
        self.digital('awayreturn',24,132,366,142,dt.datetime.fromtimestamp(deadline).strftime('%H:%M'),3,c['ink'],c['bg'])
        remaining='Faltan '+self.countdown()
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
            language=repo.get('language') or 'Proyecto publico'
            stats=language+' / '+str(repo.get('stargazers_count',0))+' estrellas'
            number=f'{index+1} de {len(repos)}'
        else:
            repo=dict(name='GitHub',description='Los proyectos publicos aparecen al conectar con GitHub.')
            stats='Solo informacion publica'; number='Sin proyectos'
        self.paragraph('awayrepo',430,137,316,repo['name'],2,0,bg=c['card'])
        self.paragraph('awaydescription',430,227,316,repo.get('description') or 'Codigo y documentacion de este proyecto en GitHub.',3,2,c['muted'],c['card'])
        self.text('awaystats',430,311,318,25,2,self.fit(stats,318),c['mint'],c['card'])
        self.soft_button('projectprev',430,343,70,32,'<')
        self.text('projectnumber',506,345,168,28,2,number,c['muted'],c['card'],1)
        self.soft_button('projectnext',680,343,68,32,'>')
        if self.unlocked: self.soft_button('awayhome',32,416,208,44,'Volver al inicio')
        else: self.text('awayprivacy',32,413,480,27,2,'Proyectos publicos. El panel sigue bloqueado.',c['muted'],c['bg'])
        self.soft_button('awayunlock',552,416,216,44,'Bloquear' if self.unlocked else 'Desbloquear',True,2)

    def draw_away_setup(self):
        c=self.theme; away=self.timer.data['mode']=='away'
        for i,v in enumerate([5,15,30,60,120]):
            self.soft_button('preset'+str(i),24+i*150,82,144,48,str(v)+' min',away and self.timer.data['duration']==v*60)
        self.text('awaytitle',24,147,752,30,2,'¿EN CUANTO TIEMPO VUELVES?',c['muted'],c['bg'],1)
        self.digital('awaytime',24,183,752,66,self.countdown() if away else '30:00',1,c['ink'],c['bg'])
        self.button('awaystart',24,256,366,52,'Estoy fuera',True)
        self.button('awayreset',410,256,366,52,'Reiniciar')
        for i,v in enumerate(['-5 min','-1 min','+1 min','+5 min']): self.button('awayadjust'+str(i),24+i*188,334,180,52,v)
        self.text('return',24,393,752,24,2,'Se muestra tu regreso, se bloquea el panel y se detiene Spotify.',c['muted'],c['bg'],1)

    def draw_music(self,music):
        c=self.theme; self.art('music',40,96,192)
        self.paragraph('musictitle',280,82,496,music['title'],2,0)
        self.text('musicartist',280,166,496,26,2,self.fit(music['artist'],496),c['muted'],c['bg'])
        self.text('musiccontext',280,199,496,24,2,self.fit(music.get('context') or 'Spotify Connect',496),c['mint'],c['bg'])
        ms=position_ms(music); duration=music.get('duration',0)
        self.text('tracktime',280,230,496,24,2,f'{int(ms)//60000}:{int(ms)//1000%60:02} / {duration//60000}:{duration//1000%60:02}',c['muted'],c['bg'])
        self.progress('trackprogress',280,259,496,ms/max(1,duration),c['mint'])
        for i,title in enumerate(['Anterior','Pausar' if music['status']=='playing' else 'Reproducir','Siguiente']):
            self.soft_button('music'+str(i),280+i*165,282,156,54,title,i==1,2)
        self.soft_button('volminus',280,350,130,44,'Vol -')
        self.text('volume',420,350,216,44,0,str(music['volume'])+' %',c['ink'],c['bg'],1)
        self.soft_button('volplus',646,350,130,44,'Vol +')
        options=music.get('options',{}); repeat=options.get('repeat','off')
        self.soft_button('shuffle',280,400,236,24,'Aleatorio',options.get('shuffle',False),2)
        self.soft_button('repeat',528,400,248,24,'Repetir / '+{'off':'No','context':'Lista','track':'Tema'}.get(repeat,'No'),repeat!='off',2)
        self.text('playing',24,306,224,30,2,'REPRODUCIENDO' if music['status']=='playing' else 'EN PAUSA',c['mint'],c['bg'],1)
        self.activity('music',88,375,music['status']=='playing',c['mint'],c['bg'])
        self.text('nexttrack',24,389,224,23,2,self.fit('Luego / '+music['next_title'],224) if music.get('next_title') else 'Spotify Connect',c['muted'],c['bg'],1)
