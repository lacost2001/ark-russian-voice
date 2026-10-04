"""Signed application updates. No shell commands or elevated privileges."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from updates import canonical

def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):
        raise ValueError('Неверная версия обновления приложения.')
    return tuple(map(int,value.split('.')))

def verify_manifest(raw,config):
    envelope=json.loads(raw);data=envelope['payload']
    Ed25519PublicKey.from_public_bytes(base64.b64decode(config['public_key'])).verify(
        base64.b64decode(envelope['signature']),canonical(data))
    version(data['version'])
    expected='https://github.com/'+config['repository']+'/releases/download/v'+data['version']+'/ARK-Russian-Voice.exe'
    if data.get('schema')!=1 or data.get('url')!=expected:
        raise ValueError('Неизвестный источник обновления приложения.')
    if not re.fullmatch('[0-9a-f]{64}',data.get('sha256','')) or not 0<data['size']<150_000_000:
        raise ValueError('Неверные параметры обновления приложения.')
    return data

def fetch_manifest(config,opener=urllib.request.urlopen):
    url='https://github.com/'+config['repository']+'/releases/latest/download/app-update.json'
    with opener(urllib.request.Request(url,headers={'User-Agent':'ARK-Voices','Cache-Control':'no-cache'}),timeout=20) as response:
        raw=response.read(65537)
    if len(raw)>65536:raise ValueError('Слишком большой манифест приложения.')
    return raw,verify_manifest(raw,config)

def prepare_update(raw,config,cache,progress=lambda t,v:None,opener=urllib.request.urlopen):
    data=verify_manifest(raw,config)
    if version(data['version'])<=version(config['app_version']):return None
    folder=Path(cache)/'app-updates'/data['version'];folder.mkdir(parents=True,exist_ok=True)
    target=folder/'ARK-Russian-Voice.exe';partial=folder/'download.part'
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=data['sha256']:
        try:
            with opener(data['url'],timeout=60) as response,partial.open('wb') as stream:
                total=0;digest=hashlib.sha256()
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    total+=len(chunk)
                    if total>data['size']:raise ValueError('Превышен размер обновления приложения.')
                    stream.write(chunk);digest.update(chunk)
                    progress('Обновление программы до '+data['version']+'…',int(total*100/data['size']))
            if total!=data['size'] or digest.hexdigest()!=data['sha256']:
                raise ValueError('Обновление приложения повреждено; текущая версия сохранена.')
            os.replace(partial,target)
        finally:partial.unlink(missing_ok=True)
    (folder/'app-update.json').write_bytes(raw)
    return target

def launch_update(staged,target,parent_pid):
    """The staged EXE waits for this app, replaces it and opens the new version."""
    target=Path(target).resolve();staged=Path(staged).resolve()
    # Fail while the current app is still available if its folder is read-only.
    probe=target.with_name(target.name+'.update-probe')
    with probe.open('xb'):pass
    probe.unlink()
    request=staged.parent/'request.json'
    request.write_text(json.dumps({'target':str(target),'parent_pid':parent_pid}),encoding='utf-8')
    subprocess.Popen([str(staged),'--apply-app-update',str(request)],close_fds=True)

def replace_application(source,target,expected,launch):
    """Preserve old EXE and roll back if replacement or process creation fails."""
    source=Path(source).resolve();target=Path(target).resolve()
    if source==target or target.suffix.lower()!='.exe' or not target.is_file():
        raise ValueError('Неверный путь установленного приложения.')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise ValueError('Повреждён EXE обновления.')
    previous=target.with_name(target.name+'.previous');pending=target.with_name(target.name+'.pending')
    moved=False
    try:
        shutil.copyfile(source,pending)
        os.replace(target,previous);moved=True
        os.replace(pending,target)
        launch([str(target)])
    except Exception:
        if moved:os.replace(previous,target)
        raise
    finally:pending.unlink(missing_ok=True)

def apply_request(request_path,config):
    request_path=Path(request_path).resolve();source=Path(sys.executable).resolve()
    if request_path.parent!=source.parent:raise ValueError('Неверная папка обновления.')
    data=verify_manifest((source.parent/'app-update.json').read_bytes(),config)
    if data['version']!=config['app_version']:raise ValueError('Версия EXE не совпадает с подписью.')
    request=json.loads(request_path.read_text('utf-8'))
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x100000,False,int(request['parent_pid']))
    if handle:
        try:
            if kernel.WaitForSingleObject(handle,120000)!=0:raise TimeoutError('Программа не закрылась вовремя.')
        finally:kernel.CloseHandle(handle)
    # PyInstaller parent may briefly retain the old executable after its child exits.
    for attempt in range(20):
        try:
            replace_application(source,request['target'],data['sha256'],lambda command:subprocess.Popen(command,close_fds=True))
            return
        except PermissionError:
            if attempt==19:raise
            time.sleep(.5)
