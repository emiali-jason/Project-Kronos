"""Test-only compile-filename adapter for legacy production capability identity.

Physical source and every writable store remain in the isolated test estate.
The production checkout is never read or written by this adapter.
"""
from pathlib import Path
import importlib.abc
import importlib.machinery
import importlib.util
import json
from hashlib import sha256
import sys

ROOT=Path(__file__).resolve().parents[3]
CANONICAL=Path('/Users/imranali/Documents/GitHub/Project-Kronos')
LOADED={}

class CandidateLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        source=self.get_data(self.path)
        relative=str(Path(self.path).relative_to(ROOT))
        LOADED[relative]=sha256(source).hexdigest()
        logical=CANONICAL/relative
        return compile(source,str(logical),'exec',dont_inherit=True)

class CandidateFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith('kronos.'):
            return None
        physical=ROOT/'src'/Path(*fullname.split('.'))
        package=physical/'__init__.py'
        filename=package if package.is_file() else physical.with_suffix('.py')
        if not filename.is_file():
            return None
        return importlib.util.spec_from_file_location(fullname,filename,
            loader=CandidateLoader(fullname,str(filename)),
            submodule_search_locations=[str(physical)] if filename==package else None)

sys.meta_path.insert(0,CandidateFinder())
from kronos.intraday import runtime_identity

def canonical_pinned_code(self, fullname):
    relative=str(Path(self.filename).relative_to(ROOT))
    LOADED[relative]=sha256(self.payload).hexdigest()
    return compile(self.payload,str(CANONICAL/relative),'exec',dont_inherit=True)
runtime_identity._PinnedLoader.get_code=canonical_pinned_code

import pytest
result=pytest.main([str(ROOT/'tests/unit/tools/test_iwo06a_post_expiry.py'),
    '-q','-k','production_copy','--junitxml='+sys.argv[1]])
for relative,digest in LOADED.items():
    assert sha256((ROOT/relative).read_bytes()).hexdigest()==digest
Path(sys.argv[1]).with_name('production-copy-loaded-source.json').write_text(json.dumps(LOADED,indent=2)+'\n')
raise SystemExit(result)
