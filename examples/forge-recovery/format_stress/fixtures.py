"""Extra semantic coverage; independent Python encoding, frozen JS validation."""
import copy
import json
import random
import struct
import zlib
from pathlib import Path

NAMES = ['oak', 'café', '東京', '', 'rivet-Δ', 'leaf', 'with space', 'β', '𐐀']
MAGIC = {'chunks': b'CHNK', 'journal': b'JRNL', 'columns': b'COLM', 'tree': b'TREE'}


def var(n):
    assert 0 <= n < 2**32
    out = bytearray()
    while n >= 128:
        out.append((n & 127) | 128)
        n >>= 7
    return bytes(out) + bytes([n])


def signed(n): return var(2*n if n >= 0 else -2*n-1)
def text(s):
    raw = s.encode('utf-8')
    return var(len(raw)) + raw


def wrap(case, version, flags, count, body):
    return MAGIC[case] + struct.pack('<BBHII', version, flags, count, len(body), zlib.crc32(body)) + body


def dictionary(names): return var(len(names)) + b''.join(text(s) for s in names)


def records(seed, n):
    rng = random.Random(seed)
    ids = rng.sample(range(17, 3000), n)
    return [dict(id=id, label=NAMES[(i+seed) % len(NAMES)], value=rng.randint(-20000, 20000), active=(i+seed) % 3 != 0) for i, id in enumerate(ids)]


def chunk_file(rows, version, flags, seed, defect=None):
    rng = random.Random(seed)
    groups = [rows[:1], rows[1:3], rows[3:]]
    blobs = [zlib.compress(b''.join(struct.pack('<I', r['id']) + text(r['label']) + struct.pack('<iB', -r['value'] if version == 2 else r['value'], r['active']) for r in group)) for group in groups]
    if defect == 'chunk-trailing': blobs[1] = zlib.compress(zlib.decompress(blobs[1]) + b'\0')
    physical = [2, 0, 1] if seed % 2 else [1, 2, 0]
    cursor = 1 + 12*len(groups); entries = {}; payload = b''
    for i in physical:
        entries[i] = [3+i*7, len(groups[i]), cursor, len(blobs[i])]
        payload += blobs[i]; cursor += len(blobs[i])
    if defect == 'duplicate-slot': entries[2][0] = entries[0][0]
    if defect == 'chunk-overlap': entries[1][2] = entries[0][2]
    order = [0, 2, 1]; rng.shuffle(order)
    body = bytes([len(groups)]) + b''.join(struct.pack('<HHII', *entries[i]) for i in order) + payload
    count = len(rows) + (1 if defect == 'count' else 0)
    return wrap('chunks', version, flags, count, body)


def journal_file(rows, version, flags, pattern, defect=None):
    names = list(dict.fromkeys([r['label'] for r in rows] + ['changed', 'committed']))
    ops = []; state = {}; saved = None
    def put(r):
        prior = state.get(r['id'])
        encoded = r['value'] - (prior['value'] if prior and version == 2 else 0)
        ops.append(b'\1' + var(r['id']) + var(names.index(r['label'])) + signed(encoded) + bytes([r['active']]))
        state[r['id']] = dict(r)
    def delete(id):
        ops.append(b'\2' + var(id)); state.pop(id, None)
    for r in rows: put(r)
    ops.append(b'\3'); saved = copy.deepcopy(state)
    delete(rows[0]['id']); put({**rows[1], 'value': 731, 'label': 'changed', 'active': False})
    ops.append(b'\5'); state = saved
    ops.append(b'\3')
    put({**rows[0], 'value': -913, 'label': 'committed', 'active': True})
    put({**rows[-1], 'value': 1258, 'active': False})
    if pattern: delete(rows[2]['id'])
    ops.append(b'\4')
    # Repeated update outside a transaction must use the version-specific encoding.
    put({**state[rows[0]['id']], 'value': 61})
    delete(999999)  # deleting an absent record is accepted by the shipped reader
    if defect == 'nested': ops.extend([b'\3', b'\3'])
    elif defect == 'orphan-commit': ops.append(b'\4')
    elif defect == 'orphan-abort': ops.append(b'\5')
    elif defect == 'open-transaction': ops.append(b'\3')
    body = dictionary(names) + b''.join(ops)
    return wrap('journal', version, flags, len(ops), body), sorted(state.values(), key=lambda r: r['id'])


