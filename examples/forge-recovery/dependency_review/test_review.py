import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from fixtures import prepare, CASES, SCENARIOS, AXES
from checker import evaluate
from run import source_tool


def test_read_boundary_and_numbered_evidence(tmp_path):
    prepare(tmp_path)
    inputs=tmp_path/'inputs/build_hook'
    value=source_tool('read_file',{'path':'candidate/install.js'},inputs)
    assert value['lines'][0]['line']==1
    assert "require('fs')" in value['lines'][0]['text']
    with pytest.raises(ValueError): source_tool('read_file',{'path':'../../oracle.json'},inputs)
    with pytest.raises(ValueError): source_tool('read_file',{'path':'/etc/passwd'},inputs)
    assert source_tool('search',{'text':'build-token'},inputs)['total_matches']==0


def test_false_boolean_and_fabricated_citation_do_not_pass(tmp_path):
    prepare(tmp_path);inputs=tmp_path/'inputs/build_hook'
    expected={s:{a:False for a in AXES} for s in SCENARIOS};expected['install']['writes_generated_file']=True
    review={'scenarios':json.loads(json.dumps(expected)),'citations':[{'path':'candidate/install.js','start_line':1,'end_line':1,'quote':"const fs = require('fs');"}]}
    assert evaluate(review,{'candidate':expected},inputs)['passed']
    review['scenarios']['install']['writes_generated_file']='true'
    result=evaluate(review,{'candidate':expected},inputs)
    assert result['facts_correct']==8 and not result['passed']
    review['scenarios']['install']['writes_generated_file']=True
    review['citations'][0]['quote']='invented code'
    assert not evaluate(review,{'candidate':expected},inputs)['passed']


def test_fixture_archives_are_repeatable_and_unreachable_code_is_distinct(tmp_path):
    prepare(tmp_path/'a');prepare(tmp_path/'b')
    for case in CASES:
        assert (tmp_path/'a/inputs'/case/'candidate.tgz').read_bytes()==(tmp_path/'b/inputs'/case/'candidate.tgz').read_bytes()
    d=tmp_path/'a/inputs/unreachable_helper/candidate'
    assert (d/'collect.js').exists()
    assert "require('./collect')" not in (d/'index.js').read_text()
