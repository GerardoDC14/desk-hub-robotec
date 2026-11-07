"""Compañero local: operaciones de estado en el hilo principal, imágenes acotadas."""
import io
import os
import queue
import threading
import time
from PIL import Image
from phone_server import PhoneServer
from phone_html import HTML
from timer_bank import NAMES

JSON='application/json; charset=utf-8'


class PhoneViews:
    def init_phone(self):
        self.phone_jobs=queue.Queue(8)
        self.phone=PhoneServer(self.phone_dispatch,self.owner,HTML)
        self.phone_message='Genera un QR y ábrelo en tu teléfono.'
        self.phone_camera=False
        self.phone_frame_seen=0

    def phone_dispatch(self,action,data,token):
        if not self.owner() or not self.phone.access.valid(token):return 401,{'error':'Acceso cerrado'},JSON
        if action=='frame':
            self.phone_frame_seen=time.monotonic()
            camera=getattr(self,'camera',None)
            with camera._cv if camera else threading.Lock():
                frame=getattr(camera,'_latest_jpeg',None)
            return (200,frame,'image/jpeg') if frame else (409,{'error':'Activa la cámara o espera el encuadre'},JSON)
        if action in ('photos','photo','thumb'):
            library=getattr(self,'photos',None)
            if not library:return 404,{'error':'Cámara no disponible'},JSON
            with library._cv:
                library._refresh_locked()
                if action=='photos':return 200,{'photos':[entry[0] for entry in library._photos]},JSON
                name=data.get('name','');path,info=library._file_info(name)
                if not 0<info.st_size<=8*1024*1024:raise ValueError('Tamaño')
                fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
                with os.fdopen(fd,'rb') as source:
                    if library._signature(os.fstat(source.fileno()))!=library._signature(info):raise ValueError('Foto cambiada')
                    raw=source.read(8*1024*1024+1)
            if action=='thumb':
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width*image.height>16_000_000:raise ValueError('Tamaño')
                    image.thumbnail((320,180));out=io.BytesIO();image.convert('RGB').save(out,format='JPEG',quality=80);raw=out.getvalue()
            return 200,raw,'image/jpeg'
        job=dict(action=action,data=data,token=token,event=threading.Event(),until=time.monotonic()+2.5)
        try:self.phone_jobs.put_nowait(job)
        except queue.Full:return 503,{'error':'Hub ocupado; vuelve a intentar'},JSON
        if not job['event'].wait(3):return 503,{'error':'El panel está ocupado'},JSON
        return job['result']

    def poll_phone(self):
        if not getattr(self,'phone',None):return
        if self.phone_camera and (not self.owner() or not self.phone.access.status()['paired'] or time.monotonic()-self.phone_frame_seen>10):
            self.phone_camera=False;self._live_on=False
            if self.camera:self.camera.stop_preview()
        for _ in range(3):
            try:job=self.phone_jobs.get_nowait()
            except queue.Empty:break
            try:
                if time.monotonic()>job['until'] or not self.owner() or not self.phone.access.valid(job['token']):
                    job['result']=(401,{'error':'Enlace cerrado o solicitud vencida'},JSON)
                elif job['action']=='state':
                    with self.lock:music={k:self.music.get(k) for k in ('title','artist','status','volume','is_active')}
                    job['result']=(200,dict(music=music,timers=[dict(name=n,seconds=t.remaining(),running=t.data['deadline'] is not None) for n,t in zip(NAMES,self.timers.timers)],camera=self.camera.snapshot()['status'] if self.camera else 'Sin cámara',session=self.phone.access.status()['session_left']),JSON)
                else:
                    message=self.phone_command(job['data']);self.screen_activity(time.monotonic())
                    job['result']=(200,{'message':message},JSON)
            except (ValueError,KeyError,TypeError):job['result']=(400,{'error':'Revisa los valores de la solicitud'},JSON)
            except Exception:job['result']=(503,{'error':'No se pudo completar la acción'},JSON)
            finally:job['event'].set()

    def phone_command(self,data):
        command=data.get('command')
        if command=='music':
            operation=data.get('operation')
            if operation not in ('play','pause','prev','next','volume'):raise ValueError('Operación')
            args=[operation]
            if operation=='volume':
                value=data.get('value')
                if type(value) is not int or not 0<=value<=100:raise ValueError('Volumen')
                args.append(str(value))
            if not self.queue_music(args):return 'Selecciona Desk Hub Robotec en Spotify primero.'
            return 'Enviado al reproductor'
        if command=='timer':
            index=data.get('index');operation=data.get('operation')
            if type(index) is not int or not 0<=index<3:raise ValueError('Cuenta')
            timer=self.timers.timers[index]
            if operation=='set':
                minutes=data.get('minutes')
                if type(minutes) is not int or not 1<=minutes<=1440:raise ValueError('Minutos')
                if timer.data['deadline'] is not None:return 'Pausa la cuenta antes de cambiar su duración.'
                timer.data.update(duration=minutes*60,remaining=minutes*60,deadline=None)
            elif operation=='start':
                if timer.data['deadline'] is None:timer.toggle()
            elif operation=='pause':
                if timer.data['deadline'] is not None:timer.toggle()
            elif operation=='reset':timer.reset()
            else:raise ValueError('Operación')
            self.save();return 'Temporizador actualizado'
        if command=='camera':
            operation=data.get('operation');camera=self.camera
            if not camera:return 'Cámara no disponible'
            state=camera.snapshot()
            if operation=='stop':
                self.phone_camera=False;self._live_on=False;camera.stop_preview();return 'Vista detenida'
            if state['timelapse'] or getattr(self,'_shot_due',None) or getattr(self,'_shot_wait',None):return 'La cámara está realizando una captura.'
            if operation=='start':
                self.navigate('viewfinder');self.phone_camera=True;self.phone_frame_seen=time.monotonic();self._live_on=True
                return 'Cámara activada; no se guardan imágenes automáticamente.'
            if operation=='capture':
                self.navigate('viewfinder');self.phone_camera=False;self._live_on=False
                camera.stop_preview();self._shot_due=time.monotonic()+.3
                return 'Tomando foto. Aparecerá en Fotos cuando termine.'
            raise ValueError('Operación')
        if command=='close':self.phone.close();return 'Enlace cerrado'
        raise ValueError('Acción')

    def draw_phone(self):
        c=self.theme;state=self.phone.access.status()
        self.text('phonetitle',32,72,736,42,0,'El Hub, también en tu teléfono',c['ink'],c['bg'])
        if state['pair_left'] and not state['paired'] and self.phone.access.pair:
            self.art('phoneqr',32,130,260)
            message=f"Escanea el QR en {state['pair_left']} s."
        else:
            if self.cache.get('phoneblank') is not True:
                self.artwork.clear();self.art_key=None;self.fill(32,130,260,260,c['bg']);self.cache['phoneblank']=True
            message='Teléfono enlazado' if state['paired'] else 'Sin enlace activo'
        self.text('phonestate',320,140,448,40,0,message,c['mint'],c['bg'])
        self.paragraph('phonehint',320,192,448,'Usa la misma red Wi-Fi. Controla música y cuentas, descarga fotos y abre la cámara.',3,0)
        self.text('phoneexpiry',320,326,448,30,2,f"Sesión: {state['session_left']//60} min" if state['paired'] else 'QR de un solo uso · sesión de 15 min',c['muted'],c['bg'])
        self.text('phonemessage',32,390,736,30,2,self.fit(self.phone_message,736),c['ink'],c['bg'])
        self.soft_button('phonenew',32,430,352,44,'Generar QR',True)
        self.soft_button('phoneclose',416,430,352,44,'Cerrar enlace')

    def touch_phone(self,x,y):
        if not self.owner():return
        if 632<=x<768 and 12<=y<52:self.navigate('sharing');return
        if 430<=y<474:
            if 32<=x<384:
                try:
                    import qrcode
                    url=self.phone.begin(self.system_info.get('address',''))
                    qr=qrcode.QRCode(border=4);qr.add_data(url);qr.make(fit=True)
                    self.images['phoneqr']=[0 if v else 65535 for row in qr.get_matrix() for v in row]
                    self.phone_message='Al bloquear el Hub se cierra el acceso del teléfono.'
                except (OSError,ValueError):self.phone_message='Conecta la Pi a Wi-Fi y vuelve a intentar.'
            elif 416<=x<768:self.phone.close();self.phone_message='Enlace cerrado.'
            self.navigate('phone')
