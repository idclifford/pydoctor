"""
Package directory used to store pydoctor templates.

Usage example:

>>> template_lookup = TemplateLookup(importlib_resources.files('pydoctor.themes') / 'base')
"""
from typing import Iterator

# In newer Python versions, use importlib.resources from the standard library.
# On older versions, a compatibility package must be installed from PyPI.
import importlib.resources as importlib_resources

def get_themes() -> Iterator[str]:
    """
    Get the list of the available themes.
    """
    for path in importlib_resources.files('pydoctor.themes').iterdir():
        if not path.name.startswith('_') and not path.is_file():
            yield path.name
