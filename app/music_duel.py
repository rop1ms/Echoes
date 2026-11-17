"""Two-track listening game. Tournament decisions and random pairs are separate.

Арена рисуется сама (QPainter): карточки наклоняются за мышью, «VS» бьёт при каждом выборе,
проигравший улетает, у победителя — вспышка и конфетти, новый соперник въезжает сбоку,
у чемпиона — корона и лучи. Таймер кадров работает, только пока страница видна."""
from __future__ import annotations
import math
import random
import threading
import time
from copy import deepcopy
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QRect, QRectF, QPointF, QPoint, QSize, QEvent, pyqtSignal
from frameclock import FrameTimer
from PyQt6.QtGui import (QColor, QPainter, QPainterPath, QPen, QBrush, QFont, QFontMetrics, QPixmap, QImage,
                         QLinearGradient, QRadialGradient, QTransform, QPolygonF)
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QCheckBox,QLineEdit,QFrame,QScrollArea)

def identity(t):
    if not isinstance(t,dict):return ''
    value=t.get('path') or t.get('url') or ''
    return str(value) if isinstance(value,(str,Path)) else ''
def compact(t):return {k:t[k] for k in ('path','url','title','artist','artists','album','genre','genres','cover','cover_url','source','duration','id','chorus_start','chorus_start_sec','preview_start') if k in t}

class Duel:
    def __init__(self):self.roster=[];self.order=[];self.champion=None;self.cursor=0;self.history=[];self.mode='king';self.pair=[]
    def start(self,tracks,mode='king',rng=None):
        if mode not in ('king','pairs'):raise ValueError('Неизвестный режим дуэли')
        rng=rng or random
        unique={identity(t):compact(t) for t in tracks if identity(t)}
        if len(unique)<2:raise ValueError('Нужно хотя бы два разных трека')
        self.roster=list(unique.values());self.order=list(range(len(self.roster)));rng.shuffle(self.order)
        self.mode=mode;self.history=[];self.cursor=1;self.champion=self.order[0];self.pair=self.order[:2]
    def current(self):
        if len(self.roster)<2:return []
        if self.mode=='king':
            if self.cursor>=len(self.order):return [self.roster[self.champion]]
            return [self.roster[self.champion],self.roster[self.order[self.cursor]]]
        return [self.roster[i] for i in self.pair]
    def vote(self,side):
        if side not in (0,1) or len(self.current())!=2:raise ValueError('Дуэль завершена')
        if self.mode=='king':
            self.history.append(self.champion)
            if side:self.champion=self.order[self.cursor]
            self.cursor+=1
        else:
            self.history.append({'pair':list(self.pair),'winner':self.pair[side]});self.history=self.history[-500:]
            self.next_pair()
    def next_pair(self):
        if self.mode!='pairs' or len(self.roster)<2:return
        previous=set(self.pair)
        self.pair=random.sample(range(len(self.roster)),2)
        if len(self.roster)>2 and set(self.pair)==previous:
            self.pair[1]=random.choice([i for i in range(len(self.roster)) if i not in previous])
    def undo(self):
        if not self.history:return
        old=self.history.pop()
        if self.mode=='king':self.champion=old;self.cursor-=1
        else:self.pair=old['pair']
    def streak(self):
        """Сколько раундов подряд держится нынешний чемпион (царь горы)."""
        if self.mode!='king':return 0
        n=0
        for index in range(len(self.history)-1,-1,-1):
            c=self.history[index+1] if index+1<len(self.history) else self.champion
            if c!=self.champion:break
            n+=1
        return n
    def wins(self):
        """{индекс трека: число побед} по истории выборов."""
        out={}
        if self.mode=='king':
            for k in range(len(self.history)):
                w=self.history[k+1] if k+1<len(self.history) else self.champion
                out[w]=out.get(w,0)+1
        else:
            for h in self.history:out[h['winner']]=out.get(h['winner'],0)+1
        return out
    def dump(self):return deepcopy({k:getattr(self,k) for k in ('roster','order','champion','cursor','history','mode','pair')})
    def restore(self,data):
        """Reject malformed sessions before replacing any live tournament state."""
        if not isinstance(data,dict):return False
        try:
            roster,order,history=data['roster'],data['order'],data['history']
            if not all(isinstance(v,list) for v in (roster,order,history)):return False
            n=len(roster);mode=data['mode']
            index=lambda value:type(value) is int and 0<=value<n
            if not 2<=n<=100000 or len(order)!=n or not all(index(i) for i in order):return False
            if len(set(order))!=n or mode not in ('king','pairs'):return False
            cursor=data['cursor'];champion=data['champion'];pair=data['pair']
            if type(cursor) is not int or not 1<=cursor<=n or not index(champion):return False
            if not isinstance(pair,list) or len(pair)!=2 or not all(index(i) for i in pair) or pair[0]==pair[1]:return False
            if any(not isinstance(t,dict) or not identity(t) for t in roster):return False
            if len({identity(t) for t in roster})!=n:return False
            if mode=='king':
                if len(history)!=cursor-1 or not all(index(i) for i in history):return False
                expected=order[0]
                for round_,previous in enumerate(history):
                    if previous!=expected:return False
                    expected=history[round_+1] if round_+1<len(history) else champion
                    if expected not in (previous,order[round_+1]):return False
                if champion!=expected:return False
            else:
                if len(history)>500:return False
                for h in history:
                    if not isinstance(h,dict):return False
                    hp=h.get('pair');winner=h.get('winner')
                    if not isinstance(hp,list) or len(hp)!=2 or not all(index(i) for i in hp):return False
                    if hp[0]==hp[1] or not index(winner) or winner not in hp:return False
            state={k:deepcopy(data[k]) for k in ('roster','order','champion','cursor','history','mode','pair')}
            for k,value in state.items():setattr(self,k,value)
            return True
        except (KeyError,TypeError,ValueError):return False


# ══════════════════════════════════════════════════════════════════════════ #
#  Анимация: твины и кривые
# ══════════════════════════════════════════════════════════════════════════ #

def ease_out_cubic(p):return 1-(1-p)**3
def ease_in_out_cubic(p):return 4*p*p*p if p<0.5 else 1-(-2*p+2)**3/2
def ease_in_back(p):return 2.70158*p*p*p-1.70158*p*p
def ease_out_back(p):
    c=1.70158;q=p-1
    return 1+(c+1)*q*q*q+c*q*q
def ease_out_elastic(p):
    if p in (0,1):return p
    return 2**(-10*p)*math.sin((p*10-0.75)*(2*math.pi)/3)+1

GOLD=QColor("#ffdb1a")


def _ph():
    try:
        import ya_skin
        return bool(ya_skin.PHANTOM_ON)
    except Exception:                                          # noqa: BLE001
        return False


def _g(c):
    """Вид Phantom — монохром: цвет → серый той же яркости (золото, подсветка обложек); иначе как был."""
    q=QColor(c)
    if not _ph():return q
    v=max(30,min(250,int(.299*q.red()+.587*q.green()+.114*q.blue())))
    import ph_style                                             # серый с оттенком картинки фона
    return ph_style.tone(v,q.alpha())
CHAMP_SCALE=0.88                       # чемпион чуть меньше — над ним корона, под ним надпись
INK=QColor(14,13,18)

def _font(px,weight=QFont.Weight.Bold,family='Segoe UI'):
    f=QFont(family);f.setPixelSize(max(1,int(px)));f.setWeight(weight);return f


class Sprite:
    """Карточка трека на арене. pos: −1 — левый слот, +1 — правый, 0 — центр; ±3 — за краем."""
    def __init__(self,track,pos):
        self.track=track;self.ident=identity(track)
        self.v={'pos':float(pos),'dy':0.0,'rot':0.0,'scale':1.0,'alpha':1.0,'glow':0.0,'dim':0.0,'stamp':0.0,'lift':0.0}
        self.tweens=[];self.side=None;self.leaving=False
        self.cover=QPixmap();self.color=QColor(120,90,200);self.card=None;self.card_key=None
        self.tilt=[0.0,0.0];self.hover=0.0;self.play_hover=0.0;self.bars=[0.0]*5
    def to(self,prop,value,dur,delay=0.0,ease=ease_out_cubic,now=None):
        now=time.perf_counter() if now is None else now
        self.tweens=[t for t in self.tweens if t[0]!=prop or t[3]<now+delay]   # новое заменяет запланированное
        self.tweens.append([prop,None,float(value),now+delay,max(0.001,dur),ease])
    def step(self,now):
        alive=[]
        for tw in self.tweens:
            prop,a,b,t0,dur,ease=tw
            if now<t0:alive.append(tw);continue
            if a is None:a=tw[1]=self.v[prop]
            p=min(1.0,(now-t0)/dur);self.v[prop]=a+(b-a)*ease(p)
            if p<1:alive.append(tw)
        self.tweens=alive
        return bool(alive)
    def finish(self):
        for prop,a,b,*_ in self.tweens:self.v[prop]=b
        self.tweens=[]


