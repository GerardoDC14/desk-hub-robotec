"""Acceso local temporal: QR de un uso, sesión revocable y solicitudes acotadas."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress
import json
import secrets
import threading
import time
from urllib.parse import urlsplit,parse_qs


class PhoneAccess:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.lock=threading.RLock();self.revoke()

    def revoke(self):
        with self.lock:self.pair='';self.pair_until=0;self.session='';self.session_until=0

    def begin(self):
        with self.lock:
            self.revoke();self.pair=secrets.token_urlsafe(24);self.pair_until=self.clock()+60
            return self.pair

    def exchange(self,value):
        with self.lock:
            if not self.pair or self.clock()>=self.pair_until or not secrets.compare_digest(value,self.pair):return None
            self.pair='';self.session=secrets.token_urlsafe(32);self.session_until=self.clock()+900
            return self.session

    def valid(self,value):
        with self.lock:return bool(self.session and self.clock()<self.session_until and secrets.compare_digest(value,self.session))

    def status(self):
        with self.lock:return dict(paired=bool(self.session and self.clock()<self.session_until),pair_left=max(0,int(self.pair_until-self.clock())),session_left=max(0,int(self.session_until-self.clock())))


class BoundedServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(6);super().__init__(*args,**kwargs)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
        try:super().process_request(request,address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()


class PhoneServer:
    def __init__(self,dispatch,owner,html,port=8765):
        self.dispatch=dispatch;self.owner=owner;self.html=html;self.port=port
        self.access=PhoneAccess();self.server=None;self.origin='';self.lock=threading.Lock();self.closing=None

    def begin(self,address):
        address=str(ipaddress.IPv4Address(address))
        if not self.owner():raise PermissionError('Desbloquea como anfitrión')
        if self.closing:
            self.closing.join(.3)
            if self.closing.is_alive():raise OSError('Servidor cerrando')
        if self.server is None:
            outer=self
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def setup(self):
                    super().setup();self.connection.settimeout(4)
                def reply(self,status,data,kind='application/json; charset=utf-8'):
                    body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
                    self.send_response(status);self.send_header('Content-Type',kind)
                    self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
                    self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
                    self.send_header('Referrer-Policy','no-referrer')
                    self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src blob: 'self'; base-uri 'none'; frame-ancestors 'none'")
                    self.end_headers();self.wfile.write(body)
                def do_GET(self):self.handle_api(False)
                def do_POST(self):self.handle_api(True)
                def handle_api(self,post):
                    try:
                        host=self.headers.get('Host','')
                        if 'http://'+host!=outer.origin or self.headers.get('Origin',outer.origin)!=outer.origin:
                            self.reply(403,{'error':'Origen no permitido'});return
                        route=urlsplit(self.path)
                        if not post and route.path=='/':self.reply(200,outer.html.encode(),'text/html; charset=utf-8');return
                        if not outer.owner():self.reply(401,{'error':'El Hub está bloqueado'});return
                        data={}
                        if post:
                            size=int(self.headers.get('Content-Length','0'))
                            if not 0<size<=4096:self.reply(413,{'error':'Solicitud demasiado grande'});return
                            data=json.loads(self.rfile.read(size))
                            if not isinstance(data,dict):raise ValueError('Formato')
                        if post and route.path=='/api/pair':
                            value=data.get('pair','')
                            token=outer.access.exchange(value) if isinstance(value,str) and len(value)<128 else None
                            self.reply(200 if token else 401,{'session':token} if token else {'error':'El QR caducó o ya se utilizó'});return
                        token=self.headers.get('Authorization','').removeprefix('Bearer ')
                        if not outer.access.valid(token):self.reply(401,{'error':'Enlace cerrado. Genera otro QR en el Hub.'});return
                        if post and route.path=='/api/command':action='command'
                        elif not post and route.path in ('/api/state','/api/photos','/api/photo','/api/thumb','/api/frame'):
                            action=route.path.rsplit('/',1)[1];data={k:v[0] for k,v in parse_qs(route.query).items()}
                        else:self.reply(404,{'error':'No disponible'});return
                        status,result,kind=outer.dispatch(action,data,token)
                        if not outer.access.valid(token) or not outer.owner():self.reply(401,{'error':'Acceso cerrado'});return
                        self.reply(status,result,kind)
                    except (ValueError,KeyError,TypeError):self.reply(400,{'error':'Solicitud no válida'})
                    except (OSError,TimeoutError):pass
                    except Exception:self.reply(503,{'error':'El Hub está ocupado; vuelve a intentar'})
            self.server=BoundedServer(('0.0.0.0',self.port),Handler)
            self.port=self.server.server_port
            threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.1},daemon=True,name='desk-hub-phone').start()
        self.origin=f'http://{address}:{self.port}'
        return self.origin+'/#pair='+self.access.begin()

    def close(self):
        self.access.revoke()
        with self.lock:
            server=self.server;self.server=None
        if server:
            def shutdown():server.shutdown();server.server_close()
            self.closing=threading.Thread(target=shutdown,daemon=True);self.closing.start()
