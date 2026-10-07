# detection/__init__.py
from .detector import Detector
from .tracker import extract_tracks

# REMOVA esta linha:
# from .strongsort import StrongSORT

__all__ = ['Detector', 'extract_tracks']