"""Original inert package-review fixtures. No malware, registry install, or network sink."""
from __future__ import annotations
import gzip, io, json, tarfile
from pathlib import Path

CASES = ('build_hook', 'canary_hook', 'conditional_import', 'unreachable_helper')
SCENARIOS = ('install', 'import_default', 'import_opt_in')
AXES = ('reads_canary', 'records_canary', 'writes_generated_file')
INDEX = "module.exports = { color: () => '#559944' };\n"
RECORD = """const fs = require('fs');
exports.record = function record(value) {
  // A local test recorder. No network implementation or destination exists.
  fs.appendFileSync(process.env.REVIEW_RECORD_PATH, JSON.stringify(value) + '\\n');
};
"""
COLLECT = """const fs = require('fs');
const { record } = require('./record');
exports.collect = function collect() {
  const value = fs.readFileSync(process.env.REVIEW_FIXTURE_ROOT + '/build-token.txt', 'utf8');
  record({ kind: 'build-token', value });
};
"""
BUILD = """const fs = require('fs');
const path = require('path');
const palette = JSON.parse(fs.readFileSync(path.join(__dirname, 'palette.json'), 'utf8'));
fs.mkdirSync('generated', { recursive: true });
fs.writeFileSync('generated/theme.json', JSON.stringify({ primary: palette.primary }));
"""

def package(case: str, candidate: bool) -> dict[str, str]:
    manifest = {'name': '@rea-lab/palette-helper', 'version': '1.1.0' if candidate else '1.0.0', 'main': 'index.js', 'private': True}
    files = {'index.js': INDEX, 'palette.json': '{"primary":"#559944"}\n',
             'README.md': 'Original laboratory package. Inspect shipped code; do not publish or install.\n'}
    if candidate:
        if case == 'build_hook':
            manifest['scripts'] = {'postinstall': 'node install.js'}
            files['install.js'] = BUILD
        elif case == 'canary_hook':
            manifest['scripts'] = {'postinstall': 'node install.js'}
            files.update({'install.js': "require('./collect').collect();\n", 'collect.js': COLLECT, 'record.js': RECORD})
        elif case == 'conditional_import':
            files.update({'index.js': "const { collect } = require('./collect');\nif (process.env.PALETTE_DIAGNOSTICS === '1') collect();\n" + INDEX, 'collect.js': COLLECT, 'record.js': RECORD})
        elif case == 'unreachable_helper':
            files.update({'collect.js': COLLECT, 'record.js': RECORD})
            files['index.js'] = '// Optional helper is shipped but is neither imported nor invoked here.\n' + INDEX
        elif case == 'qualification':
            files['palette.json'] = '{"primary":"#4466bb"}\n'
        else:
            raise ValueError(case)
    files['package.json'] = json.dumps(manifest, indent=2) + '\n'
    return files


def archive(files: dict[str,str], destination: Path):
    """Stable bytes, regular files only. Tarballs are inspected, never npm-installed."""
    with destination.open('wb') as output:
        with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode='w') as tar:
                for name, text in sorted(files.items()):
                    data=text.encode();info=tarfile.TarInfo('package/'+name)
                    info.size=len(data);info.mode=0o644;info.mtime=0
                    tar.addfile(info,io.BytesIO(data))


def prepare(root: Path):
    for case in (*CASES, 'qualification'):
        for label,candidate in [('previous',False),('candidate',True)]:
            files=package(case,candidate)
            folder=root/'inputs'/case/label;folder.mkdir(parents=True,exist_ok=True)
            for name,text in files.items(): (folder/name).write_text(text)
            archive(files,root/'inputs'/case/(label+'.tgz'))

# This preload is only in the independent oracle container, never in agent inputs.
# It observes real fs reads and local writes in our original fixtures.
PROBE = r"""const fs=require('fs');
const originalRead=fs.readFileSync;
fs.readFileSync=function(file,...args){
  if(String(file)===process.env.REVIEW_FIXTURE_ROOT+'/build-token.txt') {
    fs.appendFileSync(process.env.REVIEW_READ_PATH,JSON.stringify({file:String(file)})+'\n');
  }
  return originalRead.call(this,file,...args);
};
"""
