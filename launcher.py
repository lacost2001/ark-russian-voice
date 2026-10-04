import argparse
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from installer_core import apply,game_candidates,read_package,game_running,preflight_packages
from updates import MAPS,fetch_catalog,download,load_settings,save_settings,verify_catalog

RES=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
BASE=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
config=json.loads((RES/'release_config.json').read_text('utf-8'))
parser=argparse.ArgumentParser();parser.add_argument('--verify-package',action='store_true');parser.add_argument('--report')
args=parser.parse_args()
if args.verify_package:
    try:
        catalog=verify_catalog((BASE/'catalog.json').read_bytes(),config);counts={}
        for pack in catalog['packages']:
            m,_=read_package(BASE/pack['filename'],pack);counts[pack['map']]=counts.get(pack['map'],0)+len(m['entries'])
        result={'ok':True,'maps':counts}
    except Exception as error:result={'ok':False,'error':str(error)}
    if args.report:Path(args.report).write_text(json.dumps(result),encoding='utf-8')
    raise SystemExit(0 if result['ok'] else 1)
cache=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ARK-Russian-Voice'
cache.mkdir(parents=True,exist_ok=True)
lock=(cache/'running.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
try:
    import msvcrt
    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
except OSError:
    tk.Tk().withdraw();messagebox.showinfo('ARK — озвучка','Программа уже запущена.');raise SystemExit(0)
settings_path=cache/'settings.json';settings=load_settings(settings_path);catalog=None
for source in [cache/'catalog.json',BASE/'catalog.json']:
    try:catalog=verify_catalog(source.read_bytes(),config);break
    except Exception:pass
root=tk.Tk();root.title('ARK — русская озвучка '+config['app_version']);root.geometry('820x820');root.minsize(820,820)
style=ttk.Style();style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
ttk.Label(frame,text='Русская озвучка ARK',font=('Segoe UI',21,'bold')).pack(anchor='w')
ttk.Label(frame,text='Survival Evolved · выбор карт и обновление голосов',font=('Segoe UI',10)).pack(anchor='w',pady=(6,18))
ttk.Label(frame,text='Папка ARK или библиотека Steam:').pack(anchor='w')
folder=tk.StringVar(value=settings.get('folder',''));row=ttk.Frame(frame);row.pack(fill='x',pady=6)
entry=ttk.Entry(row,textvariable=folder);entry.pack(side='left',fill='x',expand=True)
def browse():
    value=filedialog.askdirectory(title='Папка ARK или Steam')
    if value:folder.set(value)
browse_button=ttk.Button(row,text='Выбрать…',command=browse);browse_button.pack(side='right',padx=(8,0))
maps_frame=ttk.LabelFrame(frame,text='Карты и общие голоса',padding=10);maps_frame.pack(fill='x',pady=12)
map_vars={};map_widgets={};map_labels={}
for index,(key,title) in enumerate(MAPS.items()):
    variable=tk.BooleanVar(value=key in settings.get('maps',['Shared','TheIsland']));map_vars[key]=variable
    widget=ttk.Checkbutton(maps_frame,text=title,variable=variable);widget.grid(row=index,column=0,sticky='w',padx=(0,24));map_widgets[key]=widget
    label=ttk.Label(maps_frame,text='Готовится');label.grid(row=index,column=1,sticky='w');map_labels[key]=label
automatic=tk.BooleanVar(value=settings.get('automatic',True))
auto_widget=ttk.Checkbutton(frame,text='Обновлять выбранные карты при запуске программы',variable=automatic);auto_widget.pack(anchor='w')
status=tk.StringVar(value='Проверка обновлений…')
ttk.Label(frame,textvariable=status,wraplength=700).pack(anchor='w',pady=10)
bar=ttk.Progressbar(frame,maximum=100);bar.pack(fill='x')
buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=14)
events=queue.Queue();busy=False
def persist():save_settings(settings_path,{'folder':folder.get(),'maps':[m for m,v in map_vars.items() if v.get()],'automatic':automatic.get(),'backup_folder':settings.get('backup_folder','')})
def refresh_maps():
    available={}
    for p in (catalog or {}).get('packages',[]):
        if p['map'] not in available:available[p['map']]=dict(p)
        else:
            available[p['map']]['count']+=p['count']
            available[p['map']]['version']=max(available[p['map']]['version'],p['version'],key=lambda v:tuple(int(n) for n in v.split('.')))
    for key,widget in map_widgets.items():
        pack=available.get(key);widget.configure(state='normal' if pack and not busy else 'disabled')
        map_labels[key].configure(text=f'{pack["count"]} файлов озвучки · версия {pack["version"]}' if pack else 'Готовится — пока недоступно')
def set_busy(value):
    global busy
    busy=value
    for widget in (entry,browse_button,install,restore_button,check_button,backup_button,auto_widget):widget.configure(state='disabled' if value else 'normal')
    refresh_maps()
