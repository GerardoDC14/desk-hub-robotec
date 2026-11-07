"""Exportación MP4 local y cancelable, con originales y recursos acotados."""
import io
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import threading
import time
import uuid
from notion_board import read_private,write_private

VIDEO_NAME=re.compile(r'timelapse-[a-f0-9]{32}\.mp4\Z')
MAX_VIDEO=32*1024*1024
VIDEO_STORAGE=250*1024*1024
FPS=(6,12,24)


def video_command(executable,path,fps):
    if fps not in FPS:raise ValueError('Velocidad')
    return [str(executable),'-hide_banner','-loglevel','error','-nostdin','-y',
            '-protocol_whitelist','file,pipe','-f','image2pipe','-vcodec','mjpeg','-framerate',str(fps),'-i','pipe:0',
            '-an','-vf','scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2',
            '-c:v','libx264','-preset','veryfast','-crf','23','-threads','1','-pix_fmt','yuv420p','-movflags','+faststart','-fs',str(MAX_VIDEO),str(path)]


class VideoExporter:
    def __init__(self,directory,photos,popen=subprocess.Popen,which=shutil.which):
        self.directory=Path(directory)/'videos';self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.directory.is_symlink():raise ValueError('Carpeta de vídeos no válida')
        os.chmod(self.directory,0o700);self.root=self.directory.resolve()
        self.photos=photos;self.executable=which('ffmpeg');self.popen=popen;self.lock=threading.RLock()
        self.busy=False;self.completed=0;self.total=0;self.message='Elige una sesión para crear un vídeo.'
        self.process=None;self.thread=None;self.generation=0;self.result='';self.closed=False
        self.index=[]
        try:
            rows=read_private(self.directory/'index.json',128*1024)
            if isinstance(rows,list):self.index=[r for r in rows[:100] if isinstance(r,dict) and VIDEO_NAME.fullmatch(str(r.get('name',''))) and isinstance(r.get('frames'),int) and r.get('fps') in FPS]
        except (OSError,ValueError,TypeError):pass

    def file(self,name):
        if not isinstance(name,str) or not VIDEO_NAME.fullmatch(name) or self.directory.is_symlink() or self.directory.resolve()!=self.root:raise ValueError('Vídeo no válido')
        path=self.directory/name;info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not 0<info.st_size<=MAX_VIDEO:raise ValueError('Archivo no válido')
        return path,info

    def entries(self):
        with self.lock:
            result=[]
            for entry in self.index:
                try:path,info=self.file(entry['name'])
                except (OSError,ValueError):continue
                result.append(dict(entry,bytes=info.st_size))
            return result

    def start(self,session_id,fps=12,unlocked=False):
        if not unlocked or fps not in FPS:return False
        with self.lock,self.photos._cv:
            c=self.photos.camera
            if self.busy or self.closed:return False
            if not self.executable:self.message='Instala ffmpeg para exportar vídeos.';return False
            if c._busy or c._job or c._sequence or c._editing or getattr(c,'_video_working',False):self.message='Detén la cámara antes de exportar.';return False
            session=next((s for s in self.photos.catalog.sessions() if s['id']==session_id and s['kind']=='timelapse'),None)
            if not session or not 2<=len(session['names'])<=60:self.message='Se necesitan entre 2 y 60 fotos de una sesión.';return False
            try:
                keys=[]
                for name in session['names']:
                    _,info=self.photos._file_info(name);keys.append((name,self.photos._signature(info),'Original',self.photos.catalog.meta(name)['rotation']))
                if sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file() and not p.is_symlink())+MAX_VIDEO>VIDEO_STORAGE or shutil.disk_usage(self.directory).free<MAX_VIDEO+100*1024*1024:
                    self.message='Libera espacio antes de exportar.';return False
            except (OSError,ValueError):self.message='Faltan fotos de esta sesión; restaura las que estén en la papelera.';return False
            self.generation+=1;generation=self.generation;self.busy=True;self.completed=0;self.total=len(keys);self.result=''
            self.message='Preparando el vídeo…';c._video_working=True
            self.thread=threading.Thread(target=self._run,args=(keys,session_id,fps,generation),daemon=True,name='desk-hub-video');self.thread.start();return True

    def cancel(self):
        with self.lock:
            self.generation+=1;process=self.process
            if self.busy:self.message='Exportación cancelada. Las fotos se conservan.'
        if process:
            try:process.terminate()
            except OSError:pass

    def _valid(self,generation):
        with self.lock:return not self.closed and generation==self.generation

    def _run(self,keys,session_id,fps,generation):
        token=uuid.uuid4().hex;name='timelapse-'+token+'.mp4';temporary=self.directory/('.'+token+'.mp4');process=None;watchdog=None
        try:
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
            with self.lock:
                if not self._valid(generation):return
                process=self.popen(video_command(self.executable,temporary,fps),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,shell=False)
                self.process=process
            watchdog=threading.Timer(120,process.kill);watchdog.daemon=True;watchdog.start()
            for i,key in enumerate(keys):
                if not self._valid(generation):return
                image=self.photos._read_image(key);image.thumbnail((1280,720));frame=io.BytesIO();image.save(frame,format='JPEG',quality=90)
                process.stdin.write(frame.getvalue())
                with self.lock:self.completed=i+1;self.message=f'Procesando {i+1} de {len(keys)} fotos…'
            process.stdin.close();process.stdin=None;process.communicate(timeout=60)
            if process.returncode:raise ValueError('Codificador')
            info=temporary.stat()
            if not 0<info.st_size<MAX_VIDEO:raise ValueError('Límite de vídeo')
            with self.lock:
                if not self._valid(generation):return
                if self.directory.is_symlink() or self.directory.resolve()!=self.root:raise ValueError('Carpeta')
                destination=self.directory/name;os.link(temporary,destination);temporary.unlink()
                entry=dict(name=name,session=session_id,frames=len(keys),fps=fps,created=time.time())
                new=[entry]+self.index[:99]
                try:write_private(self.directory/'index.json',new)
                except (OSError,ValueError):destination.unlink();raise
                self.index=new;self.result=name;self.message='Vídeo listo. Guardado en la Raspberry.'
        except Exception:
            with self.lock:
                if self._valid(generation):self.message='No se pudo exportar el vídeo. Tus fotos se conservan.'
        finally:
            if watchdog:watchdog.cancel()
            if process:
                try:
                    if process.poll() is None:process.kill()
                    process.communicate(timeout=2)
                except (OSError,ValueError,subprocess.SubprocessError):pass
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
            with self.lock:self.busy=False;self.process=None
            with self.photos._cv:self.photos.camera._video_working=False;self.photos._cv.notify_all()

    def close(self):
        self.closed=True;self.cancel()
        if self.thread:self.thread.join(3)
