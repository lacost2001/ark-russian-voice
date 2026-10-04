import base64,hashlib,io,json,tempfile,unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from updates import canonical,verify_catalog,download,load_settings
class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate();self.config={'repository':'owner/repo','public_key':base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}
        self.pack={'map':'TheIsland','package_sha256':hashlib.sha256(b'good').hexdigest(),'size':4,'count':1,'filename':'island.zip','url':'https://github.com/owner/repo/releases/download/v1/island.zip'}
    def signed(self,data):return json.dumps({'payload':data,'signature':base64.b64encode(self.key.sign(canonical(data))).decode()})
    def test_signature(self):
        raw=self.signed({'schema':1,'packages':[self.pack]});self.assertEqual(verify_catalog(raw,self.config)['schema'],1)
        with self.assertRaises(Exception):verify_catalog(raw.replace('TheIsland','Extinction'),self.config)
    def test_invalid_settings_recover(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'settings.json'
            for value in ['null','[]','42','broken']:
                p.write_text(value);self.assertEqual(load_settings(p)['maps'],['Shared','TheIsland'])
            p.write_text(json.dumps({'folder':12,'maps':['TheIsland','bogus'],'automatic':'no'}))
            self.assertEqual(load_settings(p),{'folder':'','maps':['TheIsland'],'automatic':True,'backup_folder':''})
    def test_additive_components(self):
        extra={**self.pack,'component':'additional','filename':'extra.zip'}
        raw=self.signed({'schema':2,'packages':[self.pack,extra]})
        self.assertEqual(len(verify_catalog(raw,self.config)['packages']),2)
        with self.assertRaises(ValueError):
            verify_catalog(self.signed({'schema':2,'packages':[extra,extra]}),self.config)
    def test_new_map_and_invalid_component(self):
        pack={**self.pack,'map':'Fjordur'}
        verify_catalog(self.signed({'schema':2,'packages':[pack]}),self.config)
        pack['component']='untrusted'
        with self.assertRaises(ValueError):
            verify_catalog(self.signed({'schema':2,'packages':[pack]}),self.config)
    def test_wrong_repository(self):
        self.pack['url']='https://attacker.invalid/island.zip'
        with self.assertRaises(ValueError):verify_catalog(self.signed({'schema':1,'packages':[self.pack]}),self.config)
    def test_corrupt_download_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):download(self.pack,temp,opener=lambda *a,**k:io.BytesIO(b'evil'))
            self.assertEqual(list(Path(temp).iterdir()),[])
            path=download(self.pack,temp,opener=lambda *a,**k:io.BytesIO(b'good'))
            self.assertEqual(path.read_bytes(),b'good')
            self.assertEqual(download(self.pack,temp,opener=lambda *a,**k:self.fail('cache should be reused')),path)
    def test_oversized_download(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):download(self.pack,temp,opener=lambda *a,**k:io.BytesIO(b'good-extra'))
            self.assertEqual(list(Path(temp).iterdir()),[])
    def test_transient_connection_retries_without_bad_cache(self):
        from unittest.mock import patch
        calls=[]
        def opener(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:raise ConnectionError('test disconnect')
            return io.BytesIO(b'good')
        with tempfile.TemporaryDirectory() as temp,patch('updates.time.sleep'):
            self.assertEqual(download(self.pack,temp,opener=opener).read_bytes(),b'good')
            self.assertEqual(len(calls),2)
            self.assertFalse(list(Path(temp).glob('*.part')))
if __name__=='__main__':unittest.main()