def _gl_possible(win):
    """Окно уже на GPU-совмещении (ya_wave.gpu_anchor) — арену можно рисовать видеокартой."""
    import os
    if os.environ.get('ECHOES_NO_GPU_DUEL')=='1' or (os.environ.get('QT_QPA_PLATFORM') or '').startswith('offscreen'):return False
    if _ph():return False                                       # Phantom: арена поверх стекла панели — растром
    anchor=getattr(win,'_gpu_anchor',None)
    try:return anchor is not None and anchor.ok()
    except RuntimeError:return False


def _canvas_class():
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget

    class ArenaCanvas(QOpenGLWidget):
        """GL-холст поверх арены: тот же Arena._paint, но QPainter рисует видеокартой (наклон карточек в 3D,
        прозрачность, текст), огонь — шейдером (native_ui.fire_draw). Окно не перекачивает в видеокарту
        растровую арену каждый кадр. Мышь и клавиши — у самой арены."""
        def __init__(self,arena):
            super().__init__(arena);self.arena=arena
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setProperty('echoes_live',True)                             # живой холст: прокрутка — растром (gpu_scroll)
            fmt=self.format();fmt.setSamples(4);self.setFormat(fmt)          # сглаживание краёв (MSAA)
        def paintGL(self):
            self.arena._paint(QPainter(self))
    return ArenaCanvas


