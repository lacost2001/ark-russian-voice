"""Sign a prepared catalog. The private key must remain outside the repository."""
import argparse,base64,json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from updates import canonical
p=argparse.ArgumentParser();p.add_argument('catalog');p.add_argument('--key',required=True);p.add_argument('--output',required=True);a=p.parse_args()
data=json.loads(Path(a.catalog).read_text('utf-8'));key=Ed25519PrivateKey.from_private_bytes(Path(a.key).read_bytes())
Path(a.output).write_text(json.dumps({'payload':data,'signature':base64.b64encode(key.sign(canonical(data))).decode()},ensure_ascii=False,indent=2),encoding='utf-8')