def column_file(rows, version, flags, pattern, defect=None):
    names = list(NAMES) + ['unused', 'oak']
    # Equal adjacent IDs are valid; the reader does not impose uniqueness.
    gaps = [0, 1, 0, 128, 9000, 0, 2, 127, 3]; total = 4
    output = []
    for i, r in enumerate(rows):
        total += gaps[i]; output.append({**r, 'id': total, 'active': (i % 3 == 1) if pattern else True})
    ids = b''; prior = 0
    for r in output: ids += var(r['id']-prior); prior = r['id']
    values = b''; prior = 0
    for r in output: values += signed(r['value']-prior); prior = r['value']
    label_indices = [names.index(r['label']) for r in output]
    if defect == 'label-index': label_indices[0] = len(names)
    labels = b''.join(var(n) for n in label_indices)
    bits = bytearray((len(output)+7)//8)
    for i, r in enumerate(output): bits[i//8] |= int(r['active']) << (i%8)
    if defect == 'padding': bits[-1] |= 128
    body = dictionary(names) + ids + (labels+values if version == 1 else values+labels) + bits
    if defect == 'body-trailing': body += b'\0'
    if defect == 'body-truncated': body = body[:-1]
    if flags & 2: body = zlib.compress(body)
    return wrap('columns', version, flags, len(output), body), output


def tree_file(rows, version, flags, pattern, seed, defect=None):
    # Paths are intended independently of physical order. Parent IDs may appear later.
    nodes = [dict(id=1, parent=0, kind=0, name='z-root', hidden=pattern),
             dict(id=2, parent=1, kind=0, name='branch', hidden=0),
             dict(id=3, parent=2, kind=0, name='deep', hidden=0),
             dict(id=4, parent=0, kind=0, name='a-root', hidden=0)]
    output = []
    for i, r in enumerate(rows):
        parent, prefix, inherited = ((3, 'z-root/branch/deep/', bool(pattern)) if i % 2 else (4, 'a-root/', False))
        name = (r['label'] or 'empty') + str(i)
        nodes.append(dict(id=r['id'], parent=parent, kind=1, name=name, hidden=not r['active'], value=r['value']))
        output.append({**r, 'label': prefix+name, 'active': r['active'] and not inherited})
    if defect == 'cycle': nodes[0]['parent'] = 3
    elif defect == 'missing-parent': nodes[-1]['parent'] = 999999
    elif defect == 'file-parent': nodes[-1]['parent'] = rows[0]['id']
    elif defect == 'duplicate-id': nodes[-1]['id'] = nodes[-2]['id']
    random.Random(seed).shuffle(nodes); body = b''
    for n in nodes:
        body += var(n['id']) + var(n['parent']) + bytes([n['kind']]) + text(n['name']) + bytes([n['hidden']])
        if n['kind']:
            value = zlib.compress(struct.pack('<i' if version == 1 else '>i', n['value']))
            body += var(len(value)) + value
    # JS compares strings as UTF-16 code units, not Unicode code-point order.
    output.sort(key=lambda r: (r['label'].encode('utf-16-be'), r['id']))
    return wrap('tree', version, flags, len(nodes), body), output


def make(case, version, flags, pattern, defect=None):
    seed = 701 + version*103 + flags*29 + pattern*47
    rows = records(seed, 8+pattern)
    if case == 'chunks': raw = chunk_file(rows, version, flags, seed, defect); expected = rows
    elif case == 'journal': raw, expected = journal_file(rows, version, flags, pattern, defect)
    elif case == 'columns': raw, expected = column_file(rows, version, flags, pattern, defect)
    else: raw, expected = tree_file(rows, version, flags, pattern, seed, defect)
    if flags & 1: expected = list(reversed(expected))
    return raw, dict(version=version, records=expected)


def prepare(root):
    if root.exists(): raise ValueError('Use a fresh stress input directory')
    defects = {'chunks': ('duplicate-slot', 'chunk-overlap', 'count', 'chunk-trailing'),
               'journal': ('nested', 'orphan-commit', 'orphan-abort', 'open-transaction'),
               'columns': ('padding', 'label-index', 'body-trailing', 'body-truncated'),
               'tree': ('cycle', 'missing-parent', 'file-parent', 'duplicate-id')}
    for case in MAGIC:
        folder = root / case; folder.mkdir(parents=True); tests = []
        for version in (1, 2):
            for flags in range(4):
                for pattern in (0, 1):
                    name = f'v{version}-flags{flags}-pattern{pattern}.bin'
                    raw, expected = make(case, version, flags, pattern)
                    (folder/name).write_bytes(raw)
                    tests.append(dict(name=name, valid=True, expected=expected, version=version, flags=flags, pattern=pattern))
        for defect in defects[case]:
            name = f'invalid-{defect}.bin'; raw, _ = make(case, 2, 3, 1, defect)
            (folder/name).write_bytes(raw); tests.append(dict(name=name, valid=False, defect=defect))
        (folder/'cases.json').write_text(json.dumps(tests, indent=2, ensure_ascii=False)+'\n')