class Arena(QWidget):
    """Арена дуэли. Рисует себя растром (QPainter по процессору) или, когда окно на GPU-совмещении, — через
    GL-холст поверх себя (_canvas): та же отрисовка _paint, но видеокартой."""
    voted=pyqtSignal(int);preview=pyqtSignal(int);start_clicked=pyqtSignal()
    def __init__(self,page):
        super().__init__();self.page=page;self._canvas=None
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMinimumHeight(470);self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.sprites=[];self.particles=[];self.events=[]
        self.vs_scale=1.0;self.vs_tw=[];self.flash=0.0;self.shake=0.0;self.lock_until=0.0
        self.champ=0.0;self.champ_on=False;self.rain_until=0.0
        self.round_text='';self.progress=0.0;self.progress_shown=0.0;self.streak=0;self.king=True
        self.mouse=QPointF(-1,-1);self.t0=time.perf_counter();self.last=self.t0;self.bg=None;self.bg_key=None
        self.start_hover=0.0;self.level=0.0
        self.timer=FrameTimer(self);self.timer.timeout.connect(self._tick)
        self._halo_cache = {}
        from duel_fire import FireCache
        self.fire_cache=FireCache();self.fire_enabled=True;self.wins_by_id={}

    # ── геометрия ── #
    def card_size(self):
        W,H=self.width(),self.height()
        avail=H-96
        cw=int(max(150,min(340,(W-200)/2,avail-112)))
        return cw,cw+112
    def slot_center(self,pos,dy=0.0):
        cw,ch=self.card_size()
        return QPointF(self.width()/2+pos*(cw/2+70),self.height()/2+14+dy)
    def sprite_rect(self,s):
        cw,ch=self.card_size();c=self.slot_center(s.v['pos'],s.v['dy'])
        return QRectF(c.x()-cw/2,c.y()-ch/2,cw,ch)
    def side_at(self,pt):
        for s in self.sprites:
            if s.side is not None and not s.leaving and self.sprite_rect(s).contains(pt):return s
        return None
    def play_rect(self,s):
        r=self.sprite_rect(s);cw,_=self.card_size();pad=16
        return QRectF(r.x()+cw-pad-62,r.y()+pad+(cw-2*pad)-62,52,52)
    def start_rect(self):
        return QRectF(self.width()/2-120,self.height()/2+14-27,240,54)

    # ── состояние ── #
    def locked(self):return time.perf_counter()<self.lock_until
    def fast_forward(self):
        for t,fn in sorted(self.events,key=lambda e:e[0]):fn()
        self.events=[]
        for s in self.sprites:s.finish()
        self.sprites=[s for s in self.sprites if not s.leaving]
        self.vs_tw=[];self.vs_scale=1.0;self.lock_until=0.0
    def _sprite(self,track,pos,side):
        s=Sprite(track,pos);s.side=side;self._load_cover(s);return s
    def set_pair(self,tracks,how='enter'):
        """Без анимации выбора: начало игры, отмена, другая пара, восстановленная сессия."""
        self.fast_forward();now=time.perf_counter()
        old=self.sprites;self.sprites=[];self.champ_on=False;self.champ=0.0
        for s in old:
            s.leaving=True;s.side=None
            if how=='swipe':s.to('dy',-self.height(),0.45,0,ease_in_back,now);s.to('alpha',0,0.4,0.05,now=now)
            else:s.to('alpha',0,0.22,now=now);s.to('scale',0.9,0.22,now=now)
            self.sprites.append(s)
        if len(tracks)==1:
            s=self._sprite(tracks[0],0,0);s.v['scale']=CHAMP_SCALE;self.sprites.append(s)
            s.v['alpha']=0;s.to('alpha',1,0.4,now=now);self._champion_on(now);return
        for i,t in enumerate(tracks):
            target=-1 if i==0 else 1
            s=self._sprite(t,target*3.2 if how!='none' else target,i)
            if how=='drop':s.v['pos']=target;s.v['dy']=-self.height();s.to('dy',0,0.6,0.08*i,ease_out_back,now)
            elif how!='none':s.to('pos',target,0.65,0.12+0.1*i,ease_out_back,now)
            self.sprites.append(s)
        self._vs_punch(now+0.3);self.lock_until=now+0.35;self._wake()
    def animate_vote(self,side,new,finished,king):
        if self.locked() or self.events:self.fast_forward()
        now=time.perf_counter()
        cur={s.side:s for s in self.sprites if s.side is not None and not s.leaving}
        win,lose=cur.get(side),cur.get(1-side)
        if win is None or lose is None:return self.set_pair(new,'enter')
        direction=-1 if side==1 else 1          # куда улетает проигравший: прочь от центра
        for s in (win,lose):s.to('pos',s.v['pos']*0.82,0.13,0,ease_out_cubic,now)
        self._vs_punch(now);self.flash=1.0
        hit=now+0.13
        lose.leaving=True;lose.side=None
        lose.to('pos',lose.v['pos']+direction*1.6,0.6,0.13,ease_in_back,now)
        lose.to('dy',self.height()*0.55,0.6,0.13,ease_in_back,now)
        lose.to('rot',direction*34,0.6,0.13,ease_in_back,now)
        lose.to('dim',0.75,0.2,0.13,now=now);lose.to('alpha',0,0.35,0.42,now=now);lose.to('scale',0.78,0.6,0.13,now=now)
        win.to('scale',1.1,0.35,0.13,ease_out_back,now);win.to('glow',1.0,0.2,0.13,now=now)
        win.to('stamp',1.0,0.45,0.15,ease_out_elastic,now)
        self.events.append((hit,lambda w=win:self._burst(w)))
        self.events.append((hit,lambda:setattr(self,'shake',1.0)))
        nxt=now+0.68
        if finished:
            win.side=0
            win.to('pos',0,0.7,0.68,ease_in_out_cubic,now);win.to('scale',CHAMP_SCALE,0.7,0.68,ease_out_back,now)
            win.to('stamp',0,0.25,0.6,now=now);win.to('glow',0.6,0.5,0.9,now=now)
            self.events.append((nxt+0.3,lambda:self._champion_on(time.perf_counter())))
        elif king:
            win.side=0
            win.to('pos',-1,0.42,0.62,ease_in_out_cubic,now);win.to('scale',1.0,0.42,0.62,now=now)
            win.to('stamp',0,0.25,0.55,now=now);win.to('glow',0.35,0.5,0.7,now=now)
            def enter(t=new[1]):
                s=self._sprite(t,3.4,1);self.sprites.append(s);s.to('pos',1,0.65,0,ease_out_back);self._vs_punch(time.perf_counter()+0.3)
            self.events.append((nxt+0.12,enter));nxt+=0.12
        else:
            win.side=None;win.leaving=True
            win.to('dy',-self.height()*0.7,0.5,0.62,ease_in_back,now);win.to('alpha',0,0.3,0.85,now=now)
            win.to('stamp',0,0.2,0.6,now=now)
            def enter(tracks=list(new)):
                n=time.perf_counter()
                for i,t in enumerate(tracks):
                    target=-1 if i==0 else 1
                    s=self._sprite(t,target*3.2,i);self.sprites.append(s);s.to('pos',target,0.65,0.07*i,ease_out_back,n)
                self._vs_punch(n+0.35)
            self.events.append((nxt,enter))
        self.lock_until=nxt+0.05;self._wake()
    def _vs_punch(self,at):
        self.vs_tw=[(at,0.12,1.0,1.55,ease_out_cubic),(at+0.12,0.45,1.55,1.0,ease_out_elastic)]
    def _champion_on(self,now):
        self.champ_on=True;self.rain_until=now+4.5;self.shake=max(self.shake,0.6)
        for s in self.sprites:
            if not s.leaving:self._burst(s,90)
        self._wake()

    # ── обложки ── #
    def _load_cover(self,s):
        t=s.track;path=t.get('cover') or ''
        if not path and t.get('cover_url'):
            try:
                from ya_online import load_thumb
                load_thumb(self.page.win,t['cover_url'],lambda p,s=s:self._read_cover(s,p))
            except Exception:pass                                    # noqa: BLE001
        elif path:self._read_cover(s,path)
        else:                                                         # нет обложки — своя картинка из «Оформления»
            try:
                from yamusic_theme import PLACEHOLDER
                ph=PLACEHOLDER.get('path') or ''
            except Exception:ph=''                                    # noqa: BLE001
            if ph:self._read_cover(s,ph)
        if s.cover.isNull():
            r=random.Random(s.ident);h=r.randrange(360)
            s.color=QColor.fromHsv(h,170,220)
    def _read_cover(self,s,path):
        """Декод в фоне: QImage отпускает GIL, звук не заикается."""
        def work():
            try:
                from img_load import read_image
                img=read_image(path,600)
            except Exception:img=QImage()                             # noqa: BLE001
            if img.isNull():return
            c=img.scaled(1,1,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation).pixelColor(0,0)
            h,sat,v,_=c.getHsv();c=QColor.fromHsv(max(0,h),min(255,max(120,int(sat*1.3))),max(170,v))
            def done():
                s.cover=QPixmap.fromImage(img);s.color=c;s.card=None;self.bg=None;self.update()
            try:self.page.win._ui_bridge.call.emit(done)
            except RuntimeError:pass
        threading.Thread(target=work,daemon=True,name='duel-cover').start()

    # ── частицы ── #
    def _burst(self,s,n=60):
        from performance import config
        if not config()['duel_particles']:return
        r=self.sprite_rect(s);c=r.center()
        cols=[s.color,GOLD,QColor(255,255,255),s.color.lighter(140)]
        for _ in range(n):
            a=random.uniform(0,2*math.pi);sp=random.uniform(260,820)
            self.particles.append([c.x()+math.cos(a)*r.width()*0.3,c.y()+math.sin(a)*r.height()*0.25,
                                   math.cos(a)*sp,math.sin(a)*sp-260,random.uniform(0.9,1.6),random.choice(cols),
                                   random.uniform(5,11),random.uniform(0,360),random.uniform(-720,720),random.random()<0.6])
        self._wake()
    def _rain(self,dt):
        from performance import config
        if not config()['duel_particles']:return
        for _ in range(int(dt*90)+(random.random()<dt*90%1)):
            self.particles.append([random.uniform(0,self.width()),-12,random.uniform(-60,60),random.uniform(120,260),
                                   random.uniform(2.5,4),random.choice([GOLD,QColor(255,90,140),QColor(90,200,255),QColor(255,255,255)]),
                                   random.uniform(6,10),random.uniform(0,360),random.uniform(-400,400),True])

    # ── кадры ── #
    def _wake(self):
        if self.isVisible() and (not self.timer.isActive() or self.timer.interval()!=16):self.timer.start(16)
    _KEYS=(Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_A,Qt.Key.Key_D,Qt.Key.Key_1,Qt.Key.Key_2,Qt.Key.Key_Backspace,Qt.Key.Key_S)
    def event(self,e):
        if e.type()==QEvent.Type.ShortcutOverride and e.key() in self._KEYS:   # стрелки плеера не перехватывают выбор
            e.accept();return True
        return super().event(e)
    def showEvent(self,e):
        super().showEvent(e);self.last=time.perf_counter();self.timer.start(16)
        if self._canvas is None and _gl_possible(self.window()):
            try:
                self._canvas=_canvas_class()(self);self._canvas.setGeometry(self.rect());self._canvas.show()
            except Exception as ex:                                   # noqa: BLE001
                print('[duel] gpu:',ex);self._canvas=None
    def resizeEvent(self,e):
        super().resizeEvent(e)
        if self._canvas is not None:self._canvas.setGeometry(self.rect())
    def update(self,*a):
        if self._canvas is not None and not a:self._canvas.update()
        else:super().update(*a)
    def hideEvent(self,e):
        self.timer.stop();super().hideEvent(e)
        if self._canvas is not None:                                  # скрыта 20 с — GL-контекст отдать (~19 МБ)
            if self.__dict__.get('_canvas_t') is None:
                self._canvas_t=QTimer(self);self._canvas_t.setSingleShot(True);self._canvas_t.timeout.connect(self._drop_canvas)
            self._canvas_t.start(600000)
    def _drop_canvas(self):
        if self.isVisible() or self._canvas is None:return
        c,self._canvas=self._canvas,None
        c.hide();c.deleteLater()
    def _tick(self):
        colors = tuple(s.color.rgb() for s in self.sprites if s.side is not None)
        if colors != getattr(self, '_page_colors', None):
            self._page_colors = colors
            self.page.widget().update()
        win=self.window()
        if win is None or win.isMinimized():return
        now=time.perf_counter();dt=min(0.05,now-self.last);self.last=now
        for at,fn in [e for e in self.events if e[0]<=now]:fn()
        self.events=[e for e in self.events if e[0]>now]
        busy=bool(self.events)
        for s in self.sprites:busy|=s.step(now)
        self.sprites=[s for s in self.sprites if not (s.leaving and s.v['alpha']<=0.01 and not s.tweens)]
        self.vs_scale=1.0
        for at,dur,a,b,ease in self.vs_tw:
            if now>=at:
                p=min(1.0,(now-at)/dur);self.vs_scale=a+(b-a)*ease(p)
                if p<1:busy=True
            else:busy=True;break
        self.flash=max(0.0,self.flash-dt*2.6);self.shake=max(0.0,self.shake-dt*2.2)
        busy|=self.flash>0 or self.shake>0
        if self.champ_on:
            self.champ=min(1.0,self.champ+dt*1.5)
            if now<self.rain_until:self._rain(dt)
        else:self.champ=max(0.0,self.champ-dt*3)
        g=900.0
        for p in self.particles:
            p[0]+=p[2]*dt;p[1]+=p[3]*dt;p[3]+=g*dt*(0.35 if p[9] else 1);p[2]*=1-dt*1.2;p[4]-=dt;p[7]+=p[8]*dt
        self.particles=[p for p in self.particles if p[4]>0 and p[1]<self.height()+30]
        busy|=bool(self.particles)
        hov=self.side_at(self.mouse) if not self.locked() else None
        playing=self.page.preview_side()
        if playing is not None:
            try:lv=float(self.page.win.engine.get_level())
            except Exception:lv=0.0                                  # noqa: BLE001
            self.level+=(min(1.0,lv*3.2)-self.level)*0.35
        for s in self.sprites:
            target=1.0 if s is hov else 0.0
            s.hover+=(target-s.hover)*min(1.0,dt*12)
            if s is hov:
                r=self.sprite_rect(s);nx=(self.mouse.x()-r.center().x())/(r.width()/2);ny=(self.mouse.y()-r.center().y())/(r.height()/2)
                tx,ty=max(-1,min(1,nx))*9,max(-1,min(1,ny))*-7
            else:tx=ty=0.0
            s.tilt[0]+=(tx-s.tilt[0])*min(1.0,dt*10);s.tilt[1]+=(ty-s.tilt[1])*min(1.0,dt*10)
            ph=1.0 if (s is hov and self.play_rect(s).contains(self.mouse)) else 0.0
            s.play_hover+=(ph-s.play_hover)*min(1.0,dt*14)
            busy|=abs(target-s.hover)>0.01 or abs(tx-s.tilt[0])>0.05 or abs(ty-s.tilt[1])>0.05
            on=playing is not None and s.side==playing and not s.leaving
            for i in range(5):
                want=(self.level*(0.55+0.45*math.sin(now*(7+i*2.3)+i*1.7))+0.12) if on else 0.0
                s.bars[i]+=(max(0.0,want)-s.bars[i])*0.4
            busy|=on
        if not self.sprites:
            self.start_hover+=((1.0 if self.start_rect().contains(self.mouse) else 0.0)-self.start_hover)*min(1.0,dt*12)
        self.progress_shown+=(self.progress-self.progress_shown)*min(1.0,dt*6)
        busy|=abs(self.progress-self.progress_shown)>0.001 or 0<self.champ<1
        # в покое — 30 кадров на «дыхание» VS растром; на GL-холсте кадр ~3 мс — плавно на полной частоте
        want=16 if busy or self._canvas is not None or (self.champ_on and now<self.rain_until) else 33
        if self.timer.interval()!=want:self.timer.setInterval(want)
        self.update()

    # ── ввод ── #
    def mouseMoveEvent(self,e):
        self.mouse=e.position()
        s=self.side_at(self.mouse)
        over=(s is not None) or (not self.sprites and self.start_rect().contains(self.mouse))
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)
        self._wake()
    def leaveEvent(self,e):
        self.mouse=QPointF(-1,-1);self._wake();super().leaveEvent(e)
    def mousePressEvent(self,e):
        if e.button()!=Qt.MouseButton.LeftButton:return
        pt=e.position();self.setFocus()
        if not self.sprites:
            if self.start_rect().contains(pt):self.start_clicked.emit()
            return
        s=self.side_at(pt)
        if s is None:return
        if self.play_rect(s).contains(pt):self.preview.emit(s.side)
        elif not self.champ_on:self.voted.emit(s.side)
    def keyPressEvent(self,e):
        k=e.key()
        if k in (Qt.Key.Key_Left,Qt.Key.Key_A):self.voted.emit(0)
        elif k in (Qt.Key.Key_Right,Qt.Key.Key_D):self.voted.emit(1)
        elif k==Qt.Key.Key_1:self.preview.emit(0)
        elif k==Qt.Key.Key_2:self.preview.emit(1)
        elif k==Qt.Key.Key_Backspace:self.page.undo()
        elif k==Qt.Key.Key_S:self.page.skip_pair()
        else:super().keyPressEvent(e)

    # ── отрисовка ── #
    def _background(self, size=None):
        W,H=(size.width(),size.height()) if size is not None else (self.width(),self.height())
        glass_key=None
        if _ph():                                              # Phantom: фон за панелью вместо чёрного стекла
            try:
                import ph_shell
                glass_key=ph_shell.backdrop_key(self)
            except Exception:                                  # noqa: BLE001
                glass_key=None
        key=(W,H,self.devicePixelRatioF(),tuple(s.color.rgb() for s in self.sprites if s.side is not None),glass_key)
        if self.bg is not None and self.bg_key==key:return self.bg
        dpr=self.devicePixelRatioF()
        if glass_key is not None:
            import ph_shell
            import ph_style
            pm=QPixmap(int(W*dpr),int(H*dpr));pm.setDevicePixelRatio(dpr);pm.fill(QColor(0,0,0,0))
            gp=QPainter(pm)
            ph_shell.paint_backdrop(self,gp,QRect(0,0,W,H))     # непрозрачная арена: под ней — то, что за панелью
            ph_style.paint_surface(gp,QRectF(0,0,W,H),"panel",22)
            gp.end()
        else:
            from echo_glass import liquid_surface
            pm=liquid_surface(QSize(int(W*dpr),int(H*dpr)),radius=22*dpr)
            pm.setDevicePixelRatio(dpr)
        p=QPainter(pm);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path=QPainterPath();path.addRoundedRect(QRectF(0,0,W,H),22,22);p.setClipPath(path)
        cols=[_g(s.color) for s in sorted([s for s in self.sprites if s.side is not None],key=lambda s:s.side)]
        if len(cols)==1:cols=cols*2
        for i,c in enumerate(cols[:2]):
            # Light comes in through the edges; the middle remains black glass.
            g=QRadialGradient(QPointF(W*(-0.06 if i==0 else 1.06),H*.48),W*.68)
            cc=QColor(c);cc.setAlpha(62);g.setColorAt(0,cc)
            cc=QColor(c);cc.setAlpha(19);g.setColorAt(.45,cc)
            cc.setAlpha(0);g.setColorAt(1,cc)
            p.fillRect(QRectF(0,0,W,H),QBrush(g))
        p.end();self.bg=pm;self.bg_key=key;return pm
    def _card(self,s):
        cw,ch=self.card_size();dpr=self.devicePixelRatioF()
        key=(cw,dpr,s.cover.cacheKey(),s.color.rgb())
        if s.card is not None and s.card_key==key:return s.card
        from echo_glass import liquid_surface
        pm=liquid_surface(QSize(int(cw*dpr),int(ch*dpr)),radius=24*dpr)
        pm.setDevicePixelRatio(dpr)
        p=QPainter(pm);p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform|QPainter.RenderHint.TextAntialiasing)
        pad=16;cs=cw-2*pad;cr=QRectF(pad,pad,cs,cs)
        clip=QPainterPath();clip.addRoundedRect(cr,16,16)
        p.save();p.setClipPath(clip)
        if not s.cover.isNull():
            src=s.cover;side=min(src.width(),src.height())
            p.drawPixmap(cr,src,QRectF((src.width()-side)/2,(src.height()-side)/2,side,side))
        else:
            gg=QLinearGradient(cr.topLeft(),cr.bottomRight());gg.setColorAt(0,s.color);gg.setColorAt(1,s.color.darker(260))
            p.fillRect(cr,QBrush(gg));p.setPen(QPen(QColor(255,255,255,70),max(3,cs/40)))
            n=cr.center();rr=cs*0.16
            p.drawEllipse(QPointF(n.x()-rr*0.6,n.y()+rr*1.1),rr*0.7,rr*0.55);p.drawLine(QPointF(n.x()+rr*0.05,n.y()+rr*1.1),QPointF(n.x()+rr*0.05,n.y()-rr*1.4))
            p.drawLine(QPointF(n.x()+rr*0.05,n.y()-rr*1.4),QPointF(n.x()+rr*0.9,n.y()-rr*0.9))
        sh=QLinearGradient(0,cr.bottom()-cs*0.35,0,cr.bottom());sh.setColorAt(0,QColor(0,0,0,0));sh.setColorAt(1,QColor(0,0,0,120))
        p.fillRect(cr,QBrush(sh));p.restore()
        y=pad+cs+12;t=s.track
        p.setFont(_font(19,QFont.Weight.ExtraBold));p.setPen(QColor(245,245,250))
        p.drawText(QRectF(pad,y,cs,26),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(p.font()).elidedText(str(t.get('title') or 'Без названия'),Qt.TextElideMode.ElideRight,int(cs)))
        art=str(t.get('artist') or '')
        net=bool(t.get('url'))
        p.setFont(_font(13,QFont.Weight.DemiBold));p.setPen(QColor(170,168,182))
        aw=cs-(78 if net else 0)
        p.drawText(QRectF(pad,y+26,aw,20),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(p.font()).elidedText(art,Qt.TextElideMode.ElideRight,int(aw)))
        if net:
            p.setFont(_font(10,QFont.Weight.Black));tr=QRectF(pad+cs-72,y+28,72,17)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(255,255,255,26));p.drawRoundedRect(tr,8,8)
            p.setPen(QColor(200,200,214));p.drawText(tr,Qt.AlignmentFlag.AlignCenter,'ИНТЕРНЕТ')
        p.end();s.card=pm;s.card_key=key;return pm
    def paintEvent(self,e):
        if self._canvas is None:self._paint(QPainter(self))
    def _paint(self,p):
        p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform|QPainter.RenderHint.TextAntialiasing)
        surface = self.page.widget()
        offset = self.mapTo(surface, QPoint(0, 0))
        p.drawPixmap(-offset.x(), -offset.y(), self._background(surface.size()))
        now=time.perf_counter();W,H=self.width(),self.height()
        if self.shake>0:
            a=self.shake**2*9;p.translate(random.uniform(-a,a),random.uniform(-a,a))
        if self.champ>0:self._paint_rays(p,now)
        self._paint_header(p,now)
        if self.sprites and self.champ<0.99:self._paint_vs(p,now)   # под карточками: пролетающие проходят поверх
        order=sorted(self.sprites,key=lambda s:(not s.leaving,s.v['scale']+s.hover*0.01))
        for s in order:self._paint_sprite(p,s,now)
        if not self.sprites:self._paint_empty(p,now)
        for x,y,vx,vy,life,c,sz,rot,vr,confetti in self.particles:
            p.save();p.translate(x,y);p.rotate(rot);cc=QColor(c);cc.setAlphaF(max(0.0,min(1.0,life*1.4)))
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(cc)
            if confetti:p.drawRect(QRectF(-sz/2,-sz/4,sz,sz/2))
            else:p.drawEllipse(QRectF(-sz/3,-sz/3,sz*0.66,sz*0.66))
            p.restore()
        if self.flash>0:
            g=QRadialGradient(QPointF(W/2,H/2),max(W,H)*0.6);c=QColor(255,255,255,int(150*self.flash))
            g.setColorAt(0,c);c2=QColor(255,255,255,0);g.setColorAt(1,c2);p.fillRect(self.rect(),QBrush(g))
        p.setFont(_font(11,QFont.Weight.DemiBold));p.setPen(QColor(255,255,255,90))
        hint='← / →  выбрать   ·   1 / 2  послушать   ·   Backspace  отменить'+('   ·   S  другая пара' if not self.king else '')
        if self.sprites and not self.champ_on:self._text(p,QRectF(0,H-30,W,22),Qt.AlignmentFlag.AlignCenter,hint)
        p.end()
    def _paint_header(self,p,now):
        W=self.width()
        if self.king and self.sprites and self.champ<0.01:
            bw=min(420,W-200);r=QRectF(W/2-bw/2,22,bw,6)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(255,255,255,24));p.drawRoundedRect(r,3,3)
            fr=QRectF(r.x(),r.y(),max(6,r.width()*self.progress_shown),r.height())
            g=QLinearGradient(fr.topLeft(),fr.topRight());g.setColorAt(0,_g("#a78b24"));g.setColorAt(1,_g(GOLD))
            p.setBrush(QBrush(g));p.drawRoundedRect(fr,3,3)
            gl=_g(GOLD);gl.setAlpha(int(90+60*math.sin(now*4)));p.setBrush(gl);p.drawEllipse(QPointF(fr.right(),fr.center().y()),7,7)
        if self.round_text and self.sprites:
            p.setFont(_font(13,QFont.Weight.Black));p.setPen(QColor(235,235,245,210))
            self._text(p,QRectF(0,34,W,24),Qt.AlignmentFlag.AlignCenter,self.round_text.upper())
    def _paint_sprite(self,p,s,now):
        a=s.v['alpha']
        if a<=0.01:return
        cw,ch=self.card_size();c=self.slot_center(s.v['pos'],s.v['dy'])
        bob=math.sin(now*1.6+(0 if (s.side or 0)==0 else 1.7))*3*(1-s.hover)*(0 if s.leaving else 1)
        sc=s.v['scale']*(1+0.035*s.hover)
        p.save();p.setOpacity(a)
        t=QTransform();t.translate(c.x(),c.y()+bob-s.hover*8)
        t.rotate(s.tilt[0],Qt.Axis.YAxis);t.rotate(s.tilt[1],Qt.Axis.XAxis);t.rotate(s.v['rot']);t.scale(sc,sc)
        p.setTransform(t,True)
        r=QRectF(-cw/2,-ch/2,cw,ch)
        wins=self.wins_by_id.get(s.ident,0)
        from duel_settings import fire_tier
        tier=fire_tier(wins)
        if self.fire_enabled and tier:
            gpu=False
            if self._canvas is not None:                             # на GL-холсте — шейдером
                from performance import config
                import native_ui
                q={'low':0,'balanced':1,'high':2}.get(config()['aura_quality'],1)
                from duel_fire import COLORS
                gpu=native_ui.fire_draw(p,cw,ch,60,COLORS[tier-1],tier,now,q)
            if not gpu:self.fire_cache.draw(p,QRectF(-cw/2-44,-ch/2-44,cw+88,ch+88),cw,ch,wins,now)
        glow=max(s.v['glow'],s.hover*0.55)
        halo = self._halo(s, glow > .01)
        if glow > .01: p.setOpacity(a * glow)
        p.drawPixmap(QPointF(-cw/2-32, -ch/2-32), halo)
        p.setOpacity(a)
        p.drawPixmap(r.topLeft(),self._card(s))
        if glow>0.01:
            col=QColor(s.color).lighter(130);col.setAlphaF(min(1.0,0.35+glow*0.6));p.setPen(QPen(col,2));p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(1,1,-1,-1),24,24)
        pad=16;cs=cw-2*pad
        if s.hover>0.01:                                             # блик, бегущий за курсором
            sx=-cw/2+cw*(0.5+s.tilt[0]/18);g=QRadialGradient(QPointF(sx,-ch/2+ch*(0.5-s.tilt[1]/14)),cw*0.8)
            g.setColorAt(0,QColor(255,255,255,int(40*s.hover)));g.setColorAt(1,QColor(255,255,255,0))
            path=QPainterPath();path.addRoundedRect(r,24,24);p.fillPath(path,QBrush(g))
        if any(b>0.01 for b in s.bars):                               # эквалайзер поверх обложки — играет превью
            bx=-cw/2+pad+14;by=-ch/2+pad+cs-14
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(0,0,0,110));p.drawRoundedRect(QRectF(bx-8,by-48,5*9+8,56),10,10)
            for i,b in enumerate(s.bars):
                h=max(3,b*40);p.setBrush(QColor(s.color).lighter(150));p.drawRoundedRect(QRectF(bx+i*9,by-h,6,h),3,3)
        if not s.leaving and s.side is not None and not self.locked():
            pr=QRectF(cw/2-pad-62,-ch/2+pad+cs-62,52,52)
            pv=self.page.preview_side()==s.side
            scale=1+0.12*s.play_hover;pc=pr.center()
            pr=QRectF(pc.x()-26*scale,pc.y()-26*scale,52*scale,52*scale)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(255,255,255,235) if s.play_hover>0.5 or pv else QColor(20,20,26,215))
            p.drawEllipse(pr)
            ink=INK if s.play_hover>0.5 or pv else QColor(255,255,255)
            p.setBrush(ink);cx,cy=pc.x(),pc.y();k=scale
            if pv:
                p.drawRoundedRect(QRectF(cx-8*k,cy-9*k,5.5*k,18*k),2,2);p.drawRoundedRect(QRectF(cx+2.5*k,cy-9*k,5.5*k,18*k),2,2)
            else:p.drawPolygon(QPolygonF([QPointF(cx-6*k,cy-10*k),QPointF(cx+11*k,cy),QPointF(cx-6*k,cy+10*k)]))
            if not self.champ_on:                                     # «ВЫБРАТЬ»
                br=QRectF(-cw/2+pad,ch/2-pad-40,cs,40)
                hv=s.hover*(1-s.play_hover)
                g=QLinearGradient(br.topLeft(),br.topRight())
                c1=_g("#fff0a0") if hv>0.5 else QColor("#23272d");c2=_g(GOLD) if hv>0.5 else QColor("#080a0d")
                g.setColorAt(0,c1);g.setColorAt(1,c2);p.setBrush(QBrush(g));p.drawRoundedRect(br,14,14)
                p.setFont(_font(14,QFont.Weight.Black));p.setPen(INK if hv>0.5 else QColor(235,235,240))
                arrow='←' if s.side==0 else '→'
                self._text(p,br,Qt.AlignmentFlag.AlignCenter,(arrow+'   ВЫБРАТЬ' if s.side==0 else 'ВЫБРАТЬ   '+arrow))
        if s.side==0 and self.king and not s.leaving and len([x for x in self.sprites if x.side is not None])==2 and self.streak>0:
            self._paint_crown(p,QPointF(0,-ch/2-6),0.8,now)
            txt=f'ЧЕМПИОН · {self.streak} ' + ('ПОБЕДА' if self.streak%10==1 and self.streak%100!=11 else 'ПОБЕДЫ' if 2<=self.streak%10<=4 and not 12<=self.streak%100<=14 else 'ПОБЕД')
            from duel_settings import tr
            txt=tr(self.page.win,txt,f'CHAMPION · {self.streak} WINS')
            p.setFont(_font(11,QFont.Weight.Black));tw=self._adv(p.font(),txt)+22
            tr=QRectF(-tw/2,-ch/2+pad+8,tw,22);p.setPen(Qt.PenStyle.NoPen);p.setBrush(_g(GOLD));p.drawRoundedRect(tr,11,11)
            p.setPen(INK);self._text(p,tr,Qt.AlignmentFlag.AlignCenter,txt)
        if s.v['dim']>0.01:
            path=QPainterPath();path.addRoundedRect(r,24,24);p.fillPath(path,QColor(10,10,14,int(200*s.v['dim'])))
        st=s.v['stamp']
        if st>0.01:                                                  # штамп «ПОБЕДА»
            p.save();p.translate(0,-ch*0.12);p.rotate(-12);p.scale(max(0.01,st),max(0.01,st))
            p.setOpacity(a*min(1.0,st));f=_font(max(22,cw*0.15),QFont.Weight.Black);p.setFont(f)
            tw=self._adv(f,'ПОБЕДА')+36;th=QFontMetrics(f).height()+12
            box=QRectF(-tw/2,-th/2,tw,th);p.setPen(QPen(_g(GOLD),4));p.setBrush(QColor(14,13,18,200));p.drawRoundedRect(box,12,12)
            p.setPen(_g(GOLD));self._text(p,box,Qt.AlignmentFlag.AlignCenter,'ПОБЕДА');p.restore()
        p.restore()
        if self.champ>0 and s.side==0 and not s.leaving and len([x for x in self.sprites if not x.leaving])==1:
            p.save();p.setOpacity(self.champ)
            self._paint_crown(p,QPointF(c.x(),c.y()-ch*sc/2-14+math.sin(now*2.2)*4),1.5,now)
            p.setFont(_font(30,QFont.Weight.Black));p.setPen(_g(GOLD))
            self._text(p,QRectF(0,c.y()+ch*sc/2+4,self.width(),40),Qt.AlignmentFlag.AlignCenter,'ВАШ ЧЕМПИОН')
            p.restore()
    def _text(self,p,rect,flags,text):
        """Надпись арены — готовой картинкой (в 2× плотности, чтобы не мылилась при наклоне и масштабе).
        drawText по карточке, наклонённой в 3D, рисовал каждую букву кривыми (~0.6 мс на надпись)."""
        rect=QRectF(rect);font=p.font();col=p.pen().color()
        w,h=max(1,int(math.ceil(rect.width()))),max(1,int(math.ceil(rect.height())))
        k=2*self.devicePixelRatioF()
        key=(text,font.key(),col.rgba(),w,h,int(flags.value if hasattr(flags,'value') else flags),k)
        cache=self.__dict__.setdefault('_text_cache',{})
        pm=cache.get(key)
        if pm is None:
            pm=QPixmap(int(w*k),int(h*k));pm.setDevicePixelRatio(k);pm.fill(Qt.GlobalColor.transparent)
            q=QPainter(pm);q.setRenderHint(QPainter.RenderHint.TextAntialiasing);q.setFont(font);q.setPen(col)
            q.drawText(QRectF(0,0,w,h),flags,text);q.end()
            if len(cache)>=160:cache.clear()
            cache[key]=pm
        p.drawPixmap(QRectF(rect.x(),rect.y(),w,h),pm,QRectF(0,0,pm.width(),pm.height()))
    def _adv(self,font,text):
        cache=self.__dict__.setdefault('_adv_cache',{})
        key=(font.key(),text)
        v=cache.get(key)
        if v is None:
            if len(cache)>=200:cache.clear()
            v=cache[key]=QFontMetrics(font).horizontalAdvance(text)
        return v

    def _halo(self, sprite, glowing):
        cw, ch = self.card_size()
        dpr = self.devicePixelRatioF()
        key = (cw, ch, dpr, sprite.color.rgb(), glowing)
        if key in self._halo_cache: return self._halo_cache[key]
        pm = QPixmap(round((cw+64)*dpr), round((ch+64)*dpr))
        pm.setDevicePixelRatio(dpr); pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(32, 32, cw, ch)
        if glowing:
            for i in range(7, 0, -1):
                color = QColor(sprite.color); color.setAlpha(26-i*3)
                painter.setPen(QPen(color, i*4.5)); painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(box, 24, 24)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            for i in range(1, 5):
                painter.setBrush(QColor(0,0,0,22))
                painter.drawRoundedRect(box.adjusted(4-i*2,6+i*3,i*2-4,i*3),24+i*2,24+i*2)
        painter.end()
        if len(self._halo_cache) >= 16: self._halo_cache.clear()
        self._halo_cache[key] = pm
        return pm

    def _paint_crown(self,p,at,k,now):
        p.save();p.translate(at);p.scale(k,k)
        pts=[(-26,0),(-30,-26),(-14,-12),(0,-32),(14,-12),(30,-26),(26,0)]
        poly=QPolygonF([QPointF(x,y) for x,y in pts])
        g=QLinearGradient(0,-32,0,0);g.setColorAt(0,_g(QColor(255,236,140)));g.setColorAt(1,_g(QColor(240,170,30)))
        p.setPen(QPen(QColor(120,70,0),2));p.setBrush(QBrush(g));p.drawPolygon(poly)
        p.setPen(Qt.PenStyle.NoPen)
        for x,y in ((-30,-26),(0,-32),(30,-26)):p.setBrush(QColor(255,80,120));p.drawEllipse(QPointF(x,y),4,4)
        sp=0.5+0.5*math.sin(now*5);p.setBrush(QColor(255,255,255,int(200*sp)));p.drawEllipse(QPointF(-8,-12),2.2,2.2)
        p.restore()
    def _paint_rays(self,p,now):
        W,H=self.width(),self.height();c=self.slot_center(0)
        p.save();p.translate(c);p.rotate(now*12);p.setPen(Qt.PenStyle.NoPen)
        R=max(W,H)
        for i in range(16):
            col=_g(GOLD);col.setAlpha(int(34*self.champ));p.setBrush(col)
            p.drawPolygon(QPolygonF([QPointF(0,0),QPointF(R,-R*0.09),QPointF(R,R*0.09)]));p.rotate(360/16)
        p.restore()
    def _paint_vs(self,p,now):
        from echo_glass import liquid_surface
        c=QPointF(self.width()/2,self.height()/2+14)
        p.save();p.translate(c);p.setOpacity(max(0.,1-self.champ))
        k=1+(max(.85,min(1.25,self.vs_scale))-1)*.3
        p.scale(k,k)
        # Short light guides connect the candidates without a rotating badge.
        colors=[s.color for s in sorted([s for s in self.sprites if s.side is not None],key=lambda s:s.side)]
        for i in range(2):
            x1,x2=(-68,-48) if i==0 else (48,68)
            col=QColor(colors[min(i,len(colors)-1)]) if colors else _g(GOLD)
            edge=QLinearGradient(x1,0,x2,0)
            low=QColor(col);low.setAlpha(0)
            high=QColor(col);high.setAlpha(125)
            edge.setColorAt(0,low if i==0 else high);edge.setColorAt(1,high if i==0 else low)
            p.setPen(QPen(QBrush(edge),1));p.drawLine(QPointF(x1,0),QPointF(x2,0))
        dpr=self.devicePixelRatioF()
        if getattr(self,'_vs_dpr',None)!=dpr:
            self._vs_surface=liquid_surface(QSize(int(88*dpr),int(56*dpr)),radius=20*dpr)
            self._vs_surface.setDevicePixelRatio(dpr);self._vs_dpr=dpr
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0,0,0,95));p.drawRoundedRect(QRectF(-44,-24,88,56),20,20)
        p.drawPixmap(QPointF(-44,-28),self._vs_surface)
        p.setFont(_font(22,QFont.Weight.DemiBold))
        p.setPen(_g(GOLD))
        self._text(p,QRectF(-44,-28,88,56),Qt.AlignmentFlag.AlignCenter,'VS')
        p.restore()
    def _paint_empty(self,p,now):
        W,H=self.width(),self.height();cw,ch=self.card_size()
        for i,pos in enumerate((-1,1)):
            c=self.slot_center(pos);bob=math.sin(now*1.5+i*1.9)*6
            r=QRectF(c.x()-cw/2,c.y()-ch/2+bob,cw,ch)
            pen=QPen(QColor(255,255,255,50),2,Qt.PenStyle.DashLine);pen.setDashPattern([6,6]);pen.setDashOffset(now*12*(1 if i else -1))
            p.setPen(pen);p.setBrush(QColor(255,255,255,8));p.drawRoundedRect(r,24,24)
            p.setFont(_font(cw*0.42,QFont.Weight.Black));p.setPen(QColor(255,255,255,40));self._text(p,r,Qt.AlignmentFlag.AlignCenter,'?')
        r=self.start_rect();h=self.start_hover
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(4,0,-1):
            col=_g(GOLD);col.setAlpha(int((0.3+0.4*h+0.15*math.sin(now*3))*14*i/4));p.setBrush(col)
            p.drawRoundedRect(r.adjusted(-i*4,-i*4,i*4,i*4),27+i*4,27+i*4)
        g=QLinearGradient(r.topLeft(),r.topRight());g.setColorAt(0,_g(GOLD));g.setColorAt(1,_g(QColor(255,150,40)))
        p.setBrush(QBrush(g));p.drawRoundedRect(r,27,27)
        p.setFont(_font(17,QFont.Weight.Black));p.setPen(INK);self._text(p,r,Qt.AlignmentFlag.AlignCenter,'НАЧАТЬ ДУЭЛЬ')


