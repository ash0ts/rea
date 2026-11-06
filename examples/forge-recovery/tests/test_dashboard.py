import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def dashboard():
    path = Path(__file__).resolve().parents[1] / 'notebooks/publish_dashboard.py'
    spec = importlib.util.spec_from_file_location('dashboard_test',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dashboard_unknowns_do_not_become_zeros(dashboard):
    result = dashboard.measurements({'task_status':'timeout','usage':{'unknown_usage_requests':1,'input_tokens':100,'output_tokens':3},'checker':None,'agent_resources':None}, {})
    assert result['task_tokens'] is None
    assert result['passed_all_checks'] is None
    assert result['checks_available'] == 0
    assert result['agent_cpu_seconds'] is None
    assert result['rea_returned_calls'] is None
    failed = dashboard.measurements({'task_status':'budget_stop','checker':{'passed':False},'usage':{'unknown_usage_requests':0,'input_tokens':100,'output_tokens':3}}, {'rea_returned_calls':0})
    assert failed['task_tokens'] == 103
    assert failed['passed_all_checks'] == 0
    assert failed['checks_available'] == 1
    assert failed['rea_returned_calls'] == 0


@pytest.mark.parametrize('url', [
    'https://wandb.ai/wandb/rea-showcase?nw=owned',
    'https://forge.coreweave.com/wandb/rea-showcase?nw=owned',
    'https://forge.coreweave.com/wandb/wandb/rea-showcase?nw=owned',
])
def test_dashboard_urls_retain_forge_route_and_saved_view(dashboard,url):
    assert dashboard.forge_url(url,'wandb','rea-showcase') == 'https://forge.coreweave.com/wandb/wandb/rea-showcase?nw=owned'


def test_dashboard_navigation_retains_unrun_attempts(dashboard):
    planned=[{'attempt_id':'a','fixture':'basic','arm':'baseline','repetition':1},
             {'attempt_id':'b','fixture':'basic','arm':'rea','repetition':1}]
    table=dashboard.navigation({'planned':planned,'attempts':[{'attempt_id':'a','task_status':'timeout'}]})
    assert '| baseline | 1 | timeout | Unavailable |' in table
    assert '| rea | 1 | Not run | Unavailable |' in table
