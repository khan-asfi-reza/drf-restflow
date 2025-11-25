"""
MkDocs macros for drf-restflow documentation.

"""

import sys
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

try:
    from restflow import __version__
except ImportError:
    __version__ = "unknown"


def define_env(env):
    env.variables.version = __version__
    env.variables.version_human = f"v{__version__}"
