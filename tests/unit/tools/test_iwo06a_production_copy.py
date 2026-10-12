"""Fresh-process canonical filename qualification within inherited kernel denial."""
from pathlib import Path
import subprocess
import sys
import pytest


def test_production_copy_canonical_composition(request):
    if not request.config.option.xmlpath:
        pytest.skip('Production-copy qualification requires explicit evidence directory')
    output=Path(request.config.option.xmlpath).parent
    if not (output/'production-authority-snapshot').is_dir():
        pytest.skip('Production authority snapshot is external immutable qualification evidence')
    child=Path(__file__).with_name('iwo06a_canonical_child.py')
    result=subprocess.run([sys.executable,str(child),str(output/'production-copy-child.xml')],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    (output/'production-copy-child.log').write_text(result.stdout)
    assert result.returncode==0,result.stdout
