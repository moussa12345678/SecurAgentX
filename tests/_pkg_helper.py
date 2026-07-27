"""Helper to get the actual package name from the filesystem."""
import os

# Resolve the package directory (it's the directory under cwd starting with 'secur')
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
_dirs = [d for d in os.listdir(_root) 
         if os.path.isdir(os.path.join(_root, d)) 
         and d.startswith('secur') 
         and '.' not in d
         and d != 'securagentx.egg-info']

if _dirs:
    PACKAGE = _dirs[0]
else:
    PACKAGE = 'securagentx'  # fallback
