import base64,hashlib,io,json,tempfile,unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from updates import canonical,verify_catalog,download
class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate();self.config={'repository':'owner/repo','public_key':base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}
        self.pack={'map':'TheIsland','package_sha256':hashlib.sha256(b'good').hexdigest(),'size':4,'count':1,'filename':'island.zip','url':'https://github.com/owner/repo/releases/download/v1/island.zip'}
    def signed(self,data):return json.dumps({'payload':data,'signature':base64.b64encode(self.key.sign(canonical(data))).decode()})
    def test_signature(self):
        raw=self.signed({'schema':1,'packages':[self.pack]});self.assertEqual(verify_catalog(raw,self.config)['schema'],1)
        with self.assertRaises(Exception):verify_catalog(raw.replace('TheIsland','Extinction'),self.config)
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
if __name__=='__main__':unittest.main()
