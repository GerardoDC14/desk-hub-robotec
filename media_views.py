"""Álbum visual, presentación privada y encuadre local de cámara."""
import time
from gallery_pixels import rect_image_commands, preview_passes, stable_pixels


class MediaViews:
    def media_art(self, commands):
        if not self.artwork:
            self.art_started=time.monotonic(); self.art_total=0
        self.artwork.extend(commands); self.art_total+=len(commands)

    def draw_gallery_grid(self):
        if getattr(self,'_photo_action',None): self.draw_photo_dialog(); return
        c=self.theme; library=getattr(self,'photos',None)
        if not library: return
        state=library.grid(getattr(self,'_album_page',0),unlocked=self.unlocked)
        self._album_page=state['page']; self._album_names=[i['name'] for i in state['items']]
        self.text('albumtitle',32,62,528,30,0,'Tus momentos',c['ink'],c['bg'])
        self.soft_button('albumtrash',600,58,168,38,'Papelera',False,2)
        identity=tuple(i['key'] for i in state['items'])
        if self.cache.get('album-layout')!=identity:
            self.artwork.clear(); self.art_key=None
            self.fill(32,100,736,304,c['bg'])
            self.cache['album-layout']=identity; self._album_painted=set()
            for key in list(self.cache):
                if key.startswith(('thumb','albumempty')): self.cache.pop(key,None)
        if not state['count']:
            self.paragraph('albumempty',100,178,600,'Tu álbum empieza con una foto. Abre Cámara para capturar tu primer momento.',3,0)
        # Todas las vistas rápidas aparecen antes de las pasadas de detalle.
        coarse=[]; detail=[]
        for i,item in enumerate(state['items']):
            x=32+(i%3)*248; y=102+(i//3)*152
            pixels=item['preview']; key=item['key']
            self.panel('thumbcard'+str(i),x,y,224,126,c['card'],6)
            if pixels and key not in self._album_painted:
                cols,rows,values=pixels
                a,b=preview_passes(values,cols,rows,x,y,224,126)
                coarse.extend(a); detail.extend(b); self._album_painted.add(key)
            elif not pixels:
                self.text('thumbwait'+str(i),x+12,y+48,200,30,2,'No disponible' if item['error'] else 'Cargando…',c['muted'],c['card'],1)
            label=self.photo_caption(item['name'])
            self.text('thumbcaption'+str(i),x,y+128,224,22,2,self.fit(label,224),c['ink'],c['bg'])
        if coarse or detail: self.media_art(coarse+detail)
        self.soft_button('albumbefore',32,418,144,44,'Anterior')
        self.text('albumpage',192,418,416,44,2,f"{state['page']+1} / {state['pages']}   ·   {state['count']} fotos",c['muted'],c['bg'],1)
        self.soft_button('albumafter',624,418,144,44,'Siguiente')

    @staticmethod
    def photo_caption(name):
        parts=name.split('-')
        if len(parts)>=3 and len(parts[1])==8 and len(parts[2])==6:
            day,clock=parts[1:3]
            return ('Efecto · ' if parts[0]=='efecto' else '')+f'{day[6:8]}/{day[4:6]}  {clock[:2]}:{clock[2:4]}'
        return 'Foto guardada'

    def draw_viewfinder(self):
        c=self.theme; camera=getattr(self,'camera',None)
        if not camera: return
        now=time.monotonic(); state=camera.snapshot()
        live=getattr(self,'_live_on',False); due=getattr(self,'_shot_due',None)
        waiting=getattr(self,'_shot_wait',None)
        if live and state['error'] and not state['busy']:
            self._live_on=live=False
        self.text('cameratitle',32,64,528,30,0,'Tu cámara',c['ink'],c['bg'])
        self.panel('viewfinderframe',32,104,528,297,c['card'],6)
        frame=state.get('preview'); ident=state.get('preview_id')
        # Nunca reemplazar una imagen a medio transmitir; descartar trabajo viejo al salir.
        if frame and self.art_key!=('live',ident) and not self.artwork:
            cols,rows,pixels=frame
            old=getattr(self,'_live_pixels',None) if self.art_key and self.art_key[0]=='live' else None
            pixels=stable_pixels(pixels,old)
            self.media_art(rect_image_commands(pixels,cols,rows,32,104,528,297,old))
            self.art_key=('live',ident); self._live_pixels=pixels
            self._live_drawn=now
        elif not frame and not self.art_key:
            self.paragraph('viewfinderhint',80,206,432,'Activa la cámara para encuadrar',2,0,bg=c['card'])
        self.soft_button('livecapture',584,104,184,76,
                         str(max(1,int(due-now)+1)) if due else 'Guardando…' if waiting else 'En timelapse' if state['timelapse'] else 'Tomar foto',True,0 if due else 2)
        self.soft_button('livetoggle',584,196,184,44,'Pausar vista' if live else 'Activar cámara')
        delay=getattr(self,'_shot_delay',0)
        self.soft_button('livedelay',584,254,184,44,'Cuenta: 3 s' if delay else 'Sin cuenta',bool(delay))
        self.soft_button('livealbum',584,312,184,44,'Galería')
        self.soft_button('livetimelapse',584,370,184,44,'Timelapse')
        message=state['status']
        if due: message='Prepárate / '+str(max(1,int(due-now)+1))
        elif waiting: message='Guardando tu foto…'
        elif not live and not state['busy'] and not state['error']: message='Vista pausada · no se guardan fotos automáticamente'
        self.text('livestatus',32,416,528,26,2,self.fit(message,528),c['mint'],c['bg'])
        self.text('livehint',32,446,736,22,2,'Vista local · la foto se guarda a 1280 × 720',c['muted'],c['bg'])
        if due and now>=due and not state['busy']:
            if camera.capture(unlocked=self.unlocked):
                self._shot_due=None; self._shot_wait=(state['last_filename'],now)
            else:
                self._shot_due=None
        if waiting and not state['busy']:
            self._shot_wait=None
            if state['last_filename']!=waiting[0]:
                self.photos.select(state['last_filename'],unlocked=self.unlocked)
                self.photos.set_filter('Original',unlocked=self.unlocked)
                self._capture_notice=(state['last_filename'],now+5)
                self.navigate('gallery'); return
        if live and not due and not waiting and not state['busy'] and not state['timelapse'] and not self.artwork:
            if now-getattr(self,'_live_request',0)>=1:
                if camera.preview(unlocked=self.unlocked): self._live_request=now

    def draw_photo_show(self):
        c=self.theme; state=self.photos.snapshot(unlocked=self.unlocked)
        self.text('showtitle',32,62,736,28,2,'Tus momentos · '+str(state['index']+1 if state['count'] else 0)+' / '+str(state['count']),c['ink'],c['bg'],1)
        key=state.get('preview_key'); preview=state.get('preview')
        if preview and key and key[:2]==(state['filename'],state['filter']):
            if self.art_key!=('show',key):
                self.artwork.clear(); self.art_key=('show',key); self._show_due=None
                a,b=preview_passes(preview[2],preview[0],preview[1],112,96,576,324)
                self.media_art(a+b)
            if not self.artwork and getattr(self,'_show_due',None) is None:
                self._show_due=time.monotonic()+8
            if (getattr(self,'_show_play',True) and getattr(self,'_show_due',None)
                    and time.monotonic()>=self._show_due and state['count']>1):
                self.photos.select((state['index']+1)%state['count'],unlocked=True)
                self._show_due=None
        else:
            # Ocultar foto previa para no atribuirla al siguiente archivo.
            if self.art_key!=('show-wait',state['filename']):
                self.artwork.clear(); self.fill(112,96,576,324,c['card'])
                self.art_key=('show-wait',state['filename'])
                self.cache.pop('showwait',None)
            self.text('showwait',180,230,440,40,2,'Foto no disponible' if state['error'] else 'Preparando foto…',c['muted'],c['card'],1)
        self.soft_button('showprev',112,430,160,42,'Anterior')
        self.soft_button('showtoggle',296,430,208,42,'Pausar' if getattr(self,'_show_play',True) else 'Continuar',True)
        self.soft_button('shownext',528,430,160,42,'Siguiente')

    def touch_media(self,x,y):
        if not self.unlocked: return False
        screen=self.screen
        if screen=='gallery_grid' and getattr(self,'_photo_action',None): return self.touch_photo_dialog(x,y)
        if 632<=x<768 and 12<=y<52:
            self.navigate('status' if screen=='viewfinder' else 'viewfinder' if screen=='gallery_grid' else 'gallery_grid'); return True
        if screen=='gallery_grid':
            if 600<=x<768 and 58<=y<96:
                self.photo_dialog('trash_list'); return True
            if 496<=x<616 and 12<=y<52:
                state=self.photos.grid(getattr(self,'_album_page',0),unlocked=True)
                if state['count']:
                    self.photos.select(state['page']*6,unlocked=True); self.photos.set_filter('Original',unlocked=True)
                    self._show_play=True; self.navigate('photo_show')
                return True
            if 418<=y<462:
                step=-1 if 32<=x<176 else 1 if 624<=x<768 else 0
                if step:
                    state=self.photos.grid(getattr(self,'_album_page',0),unlocked=True)
                    page=max(0,min(state['pages']-1,state['page']+step))
                    if page!=state['page']:
                        self._album_page=page; self.navigate('gallery_grid')
                return bool(step)
            for i,name in enumerate(getattr(self,'_album_names',[])):
                xx=32+(i%3)*248; yy=102+(i//3)*152
                if xx<=x<xx+224 and yy<=y<yy+150:
                    if self.photos.select(name,unlocked=True):
                        self.photos.set_filter('Original',unlocked=True); self.navigate('gallery')
                    return True
        elif screen=='viewfinder':
            if not (584<=x<768): return False
            state=self.camera.snapshot()
            if 104<=y<180 and not getattr(self,'_shot_due',None) and not getattr(self,'_shot_wait',None):
                if state['timelapse']: return False
                self._live_on=False; self.camera.stop_preview()
                self._shot_due=time.monotonic()+getattr(self,'_shot_delay',0)
            elif 196<=y<240 and not getattr(self,'_shot_due',None) and not getattr(self,'_shot_wait',None):
                if getattr(self,'_live_on',False):
                    self._live_on=False; self.camera.stop_preview()
                elif self.camera.preview(unlocked=True):
                    self._live_on=True; self._live_request=time.monotonic()
            elif 254<=y<298:
                self._shot_delay=0 if getattr(self,'_shot_delay',0) else 3
            elif 312<=y<356: self.navigate('gallery_grid')
            elif 370<=y<414: self.navigate('camera')
            else: return False
            return True
        elif screen=='photo_show' and 430<=y<472:
            state=self.photos.snapshot(unlocked=True)
            if 296<=x<504: self._show_play=not getattr(self,'_show_play',True); self._show_due=None
            elif state['count'] and (112<=x<272 or 528<=x<688):
                self.photos.select((state['index']+(-1 if x<272 else 1))%state['count'],unlocked=True)
                self.artwork.clear(); self._show_due=None
            return True
        return False