class Leaders(QWidget):
    """Таблица лидеров по победам: полоски плавно дорастают до новых значений. Клик по строке — слушать трек,
    «Слушать топ» — все лидеры подряд."""
    play=pyqtSignal(int);play_all=pyqtSignal()
    def __init__(self):
        super().__init__();self.rows=[];self.shown={};self.timer=QTimer(self);self.timer.timeout.connect(self._tick)
        self.setFixedHeight(0);self.setMouseTracking(True);self.hover=-2
    def _row_at(self,pt):
        x,y=pt.x()-14,pt.y()-4
        if 4<=y<=32 and self._all_rect().contains(pt):return -1
        i=int((y-40)//34)
        return i if 0<=i<len(self.rows) and y>=40 else -2
    def _all_rect(self):
        return QRectF(self.width()-14-150,8,150,28)
    def mouseMoveEvent(self,e):
        h=self._row_at(e.position())
        if h!=self.hover:
            self.hover=h;self.setCursor(Qt.CursorShape.PointingHandCursor if h!=-2 else Qt.CursorShape.ArrowCursor);self.update()
    def leaveEvent(self,e):
        self.hover=-2;self.update();super().leaveEvent(e)
    def mouseReleaseEvent(self,e):
        if e.button()!=Qt.MouseButton.LeftButton:return
        h=self._row_at(e.position())
        if h==-1:self.play_all.emit()
        elif h>=0:self.play.emit(h)
    def set_rows(self,rows):
        self.rows=rows[:5];self.setFixedHeight(0 if not self.rows else 52+34*len(self.rows))
        if self.isVisible():self.timer.start(16)
    def showEvent(self,e):
        super().showEvent(e)
        if self.rows:self.timer.start(16)
    def hideEvent(self,e):
        self.timer.stop();super().hideEvent(e)
    def _tick(self):
        top=max([w for _,w in self.rows] or [1]);moving=False
        for t,w in self.rows:
            k=identity(t);cur=self.shown.get(k,0.0);want=w/top
            cur+=(want-cur)*0.18;self.shown[k]=cur;moving|=abs(want-cur)>0.002
        self.update()
        if not moving:self.timer.stop()
    def paintEvent(self,e):
        if not self.rows:return
        p=QPainter(self);p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.TextAntialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(22,21,28));p.drawRoundedRect(QRectF(self.rect()),18,18)
        p.translate(14,4);W=self.width()-28
        p.setFont(_font(16,QFont.Weight.ExtraBold));p.setPen(QColor(240,240,246));p.drawText(QRectF(4,4,W,28),Qt.AlignmentFlag.AlignVCenter,'Лидеры по победам')
        ar=self._all_rect().translated(-14,-4)                       # «▶ Слушать топ»
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(_g(GOLD) if self.hover==-1 else QColor(255,255,255,26));p.drawRoundedRect(ar,14,14)
        p.setFont(_font(12,QFont.Weight.Black));p.setPen(INK if self.hover==-1 else QColor(240,240,246))
        p.drawText(ar,Qt.AlignmentFlag.AlignCenter,'▶  Слушать топ')
        medals=[_g(GOLD),_g(QColor(200,205,215)),_g(QColor(214,140,80))]
        for i,(t,w) in enumerate(self.rows):
            y=40+i*34;val=self.shown.get(identity(t),0.0)
            if self.hover==i:
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(255,255,255,16));p.drawRoundedRect(QRectF(-6,y-1,W+12,32),10,10)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(medals[i] if i<3 else QColor(255,255,255,40));p.drawEllipse(QRectF(4,y+4,22,22))
            p.setFont(_font(11,QFont.Weight.Black));p.setPen(INK if i<3 else QColor(230,230,236))
            p.drawText(QRectF(4,y+4,22,22),Qt.AlignmentFlag.AlignCenter,'▶' if self.hover==i else str(i+1))
            name=str(t.get('title') or '')+('  ·  '+str(t.get('artist')) if t.get('artist') else '')
            tw=min(340,W*0.42)
            p.setFont(_font(13,QFont.Weight.DemiBold));p.setPen(QColor(225,225,232))
            p.drawText(QRectF(36,y,tw,30),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(p.font()).elidedText(name,Qt.TextElideMode.ElideRight,int(tw)))
            bx=36+tw+14;bw=max(40,W-bx-60);br=QRectF(bx,y+10,bw,10)
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(255,255,255,18));p.drawRoundedRect(br,5,5)
            g=QLinearGradient(br.topLeft(),br.topRight());g.setColorAt(0,_g("#a78b24"));g.setColorAt(1,_g(GOLD))
            p.setBrush(QBrush(g));p.drawRoundedRect(QRectF(bx,y+10,max(10,bw*val),10),5,5)
            p.setFont(_font(13,QFont.Weight.Black));p.setPen(QColor(240,240,246))
            p.drawText(QRectF(bx+bw+8,y,50,30),Qt.AlignmentFlag.AlignVCenter,str(w))
        p.end()


