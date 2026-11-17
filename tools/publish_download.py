"""Publish downloadable assets from an already signed stable release.

Requires GH_TOKEN (CI), or the existing Git credential on the author's computer.
Never reads or uploads the signing key.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import release_sign as rs  # noqa: E402


def main():
    manifest = json.loads((ROOT / 'release/stable.json').read_text('utf-8'))
    if not rs.verify(manifest):
        raise RuntimeError('Invalid release signature')
    token = os.environ.get('GH_TOKEN')
    if not token:
        result = subprocess.run(['git', 'credential', 'fill'],
                                input='protocol=https\nhost=github.com\n\n',
                                text=True, capture_output=True, check=True)
        fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        token = fields['password']
    repo = os.environ.get('GITHUB_REPOSITORY', 'rop1ms/Echoes')
    api = f'https://api.github.com/repos/{repo}'

    def request(url, method='GET', data=None, content_type='application/json'):
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer ' + token, 'User-Agent': 'ECHOES-release',
            'Accept': 'application/vnd.github+json', 'Content-Type': content_type})
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.load(response)

    # GET follows repository rename redirects; POST does not. Resolve before writing.
    api = 'https://api.github.com/repos/' + request(api)['full_name']
    tag = 'v' + manifest['version']
    with tempfile.TemporaryDirectory(prefix='echoes-release-') as temp:
        folder = Path(temp)
        archive = folder / 'ECHOES_Setup.zip'
        subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'archive',
                        '--format=zip', '--prefix=ECHOES/', '-o', str(archive), manifest['commit']],
                       cwd=ROOT, check=True)
        with zipfile.ZipFile(archive) as z:
            z.extractall(folder / 'verify')
        source = folder / 'verify/ECHOES'
        problems = rs.check_tree(source, manifest)
        if problems:
            raise RuntimeError('; '.join(problems[:5]))
        # GitHub replaces spaces in asset names with dots. Use its final name in checksums too.
        launcher = folder / 'ECHOES.Launcher.exe'
        shutil.copyfile(source / 'ECHOES Launcher.exe', launcher)
        assets = [archive, launcher, ROOT / 'release/stable.json']
        zip_assets = {archive}
        if manifest.get('launcher_sha256'):
            if hashlib.sha256(launcher.read_bytes()).hexdigest() != manifest['launcher_sha256']:
                raise RuntimeError('Launcher does not match the signed release')
            app_archive = folder / 'ECHOES.App.zip'
            subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'archive',
                            '--format=zip', '--prefix=ECHOES/', '-o', str(app_archive), manifest['commit'],
                            'app', 'setup'], cwd=ROOT, check=True)
            assets.insert(1, app_archive)
            zip_assets.add(app_archive)
        checksums = folder / 'SHA256SUMS.txt'
        checksums.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
                                     for p in assets), 'utf-8')
        assets.append(checksums)
        try:
            release = request(api + '/releases/tags/' + tag)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            body = {'tag_name': tag, 'target_commitish': manifest['commit'],
                    'name': 'ECHOES ' + manifest['version'], 'draft': True,
                    'body': 'Скачайте ECHOES Launcher.exe для установки и обновления.\n\n'
                            'Или распакуйте ECHOES_Setup.zip целиком и запустите УСТАНОВИТЬ ECHOES.bat.\n\n'
                            'Download ECHOES Launcher.exe, or extract ECHOES_Setup.zip and run Install ECHOES.bat.\n\n'
                            + manifest.get('notes', '')}
            release = request(api + '/releases', 'POST', json.dumps(body).encode())
        existing = {a['name']: a for a in release['assets']}
        for asset in assets:
            digest = 'sha256:' + hashlib.sha256(asset.read_bytes()).hexdigest()
            if asset.name in existing:
                if existing[asset.name].get('digest') != digest:
                    if asset == checksums:
                        with urllib.request.urlopen(existing[asset.name]['browser_download_url'], timeout=30) as response:
                            old_sums = response.read()
                        if ('sha256:' + hashlib.sha256(old_sums).hexdigest() == existing[asset.name]['digest']
                                and old_sums.replace(b'\r\n', b'\n') == checksums.read_bytes().replace(b'\r\n', b'\n')):
                            continue
                    if asset not in zip_assets:
                        raise RuntimeError('Existing asset differs: ' + asset.name)
                    # Git on Windows/Linux may use different ZIP compression libraries.
                    # Accept an existing archive only when every entry has identical content.
                    with urllib.request.urlopen(existing[asset.name]['browser_download_url'], timeout=180) as response:
                        old_bytes = response.read()
                    if 'sha256:' + hashlib.sha256(old_bytes).hexdigest() != existing[asset.name]['digest']:
                        raise RuntimeError('Existing archive checksum mismatch')
                    with zipfile.ZipFile(io.BytesIO(old_bytes)) as old, zipfile.ZipFile(asset) as new:
                        if set(old.namelist()) != set(new.namelist()) or any(
                                old.read(name) != new.read(name) for name in new.namelist()):
                            raise RuntimeError('Existing archive content differs')
                    asset.write_bytes(old_bytes)
                    checksums.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
                                                for p in assets if p != checksums), 'utf-8')
                continue
            uploaded = request(release['upload_url'].split('{')[0] + '?name=' + urllib.parse.quote(asset.name),
                               'POST', asset.read_bytes(), 'application/octet-stream')
            if uploaded.get('digest') != digest:
                raise RuntimeError('Uploaded checksum differs: ' + asset.name)
            print('Uploaded:', asset.name, flush=True)
        if release['draft']:
            release = request(release['url'], 'PATCH', json.dumps({'draft': False, 'make_latest': 'true'}).encode())
        print(release['html_url'])


if __name__ == '__main__':
    main()
