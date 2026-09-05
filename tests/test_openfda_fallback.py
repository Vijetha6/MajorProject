import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app


def test_openfda_candidates_include_common_synonym():
    candidates = app.build_openfda_search_candidates('paracetamol')
    assert 'acetaminophen' in candidates