def check(startup=False):
    if busy:return
    set_busy(True);status.set('Проверка обновлений…')
    def run():
        try:events.put(('catalog',fetch_catalog(config,cache),startup))
        except Exception as error:events.put(('offline',str(error)))
    threading.Thread(target=run,daemon=True).start()
def work(restore=False,auto=False):
    if busy:return
    found=game_candidates(folder.get()) if folder.get() else []
    if len(found)!=1:status.set('Выберите папку ARK, затем нажмите «Установить / обновить».');return
    folder.set(str(found[0]))
    if restore:automatic.set(False)
    persist()
    selected=[p for p in (catalog or {}).get('packages',[]) if map_vars[p['map']].get()]
    if not selected:status.set('Выберите хотя бы одну доступную карту.');return
    if game_running():status.set('ARK запущен. Закройте игру и нажмите «Установить / обновить».');return
    set_busy(True)
    legacy_roots=[BASE/'work/original',BASE.parent.parent/'work/original']
    if settings.get('backup_folder'):legacy_roots.insert(0,Path(settings['backup_folder']))
    def run():
        completed=[];packages=[]
        try:
            for pack in selected:
                local=BASE/pack['filename']
                if local.is_file():
                    try:read_package(local,pack)
                    except Exception:local=download(pack,cache,lambda t,v:events.put(('progress',t,v)))
                else:local=download(pack,cache,lambda t,v:events.put(('progress',t,v)))
                packages.append((local,pack))
            events.put(('progress','Проверка всех выбранных пакетов и оригиналов…',0))
            preflight_packages(found[0],packages,restore,legacy_roots)
            for index,(local,pack) in enumerate(packages):
                apply(found[0],local,pack,restore,lambda t,v:events.put(('progress',t,v)),legacy_roots=legacy_roots)
                if not any(p['map']==pack['map'] for _,p in packages[index+1:]):completed.append(MAPS[pack['map']])
            events.put(('done','Оригиналы восстановлены.' if restore else 'Выбранная озвучка актуальна: '+', '.join(completed)))
        except Exception as error:events.put(('error',str(error)+('\nЗавершены карты: '+', '.join(completed) if completed else '')))
    threading.Thread(target=run,daemon=True).start()
install=ttk.Button(buttons,text='Установить / обновить',command=work);install.pack(side='left')
restore_button=ttk.Button(buttons,text='Вернуть оригинал',command=lambda:work(True));restore_button.pack(side='left',padx=8)
check_button=ttk.Button(buttons,text='Проверить обновления',command=check);check_button.pack(side='left')
def choose_backups():
    value=filedialog.askdirectory(title='Папка оригиналов: work/original или .ark-russian-voice-backup')
    if value:
        settings['backup_folder']=value;persist();status.set('Папка копий выбрана. Нажмите «Установить / обновить». Оригиналы будут проверены автоматически.')
backup_button=ttk.Button(frame,text='Найти резервные копии…',command=choose_backups);backup_button.pack(anchor='w',pady=(0,10))
ttk.Label(frame,text='Оригиналы сохраняются. Снятие галочки не удаляет озвучку.\nДля удаления выберите карту и нажмите «Вернуть оригинал».',wraplength=700).pack(anchor='w')
ttk.Label(frame,text='Состав озвучки: готовые записки, досье, диалоги и кат-сцены.\nРанее беззвучные записки других авторов и неразборчивый фоновый шёпот пока не включены.',wraplength=750).pack(anchor='w',pady=(8,0))
def pump():
    global catalog
    try:
        while True:
            e=events.get_nowait()
            if e[0]=='progress':status.set(e[1]);bar['value']=e[2];continue
            set_busy(False)
            if e[0]=='catalog':
                catalog=e[1];refresh_maps();status.set('Каталог обновлён. Выберите карты для установки.')
                if e[2] and automatic.get():work(auto=True)
            elif e[0]=='offline':
                status.set('Нет доступа к обновлениям. Можно установить сохранённые пакеты.')
                if catalog and automatic.get() and folder.get():work(auto=True)
            elif e[0]=='done':status.set(e[1]);bar['value']=100
            elif e[0]=='error':status.set('Операция остановлена.');messagebox.showerror('Озвучка ARK',e[1])
    except queue.Empty:pass
    root.after(100,pump)
def close():
    if busy:messagebox.showinfo('Подождите','Дождитесь завершения загрузки или установки.')
    else:persist();root.destroy()
root.protocol('WM_DELETE_WINDOW',close)
if not folder.get():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as k:steam=winreg.QueryValueEx(k,'SteamPath')[0]
        candidates=game_candidates(steam)
        if candidates:folder.set(str(candidates[0]))
    except OSError:pass
refresh_maps();root.after(100,pump);root.after(250,lambda:check(True));root.mainloop()
