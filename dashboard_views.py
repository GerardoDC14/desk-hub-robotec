"""Herramientas de tiempo y avisos; el PIN sigue controlando el acceso."""
import datetime as dt
import time


class DashboardViews:
    def set_duration(self,seconds):
        self.timer.data = dict(mode='timer',duration=seconds,remaining=seconds,deadline=None)
        self.save()

    def lap(self):
        if self.watch['started'] is None: return
        laps = self.watch.setdefault('laps',[])
        laps.append(self.elapsed())
        del laps[:-5]
        self.watch['lap_count'] = self.watch.get('lap_count',0)+1
        self.save()

    @staticmethod
    def hms(seconds):
        value = int(seconds)
        return f'{value//3600:02}:{value//60%60:02}:{value%60:02}'

    def touch_time(self,x,y):
        if 80<=y<124 and 24<=x<776:
            mode = ['timer','watch','alarm'][min(2,(x-24)//254)]
            self.time_mode = mode
            if mode=='timer' and self.timer.data['mode']=='away': self.set_duration(600)
            self.navigate('time')
            return
        if self.time_mode=='alarm':
            if 250<=y<294 and 24<=x<776:
                self.alarm.adjust(**[{'hours':-1},{'hours':1},{'minutes':-1},{'minutes':1}][min(3,(x-24)//188)])
                self.save()
            elif 316<=y<368:
                if x<390:
                    if self.alarm.data['enabled']: self.alarm.cancel()
                    else: self.alarm.arm()
                    self.save()
                else: self.alert_sound.play()
            return
        watch = self.time_mode=='watch'
        if not watch and 248<=y<290 and 24<=x<776:
            self.set_duration([300,1500,2700,3600][min(3,(x-24)//188)])
        elif 306<=y<358:
            if x<390:
                if watch:
                    if self.watch['started'] is None: self.watch['started']=time.time()
                    else: self.watch.update(elapsed=self.elapsed(),started=None)
                else:
                    self.time_mode='timer'
                    if self.timer.data['mode']=='away': self.set_duration(600)
                    self.timer.toggle()
            else:
                if watch: self.watch={'elapsed':0.0,'started':None,'laps':[],'lap_count':0}
                else: self.timer.reset()
            self.save(); self.navigate('time')
        elif 372<=y<414:
            if watch: self.lap()
            elif 24<=x<776: self.change([-300,-60,60,300][min(3,(x-24)//188)])

    def render_time(self):
        c=self.theme
        for i,(mode,title) in enumerate([('timer','Temporizador'),('watch','Cronometro'),('alarm','Alarma')]):
            self.button('mode'+mode,24+i*254,80,244,44,title,self.time_mode==mode)
        if self.time_mode=='alarm':
            self.digital('alarmvalue',24,147,752,90,f"{self.alarm.data['hour']:02}:{self.alarm.data['minute']:02}",1,c['mint'],c['bg'])
            for i,title in enumerate(['Hora -','Hora +','Minuto -','Minuto +']):
                self.button('alarmadjust'+str(i),24+i*188,250,180,44,title)
            self.button('alarmtoggle',24,316,366,52,'Desactivar' if self.alarm.data['enabled'] else 'Activar',self.alarm.data['enabled'])
            self.button('alarmtest',410,316,366,52,'Probar sonido')
            deadline=self.alarm.data['deadline']
            status='Sonara el '+dt.datetime.fromtimestamp(deadline).strftime('%d/%m a las %H:%M') if deadline else 'Alarma de una vez / requiere Pi encendida'
            self.label('alarmhint',24,388,752,28,status,2,c['muted'],c['bg'],1)
            return
        watch=self.time_mode=='watch'
        if watch:
            self.digital('watchvalue',24,156,470,92,self.hms(self.elapsed()),1,c['mint'],c['bg'])
            self.analog('watchdial',638,205,69,self.elapsed(),c['muted'],c['mint'],c['bg'])
        else:
            self.digital('timevalue',24,140,752,90,self.countdown(),1,c['mint'],c['bg'])
            for i,title in enumerate(['5 / Descanso','25 / Enfoque','45 min','60 min']):
                self.button('duration'+str(i),24+i*188,248,180,42,title)
            self.progress('timerbar',24,232,752,1-self.timer.remaining()/max(1,self.timer.data['duration']))
        running=self.watch['started'] is not None if watch else self.timer.data['deadline'] is not None
        self.button('start',24,306,366,52,'Pausar' if running else 'Iniciar',True)
        self.button('reset',410,306,366,52,'Reiniciar')
        if watch:
            last=self.watch.get('laps',[])
            text='Marcar vuelta' if not last else 'Vuelta '+str(self.watch.get('lap_count',len(last)))+' / '+self.hms(last[-1])
            self.button('lap',24,372,752,42,text)
        else:
            for i,title in enumerate(['-5 min','-1 min','+1 min','+5 min']):
                self.button('adjust'+str(i),24+i*188,372,180,42,title)

    def render_running(self):
        c=self.theme
        watch=self.time_mode=='watch'
        self.label('runningtitle',24,75,752,48,'Cronometro' if watch else 'Temporizador',0,c['lilac'],c['bg'],1)
        if watch:
            self.digital('runningtime',24,153,470,135,self.hms(self.elapsed()),1,c['ink'],c['bg'])
            self.analog('watchdial',638,213,88,self.elapsed(),c['muted'],c['mint'],c['bg'])
            last=self.watch.get('laps',[])
            text='Marcar vuelta' if not last else 'Vuelta '+str(self.watch.get('lap_count',len(last)))+' / '+self.hms(last[-1])
            self.button('runlap',124,412,552,36,text)
        else:
            self.digital('runningtime',24,145,752,155,self.countdown(),3,c['ink'],c['bg'])
            self.progress('runbar',124,309,552,1-self.timer.remaining()/max(1,self.timer.data['duration']),c['coral'])
        self.button('runpause',124,342,266,58,'Pausar',True)
        self.button('runreset',410,342,266,58,'Reiniciar')

    def notify(self,title,kind):
        if not self.notice:
            self.notice={'title':title,'kind':kind,'previous':self.screen}
        else:
            self.notice['title']=title
            self.notice['kind']=kind
        self.dirty=True; self.cache.clear(); self.artwork.clear(); self.art_key=None
        if kind!='missed': self.alert_sound.play()

    def poll_tools(self):
        changed=self.alarm.poll()
        if changed:
            self.save()
            self.notify('Es la hora' if changed=='ring' else 'Alarma vencida', 'alarm' if changed=='ring' else 'missed')
        if self.timer.data['deadline'] is not None and self.timer.remaining()==0:
            mode=self.timer.data['mode']
            self.timer.data.update(deadline=None,remaining=0)
            self.save()
            if mode=='away':
                self.compact=False
                self.navigate('home' if self.unlocked else 'lock')
            else:
                self.compact=False
                self.notify('Tiempo cumplido','timer')

    def render_notice(self):
        c=self.theme
        self.label('noticetitle',24,84,752,100,self.notice['title'],1,c['mint'],c['bg'],1)
        self.label('noticeclock',24,193,752,45,dt.datetime.now().strftime('%H:%M'),0,c['muted'],c['bg'],1)
        self.button('dismiss',124,270,266,60,'Aceptar',True)
        if self.notice['kind']=='alarm': self.button('snooze',410,270,266,60,'Posponer 5 min')
        self.label('noticehint',24,369,752,40,'Tu PIN sigue protegiendo el panel' if not self.unlocked else 'Puedes volver a tu actividad',2,c['muted'],c['bg'],1)

    def touch_notice(self,x,y):
        if not 270<=y<330: return
        if 410<=x<676 and self.notice['kind']=='alarm':
            self.alarm.snooze(); self.save()
        elif not 124<=x<390:
            return
        previous=self.notice['previous']
        self.alert_sound.silence(); self.notice=None
        self.navigate(previous)
