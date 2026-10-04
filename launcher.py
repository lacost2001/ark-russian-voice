import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import webbrowser
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from installer_core import apply,game_candidates,read_package,game_running,preflight_packages
from app_update import fetch_manifest,prepare_update,launch_update,apply_request
from updates import MAPS,fetch_catalog,download,load_settings,save_settings,verify_catalog

RES=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
BASE=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
config=json.loads((RES/'release_config.json').read_text('utf-8'))
parser=argparse.ArgumentParser();parser.add_argument('--verify-package',action='store_true');parser.add_argument('--report');parser.add_argument('--smoke-test',action='store_true');parser.add_argument('--preview',action='store_true');parser.add_argument('--apply-app-update')
args=parser.parse_args()
if args.apply_app_update:
    try:apply_request(args.apply_app_update,config)
    except Exception as error:
        tk.Tk().withdraw();messagebox.showerror('Обновление приложения',str(error)+'\nПредыдущий EXE сохранён рядом с программой с окончанием .previous.');raise SystemExit(1)
    raise SystemExit(0)
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
logger=logging.getLogger('ark-voice');logger.setLevel(logging.INFO)
handler=RotatingFileHandler(cache/'installer.log',maxBytes=1000000,backupCount=2,encoding='utf-8');logger.addHandler(handler)
settings_path=cache/'settings.json';settings=load_settings(settings_path);catalog=None
for source in [cache/'catalog.json',BASE/'catalog.json']:
    try:catalog=verify_catalog(source.read_bytes(),config);break
    except Exception:pass
root=tk.Tk();root.title('ARK · Русская озвучка — '+config['app_version']);root.geometry('1000x920');root.minsize(960,650)
BG='#101821';CARD='#192633';TEXT='#e8f0f6';MUTED='#9db0c1';ACCENT='#56dbc2'
root.configure(bg=BG)
style=ttk.Style();style.theme_use('clam')
style.configure('.',font=('Segoe UI',10),background=BG,foreground=TEXT)
style.configure('TFrame',background=BG)
style.configure('Card.TFrame',background=CARD)
style.configure('Card.TLabel',background=CARD,foreground=MUTED,font=('Segoe UI',9))
style.configure('Card.TCheckbutton',background=CARD)
style.configure('TLabel',background=BG,foreground=TEXT)
style.configure('Muted.TLabel',foreground=MUTED)
style.configure('TCheckbutton',background=BG,foreground=TEXT,padding=(4,4))
style.map('TCheckbutton',background=[('active',CARD)],foreground=[('disabled','#63788b')])
style.configure('TEntry',fieldbackground=CARD,foreground=TEXT,insertcolor=TEXT,padding=8)
style.configure('TButton',background=CARD,foreground=TEXT,padding=(12,9),borderwidth=0)
style.map('TButton',background=[('active','#2a4255')],foreground=[('disabled','#64788a')])
style.configure('Accent.TButton',background=ACCENT,foreground='#0b2620',font=('Segoe UI',10,'bold'))
style.map('Accent.TButton',background=[('active','#8cebd8'),('disabled','#365f59')])
style.configure('TLabelframe',background=BG,bordercolor='#2c4050')
style.configure('TLabelframe.Label',background=BG,foreground=ACCENT,font=('Segoe UI',10,'bold'))
style.configure('Horizontal.TProgressbar',background=ACCENT,troughcolor=CARD,borderwidth=0)
canvas=tk.Canvas(root,bg=BG,highlightthickness=0);canvas.pack(side='left',fill='both',expand=True)
scrollbar=ttk.Scrollbar(root,orient='vertical',command=canvas.yview);scrollbar.pack(side='right',fill='y')
canvas.configure(yscrollcommand=scrollbar.set)
frame=ttk.Frame(canvas,padding=(24,20));content=canvas.create_window((0,0),window=frame,anchor='nw')
frame.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
canvas.bind('<Configure>',lambda e:canvas.itemconfigure(content,width=e.width))
root.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-int(e.delta/120),'units'))
header=ttk.Frame(frame);header.pack(fill='x',pady=(0,16))
ttk.Label(header,text='ARK  /  VOICES',foreground=ACCENT,font=('Segoe UI',11,'bold')).pack(anchor='w')
ttk.Label(header,text='Истории оживают',font=('Segoe UI',25,'bold')).pack(anchor='w',pady=(4,2))
ttk.Label(header,text='Русская озвучка Survival Evolved · записки, диалоги и кат-сцены',style='Muted.TLabel').pack(anchor='w')
ttk.Label(frame,text='Папка ARK или библиотека Steam:').pack(anchor='w')
folder=tk.StringVar(value=settings.get('folder',''));row=ttk.Frame(frame);row.pack(fill='x',pady=6)
entry=ttk.Entry(row,textvariable=folder);entry.pack(side='left',fill='x',expand=True)
def browse():
    value=filedialog.askdirectory(title='Папка ARK или Steam')
    if value:folder.set(value)
