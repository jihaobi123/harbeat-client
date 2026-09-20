"""A fresh checkout must load the confirmed renderer without local deliveries."""
from pathlib import Path
from analysis_platform.colleague_policy import SOURCE, PACKAGE, load_policy
from analysis_platform.demo_v3 import load_renderer

def test_v3_sources_are_versioned_and_independent_of_outputs():
    assert 'outputs' not in SOURCE.parts
    assert 'outputs' not in PACKAGE.parts
    api=load_renderer(SOURCE)
    assert api['RENDER_GAIN']==.76
    assert load_policy({})['provenance']['colleague_source_sha256']
