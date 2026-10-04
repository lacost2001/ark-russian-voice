import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from installer_core import apply,game_candidates,safe_path,preflight_packages

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.game=self.root/'SteamLibrary/steamapps/common/ARK'
        exe=self.game/'ShooterGame/Binaries/Win64/ShooterGame.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'exe')
        self.paths=['ShooterGame/Content/PrimalEarth/Sound/SFX/Characters/Helena/'+n+'.uasset' for n in ['one','two']]
        entries=[]
        self.package=self.root/'voices.zip'
        with zipfile.ZipFile(self.package,'w') as z:
            for p in self.paths:
                target=self.game/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'original')
                entries.append({'path':p,'original_sha256':hashlib.sha256(b'original').hexdigest(),'new_sha256':hashlib.sha256(b'new').hexdigest()})
                z.writestr('files/'+p,b'new')
            z.writestr('manifest.json',json.dumps({'entries':entries}))
        self.config={'count':2,'package_sha256':hashlib.sha256(self.package.read_bytes()).hexdigest()}
    def install(self,restore=False):return apply(self.game,self.package,self.config,restore,check_running=lambda:False)
    def test_install_repeat_restore(self):
        self.assertEqual(self.install(),2);self.assertEqual(self.install(),0)
        self.assertTrue(all((self.game/p).read_bytes()==b'new' for p in self.paths))
        self.assertEqual(self.install(True),2)
        self.assertTrue(all((self.game/p).read_bytes()==b'original' for p in self.paths))
    def test_mismatch_changes_nothing(self):
        (self.game/self.paths[1]).write_bytes(b'unknown-build')
        with self.assertRaises(ValueError):self.install()
        self.assertEqual((self.game/self.paths[0]).read_bytes(),b'original')
    def test_legacy_originals_recovered_and_restore_works(self):
        legacy=self.root/'legacy'
        for path in self.paths:
            (self.game/path).write_bytes(b'new')
            source=legacy/path;source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(b'original')
        options=dict(check_running=lambda:False,legacy_roots=[legacy])
        apply(self.game,self.package,self.config,dry_run=True,**options)
        self.assertFalse((self.game/'.ark-russian-voice-backup').exists())
        self.assertEqual(apply(self.game,self.package,self.config,**options),0)
        self.assertEqual(self.install(True),2)
        self.assertTrue(all((self.game/p).read_bytes()==b'original' for p in self.paths))
    def test_wrong_legacy_copy_is_rejected(self):
        legacy=self.root/'legacy'
        for path in self.paths:
            (self.game/path).write_bytes(b'new')
            source=legacy/path;source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(b'wrong-original')
        with self.assertRaisesRegex(ValueError,'Найдена прежняя озвучка'):
            apply(self.game,self.package,self.config,check_running=lambda:False,legacy_roots=[legacy])
        self.assertFalse((self.game/'.ark-russian-voice-backup').exists())
    def test_all_packages_preflight_before_any_writes(self):
        invalid=self.root/'invalid.zip';invalid.write_bytes(b'broken')
        with self.assertRaises(ValueError):
            preflight_packages(self.game,[(self.package,self.config),(invalid,self.config)],check_running=lambda:False)
        self.assertTrue(all((self.game/p).read_bytes()==b'original' for p in self.paths))
        self.assertFalse((self.game/'.ark-russian-voice-backup').exists())
    def test_upgrade_preserves_original_and_restores(self):
        self.install()
        original=hashlib.sha256(b'original').hexdigest();previous=hashlib.sha256(b'new').hexdigest()
        with zipfile.ZipFile(self.package,'w') as z:
            entries=[]
            for p in self.paths:
                entries.append({'path':p,'original_sha256':original,'new_sha256':hashlib.sha256(b'updated').hexdigest(),'previous_sha256':[previous]})
                z.writestr('files/'+p,b'updated')
            z.writestr('manifest.json',json.dumps({'entries':entries}))
        self.config['package_sha256']=hashlib.sha256(self.package.read_bytes()).hexdigest()
        self.assertEqual(self.install(),2)
        self.assertEqual((self.game/'.ark-russian-voice-backup'/(original+'.uasset')).read_bytes(),b'original')
        self.assertEqual(self.install(True),2)
        self.assertTrue(all((self.game/p).read_bytes()==b'original' for p in self.paths))
    def test_corrupt_payload_changes_nothing(self):
        with self.package.open('ab') as f:f.write(b'corrupt')
        with self.assertRaises(ValueError):self.install()
        self.assertEqual((self.game/self.paths[0]).read_bytes(),b'original')
    def test_running_game(self):
        with self.assertRaises(ValueError):apply(self.game,self.package,self.config,check_running=lambda:True)
    def test_path_escape(self):
        for p in ['../escape.uasset','C:/escape.uasset','ShooterGame/../escape.uasset']:
            with self.assertRaises(ValueError):safe_path(self.game,p)
    def test_genesis_paths_and_neighbors(self):
        for p in ['ShooterGame/Content/Genesis/Sound/Characters/HLNA/Glitches/English/a.uasset',
                  'ShooterGame/Content/Genesis2/Sounds/Characters/HLNA/Chronicles/a.uasset']:
            self.assertEqual(safe_path(self.game,p),self.game/p)
        for p in ['ShooterGame/Content/Genesis/Sound/Characters/HLNA/Glitches/English/../../a.uasset',
                  'ShooterGame/Content/Genesis/Sound/Characters/HLNA/Glitches/English/a.exe',
                  'ShooterGame/Content/Genesis2/Sounds/Characters/HLNA/Other/a.uasset']:
            with self.assertRaises(ValueError):safe_path(self.game,p)
    def test_cinematic_allowlist(self):
        for p in ['ShooterGame/Content/Movies/TheIsland_in.mp4','ShooterGame/Content/Movies/Extinction_in.wmv',
                  'ShooterGame/Content/Extinction/Matinee/Ascension/Sound/s_ascension_vo_01.uasset']:
            self.assertEqual(safe_path(self.game,p),self.game/p)
        for p in ['ShooterGame/Content/Movies/unknown.mp4','ShooterGame/Content/Movies/TheIsland_in.exe',
                  'ShooterGame/Content/Movies/../Movies/TheIsland_in.mp4']:
            with self.assertRaises(ValueError):safe_path(self.game,p)
    def test_steam_library_detection(self):
        self.assertEqual(game_candidates(self.root/'SteamLibrary'),[self.game.resolve()])
    def test_rollback_write_failure(self):
        from unittest.mock import patch
        import os
        real=os.replace;calls=[]
        def fail_second(a,b):
            calls.append(b)
            if len(calls)==2:raise OSError('simulated disk failure')
            return real(a,b)
        with patch('installer_core.os.replace',side_effect=fail_second):
            with self.assertRaises(OSError):self.install()
        self.assertTrue(all((self.game/p).read_bytes()==b'original' for p in self.paths))

if __name__=='__main__':unittest.main()
