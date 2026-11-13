"""Cabinet-sized launcher: 320x240 base, integer-sized fonts, keyboard/yoke access."""
import json
import os
import secrets
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from . import __version__
from .bridge import Bridge
from .storage import ROOT, load_config, save_json, install_package
from .roms import import_rom
from .inputs import Navigation

ASSETS=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
ORANGE='#ff7900';BG='#101010';FG='#f4f4f4'

class CabinetApp:
    def __init__(self, root):
        self.root=root
        self.config=load_config(Path(sys.executable).parent if getattr(sys,'frozen',False) else ASSETS)
        self.bridge=None;self.process=None;self.process_log=None;self.started=0
        self.page='games';self.scale=1;self.selected=0;self.monitor_page=0
        self.games=json.loads((ASSETS/'games.json').read_text())
        self.nav=Navigation()
        self.root.title('Open Motion: G-LOC')
        self.root.configure(bg=BG)
        self.root.geometry('640x480');self.root.minsize(320,240)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.body=tk.Frame(root,bg=BG);self.body.pack(fill='both',expand=True)
        self.root.bind('<Configure>',self.resize)
        self.root.bind('<Up>',lambda e:self.navigate(-1))
        self.root.bind('<Down>',lambda e:self.navigate(1))
        self.root.bind('<Escape>',lambda e:self.back())
        self.root.bind('<Return>',lambda e:self.activate())
        self.root.bind('<F6>',lambda e:self.show_monitor())
        self.root.bind('<F2>',lambda e:self.setup())
        self.root.bind('<Control-i>',lambda e:self.import_selected())
        self.draw_games()
        self.root.after(100,self.tick)

    def resize(self,event):
        if event.widget is not self.root:return
        scale=min(event.width/320,event.height/240)
        if abs(scale-self.scale)>0.05:
            self.scale=scale
            if self.page=='games':self.draw_games()
            elif self.page=='setup':self.setup()
            elif self.page=='monitor':self.show_monitor()

    def clear(self,title):
        for child in self.body.winfo_children():child.destroy()
        self.label(title,20,ORANGE).pack(anchor='w',padx=self.px(10),pady=(self.px(6),0))
        self.items=[]

    def px(self,n):return max(1,round(n*self.scale))
    def label(self,text,size=14,colour=FG):
        return tk.Label(self.body,text=text,font=('Arial',-self.px(size),'bold'),fg=colour,bg=BG,anchor='w')
    def button(self,text,command,parent=None):
        b=tk.Button(parent or self.body,text=text,command=command,takefocus=True,
                    font=('Arial',-self.px(14),'bold'),bg='#252525',fg=FG,activebackground=ORANGE,
                    activeforeground=BG,relief='flat',highlightthickness=1,highlightcolor=ORANGE,pady=self.px(3))
        self.items.append(b)
        return b

    def draw_games(self):
        self.page='games';self.clear('OPEN MOTION: G-LOC')
        self.list=tk.Listbox(self.body,bg=BG,fg=FG,selectbackground=ORANGE,selectforeground=BG,
                             font=('Arial',-self.px(18),'bold'),height=4,bd=0,activestyle='none',exportselection=False)
        for g in self.games:self.list.insert('end',g['label'])
        self.list.pack(fill='both',expand=True,padx=self.px(10),pady=self.px(4))
        self.list.selection_set(self.selected);self.list.see(self.selected)
        self.list.bind('<<ListboxSelect>>',self.select)
        self.list.bind('<Double-1>',lambda e:self.launch())
        self.info=self.label(self.game()['version']+' | Motion off',12,'#bbbbbb')
        self.info.pack(fill='x',padx=self.px(10))
        row=tk.Frame(self.body,bg=BG);row.pack(fill='x',padx=self.px(6),pady=self.px(5))
        for title,fn in [('Play',self.launch),('Import',self.import_selected),('Setup',self.setup)]:
            self.button(title,fn,row).pack(side='left',fill='x',expand=True,padx=self.px(3))
        self.list.focus_set()

    def game(self):return self.games[self.selected]
    def select(self,event=None):
        if self.list.curselection():self.selected=self.list.curselection()[0]
        self.info.config(text=self.game()['version']+' | Motion off')
    def navigate(self,delta):
        if self.page=='games':
            self.selected=(self.selected+delta)%len(self.games)
            self.list.selection_clear(0,'end');self.list.selection_set(self.selected);self.list.see(self.selected);self.select()
        else:
            focus=self.root.focus_get()
            if self.items:
                index=self.items.index(focus) if focus in self.items else -1
                self.items[(index+delta)%len(self.items)].focus_set()
        return 'break'
    def activate(self):
        focused=self.root.focus_get()
        if isinstance(focused,tk.Button):focused.invoke()
        elif self.page=='games':self.launch()
        return 'break'
    def back(self):
        if self.page!='games':self.draw_games()
        elif self.process and self.process.poll() is None:self.stop_game()
        else:self.close()
        return 'break'

    def setup(self):
        self.page='setup';self.clear('CABINET SETUP')
        for label,fn in [('Emulator package',self.choose_emulator),('ROM folder',self.choose_rompath),
                         ('Controller: '+(self.config['port'] or 'Not set'),self.choose_port),
                         ('Full screen: '+('On' if self.config['fullscreen'] else 'Off'),self.toggle_fullscreen),
                         ('Install update ZIP',self.install_update),('About / help',self.about),('Back',self.draw_games)]:
            self.button(label,fn).pack(fill='x',padx=self.px(10),pady=self.px(1))
        self.items[0].focus_set()

    def choose_rompath(self):
        path=filedialog.askdirectory(title='Choose ROM folder',initialdir=self.config['rompath'])
        if path:self.config['rompath']=path;self.save()
    def choose_emulator(self):
        packages=list((ROOT/'packages'/'emulator').glob('*/*/manifest.json'))
        if not packages:
            messagebox.showinfo('Install game support','Install the Open Motion emulator update ZIP first.');return
        win=tk.Toplevel(self.root);win.title('Choose emulator version');win.geometry('320x240');win.configure(bg=BG)
        box=tk.Listbox(win,font=('Arial',-18),bg=BG,fg=FG,selectbackground=ORANGE)
        for p in packages:
            m=json.loads(p.read_text());box.insert('end',m['id']+' '+m['version'])
        box.pack(fill='both',expand=True);box.selection_set(0)
        def choose(event=None):
            if not box.curselection():return
            manifest=packages[box.curselection()[0]]
            self.config['emulator']=str(manifest.parent);self.save();win.destroy()
        box.bind('<Return>',choose);box.bind('<Double-1>',choose)
        tk.Button(win,text='Use this version',command=choose,font=('Arial',-18)).pack(fill='x');box.focus_set()

    def choose_port(self):
        try:
            from serial.tools import list_ports
            ports=list(list_ports.comports())
        except ImportError:ports=[]
        win=tk.Toplevel(self.root);win.title('Controller port');win.geometry('320x240');win.configure(bg=BG)
        tk.Label(win,text='Controller at 115200 baud',font=('Arial',-18),bg=BG,fg=FG).pack()
        box=tk.Listbox(win,font=('Arial',-16),bg=BG,fg=FG,selectbackground=ORANGE)
        for p in ports:box.insert('end',f'{p.device}  {p.description[:23]}')
        box.pack(fill='both',expand=True)
        entry=tk.Entry(win,font=('Arial',-18));entry.insert(0,self.config['port']);entry.pack(fill='x')
        def select(event=None):
            if box.curselection():entry.delete(0,'end');entry.insert(0,ports[box.curselection()[0]].device)
        box.bind('<<ListboxSelect>>',select)
        def save(event=None):self.config['port']=entry.get().strip();self.save();win.destroy();self.setup()
        entry.bind('<Return>',save)
        tk.Button(win,text='Save',command=save,font=('Arial',-18)).pack(fill='x')
    def toggle_fullscreen(self):
        self.config['fullscreen']=not self.config['fullscreen'];self.save();self.setup()
    def save(self):save_json(ROOT/'cabinet.json',self.config)

    def install_update(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('Game running','Exit the game before installing an update.');return
        file=filedialog.askopenfilename(title='Install Open Motion update',filetypes=[('Update ZIP','*.zip')])
        if not file:return
        try:
            path,manifest=install_package(file)
            if manifest['kind']=='emulator' and not self.config['emulator']:
                self.config['emulator']=str(path);self.save()
            messagebox.showinfo('Update installed',f"{manifest['id']} {manifest['version']} installed.\nEarlier versions and cabinet settings retained.")
        except Exception as e:messagebox.showerror('Update not installed',str(e))

    def recipe(self):
        name=self.game()['recipe']
        if not name:return None
        # Recipe packages can be installed independently. Their driver API is
        # checked before use; a new incompatible package cannot become active.
        candidates=list((ROOT/'packages'/'rom_patch').glob('*/*/manifest.json'))
        candidates.sort(key=lambda p:p.stat().st_mtime,reverse=True)
        for p in candidates:
            manifest=json.loads(p.read_text())
            recipe=p.parent/'payload'/name
            if manifest.get('requires',{}).get('driver_api')=='openmotion-0276-v1' and recipe.is_file():return recipe
        return ASSETS/'rom-patches'/name

    def import_selected(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('Game running','Exit the game before importing ROMs.');return
        file=filedialog.askopenfilename(title='Import complete '+self.game()['label']+' ROM ZIP',filetypes=[('ROM ZIP','*.zip')])
        if not file:return
        try:
            target=Path(self.config['rompath'])/(self.game()['set']+'.zip')
            import_rom(file,target,self.recipe())
            messagebox.showinfo('ROM imported','ROM installed. Original ZIP preserved.\nPlay starts with motion disabled.')
        except Exception as e:messagebox.showerror('ROM not imported',str(e))

    def launch(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('Game running','Exit the current game first.');return
        try:
            package=Path(self.config['emulator'])
            manifest=json.loads((package/'manifest.json').read_text())
            if manifest.get('driver_api')!='openmotion-0276-v1':raise ValueError('Install a compatible Open Motion emulator package')
            game=self.game()['set']
            if game not in manifest.get('games',[]):raise ValueError('This emulator package does not support the selected game')
            exe=package/'payload'/manifest['executable']
            import hashlib
            if hashlib.sha256(exe.read_bytes()).hexdigest()!=manifest['files']['payload/'+manifest['executable']]:
                raise ValueError('Emulator checksum mismatch; reinstall this support package')
            if not (Path(self.config['rompath'])/(game+'.zip')).is_file():raise ValueError('Import the complete game ROM ZIP first')
            # Fail early if another MAME instance owns the output port.
            import socket
            probe=socket.socket()
            try:probe.bind(('127.0.0.1',8000))
            finally:probe.close()
            token=secrets.randbelow(100000000)+1
            session=ROOT/'sessions'/str(token);session.mkdir(parents=True)
            env=dict(os.environ,OPEN_MOTION_SESSION=str(token),OPEN_MOTION_STATUS=str(session/'bridge.txt'),
                     OPEN_MOTION_PROFILE=game,OPEN_MOTION_OVERLAY='1' if self.config['overlay'] else '0')
            self.bridge=Bridge(game,token,session/'bridge.txt',session/'commands.jsonl',self.config['port'])
            cfg=ROOT/'cfg'/game;cfg.mkdir(parents=True,exist_ok=True)
            cmd=[str(exe),game,'-rompath',str(Path(self.config['rompath']).resolve()),'-output','network',
                 '-pluginspath',str(ASSETS/'plugins')+';'+str(package/'payload'/'plugins'),'-plugin','openmotion',
                 '-cfg_directory',str(cfg),'-nvram_directory',str(ROOT/'nvram'),'-joystick','-skip_gameinfo',
                 '-inipath',str(ROOT/'ini'),'-ui_font','default','-fontpath',str(package/'payload'),
                 '-window' if not self.config['fullscreen'] else '-nowindow']
            self.process_log=(session/'emulator.log').open('w',encoding='utf-8')
            self.process=subprocess.Popen(cmd,cwd=exe.parent,env=env,stdout=self.process_log,stderr=subprocess.STDOUT)
            self.bridge.start();self.started=time.monotonic();self.show_monitor()
        except Exception as e:
            if self.bridge:self.bridge.close();self.bridge=None
            if self.process_log:self.process_log.close();self.process_log=None
            messagebox.showerror('Cannot launch',str(e))

    def show_monitor(self):
        self.page='monitor';self.clear('COMMAND MONITOR')
        self.monitor=self.label('No game running',16);self.monitor.pack(fill='both',expand=True,padx=self.px(10))
        self.button('Motion on / off',self.toggle_motion).pack(fill='x',padx=self.px(10))
        self.button('Next page',self.next_monitor).pack(fill='x',padx=self.px(10),pady=self.px(2))
        self.button('Exit game / Back',self.monitor_back).pack(fill='x',padx=self.px(10),pady=self.px(2))
        self.items[0].focus_set()
    def next_monitor(self):self.monitor_page=(self.monitor_page+1)%3
    def monitor_back(self):
        if self.process and self.process.poll() is None:self.stop_game()
        self.draw_games()
    def toggle_motion(self):
        if not self.bridge:return
        if self.bridge.armed:self.bridge.disable()
        else:
            if not messagebox.askokcancel('Enable cabinet movement','Controller must be calibrated and ready.\nOpening USB may restart some controllers.\nEnable motion for this session?'):return
            try:self.bridge.enable()
            except Exception as e:messagebox.showerror('Motion remains off',str(e))
    def stop_game(self):
        if self.bridge:self.bridge.disable('Exiting game')
        if self.process and self.process.poll() is None:self.process.terminate()
    def about(self):
        messagebox.showinfo('Open Motion: G-LOC',f'Open Motion {__version__}\nBy Luke McMillan\ngithub.com/BertyB3/OpenMotionGLOC\n\nF6: overlay off / compact / detail\nTAB in MAME: bind A-PAC controls\nController: 115200, 8N1\n\nCentre is a movement command, not an emergency stop.\nDesktop/cabinet validation is in progress.')
    def tick(self):
        if self.process and self.process.poll() is not None:
            code=self.process.returncode
            if self.bridge:self.bridge.close()
            if self.process_log:self.process_log.close();self.process_log=None
            self.process=None
            if code:messagebox.showerror('Emulator stopped',f'Exit code {code}. See sessions/emulator.log for details.')
        if self.page=='monitor' and self.bridge:
            s=self.bridge.status();p=s['pose']
            if self.monitor_page==0:
                text=f"Q {p['q']:02d}  R {p['r']:02d}\nSpeed {p['s']} / {p['t']}\n"+('MOTION ON' if s['armed'] else 'MONITOR ONLY')
            elif self.monitor_page==1:text='SENT\n'+s['tx']+'\nRECEIVED\n'+s['rx'][:55]
            else:text=s['reason']+'\nF6: game overlay\nTAB: MAME input setup'
            self.monitor.config(text=text,wraplength=self.root.winfo_width()-self.px(20))
        if not self.process and self.root.focus_displayof() is not None and self.root.focus_get() is not None:
            key=self.nav.poll()
            if key:self.root.event_generate('<'+key+'>')
        self.root.after(100,self.tick)
    def close(self):
        self.stop_game()
        if self.bridge:self.bridge.close()
        if self.process_log:self.process_log.close()
        self.root.destroy()

def main():
    root=tk.Tk();app=CabinetApp(root)
    if '--smoke-test' in sys.argv:
        results=[]
        for width,height in [(320,240),(640,480)]:
            root.geometry(f'{width}x{height}')
            root.update()
            app.draw_games();root.update()
            for child in app.body.winfo_children():
                if child.winfo_ismapped() and (child.winfo_y()<0 or child.winfo_y()+child.winfo_height()>app.body.winfo_height()+1):
                    raise AssertionError('Launcher control exceeds the window height')
            results.append({'width':width,'height':height,'game_rows':app.list.size(),'status':'pass'})
        Path('launcher-smoke.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        app.close()
    else:
        root.mainloop()
