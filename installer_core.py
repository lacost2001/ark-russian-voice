"""Offline, hash-pinned ARK audio installation and recovery."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import zipfile

def digest(data): return hashlib.sha256(data).hexdigest()

def game_running():
    result=subprocess.run(['tasklist','/FI','IMAGENAME eq ShooterGame.exe','/FO','CSV','/NH'],
        capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
    return b'shootergame.exe' in result.stdout.lower()

def game_candidates(folder):
    root=Path(folder).expanduser().resolve()
    bases=[root,root/'steamapps/common/ARK',root/'common/ARK',root/'ARK']
    for vdf in [root/'steamapps/libraryfolders.vdf',root/'libraryfolders.vdf']:
        if vdf.is_file():
            for value in re.findall(r'"path"\s*"([^"]+)"',vdf.read_text('utf-8',errors='replace')):
                bases.append(Path(value.replace('\\\\','\\'))/'steamapps/common/ARK')
    found=[]
    for p in bases:
        if (p/'ShooterGame/Binaries/Win64/ShooterGame.exe').is_file() and p.resolve() not in found:
            found.append(p.resolve())
    return found

def safe_path(root,relative):
    p=PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative or ':' in relative:
        raise ValueError('Недопустимый путь в пакете.')
    allowed=('ShooterGame/Content/PrimalEarth/Sound/SFX/Characters/',
             'ShooterGame/Content/PrimalEarth/ExplorerNotes/HLNA/Audio/Prelaunch/English/',
             'ShooterGame/Content/Genesis/Sound/Characters/HLNA/Glitches/English/',
             'ShooterGame/Content/Genesis/Sound/Characters/HLNA/Cinematics/English/',
             'ShooterGame/Content/Genesis/Sound/Characters/HLNA/Functional/',
             'ShooterGame/Content/Genesis/Sound/Characters/HLNA/Missions/English/',
             'ShooterGame/Content/Genesis/Sound/Characters/HLNA/Store/English/',
             'ShooterGame/Content/Genesis/Sound/Characters/VRBoss/Voice/',
             'ShooterGame/Content/Extinction/Matinee/Ascension/Sound/',
             'ShooterGame/Content/Genesis2/Sounds/Characters/HLNA/Chronicles/',
             'ShooterGame/Content/Genesis2/Sounds/Characters/HLNA/Cinematics/',
             'ShooterGame/Content/Genesis2/Sounds/Characters/HLNA/Boss/',
             'ShooterGame/Content/Genesis2/Sounds/Characters/HLNA/Missions/',
             'ShooterGame/Content/Genesis2/Sounds/Characters/HLNB/',
             'ShooterGame/Content/Genesis2/Sounds/Characters/Rockwell/',
             'ShooterGame/Content/Genesis2/Sounds/Characters/Santiago/')
    movies=('TheIsland_in','TheIsland_out','ScorchedEarth_in','ScorchedEarth_out','Aberration_in','Aberration_out','Extinction_in')
    is_movie=str(p.parent)=='ShooterGame/Content/Movies' and p.stem in movies and p.suffix in ('.mp4','.wmv')
    legacy_hlna=str(p.parent)=='ShooterGame/Content/Genesis/Sound/Characters/HLNA' and p.stem.startswith('s_hlna_')
    if not is_movie and ((not relative.startswith(allowed) and not legacy_hlna) or p.suffix!='.uasset'):
        raise ValueError('Пакет содержит посторонний файл.')
    root=Path(root).resolve()
    path=root.joinpath(*p.parts)
    if not path.resolve().is_relative_to(root):raise ValueError('Путь выходит за папку ARK.')
    current=path
    while current!=root:
        if current.is_symlink() or (hasattr(current,'is_junction') and current.is_junction()):
            raise ValueError('Ссылки в пути установки не поддерживаются.')
        current=current.parent
    return path

def read_package(package,config):
    package=Path(package)
    if not package.is_file():raise ValueError('Рядом с установщиком нет файла voices.zip. Распакуйте весь архив.')
    if digest(package.read_bytes())!=config['package_sha256']:
        raise ValueError('Пакет повреждён или не соответствует установщику. Получите полный архив заново.')
    with zipfile.ZipFile(package) as z:
        m=json.loads(z.read('manifest.json'))
        assert len(m['entries'])==config['count']
        assert len({e['path'] for e in m['entries']})==len(m['entries'])
        payload={}
        for e in m['entries']:
            safe_path(Path.cwd(),e['path'])
            data=z.read('files/'+e['path'])
            if digest(data)!=e['new_sha256']:raise ValueError('Повреждён файл: '+e['path'])
            payload[e['path']]=data
    return m,payload

def apply(game,package,config,restore=False,progress=lambda text,value:None,check_running=game_running):
    game=Path(game).resolve()
    if game not in game_candidates(game):raise ValueError('Выберите папку ARK: внутри должна находиться папка ShooterGame.')
    if check_running():raise ValueError('Полностью закройте ARK перед установкой или восстановлением.')
    progress('Проверка пакета…',0)
    manifest,payload=read_package(package,config)
    backup_root=game/'.ark-russian-voice-backup'
    if backup_root.is_symlink() or (backup_root.exists() and backup_root.resolve()!=backup_root):
        raise ValueError('Некорректная папка резервной копии.')
    prepared=[]
    for e in manifest['entries']:
        target=safe_path(game,e['path'])
        if not target.is_file():raise ValueError('В этой версии ARK отсутствует файл: '+e['path'])
        old=target.read_bytes()
        oldhash=digest(old)
        if oldhash not in [e['original_sha256'],e['new_sha256'],*e.get('previous_sha256',[])]:
            raise ValueError('Версия ARK отличается либо установлен другой мод озвучки. Ни один файл не изменён.\n'+target.name)
        backup=backup_root/(e['original_sha256']+'.uasset')
        if backup.exists() and (backup.is_symlink() or digest(backup.read_bytes())!=e['original_sha256']):
            raise ValueError('Резервная копия повреждена: '+target.name)
        if oldhash!=e['original_sha256'] and not backup.exists():
            raise ValueError('Для обновления нужна резервная копия оригинала: '+target.name)
        if restore:
            if oldhash==e['original_sha256']:continue
            if not backup.exists():raise ValueError('Нет резервной копии оригинала: '+target.name)
            new=backup.read_bytes()
        else:
            if oldhash==e['new_sha256']:continue
            new=payload[e['path']]
        prepared.append((target,backup,old,new,e))
    if not prepared:
        progress('Оригиналы уже восстановлены.' if restore else 'Озвучка уже установлена.',100)
        return 0
    required=sum(len(old)+len(new) for _,_,old,new,_ in prepared)+64*1024*1024
    if shutil.disk_usage(game).free<required:raise ValueError('Недостаточно свободного места для установки с резервной копией.')
    if check_running():raise ValueError('ARK запущен. Закройте игру и повторите.')
    backup_root.mkdir(exist_ok=True)
    # Save originals before changing any live file. They survive interrupted runs.
    if not restore:
        for target,backup,old,new,e in prepared:
            if not backup.exists():
                with open(backup,'xb') as stream:stream.write(old)
            if digest(backup.read_bytes())!=e['original_sha256']:raise ValueError('Не удалось проверить резервную копию.')
    changed=[]
    try:
        for i,(target,backup,old,new,e) in enumerate(prepared):
            if target.read_bytes()!=old:raise ValueError('Файл игры изменился во время установки.')
            fd,name=tempfile.mkstemp(prefix='.ark-voice-',suffix='.tmp',dir=target.parent)
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(new)
                changed.append((target,old))
                os.replace(name,target)
            finally:
                if os.path.exists(name):os.unlink(name)
            if target.read_bytes()!=new:raise ValueError('Ошибка проверки записанного файла.')
            progress(('Восстановление' if restore else 'Установка')+f': {i+1} / {len(prepared)}',int((i+1)*100/len(prepared)))
    except Exception:
        errors=[]
        for target,old in reversed(changed):
            try:target.write_bytes(old)
            except OSError:errors.append(target.name)
        if errors:raise RuntimeError('Не удалось завершить откат: '+', '.join(errors)+'. Оригиналы сохранены в резервной папке.')
        raise
    progress('Оригинальная озвучка восстановлена.' if restore else 'Готово! Русская озвучка установлена.',100)
    return len(prepared)
