"""Archive final figures and native screenshots after the saved Report exists."""
import argparse
import json
import sys
from pathlib import Path

import wandb
from publish_format_recovery import read, write, sha


def publish(root):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
    from forge_recovery.telemetry import credentials, ensure_private_project
    credentials(); ensure_private_project('wandb')
    if (root/'media-publication.json').exists(): return read(root/'media-publication.json')
    if (root/'media-publication-progress.json').exists(): raise RuntimeError('Reconcile the existing media publication before retrying')
    evidence = read(root/'publication.json')
    assert evidence['state'] == 'saved_and_api_verified'
    assert (root/'media/native-format-report.png').is_file(), 'Capture and inspect the saved native Report first'
    files = {'media/'+str(p.relative_to(root/'media')): p for p in (root/'media').rglob('*') if p.is_file()}
    for name in ('publication.json', 'report-readback.json', 'ui-verification.json'):
        assert (root/name).is_file(), name
        files['verification/'+name] = root/name
    for name in ('build_format_example.py','build_format_media.py','publish_format_media.py','publish_format_recovery.py'):
        files['source/'+name] = Path(__file__).parent/name
    for path in (root/'report-revisions').glob('*'):
        if path.is_file(): files['verification/report-revisions/'+path.name] = path
    manifest = {'evidence_artifact': evidence['artifact'], 'report_url': evidence['report_url'],
                'files': {name: sha(path) for name,path in files.items()},
                'scope': 'Final recorded-result figures and real native screenshots; no new inference or decoder execution.'}
    write(root/'review-media-manifest.json', manifest)
    files['manifest.json'] = root/'review-media-manifest.json'
    progress = {'state': 'publishing', 'experiment_id': evidence['experiment_id']}
    write(root/'media-publication-progress.json', progress)
    with wandb.init(entity='wandb', project='rea-showcase', id=evidence['experiment_id']+'-media',
                    job_type='format-recovery-media', dir=str(root),
                    settings=wandb.Settings(disable_git=True, disable_code=True, console='off')) as run:
        artifact = wandb.Artifact(evidence['experiment_id']+'-review-media', type='review-media',
                                  metadata={'evidence_artifact': evidence['artifact'], 'report_url': evidence['report_url']})
        for name,path in files.items(): artifact.add_file(str(path), name=name)
        saved = run.log_artifact(artifact).wait()
        progress.update(artifact='wandb/rea-showcase/'+saved.name, artifact_digest=saved.digest)
        write(root/'media-publication-progress.json', progress)
    downloaded = Path(wandb.Api(timeout=60).artifact(progress['artifact']).download(root=str(root/'review-media-readback')))
    assert all(sha(downloaded/name)==digest for name,digest in manifest['files'].items())
    assert sha(downloaded/'manifest.json')==sha(root/'review-media-manifest.json')
    name,version = progress['artifact'].rsplit('/',1)[1].split(':')
    progress.update(state='downloaded_and_hash_verified', verified_payload_files=len(manifest['files']),
                    artifact_url=f'https://forge.coreweave.com/wandb/wandb/rea-showcase/artifacts/review-media/{name}/{version}/files')
    write(root/'media-publication.json', progress)
    return progress


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('root', type=Path); args = parser.parse_args()
    print(json.dumps(publish(args.root.resolve()), indent=2))
