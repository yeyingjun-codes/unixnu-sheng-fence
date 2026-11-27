import io
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import zipfile

work = Path(os.environ['WORK'])
work.mkdir(parents=True, exist_ok=True)
headers = {'Authorization': 'Bearer ' + os.environ['GHTOKEN'], 'User-Agent': 'sheng'}
base = 'https://api.github.com/repos/yeyingjun-codes/unixnu-sheng-fence'
with urllib.request.urlopen(urllib.request.Request(base + '/actions/runs/45847085054/artifacts', headers=headers), timeout=90) as response:
    artifact = json.load(response)['artifacts'][0]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

url = base + '/actions/artifacts/' + str(artifact['id']) + '/zip'
try:
    urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, headers=headers), timeout=60)
except urllib.error.HTTPError as error:
    with urllib.request.urlopen(urllib.request.Request(error.headers['Location'], headers={'User-Agent': 'sheng'}), timeout=90) as response:
        raw = response.read()
zipfile.ZipFile(io.BytesIO(raw)).extractall(work)
subprocess.run(['git', 'init', '-q', str(work / 'uefi-sheng')], check=True)
subprocess.run(['git', '-C', str(work / 'uefi-sheng'), 'remote', 'add', 'origin', 'https://github.com/UniXNU/uefi-sheng.git'], check=True)
subprocess.run(['git', '-C', str(work / 'uefi-sheng'), 'fetch', '--depth', '1', 'origin', 'b303410c8e401fc9419ae65a024356ed09a438ef'], check=True)
subprocess.run(['git', '-C', str(work / 'uefi-sheng'), 'checkout', '-q', 'FETCH_HEAD'], check=True)
print('Verified source image and mkbootimg fetched; no firmware build.', flush=True)
