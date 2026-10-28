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
            self.navigate('time'); return
        if self.time_mode=='alarm':
            if 158<=y<246 and 286<=x<514:
                self.alarm_field='hour' if x<400 else 'minute'
            elif 178<=y<236 and (209<=x<267 or 533<=x<591):
                field=getattr(self,'alarm_field','minute')
                self.alarm.adjust(**{('hours' if field=='hour' else 'minutes'):-1 if x<400 else 1})
                self.save()
            elif 279<=y<319 and 360<=x<668:
                self.alarm.data['volume']=max(20,min(100,round((x-360)/308*100)))
                self.save()
            elif 342<=y<398 and 240<=x<560:
                if self.alarm.data['enabled']: self.alarm.cancel()
                else: self.alarm.arm()
                self.save()
            elif 342<=y<398 and 600<=x<768:
                self.alert_sound.play(seconds=5,volume=self.alarm.data['volume'])
            return
        watch=self.time_mode=='watch'
        if not watch:
            if 178<=y<236 and (209<=x<267 or 533<=x<591):
                self.set_duration(max(60,min(86400,self.timer.remaining()+(-60 if x<400 else 60))))
            elif 283<=y<323 and 194<=x<614:
                self.set_duration([300,1500,3600][min(2,(x-194)//140)])
            elif 342<=y<398 and 240<=x<560:
                if self.timer.data['mode']=='away': self.set_duration(600)
                self.timer.toggle(); self.save(); self.navigate('time')
            elif 342<=y<398 and 600<=x<768:
                self.timer.reset(); self.save(); self.navigate('time')
        elif 342<=y<398:
            if 240<=x<560:
                self.watch['started']=time.time(); self.save(); self.navigate('time')
            elif 600<=x<768:
                self.watch={'elapsed':0.0,'started':None,'laps':[],'lap_count':0}
                self.save(); self.navigate('time')

    def render_time(self):
        c=self.theme
        for i,(mode,title) in enumerate([('timer','Temporizador'),('watch','Cronometro'),('alarm','Alarma')]):
            self.text_action('mode'+mode,24+i*254,80,244,44,title,self.time_mode==mode,0)
            if self.cache.get('timemode')!=self.time_mode:
                self.fill(74+i*254,126,144,2,c['mint'] if self.time_mode==mode else c['bg'])
        self.cache['timemode']=self.time_mode
        if self.time_mode=='alarm':
            field=getattr(self,'alarm_field','minute')
            for name,x,value in [('hour',286,self.alarm.data['hour']),('minute',414,self.alarm.data['minute'])]:
                self.text('alarm'+name,x,158,100,86,1,f'{value:02}',c['mint'] if field==name else c['ink'],c['bg'],1)
            self.text('alarmcolon',386,158,28,86,1,':',c['ink'],c['bg'],1)
            self.icon_button('alarmminus',238,207,29,'minus'); self.icon_button('alarmplus',562,207,29,'plus')
            self.text('alarmselect',294,247,212,28,2,'Toca hora o minutos',c['muted'],c['bg'],1)
            self.text('alarmvolume',132,282,212,36,2,'Volumen del aviso',c['muted'],c['bg'])
            self.progress('alarmvol',360,296,308,self.alarm.data['volume']/100,c['mint'])
            self.text('alarmpercent',684,282,84,36,2,str(self.alarm.data['volume'])+'%',c['ink'],c['bg'],2)
            self.soft_button('alarmtoggle',240,342,320,56,'Desactivar' if self.alarm.data['enabled'] else 'Activar alarma',True,0)
            self.text_action('alarmtest',600,342,168,56,'Probar sonido')
            deadline=self.alarm.data['deadline']
            status='Programada: '+dt.datetime.fromtimestamp(deadline).strftime('%d/%m · %H:%M') if deadline else 'Se repite hasta detenerla, hasta 3 minutos'
            self.text('alarmhint',32,400,736,23,2,status,c['muted'],c['bg'],1)
            return
        watch=self.time_mode=='watch'
        if watch:
            self.digital('watchvalue',48,166,450,92,self.hms(self.elapsed()),1,c['ink'],c['bg'])
            self.analog('watchdial',638,215,69,self.elapsed(),c['muted'],c['mint'],c['bg'])
            last=self.watch.get('laps',[])
            detail='Listo para comenzar' if not last else 'Ultima vuelta / '+self.hms(last[-1])
            self.text('watchdetail',48,282,704,40,2,detail,c['muted'],c['bg'],1)
        else:
            self.duration_picker('timer',self.timer.remaining(),[(5,'5 / Descanso'),(25,'25 / Enfoque'),(60,'1 hora')])
        elapsed=self.elapsed()>0 if watch else self.timer.remaining()<self.timer.data['duration']
        self.soft_button('start',240,342,320,56,'Continuar' if elapsed else 'Iniciar',True,0)
        self.text_action('reset',600,342,168,56,'Reiniciar' if elapsed else '')

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
        if kind!='missed': self.alert_sound.play(seconds=180 if kind=='alarm' else 30,volume=self.alarm.data['volume'],kind=kind)

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
                self.away_pending=True
                self.save(); self.navigate('away')
            else:
                self.compact=False
                self.notify('Tiempo cumplido','timer')

    def render_notice(self):
        c=self.theme
        self.label('noticetitle',24,84,752,100,self.notice['title'],1,c['mint'],c['bg'],1)
        self.label('noticeclock',24,193,752,45,dt.datetime.now().strftime('%H:%M'),0,c['muted'],c['bg'],1)
        self.button('dismiss',124,270,266,60,'Detener',True)
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