browse_button=ttk.Button(row,text='Выбрать…',command=browse);browse_button.pack(side='right',padx=(8,0))
maps_frame=ttk.LabelFrame(frame,text='Карты и общие голоса',padding=10);maps_frame.pack(fill='x',pady=10)
map_vars={};map_widgets={};map_labels={}
for index,(key,title) in enumerate(MAPS.items()):
    variable=tk.BooleanVar(value=key in settings.get('maps',['Shared','TheIsland']));map_vars[key]=variable
    card=ttk.Frame(maps_frame,style='Card.TFrame',padding=(6,7));card.grid(row=index//3,column=index%3,sticky='nsew',padx=4,pady=4)
    maps_frame.columnconfigure(index%3,weight=1,uniform='cards')
    widget=ttk.Checkbutton(card,text=title,variable=variable,style='Card.TCheckbutton');widget.pack(anchor='w');map_widgets[key]=widget
    label=ttk.Label(card,text='Нет загруженного каталога',style='Card.TLabel');label.pack(anchor='w',padx=(4,0));map_labels[key]=label
automatic=tk.BooleanVar(value=settings.get('automatic',True))
auto_widget=ttk.Checkbutton(frame,text='Обновлять выбранные карты при запуске программы',variable=automatic);auto_widget.pack(anchor='w')
app_automatic=tk.BooleanVar(value=settings.get('app_automatic',True))
app_auto_widget=ttk.Checkbutton(frame,text='Автоматически обновлять само приложение и перезапускать его',variable=app_automatic);app_auto_widget.pack(anchor='w')
status=tk.StringVar(value='Проверка обновлений…')
ttk.Label(frame,textvariable=status,wraplength=870).pack(anchor='w',pady=10)
bar=ttk.Progressbar(frame,maximum=100);bar.pack(fill='x')
buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=14)
events=queue.Queue();busy=False
def persist():save_settings(settings_path,{'folder':folder.get(),'maps':[m for m,v in map_vars.items() if v.get()],'automatic':automatic.get(),'app_automatic':app_automatic.get(),'backup_folder':settings.get('backup_folder','')})
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
    for widget in (entry,browse_button,install,restore_button,check_button,backup_button,diagnose_button,auto_widget,app_auto_widget):widget.configure(state='disabled' if value else 'normal')
    refresh_maps()
def check(startup=False):
    if busy:return
    set_busy(True);status.set('Проверка обновлений…')
    update_app=getattr(sys,'frozen',False) and (app_automatic.get() or not startup)
    def run():
        try:
            if update_app:
                try:
                    raw,_=fetch_manifest(config)
                    staged=prepare_update(raw,config,cache,lambda t,v:events.put(('progress',t,v)))
                    if staged:
                        events.put(('app_ready',staged));return
                except Exception as error:logger.warning('Application update unavailable: %s',error)
            events.put(('catalog',fetch_catalog(config,cache),startup))
        except Exception as error:
            logger.warning('Catalog update failed: %s',error)
            events.put(('offline',str(error)))
    threading.Thread(target=run,daemon=True).start()
def work(restore=False,auto=False,diagnose=False):
    if busy:return
    if args.preview:
        status.set('Режим просмотра: установка отключена.');return
    found=game_candidates(folder.get()) if folder.get() else []
    if len(found)!=1:status.set('Выберите папку ARK, затем нажмите «Установить / исправить».');return
    folder.set(str(found[0]))
    if restore and not diagnose:automatic.set(False)
    persist()
    selected=[p for p in (catalog or {}).get('packages',[]) if map_vars[p['map']].get()]
    if not selected:status.set('Выберите хотя бы одну доступную карту.');return
    if game_running():status.set('ARK запущен. Закройте игру и нажмите «Установить / исправить».');return
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
            if diagnose:
                events.put(('done','Проверка пройдена. Пакеты и файлы совместимы; можно установить или восстановить озвучку. Файлы игры не изменялись.'))
                return
            for index,(local,pack) in enumerate(packages):
                apply(found[0],local,pack,restore,lambda t,v:events.put(('progress',t,v)),legacy_roots=legacy_roots)
                if not any(p['map']==pack['map'] for _,p in packages[index+1:]):completed.append(MAPS[pack['map']])
            events.put(('done','Оригиналы восстановлены.' if restore else 'Выбранная озвучка актуальна: '+', '.join(completed)))
        except Exception as error:
            logger.exception('Installation operation failed')
            events.put(('error',str(error)+('\nЗавершены карты: '+', '.join(completed) if completed else '')))
    threading.Thread(target=run,daemon=True).start()
