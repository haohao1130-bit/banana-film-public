"""BANANA FILM 5070 Windows environment probe.

Backend just hosts the UI and talks to ComfyUI over HTTP; it does not execute
CUDA models. Therefore CUDA 12.9 in a backend-only Python is supported.
Only the Python interpreter used to START ComfyUI must be CUDA 13.
"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("backend", "comfy"), default="comfy")
    args = parser.parse_args()
    try:
        import PIL  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as exc:
        print(f"FILM 5070: missing Python library: {exc}", file=sys.stderr)
        return 2
    if args.role == "backend":
        print("FILM V2 backend ready (Pillow + NumPy). GPU models run in ComfyUI.", flush=True)
        return 0
    try:
        import torch
    except ImportError as exc:
        print(f"FILM 5070 ComfyUI Python missing torch: {exc}", file=sys.stderr)
        return 2
    cuda = str(getattr(torch.version, "cuda", None) or "")
    if not torch.cuda.is_available():
        print("FILM 5070 ComfyUI Python: CUDA GPU is unavailable.", file=sys.stderr)
        return 3
    print(f"ComfyUI GPU: {torch.cuda.get_device_name(0)} | Torch CUDA: {cuda}", flush=True)
    if not cuda.startswith("13"):
        print("FILM 5070: ComfyUI auto-start requires existing CUDA 13 PyTorch.", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
