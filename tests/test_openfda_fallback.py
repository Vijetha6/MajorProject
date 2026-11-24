import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app


def test_openfda_candidates_include_common_synonym():
    candidates = app.build_openfda_search_candidates('paracetamol')
    assert 'acetaminophen' in candidates


def test_openfda_candidates_preserve_strength_and_normalize_whitespace():
    candidates = app.build_openfda_search_candidates('  Paracetamol   500 mg ')

    assert candidates == ['Paracetamol 500 mg', 'acetaminophen 500 mg']


def test_openfda_candidates_are_bidirectional_and_ignore_unknown_aliases():
    assert app.build_openfda_search_candidates('acetaminophen') == [
        'acetaminophen',
        'paracetamol',
    ]
    assert app.build_openfda_search_candidates('amoxicillin') == ['amoxicillin']
    assert app.build_openfda_search_candidates('  ') == []
