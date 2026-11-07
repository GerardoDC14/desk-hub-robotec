"""Cuatro capturas explícitas y composición privada, conservando originales."""
import math
import os
import threading
import time
import uuid
from PIL import Image,ImageDraw,ImageFont,ImageOps
from photo_library import apply_filter
from camera_tools import MAX_FILE_BYTES,MAX_PHOTOS,MAX_STORAGE_BYTES

LAYOUTS=('Cuadrícula','Tira')
EFFECTS=('Original','B/N','Sepia','Pop')
FRAMES=('Claro','Oscuro','Menta')


def compose(images,layout,effect,frame):
    if len(images)!=4 or layout not in LAYOUTS or effect not in EFFECTS or frame not in FRAMES:raise ValueError('Opciones')
    columns=2 if layout=='Cuadrícula' else 1;rows=4//columns;gap=24;w=640;h=360
    bg={'Claro':'#f8f2e8','Oscuro':'#14232b','Menta':'#b0e8d7'}[frame]
    ink='#eef8f6' if frame=='Oscuro' else '#18342f'
    canvas=Image.new('RGB',(columns*w+(columns+1)*gap,rows*h+(rows+1)*gap+52),bg)
    for i,image in enumerate(images):
        tile=ImageOps.fit(apply_filter(image,effect),(w,h),method=Image.Resampling.LANCZOS)
        canvas.paste(tile,(gap+(i%columns)*(w+gap),gap+(i//columns)*(h+gap)))
    draw=ImageDraw.Draw(canvas)
    try:font=ImageFont.truetype('DejaVuSans.ttf',22)
    except OSError:font=ImageFont.load_default()
    draw.text((gap,canvas.height-48),'ROBOTEC / '+time.strftime('%d.%m.%Y'),fill=ink,font=font)
    return canvas


class Photobooth:
    def __init__(self,camera,photos,clock=time.monotonic):
        self.camera=camera;self.photos=photos;self.clock=clock
        self.active=False;self.composing=False;self.names=[];self.result='';self.message='Cuatro fotos, un recuerdo.'
        self.due=None;self.waiting=None;self.generation=0;self.thread=None

    def start(self,layout='Cuadrícula',effect='Original',frame='Claro',unlocked=False):
        if not unlocked or layout not in LAYOUTS or effect not in EFFECTS or frame not in FRAMES:return False
        c=self.camera
        with c._cv:
            if self.active or self.composing or c._closed or c._busy or c._job or c._sequence or c._editing or getattr(c,'_booth_working',False) or not c.executable:
                self.message='Espera a que la cámara quede disponible.';return False
            count,size=c._usage()
            if count+5>MAX_PHOTOS or size+5*MAX_FILE_BYTES>MAX_STORAGE_BYTES:
                self.message='Libera espacio para cuatro fotos y su composición.';return False
            self.generation+=1;self.active=True;c._booth_active=True
            self.layout=layout;self.effect=effect;self.frame=frame
            self.names=[];self.result='';self.waiting=None;self.due=self.clock()+3
            self.message='Prepárate para la primera foto.';return True

    def cancel(self):
        c=self.camera
        with c._cv:
            was=self.active or self.composing;self.generation+=1;self.active=False;self.due=None;self.waiting=None
            c._booth_active=False
            if was:c._cancel('Cabina detenida');self.message='Sesión detenida. Se conservan las fotos tomadas.'

    def poll(self,unlocked):
        if not self.active:return
        if not unlocked:self.cancel();return
        c=self.camera
        with c._cv:
            if c._busy or c._job:return
            if not getattr(c,'_booth_active',False):self.cancel();return
            if self.waiting is not None:
                if c._error or c._last_filename==self.waiting:
                    self.message=c._error or 'No se pudo guardar la foto.';self.active=False;c._booth_active=False;return
                self.names.append(c._last_filename);self.waiting=None
                if len(self.names)==4:
                    self.active=False;self.composing=True;c._booth_working=True;self.due=None;self.message='Creando tu composición…'
                    self.thread=threading.Thread(target=self._compose,args=(self.generation,),daemon=True,name='desk-hub-photobooth');self.thread.start();return
                self.due=self.clock()+3;self.message='Cambia de pose para la siguiente foto.'
            if self.due is not None and self.clock()>=self.due:
                previous=c._last_filename
                if c.capture(unlocked=True,booth=True):self.waiting=previous;self.due=None;self.message=f'Tomando foto {len(self.names)+1} de 4…'

    def _compose(self,generation):
        c=self.camera;temporary=None
        try:
            images=[]
            for name in self.names:
                _,info=self.photos._file_info(name)
                images.append(self.photos._read_image((name,self.photos._signature(info),'Original')))
            image=compose(images,self.layout,self.effect,self.frame)
            token=uuid.uuid4().hex;name='efecto-cabina-'+time.strftime('%Y%m%d-%H%M%S')+'-'+token[:8]+'.jpg'
            temporary=c.directory/('.cabina-'+token+'.tmp')
            fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as out:image.save(out,format='JPEG',quality=92);out.flush();os.fsync(out.fileno())
            with c._cv:
                if generation!=self.generation or not c._booth_active or c._closed:return
                if not self.photos._root_valid():raise ValueError('Carpeta cambiada')
                if temporary.stat().st_size>MAX_FILE_BYTES or c._usage()[1]>MAX_STORAGE_BYTES:raise ValueError('Espacio')
                os.link(temporary,c.directory/name);temporary.unlink();temporary=None
                c._usage_cache=None;self.result=name;self.message='Tu composición y las cuatro fotos están guardadas.'
        except Exception:
            with c._cv:
                if generation==self.generation:self.message='No se pudo crear la composición. Tus originales se conservan.'
        finally:
            if temporary:
                try:temporary.unlink(missing_ok=True)
                except OSError:pass
            with c._cv:self.composing=False;c._booth_working=False;c._booth_active=False;c._usage_cache=None


class BoothViews:
    def draw_booth(self):
        c=self.theme;b=self.booth
        mode=b.active or b.composing
        if self.cache.get('booth-layout')!=mode:
            self.fill(32,130,736,344,c['bg'])
            for key in list(self.cache):
                if key.startswith('booth'):self.cache.pop(key,None)
            self.cache['booth-layout']=mode
        self.text('boothtitle',32,70,736,44,0,'Cuatro fotos. Un buen momento.',c['ink'],c['bg'])
        if b.active or b.composing:
            count=str(max(1,math.ceil(b.due-b.clock()))) if b.due else '…'
            self.digital('boothcount',32,142,736,132,count,3,c['mint'],c['bg'])
            self.text('boothprogress',32,282,736,38,0,f'{len(b.names)} de 4 fotos guardadas',c['ink'],c['bg'],1)
            self.soft_button('boothcancel',240,400,320,56,'Detener',False,0)
        else:
            for row,(label,options,attr) in enumerate((('Formato',LAYOUTS,'_booth_layout'),('Filtro',EFFECTS,'_booth_effect'),('Marco',FRAMES,'_booth_frame'))):
                value=getattr(self,attr,options[0]);y=142+row*64
                self.text('boothlabel'+str(row),32,y,150,46,0,label,c['ink'],c['bg'])
                width=560//len(options)
                for i,option in enumerate(options):self.soft_button('boothoption'+str(row)+str(i),200+i*width,y,width-8,46,option,value==option,2)
            self.soft_button('boothstart',32,400,352,56,'Empezar / 4 fotos',True,0)
            self.soft_button('boothresult',416,400,352,56,'Ver composición' if b.result else 'Galería',False,0)
        self.text('boothmessage',32,346,736,42,2,self.fit(b.message,736),c['ink'],c['bg'],1)

    def touch_booth(self,x,y):
        if not self.owner():return
        b=self.booth
        if 632<=x<768 and 12<=y<52:
            b.cancel();self.navigate('viewfinder');return
        if b.active or b.composing:
            if 240<=x<560 and 400<=y<456:b.cancel();self.navigate('booth')
            return
        for row,options,attr in ((0,LAYOUTS,'_booth_layout'),(1,EFFECTS,'_booth_effect'),(2,FRAMES,'_booth_frame')):
            if 142+row*64<=y<188+row*64:
                width=560//len(options);i=(x-200)//width
                if 200<=x<760 and 0<=i<len(options):setattr(self,attr,options[i]);self.navigate('booth');return
        if 400<=y<456:
            if 32<=x<384:
                b.start(getattr(self,'_booth_layout',LAYOUTS[0]),getattr(self,'_booth_effect',EFFECTS[0]),getattr(self,'_booth_frame',FRAMES[0]),unlocked=True);self.navigate('booth')
            elif 416<=x<768:
                if b.result and self.photos.select(b.result,unlocked=True):self.photos.set_filter('Original',unlocked=True);self.navigate('gallery')
                else:self.navigate('gallery_grid')
