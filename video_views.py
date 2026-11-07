"""Selección de sesiones y exportación de timelapses desde la pantalla."""
import datetime as dt
from video_export import FPS


class VideoViews:
    def draw_videos(self):
        c=self.theme;v=self.videos
        if v is None:
            self.paragraph('videoerror',64,160,672,'No se puede abrir el almacenamiento de vídeos. Revisa el espacio y los permisos de la Raspberry.',3,0)
            return
        mode=v.busy
        if self.cache.get('video-layout')!=mode:
            self.fill(32,120,736,350,c['bg'])
            for key in list(self.cache):
                if key.startswith('video'):self.cache.pop(key,None)
            self.cache['video-layout']=mode
        self.text('videotitle',32,72,736,42,0,'Tus timelapses, en vídeo',c['ink'],c['bg'])
        self.text('videomessage',32,376,736,32,2,self.fit(v.message,736),c['mint'],c['bg'])
        if mode:
            self.digital('videocount',32,150,736,100,f'{v.completed} / {v.total}',1,c['mint'],c['bg'])
            self.progress('videoprogress',80,280,640,v.completed/max(1,v.total),c['mint'])
            self.soft_button('videocancel',240,416,320,48,'Cancelar exportación',False,0)
            return
        sessions=[s for s in self.photos.catalog.sessions() if s['kind']=='timelapse' and len(s['names'])>=2]
        page=max(0,min(getattr(self,'_video_page',0),max(0,(len(sessions)-1)//2)));self._video_page=page;self._video_items=sessions[page*2:page*2+2]
        fps=getattr(self,'_video_fps',12)
        for i,session in enumerate(self._video_items):
            y=130+i*108;n=len(session['names']);seconds=n/fps
            self.panel('videocard'+str(i),32,y,736,96,c['card'],8)
            label=dt.datetime.fromtimestamp(session['created']).strftime('%d/%m · %H:%M')+' / '+str(n)+' fotos'
            self.text('videoname'+str(i),48,y+10,480,34,0,label,c['ink'],c['card'])
            estimate=max(.1,seconds*.25)
            self.text('videoestimate'+str(i),48,y+52,480,28,2,f'Vídeo {seconds:.1f} s · aprox. {estimate:.1f} MiB',c['muted'],c['card'])
            self.soft_button('videoexport'+str(i),576,y+22,168,52,'Exportar',True,0)
        if not sessions:self.paragraph('videoempty',64,160,672,'Crea un timelapse y guarda al menos dos fotos. Sus sesiones aparecerán aquí.',3,0)
        self.text('videofpslabel',32,418,180,44,2,'Fotos por segundo',c['ink'],c['bg'])
        for i,value in enumerate(FPS):self.soft_button('videofps'+str(i),220+i*88,418,80,44,str(value),fps==value,0)
        self.soft_button('videoprev',504,418,120,44,'Anterior',False,2)
        self.soft_button('videonext',640,418,128,44,'Siguiente',False,2)

    def touch_videos(self,x,y):
        if not self.owner():return
        if 632<=x<768 and 12<=y<52:self.navigate('camera');return
        if self.videos is None:return
        if self.videos.busy:
            if 240<=x<560 and 416<=y<464:self.videos.cancel()
            return
        for i,session in enumerate(getattr(self,'_video_items',[])):
            if 576<=x<744 and 152+i*108<=y<204+i*108:
                self.videos.start(session['id'],getattr(self,'_video_fps',12),unlocked=True);self.navigate('videos');return
        if 418<=y<462:
            for i,value in enumerate(FPS):
                if 220+i*88<=x<300+i*88:self._video_fps=value;self.navigate('videos');return
            if 504<=x<624 or 640<=x<768:
                self._video_page=max(0,getattr(self,'_video_page',0)+(-1 if x<624 else 1));self.navigate('videos')
