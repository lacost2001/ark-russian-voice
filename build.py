"""Build the Windows installer from this source directory."""
import argparse
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=Path('dist'))
    args=parser.parse_args()
    source=Path(__file__).resolve().parent
    out=args.out.resolve()
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',
        '--onefile','--windowed','--name','ARK-Russian-Voice',
        '--distpath',str(out),'--workpath',str(out.parent/'build-2.4.0'),
        '--specpath',str(out.parent/'build-2.4.0'),
        '--add-data',str(source/'release_config.json')+';.',str(source/'launcher.py')],check=True)