install=ttk.Button(buttons,text='Установить / исправить',style='Accent.TButton',command=work);install.pack(side='left')
restore_button=ttk.Button(buttons,text='Вернуть оригинал',command=lambda:work(True));restore_button.pack(side='left',padx=8)
check_button=ttk.Button(buttons,text='Проверить обновления',command=check);check_button.pack(side='left')
diagnose_button=ttk.Button(buttons,text='Проверить файлы',command=lambda:work(diagnose=True));diagnose_button.pack(side='left',padx=(8,0))

def choose_backups():
    value=filedialog.askdirectory(title='Папка оригиналов: work/original или .ark-russian-voice-backup')
    if value:
        settings['backup_folder']=value;persist();status.set('Папка копий выбрана. Нажмите «Установить / исправить». Оригиналы будут проверены автоматически.')
backup_button=ttk.Button(frame,text='Указать папку оригиналов…',command=choose_backups);backup_button.pack(anchor='w',pady=(0,8))
utility=ttk.Frame(frame);utility.pack(fill='x',pady=(0,8))
ttk.Button(utility,text='Открыть журнал ошибок',command=lambda:os.startfile(str(cache/'installer.log'))).pack(side='left')
ttk.Button(utility,text='Новая версия программы ↗',command=lambda:webbrowser.open('https://github.com/'+config['repository']+'/releases/latest')).pack(side='left',padx=8)
ttk.Label(frame,text='Оригиналы сохраняются. Снятие галочки не удаляет озвучку.\nДля удаления выберите карту и нажмите «Вернуть оригинал».',wraplength=700).pack(anchor='w')
ttk.Label(frame,style='Muted.TLabel',text='Состав озвучки: готовые записки, досье, диалоги и кат-сцены.\nИзначально немые записки не озвучиваются. Совместимость: preaquatica. Версия программы '+config['app_version']+'.',wraplength=750).pack(anchor='w',pady=(8,0))
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
            elif e[0]=='app_ready':
                try:
                    persist();launch_update(e[1],sys.executable,os.getpid());root.destroy();return
                except Exception as error:
                    logger.exception('Application replacement could not start')
                    status.set('Не удалось обновить приложение. Текущая версия сохранена.')
                    messagebox.showerror('Обновление приложения',str(error)+'\nПереместите программу в доступную для записи папку или скачайте новую версию из GitHub.')
            elif e[0]=='offline':
                status.set('Нет доступа к обновлениям. Можно установить сохранённые пакеты.')
                if catalog and automatic.get() and folder.get():work(auto=True)
            elif e[0]=='done':status.set(e[1]);bar['value']=100
            elif e[0]=='error':
                status.set('Не удалось завершить операцию. Причина сохранена в журнале.');messagebox.showerror('Нужно ваше действие',e[1]+'\n\nПодробности: кнопка «Открыть журнал ошибок».')
    except queue.Empty:pass
    root.after(100,pump)
def close():
    if busy:messagebox.showinfo('Подождите','Дождитесь завершения загрузки или установки.')
    else:
        if not args.preview:persist()
        root.destroy()
root.protocol('WM_DELETE_WINDOW',close)
if not folder.get():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as k:steam=winreg.QueryValueEx(k,'SteamPath')[0]
        candidates=game_candidates(steam)
        if candidates:folder.set(str(candidates[0]))
    except OSError:pass
def report_callback(exc,val,tb):
    logger.error('UI callback failed',exc_info=(exc,val,tb))
    messagebox.showerror('Ошибка программы','Подробности сохранены в журнале ошибок.')
root.report_callback_exception=report_callback
refresh_maps()
if args.smoke_test:
    root.after(800,root.destroy)
elif args.preview:
    status.set('Режим просмотра · файлы игры не изменяются.')
else:
    root.after(100,pump);root.after(250,lambda:check(True))
root.mainloop()
