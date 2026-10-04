import base64,hashlib,io,json,tempfile,unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app_update import verify_manifest,prepare_update,replace_application,version
from updates import canonical

class AppUpdateTests(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        self.config={'repository':'owner/repo','app_version':'2.4.0','public_key':base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}
        self.data={'schema':1,'version':'2.5.0','url':'https://github.com/owner/repo/releases/download/v2.5.0/ARK-Russian-Voice.exe','sha256':hashlib.sha256(b'new-exe').hexdigest(),'size':7}
    def signed(self):
        return json.dumps({'payload':self.data,'signature':base64.b64encode(self.key.sign(canonical(self.data))).decode()}).encode()
    def test_signature_and_origin(self):
        raw=self.signed();self.assertEqual(verify_manifest(raw,self.config)['version'],'2.5.0')
        with self.assertRaises(Exception):verify_manifest(raw.replace(b'2.5.0',b'9.5.0'),self.config)
        self.data['url']='https://example.com/evil.exe'
        with self.assertRaises(ValueError):verify_manifest(self.signed(),self.config)
    def test_download_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):prepare_update(self.signed(),self.config,temp,opener=lambda *a,**k:io.BytesIO(b'bad-exe'))
            self.assertFalse(list(Path(temp).rglob('*.exe')))
            self.assertFalse(list(Path(temp).rglob('*.part')))
    def test_update_download_and_no_downgrade(self):
        with tempfile.TemporaryDirectory() as temp:
            result=prepare_update(self.signed(),self.config,temp,opener=lambda *a,**k:io.BytesIO(b'new-exe'))
            self.assertEqual(result.read_bytes(),b'new-exe')
            self.config['app_version']='2.5.0'
            self.assertIsNone(prepare_update(self.signed(),self.config,temp,opener=lambda *a,**k:self.fail('unneeded download')))
    def test_swap_preserves_previous(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'new.exe';source.write_bytes(b'new-exe')
            target=Path(temp)/'installed.exe';target.write_bytes(b'old-exe');calls=[]
            replace_application(source,target,self.data['sha256'],calls.append)
            self.assertEqual(target.read_bytes(),b'new-exe')
            self.assertEqual(target.with_name('installed.exe.previous').read_bytes(),b'old-exe')
            self.assertEqual(calls,[[str(target.resolve())]])
    def test_launch_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'new.exe';source.write_bytes(b'new-exe')
            target=Path(temp)/'installed.exe';target.write_bytes(b'old-exe')
            def fail(command):raise OSError('process creation failed')
            with self.assertRaises(OSError):replace_application(source,target,self.data['sha256'],fail)
            self.assertEqual(target.read_bytes(),b'old-exe')
            self.assertFalse(target.with_name('installed.exe.pending').exists())
    def test_version_order(self):
        self.assertGreater(version('2.10.0'),version('2.9.0'))
        with self.assertRaises(ValueError):version('../../evil')

if __name__=='__main__':unittest.main()
