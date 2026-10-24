"""Explicit download/check of default v0.6 weights; standard library only."""
import argparse
import hashlib
from pathlib import Path
import tempfile
import urllib.request

WEIGHTS={
 'sam2.1_hiera_tiny.pt':('https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt',156008466,'7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69'),
 'deeplabv3_mobilenet_v3_large-fc3c493d.pth':('https://download.pytorch.org/models/deeplabv3_mobilenet_v3_large-fc3c493d.pth',44356159,'fc3c493d68e89cc31ef488c803d5d7dd2f3190fb570598faa49fef69be8e5e70'),
}


def verify(path,size,digest):
    if not path.is_file() or path.stat().st_size!=size:return False
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()==digest


def download(url,path,size,digest):
    if not url.startswith('https://'):raise ValueError('下载源必须使用HTTPS。')
    path.parent.mkdir(parents=True,exist_ok=True)
    part=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False,suffix='.part') as f:
            part=Path(f.name);received=0
            with urllib.request.urlopen(url,timeout=30) as response:
                while block:=response.read(1024*1024):
                    received+=len(block)
                    if received>size:raise ValueError('下载超过预期大小。')
                    f.write(block)
        if not verify(part,size,digest):raise ValueError('模型大小或SHA256校验失败，保留现有文件。')
        part.replace(path)
    finally:
        if part is not None and part.exists():part.unlink()


def main():
    parser=argparse.ArgumentParser(description='检查默认人物提取模型；只有--download才联网下载。')
    parser.add_argument('--directory',type=Path,default=Path(__file__).resolve().parents[3]/'models'/'sam2')
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--sam-url',help='SAM2模型镜像完整HTTPS地址，仍须通过原文件SHA256校验')
    parser.add_argument('--person-url',help='人物语义模型镜像完整HTTPS地址，仍须通过原文件SHA256校验')
    args=parser.parse_args();ok=True
    for name,(official,size,digest) in WEIGHTS.items():
        path=args.directory/name
        if not verify(path,size,digest) and args.download:
            url=(args.sam_url if name.startswith('sam2') else args.person_url) or official
            print('下载并校验：'+name,flush=True);download(url,path,size,digest)
        valid=verify(path,size,digest);ok&=valid
        print(('OK ' if valid else '缺失或校验不符 ')+str(path))
    return 0 if ok else 1


if __name__=='__main__':raise SystemExit(main())
