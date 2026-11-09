"""Grade explicit scenario facts, then validate citations; no model judge."""
from __future__ import annotations
import json
from pathlib import Path
from fixtures import AXES, SCENARIOS


def evaluate(review: dict, oracle: dict, inputs: Path) -> dict:
    criteria=[]
    for scenario in SCENARIOS:
        for axis in AXES:
            value=review.get('scenarios',{}).get(scenario,{}).get(axis)
            expected=oracle['candidate'][scenario][axis]
            criteria.append({'scenario':scenario,'axis':axis,'expected':expected,'actual':value,
                             'passed':type(value) is bool and value==expected})
    citation_results=[]
    for c in review.get('citations',[]):
        try:
            path=Path(c['path'])
            if path.is_absolute() or '..' in path.parts or path.parts[0] not in ('previous','candidate'):
                raise ValueError('Citation must name an input-relative source file')
            lines=(inputs/path).read_text().splitlines()
            lo,hi=c['start_line'],c['end_line']
            if type(lo) is not int or type(hi) is not int or not 1<=lo<=hi<=len(lines):
                raise ValueError('Invalid source range')
            passed='\n'.join(lines[lo-1:hi])==c['quote']
            citation_results.append({'citation':c,'passed':passed})
        except (KeyError,ValueError,OSError,TypeError) as error:
            citation_results.append({'citation':c,'passed':False,'error':str(error)})
    citations_valid=bool(citation_results) and all(c['passed'] for c in citation_results)
    complete=sum(x['passed'] for x in criteria)
    return {'facts_correct':complete,'facts_total':len(criteria),'criteria':criteria,
            'citations_valid':citations_valid,'citations':citation_results,
            'passed':complete==len(criteria) and citations_valid,
            'limitation':'Exact facts and quotation ranges are graded. Whether the quoted code supports the explanation requires a separate semantic audit.'}


def parse_submission(text: str) -> dict:
    value=json.loads(text)
    if not isinstance(value,dict): raise ValueError('Review must be an object')
    if not isinstance(value.get('explanation'),str): raise ValueError('Missing explanation')
    if not isinstance(value.get('citations'),list): raise ValueError('Missing citations')
    return value
