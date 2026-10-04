"""Signed catalog and verified downloads. Players need no accounts or API keys."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request
import urllib.error
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAPS={'Shared':'Общие реплики HLN-A','TheIsland':'The Island','ScorchedEarth':'Scorched Earth','Aberration':'Aberration','Extinction':'Extinction','Genesis1':'Genesis: Part 1','Genesis2':'Genesis: Part 2','Ragnarok':'Ragnarok','Valguero':'Valguero','CrystalIsles':'Crystal Isles','LostIsland':'Lost Island','Fjordur':'Fjordur'}
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
def verify_catalog(raw,config):
    envelope=json.loads(raw);data=envelope['payload']
    Ed25519PublicKey.from_public_bytes(base64.b64decode(config['public_key'])).verify(base64.b64decode(envelope['signature']),canonical(data))
    if data['schema'] not in (1,2):raise ValueError('Нужна новая версия программы.')
    seen=set()
    for pack in data['packages']:
        identity=(pack['map'],pack.get('component','base'))
        if pack['map'] not in MAPS or identity in seen:raise ValueError('Неверный список карт.')
        if pack.get('component','base') not in ('base','additional'):raise ValueError('Неверный компонент пакета.')
        seen.add(identity)
        if not re.fullmatch('[0-9a-f]{64}',pack['package_sha256']):raise ValueError('Неверная контрольная сумма.')
        if not (0<pack['size']<2_000_000_000 and 0<pack['count']<10000):raise ValueError('Неверный размер пакета.')
        if not re.fullmatch('[A-Za-z0-9_.-]+[.]zip',pack['filename']):raise ValueError('Неверное имя пакета.')
        if not pack['url'].startswith('https://github.com/'+config['repository']+'/releases/download/'):raise ValueError('Неизвестный источник обновления.')
    return data
def fetch_catalog(config,cache,opener=urllib.request.urlopen):
    url='https://github.com/'+config['repository']+'/releases/latest/download/catalog.json'
    with opener(urllib.request.Request(url,headers={'User-Agent':'ARK-Russian-Voice/2.0','Cache-Control':'no-cache'}),timeout=20) as response:raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('Слишком большой каталог.')
    data=verify_catalog(raw,config);cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    temp=cache/'catalog.tmp';temp.write_bytes(raw);os.replace(temp,cache/'catalog.json');return data
def download(pack,cache,progress=lambda text,value:None,opener=urllib.request.urlopen):
    for attempt in range(3):
        try:return _download_once(pack,cache,progress,opener)
        except (urllib.error.URLError,TimeoutError,ConnectionError) as error:
            if isinstance(error,urllib.error.HTTPError) and error.code not in (408,429,500,502,503,504):raise
            if attempt==2:raise
            progress('Соединение прервалось. Повтор загрузки '+str(attempt+2)+' из 3…',0)
            time.sleep(attempt+1)

def _download_once(pack,cache,progress=lambda text,value:None,opener=urllib.request.urlopen):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True);target=cache/(pack['package_sha256']+'.zip')
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==pack['package_sha256']:return target
    partial=target.with_suffix('.part')
    try:
        total=0;hasher=hashlib.sha256()
        with opener(urllib.request.Request(pack['url'],headers={'User-Agent':'ARK-Russian-Voice/2.0'}),timeout=30) as response,partial.open('wb') as stream:
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                total+=len(chunk)
                if total>pack['size']:raise ValueError('Размер загрузки не соответствует каталогу.')
                hasher.update(chunk);stream.write(chunk)
                progress('Загрузка '+MAPS[pack['map']]+f': {total//1048576} / {pack["size"]//1048576} МБ',int(total*100/pack['size']))
        if total!=pack['size'] or hasher.hexdigest()!=pack['package_sha256']:raise ValueError('Загрузка повреждена. Игра не изменена.')
        os.replace(partial,target);return target
    finally:partial.unlink(missing_ok=True)
def load_settings(path):
    defaults={'folder':'','maps':['Shared','TheIsland'],'automatic':True,'backup_folder':''}
    try:
        data=json.loads(Path(path).read_text('utf-8'))
        if not isinstance(data,dict):return defaults
        for key in ('folder','backup_folder'):
            if isinstance(data.get(key),str):defaults[key]=data[key]
        if isinstance(data.get('automatic'),bool):defaults['automatic']=data['automatic']
        if isinstance(data.get('maps'),list):defaults['maps']=[m for m in MAPS if m in data['maps']]
        return defaults
    except (OSError,ValueError):return defaults
def save_settings(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');os.replace(temp,path)
