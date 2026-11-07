"""Código temporal para invitados; nunca persiste el código legible."""
import hashlib
import secrets
import time
from pin_setup import verify_pin

GUEST_VIEWS={'home','time','timers','focus','music','music_options','library','ambient','duration','help','lock'}


class GuestAccess:
    def __init__(self,data=None,clock=time.time):
        self.clock=clock;self.data=data if isinstance(data,dict) else {}
        try:
            if len(bytes.fromhex(self.data['salt']))!=16 or len(bytes.fromhex(self.data['hash']))!=32 or self.data['iterations']!=120000 or not 0<self.data['expires']<4102444800:
                self.data={}
        except (KeyError,ValueError,TypeError):self.data={}

    def active(self):return self.data.get('expires',0)>self.clock()

    def create(self,hours=1,owner=None):
        while True:
            pin=f'{secrets.randbelow(1_000_000):06}'
            if not owner or not verify_pin(pin,owner):break
        salt=secrets.token_bytes(16)
        self.data=dict(salt=salt.hex(),iterations=120000,hash=hashlib.pbkdf2_hmac('sha256',pin.encode(),salt,120000).hex(),expires=self.clock()+(8 if hours==8 else 1)*3600)
        return pin

    def verify(self,pin):return self.active() and verify_pin(pin,self.data)
    def revoke(self):self.data={}


class GuestViews:
    def owner(self):return self.unlocked and getattr(self,'role','owner')=='owner'

    def authorized_view(self,view):
        return not (self.unlocked and getattr(self,'role','owner')=='guest' and view not in GUEST_VIEWS)

    def guest_touch(self,x,y):
        if not self.unlocked or getattr(self,'role','owner')!='guest':return False
        if not self.authorized_view(self.screen):self.navigate('home');return True
        if self.screen=='home' and 504<=x<768 and 12<=y<52:self.lock_hub();return True
        if not self.compact and 224<=x<480 and 12<=y<52:return True
        if self.screen=='music_options' and 300<=y<356:return True
        if self.screen=='time' and 80<=y<124 and 532<=x<776:return True
        if not self.compact and self.screen in ('home','time','timers','focus','music','music_options','library') and 424<=y<480 and 400<=x<600:
            self.lock_hub();return True
        return False

    def draw_sharing(self):
        c=self.theme;guest=self.guest
        self.text('sharetitle',32,72,736,44,0,'Invita a usar el Hub',c['ink'],c['bg'])
        self.paragraph('sharehint',32,125,736,'El código permite música y temporizadores. Fotos, cámara, Notion y ajustes quedan reservados al anfitrión.',2,0)
        pin=getattr(self,'guest_code','')
        label=pin if pin and guest.active() else 'Código activo' if guest.active() else 'Sin invitados'
        self.digital('guestcode',32,224,736,88,label,1 if pin and guest.active() else 0,c['mint'],c['bg'])
        left=max(0,int((guest.data.get('expires',0)-time.time())/60))
        hint=f'Caduca en {left} min. Introducir en el teclado del PIN.' if guest.active() else 'Genera un código temporal; tu PIN personal no cambia.'
        self.text('guestexpiry',32,316,736,32,2,hint,c['muted'],c['bg'],1)
        self.soft_button('guest1h',32,370,224,56,'Crear / 1 hora',True,0)
        self.soft_button('guest8h',288,370,224,56,'Crear / 8 horas',False,0)
        self.soft_button('guestrevoke',544,370,224,56,'Revocar',False,0)
        self.text('guestfoot',32,438,736,28,2,'Crear otro código invalida el anterior.',c['muted'],c['bg'],1)

    def touch_sharing(self,x,y):
        if not self.owner():return
        if 496<=x<616 and 12<=y<52:self.navigate('phone');return
        if 632<=x<768 and 12<=y<52:self.guest_code='';self.navigate('status');return
        if 370<=y<426:
            if 32<=x<256 or 288<=x<512:
                self.guest_code=self.guest.create(1 if x<256 else 8,getattr(self,'pin_record',None))
            elif 544<=x<768:self.guest.revoke();self.guest_code=''
            self.save();self.navigate('sharing')
