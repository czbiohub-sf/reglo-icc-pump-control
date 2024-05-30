from pathlib import Path
import sys
sys.path.insert(0, str(Path("..").resolve()))


project = 'reglo-icc-pump-control'
copyright = '2024, Greg Courville'
author = 'Greg Courville <greg.courville@czbiohub.org>'

extensions = ['sphinx.ext.autodoc']

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

html_theme = 'classic'
html_static_path = ['_static']

#autodoc_typehints = 'both'
