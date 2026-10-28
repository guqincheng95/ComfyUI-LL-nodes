"""Explicit, hash-verified optional parsing setup. Does not install Torch/CUDA."""
import argparse
from importlib.metadata import version,PackageNotFoundError
from pathlib import Path
import subprocess
import sys
import tempfile

MODEL_REVISION='584abc1e1d260e23c0fc627c5217a09b2b461046'
MODEL_URL='https://huggingface.co/mattmdjaga/segformer_b2_clothes/resolve/'+MODEL_REVISION+'/onnx/model.onnx'
MODEL_SIZE=110039290
MODEL_SHA256='a93a8dac171b5c1fcc53632a8bfc180bfd9759ea69a3e207451bb07f76add54f'


def main():
    parser=argparse.ArgumentParser(description='Check local ATR ONNX model/runtime; explicit flags install/download. Upstream weights: research/evaluation license.')
    parser.add_argument('--model-path',type=Path,default=Path(__file__).resolve().parents[3]/'models/segformer_b2_clothes/onnx/model.onnx')
    parser.add_argument('--install-runtime',action='store_true')
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--model-url',default=MODEL_URL,help='HTTPS mirror URL; original SHA256 is always checked')
    args=parser.parse_args()
    print('Python:',sys.executable,flush=True)
    if args.install_runtime:
        try:
            import onnxruntime
            print('ONNX Runtime already available:',onnxruntime.__version__,flush=True)
        except ImportError:
            try:numpy_version=version('numpy')
            except PackageNotFoundError:raise SystemExit('NumPy is missing; run in the ComfyUI Python environment.')
            with tempfile.TemporaryDirectory(prefix='ll-onnx-') as folder:
                constraints=Path(folder)/'constraints.txt';constraints.write_text('numpy=='+numpy_version+'\n')
                subprocess.run([sys.executable,'-m','pip','install','--constraint',str(constraints),'onnxruntime>=1.17,<2'],check=True)
    try:
        from subject_models import verify,download
    except ImportError:
        from .subject_models import verify,download
    if not verify(args.model_path,MODEL_SIZE,MODEL_SHA256) and args.download:
        print('Downloading ATR model (110 MB); upstream NVIDIA SegFormer license applies.',flush=True)
        download(args.model_url,args.model_path,MODEL_SIZE,MODEL_SHA256)
    try:
        import onnxruntime as ort
    except ImportError:
        raise SystemExit('ONNX Runtime is missing; use --install-runtime with the ComfyUI Python executable.')
    if not verify(args.model_path,MODEL_SIZE,MODEL_SHA256):
        raise SystemExit('Model missing/hash mismatch: '+str(args.model_path)+'; use --download or copy the official ONNX file here.')
    session=ort.InferenceSession(str(args.model_path),providers=['CPUExecutionProvider'])
    print('SUCCESS: runtime and verified local model loaded.',flush=True)
    print('Input:',[(x.name,x.shape) for x in session.get_inputs()],flush=True)
    print('Model:',args.model_path,flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