class DuelSurface(QWidget):
    """One continuous arena background behind every control on the page."""
    def __init__(self, duel):
        super().__init__()
        self.duel = duel

    def paintEvent(self, event):
        arena = getattr(self.duel, 'arena', None)
        if arena is not None:
            p = QPainter(self)
            p.drawPixmap(0, 0, arena._background(self.size()))
            p.end()


class DuelPage(QScrollArea):
    def __init__(self,shell):
        super().__init__();self.shell=shell;self.win=shell.win;self.game=Duel();self.online=[];self.request=0;self.busy=False
        self._pv=None
        self._preview_request=None;self._chorus=None
        self._pending_start=None;self._save_error=''
        self.setWidgetResizable(True);self.setFrameShape(QFrame.Shape.NoFrame)
        page=DuelSurface(self);self.setWidget(page)
        lay=QVBoxLayout(page);lay.setContentsMargins(30,20,30,20);lay.setSpacing(12)
        top=QHBoxLayout();col=QVBoxLayout();col.setSpacing(2)
        title=QLabel('Echoes Duel');title.setObjectName('YaH1');col.addWidget(title)
        subtitle=QLabel('Два трека. Один выбор. Найдите своего чемпиона или просто доверьтесь ощущениям.')
        subtitle.setObjectName('YaSub');subtitle.setWordWrap(True);col.addWidget(subtitle)
        top.addLayout(col,1)
        from yamusic_theme import chip
        self.mode_btns={}
        for key,text in (('king','Царь горы'),('pairs','Бесконечные дуэли')):
            b=chip(text);b.clicked.connect(lambda _=False,k=key:self._set_mode(k));top.addWidget(b,0,Qt.AlignmentFlag.AlignVCenter);self.mode_btns[key]=b
        self.start=QPushButton('Начать заново');self.start.setCursor(Qt.CursorShape.PointingHandCursor)
        import ya_skin                                                   # акцент темы, а не всегда жёлтый
        _a,_on=ya_skin.CURRENT.get('accent','#ffdb1a'),ya_skin.CURRENT.get('on_accent','#000000')
        self.start.setStyleSheet(f'QPushButton{{background:{_a};color:{_on};border-radius:16px;padding:9px 18px;font-weight:800;}}'
                                 f' QPushButton:hover{{background:{ya_skin.lighter(_a,115)};}}')
        self.start.clicked.connect(self.begin);top.addWidget(self.start,0,Qt.AlignmentFlag.AlignVCenter);lay.addLayout(top)
        from duel_settings import tr
        self.settings_button=QPushButton(tr(self.win,'Настройки дуэли','Duel settings'))
        from yamusic_theme import ya_icon
        self.settings_button.setIcon(ya_icon('settings',18));self.settings_button.clicked.connect(self.open_settings)
        top.insertWidget(top.count()-1,self.settings_button,0,Qt.AlignmentFlag.AlignVCenter)
        self.net_row=QWidget();net=QHBoxLayout(self.net_row);net.setContentsMargins(0,0,0,0)
        self.internet=QCheckBox('Добавить треки из интернета');net.addWidget(self.internet)
        self.query=QLineEdit();self.query.setPlaceholderText('Жанр / настроение (пусто — случайное направление)');net.addWidget(self.query,1)
        self.internet.toggled.connect(self._cancel_pending_start);self.query.textEdited.connect(self._cancel_pending_start)
        self.load=QPushButton('Найти случайных соперников');self.load.clicked.connect(self.fetch);net.addWidget(self.load);lay.addWidget(self.net_row)
        self.status=QLabel('Выберите режим и начните. Турнир сохраняется после каждого выбора.');self.status.setObjectName('YaSub');self.status.setWordWrap(True);lay.addWidget(self.status)
        self.arena=Arena(self);lay.addWidget(self.arena,1)
        self.arena.voted.connect(self.vote);self.arena.preview.connect(self.preview);self.arena.start_clicked.connect(self.begin)
        row=QHBoxLayout();self.back=QPushButton('Отменить последний выбор');self.back.clicked.connect(self.undo);row.addWidget(self.back)
        self.skip=QPushButton('Другая пара');self.skip.clicked.connect(self.skip_pair);row.addWidget(self.skip)
        stop=QPushButton('Пауза');stop.clicked.connect(lambda:(self.win.engine.pause_hard(),self.win._set_playing_ui(False)));row.addWidget(stop)
        row.addStretch();lay.addLayout(row)
        self.leaders=Leaders();lay.addWidget(self.leaders)
        self.leaders.play.connect(lambda i:self.play_leaders(i,False));self.leaders.play_all.connect(lambda:self.play_leaders(0,True))
        mode='king'
        if self.game.restore(self.win.settings.get('duel_session')):mode=self.game.mode
        self._mode=mode;self.controls()
        cur=self.game.current()
        if cur:self.arena.set_pair(cur,'none')
        self.render()
        self.destroyed.connect(lambda:setattr(self,'request',-1))
    def _set_mode(self,key):
        if key!=self._mode:self._cancel_pending_start()
        self._mode=key;self.controls()
    def _cancel_pending_start(self,*_):
        self._pending_start=None
    def controls(self):
        for k,b in self.mode_btns.items():b.setChecked(k==self._mode)
        pair=self._mode=='pairs';self.net_row.setVisible(pair);self.load.setEnabled(pair and not self.busy)
        if not pair:self.internet.setChecked(False)
    def save(self):
        self.win.settings['duel_session']=self.game.dump()
        try:
            self.win.save_settings();self._save_error=''
        except (OSError,TypeError,ValueError):
            from duel_settings import tr
            self._save_error=tr(self.win,'Не удалось сохранить турнир. Игра продолжается; проверьте данные и доступ к папке сохранений.',
                               'Could not save the tournament. Play can continue; check the data and access to the save folder.')
    def open_settings(self):
        from duel_settings import open_settings
        open_settings(self)
    def options_changed(self):
        self._cancel_pending_start()
        self._preview_request=None
        from duel_settings import options
        self.arena.fire_enabled=options(self.win.settings)['fire'];self.arena.update();self._prepare_pair()
    def _prepare_pair(self):
        from duel_settings import options
        if not self.isVisible() or not self.game.current() or not options(self.win.settings)['chorus']:return
        from performance import config
        if not config(self.win.settings)['chorus_prefetch'] and self._preview_request is None:return
        if self._chorus is None:
            from duel_chorus import ChorusAnalyzer
            self._chorus=ChorusAnalyzer(self);self._chorus.ready.connect(self._chorus_ready)
        self._chorus.prepare(self.game.current()[:2])
    def _chorus_ready(self,key,result):
        request=self._preview_request
        if request is None:return
        from duel_chorus import stamp
        side,track,token=request
        current=self.game.current()
        if key!=stamp(track):return
        self._preview_request=None
        if not self.isVisible() or token!=getattr(self.win,'_stream_token',0) or side>=len(current) or identity(current[side])!=identity(track):return
        self._start_preview(track,result[0])
    def _start_preview(self,track,start=0):
        import stream_core
        item=track if track.get('path') else stream_core.make_track(track)
        self.win._duel_preview=identity(item);self._pv=(identity(track),identity(item))
        self.win.stream_tracks([item],playlist='⁣Echoes Duel',start_sec=start)
        self.arena._wake()
    def begin(self):
        self._preview_request=None
        tracks=[]
        for t in self.win.library:
            if not isinstance(t,dict) or not t.get('path') or not identity(t) or identity(t).startswith('stream:'):continue
            try:
                if Path(t['path']).is_file():tracks.append(t)
            except (OSError,ValueError,TypeError):continue
        if self._mode=='pairs' and self.internet.isChecked():
            if not self.online:
                if self.busy:self._arm_start(self.request)
                else:self.fetch(start_after=True)
                return
            tracks+=self.online
        self._cancel_pending_start()
        from duel_settings import options, filter_tracks, liked_paths
        tracks=filter_tracks(tracks,options(self.win.settings),playlists=self.win.playlists,liked=liked_paths(self.win),profiles=getattr(self.shell,'_profiles',None))
        try:
            self.game.start(tracks,self._mode);self.save();self.arena.set_pair(self.game.current(),'enter');self.render()
        except ValueError as e:
            self.status.setText(str(e))
            toast=getattr(self.win,'_toast',None)
            if callable(toast):toast(str(e))
    def _arm_start(self,request):
        from duel_settings import options
        self._pending_start=(request,self._mode,self.query.text().strip(),options(self.win.settings))
    def fetch(self,_=False,start_after=False):
        if self.busy:return
        self.busy=True;self.controls();self.request+=1;req=self.request
        if start_after:self._arm_start(req)
        query=self.query.text().strip() or random.choice(['dream pop','jazz fusion','ambient electronica','neo soul','indie rock','liquid drum and bass','synthwave','trip hop','afrobeat','city pop'])
        self.status.setText('Ищу соперников: '+query+'…')
        def work():
            try:
                import online_search
                result=online_search.search(query,'all')
            except Exception as exc:result={'tracks':[],'errors':[str(exc)]}
            try:self.win._ui_bridge.call.emit(lambda:self.received(req,result,start_after))
            except (RuntimeError,AttributeError):pass
        threading.Thread(target=work,daemon=True,name='duel-search').start()
    def received(self,req,result,start_after):
        from PyQt6 import sip
        if sip.isdeleted(self):return
        if req!=self.request:return
        self.busy=False;self.controls()
        result=result if isinstance(result,dict) else {}
        raw=result.get('tracks',[]);raw=raw if isinstance(raw,list) else []
        tracks=[t for t in raw if isinstance(t,dict) and isinstance(t.get('url'),str) and t['url']];random.shuffle(tracks);self.online=tracks[:120]
        errors=result.get('errors',[]);errors=errors if isinstance(errors,list) else []
        self.status.setText(f'Найдено {len(self.online)} онлайн-соперников. Случайный выбор из результатов поиска; это не весь каталог сервиса.' if tracks else 'Поиск не дал треков. '+('; '.join(map(str,errors)))[:300])
        from duel_settings import options
        intent=(req,self._mode,self.query.text().strip(),options(self.win.settings))
        start=tracks and self._pending_start==intent and self._mode=='pairs' and self.internet.isChecked() and self.isVisible()
        self._cancel_pending_start()
        if start:self.begin()
    def preview(self,side):
        current=self.game.current()
        if side not in (0,1) or side>=len(current):return
        track=current[side]
        if self._preview_request and identity(self._preview_request[1])==identity(track):
            self._preview_request=None;return
        self._preview_request=None
        if self.preview_side()==side:                             # повторный клик — пауза
            self.win.engine.pause_hard();self.win._set_playing_ui(False);return
        from duel_settings import options, tr
        if options(self.win.settings)['chorus']:
            if self._chorus is None:
                from duel_chorus import ChorusAnalyzer
                self._chorus=ChorusAnalyzer(self);self._chorus.ready.connect(self._chorus_ready)
            result=self._chorus.value(track)
            if result is None:
                self._preview_request=(side,dict(track),getattr(self.win,'_stream_token',0));self._chorus.prepare([track]);self.status.setText(tr(self.win,'Определяю припев в фоне…','Finding the chorus in the background…'));return
            self._start_preview(track,result[0])
        else:self._start_preview(track)
    def play_leaders(self,i,all_):
        """Слушать трек из «Лидеров по победам» (или весь топ подряд)."""
        self._preview_request=None
        rows=[t for t,_w in self.leaders.rows]
        if not rows:return
        import stream_core
        items=[t if t.get('path') else stream_core.make_track(t) for t in (rows if all_ else rows[i:i+1])]
        self._pv=None;self.win._duel_preview=None
        self.win.stream_tracks(items,playlist='⁣Топ дуэли')
    def preview_side(self):
        """Какая карточка сейчас звучит (0 / 1) или None."""
        if not self._pv or getattr(self.win,'_duel_preview',None)!=self._pv[1]:return None
        try:
            if not self.win.engine.is_playing():return None
        except Exception:return None                               # noqa: BLE001
        for i,t in enumerate(self.game.current()):
            if identity(t)==self._pv[0]:return i
        return None
    def vote(self,side):
        self._preview_request=None
        current=self.game.current()
        if len(current)!=2:return
        self._cancel_pending_start()
        try:self.game.vote(side)
        except ValueError as e:self.status.setText(str(e));return
        self.save();new=self.game.current()
        self.arena.animate_vote(side,new,len(new)==1,self.game.mode=='king');self.render()
    def undo(self):
        self._preview_request=None
        if not self.game.history:return
        self._cancel_pending_start()
        self.game.undo();self.save();self.arena.set_pair(self.game.current(),'drop');self.render()
    def skip_pair(self):
        self._preview_request=None
        if self.game.mode!='pairs' or not self.game.current():return
        self._cancel_pending_start()
        self.game.next_pair();self.save();self.arena.set_pair(self.game.current(),'swipe');self.render()
    def render(self):
        current=self.game.current();finished=len(current)==1;g=self.game
        self.back.setEnabled(bool(g.history));self.skip.setEnabled(g.mode=='pairs' and bool(current));self.skip.setVisible(g.mode=='pairs')
        a=self.arena;a.king=g.mode=='king';a.streak=g.streak()
        if current:
            if g.mode=='king':
                total=max(1,len(g.roster)-1);a.progress=min(1.0,(g.cursor-1)/total)
                a.round_text='' if finished else f'Раунд {g.cursor} из {total}'
                self.status.setText(('Ваш чемпион: '+str(current[0].get('title') or '')+' — нажмите «Начать заново», чтобы сыграть ещё') if finished else 'Победитель остаётся на ринге. Турнир сохраняется после каждого выбора.')
            else:
                a.progress=0.0;a.round_text=f'Выборов сделано: {len(g.history)}'
                self.status.setText('Каждая пара — новая история. Лидеры копятся ниже.')
        wins=g.wins()
        from duel_settings import options
        a.wins_by_id={identity(g.roster[i]):count for i,count in wins.items() if 0<=i<len(g.roster)}
        a.fire_enabled=options(self.win.settings)['fire']
        rows=sorted(((g.roster[i],w) for i,w in wins.items() if 0<=i<len(g.roster)),key=lambda x:-x[1])
        self.leaders.set_rows(rows if len(g.history)>=2 else [])
        self.widget().update()
        a._wake()
        self._prepare_pair()
        if self._save_error:self.status.setText(self.status.text()+'\n'+self._save_error)
    def hideEvent(self,event):
        self._cancel_pending_start()
        self._preview_request=None
        if self._chorus is not None:self._chorus.prepare([])
        self.win._duel_preview=None
        super().hideEvent(event)
    def showEvent(self,event):
        super().showEvent(event);self._prepare_pair()
