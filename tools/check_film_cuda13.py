"""CUDA 13 readiness probe for Windows PowerShell 5.1.

Called as a filename instead of python -c; native Windows argument parsing
must never strip the quote characters from Python source code.
Does not install, upgrade, import models, or write files.
"""
import sys


def main():
    try:
        import torch
        import PIL  # noqa: F401 - used by the Film runtime
        import numpy  # noqa: F401 - used by the Film runtime
    except ImportError as exc:
        print(f"FILM 5070: missing runtime dependency: {exc}", file=sys.stderr)
        return 2
    cuda = str(getattr(torch.version, "cuda", None) or "")
    if not torch.cuda.is_available():
        print("FILM 5070: PyTorch CUDA GPU is unavailable.", file=sys.stderr)
        return 3
    print(f"GPU: {torch.cuda.get_device_name(0)} | Torch CUDA: {cuda}", flush=True)
    if not cuda.startswith("13"):
        print("FILM 5070: expected an existing CUDA 13 PyTorch environment; no change was made.", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
