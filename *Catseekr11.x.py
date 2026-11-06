#!/usr/bin/env python3
"""CatSeek R1 0.1 — single-file Tkinter app, standard library only.
Real language generation requires an independently installed compatible BitNet CLI and weights.
"""
import ast, json, math, operator, os, pathlib, queue, re, shutil, subprocess, sys, threading, time, tkinter as tk
from tkinter import scrolledtext

NAME='CatSeek R1 0.1'
HOME=pathlib.Path.home()/'CatSeekBitNet'
OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.FloorDiv:operator.floordiv,ast.Mod:operator.mod,ast.Pow:operator.pow}

def calculate(s):
    if len(s)>140: raise ValueError('Expression too long')
    def walk(n,depth=0):
        if depth>24: raise ValueError('Expression too deep')
        if isinstance(n,ast.Expression):return walk(n.body,depth+1)
        if isinstance(n,ast.Constant) and type(n.value) in (int,float) and abs(n.value)<1e12:return n.value
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
            v=walk(n.operand,depth+1);return v if isinstance(n.op,ast.UAdd) else -v
        if isinstance(n,ast.BinOp) and type(n.op) in OPS:
            a,b=walk(n.left,depth+1),walk(n.right,depth+1)
            if isinstance(n.op,ast.Pow) and (abs(b)>10 or abs(a)>1e6):raise ValueError('Exponent too large')
            v=OPS[type(n.op)](a,b)
            if not math.isfinite(v) or abs(v)>1e15:raise ValueError('Result too large')
            return v
        raise ValueError('Unsupported arithmetic')
    return walk(ast.parse(s,mode='eval'))

def detect():
    binaries=[os.getenv('CATSEEK_BITNET_BIN',''),str(HOME/'BitNet/build/bin/llama-cli'),str(HOME/'BitNet/build/bin/bitnet-cli'),str(HOME/'BitNet/build/bin/Release/llama-cli')]
    binary=next((pathlib.Path(x) for x in binaries if x and pathlib.Path(x).is_file() and os.access(x,os.X_OK)),None)
    models=[os.getenv('CATSEEK_BITNET_MODEL',''),str(HOME/'models/CatSeek-R1-1B/ggml-model-i2_s.gguf')]
    if (HOME/'models').exists():models += [str(p) for p in (HOME/'models').rglob('*.gguf')]
    model=next((pathlib.Path(x) for x in models if x and pathlib.Path(x).is_file() and pathlib.Path(x).stat().st_size>1024*1024),None)
    return binary,model

class Engine:
    def __init__(self):self.history=[]
    def reply(self,prompt):
        s=prompt.strip(); low=s.lower(); start=time.monotonic()
        if low in ('/clear','/new'):
            self.history.clear();return 'Conversation cleared.','local'
        if low in ('/help','help'):
            return 'Commands: /help, /status, /clear, /math 2+3*4, /python, /game. For open-ended AI chat, connect a real compatible BitNet model and CLI.','local'
        if low in ('/status','/model'):
            b,m=detect();return json.dumps({'app':NAME,'backend':'native BitNet CLI only','cli':str(b) if b else None,'model':str(m) if m else None,'pretrained_inference_ready':bool(b and m),'note':'A model filename is not proof of BitNet architecture or parameter count.'},indent=2),'status'
        expression=re.sub(r'^(?:/math|calculate|compute|what is|what\'s)\s+','',s,flags=re.I).strip(' ?')
        if re.fullmatch(r'[0-9.\s+*/%()\-]+',expression) and any(x.isdigit() for x in expression):
            try:return str(calculate(expression)),'exact-math'
            except Exception as e:return 'Math error: '+str(e),'math-error'
        if low=='/python':return 'Python example:\n\ndef greet(name: str) -> str:\n    return f"Hello, {name}!"\n\nprint(greet("CatSeek"))','local-template'
        if low=='/game':return 'Minimal tkinter game loop:\n\nimport tkinter as tk\nr=tk.Tk(); c=tk.Canvas(r,width=400,height=300,bg="black");c.pack()\nx=0\ndef tick():\n    global x\n    c.delete("all");c.create_oval(x,120,x+30,150,fill="cyan")\n    x=(x+3)%400;r.after(16,tick)\ntick();r.mainloop()','local-template'
        binary,model=detect()
        if not binary or not model:
            missing=('native CLI' if not binary else '')+(' and ' if not binary and not model else '')+('pretrained GGUF checkpoint' if not model else '')
            return ('Real BitNet inference unavailable: missing '+missing+'.\n\n'
                    'This standalone Python app works for arithmetic and built-in code examples, but cannot invent pretrained neural-network weights. '
                    'Place a verified BitNet-compatible model in ~/CatSeekBitNet/models and build a compatible native CLI; /status shows detection. '
                    'No conventional model or fake AI responses are substituted.'),'bitnet-unavailable'
        context='\n'.join(f'User: {u}\nAssistant: {a}' for u,a in self.history[-4:])
        full=(context+'\n' if context else '')+'User: '+s+'\nAssistant:'
        args=[str(binary),'-m',str(model),'-p',full,'-n','384','-c','2048','--temp','0.7']
        try:
            proc=subprocess.run(args,text=True,capture_output=True,timeout=180)
        except (OSError,subprocess.TimeoutExpired) as e:return 'Native BitNet invocation failed: '+str(e),'native-error'
        if proc.returncode:return 'Native BitNet exited with error:\n'+(proc.stderr or proc.stdout)[-2200:],'native-error'
        out=proc.stdout.strip()
        if not out:return 'Native CLI returned no generated text.','native-error'
        self.history.append((s,out));self.history=self.history[-8:]
        return out,'native-bitnet'

