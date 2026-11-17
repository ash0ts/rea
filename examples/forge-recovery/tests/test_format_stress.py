"""The extra corpus must break the specific correlations found in the first one."""
import importlib.util
from pathlib import Path

source = Path(__file__).resolve().parents[1] / 'format_stress/fixtures.py'
spec = importlib.util.spec_from_file_location('format_stress_fixtures', source)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def test_chunk_logical_order_cannot_be_replaced_by_sorting_record_ids():
    for version in (1, 2):
        for flags in range(4):
            for pattern in (0, 1):
                _, expected = fixtures.make('chunks', version, flags, pattern)
                ids = [r['id'] for r in expected['records']]
                assert ids != sorted(ids) and ids != sorted(ids, reverse=True)


def test_tree_ancestor_visibility_varies_within_each_version_and_flag():
    for version in (1, 2):
        for flags in range(4):
            for pattern in (0, 1):
                _, expected = fixtures.make('tree', version, flags, pattern)
                nested = [r for r in expected['records'] if r['label'].startswith('z-root/')]
                assert nested
                assert any(r['active'] for r in nested) == (pattern == 0)
                roots = [r for r in expected['records'] if r['label'].startswith('a-root/')]
                assert any(r['active'] for r in roots)