class GUI:
    def __init__(self,root):
        self.root=root;self.engine=Engine();self.q=queue.Queue();self.busy=False;self.generation=0
        root.title(NAME);root.geometry('980x680');root.minsize(700,480);root.configure(bg='#080d17')
        head=tk.Frame(root,bg='#101c30',padx=18,pady=16);head.pack(fill='x')
        tk.Label(head,text='🐱  CATSEEK R1',bg='#101c30',fg='#8fc7ff',font=('Helvetica',20,'bold')).pack(side='left')
        self.status=tk.Label(head,text='BitNet-only · checking...',bg='#101c30',fg='#a9bed8');self.status.pack(side='right')
        body=tk.Frame(root,bg='#080d17');body.pack(fill='both',expand=True)
        side=tk.Frame(body,bg='#101c30',width=180,padx=12,pady=16);side.pack(side='left',fill='y');side.pack_propagate(False)
        for label,cmd in [('New chat',self.new),('Model status',lambda:self.submit('/status')),('Math demo',lambda:self.submit('/math (12+8)*3')),('Python demo',lambda:self.submit('/python')),('Game demo',lambda:self.submit('/game'))]:
            tk.Button(side,text=label,command=cmd,bg='#192d49',fg='#dceaff',activebackground='#284a72',activeforeground='white',relief='flat',pady=9).pack(fill='x',pady=5)
        main=tk.Frame(body,bg='#080d17');main.pack(side='left',fill='both',expand=True)
        self.chat=scrolledtext.ScrolledText(main,bg='#080d17',fg='#e0edff',insertbackground='white',wrap='word',font=('Menlo',11),relief='flat',padx=18,pady=16,state='disabled');self.chat.pack(fill='both',expand=True)
        bar=tk.Frame(main,bg='#101c30',padx=12,pady=12);bar.pack(fill='x')
        self.input=tk.Text(bar,height=3,bg='#17283f',fg='#f4f8ff',insertbackground='white',font=('Helvetica',12),relief='flat',wrap='word',padx=10,pady=8);self.input.pack(side='left',fill='x',expand=True)
        self.input.bind('<Return>',self.enter)
        self.send=tk.Button(bar,text='SEND ↑',command=self.submit,bg='#2c6bba',fg='white',relief='flat',padx=14,pady=12);self.send.pack(side='right',padx=(10,0))
        self.append('CATSEEK R1 · Single-file edition\nType /help for commands. Real model generation requires a compatible native BitNet runtime and trained checkpoint.\n\n')
        self.refresh();self.root.after(50,self.poll);self.input.focus_set()
    def append(self,s):
        self.chat.configure(state='normal');self.chat.insert('end',s);self.chat.configure(state='disabled');self.chat.see('end')
    def refresh(self):
        b,m=detect();self.status.configure(text='BitNet ready (unverified)' if b and m else 'Local tools ready · BitNet missing')
    def enter(self,event):
        if event.state & 0x1:return None
        self.submit();return 'break'
    def new(self):
        self.generation+=1;self.engine.history.clear();self.chat.configure(state='normal');self.chat.delete('1.0','end');self.chat.configure(state='disabled');self.append('New CatSeek chat\n\n')
    def submit(self,forced=None):
        if self.busy:return
        prompt=forced if isinstance(forced,str) else self.input.get('1.0','end-1c').strip()
        if not prompt:return
        self.input.delete('1.0','end');self.append('YOU\n'+prompt+'\n\nCATSEEK\n');self.busy=True;self.send.configure(state='disabled');gen=self.generation
        def work():
            try:self.q.put((gen,*self.engine.reply(prompt)))
            except Exception as e:self.q.put((gen,'Error: '+str(e),'error'))
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        try:
            while True:
                gen,answer,route=self.q.get_nowait()
                if gen==self.generation:self.append(answer+'\n\n['+route+']\n\n')
                self.busy=False;self.send.configure(state='normal');self.refresh()
        except queue.Empty:pass
        self.root.after(50,self.poll)

def main():
    if '--self-test' in sys.argv:
        assert calculate('2+3*4')==14
        assert calculate('(12+8)*3')==60
        assert 'BitNet' in Engine().reply('/status')[0]
        print('PASS: math, status, standard-library engine');return
    if '--prompt' in sys.argv:
        i=sys.argv.index('--prompt');print(Engine().reply(' '.join(sys.argv[i+1:]))[0]);return
    root=tk.Tk();GUI(root);root.mainloop()
if __name__=='__main__':main()
