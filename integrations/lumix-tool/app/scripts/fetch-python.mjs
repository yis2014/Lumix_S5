// Downloads the official Windows embeddable Python used by release builds and
// unpacks it to vendor/python-win-amd64 (bundled as resources/python).
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const VERSION = '3.13.12';
const SHA256 = '76f238f606250c87c6beac75dccd35ee99070a13490555936abb6cb64ecce3d0';
const URL = `https://www.python.org/ftp/python/${VERSION}/python-${VERSION}-embed-amd64.zip`;

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const cache = join(root, 'vendor', 'cache', `python-${VERSION}-embed-amd64.zip`);
const target = join(root, 'vendor', 'python-win-amd64');
const sha = buf => createHash('sha256').update(buf).digest('hex');

if (existsSync(join(target, 'python.exe')) && existsSync(join(target, `.version-${VERSION}`))) {
  console.log(`Python ${VERSION} already prepared`);
  process.exit(0);
}

let zip = existsSync(cache) ? readFileSync(cache) : null;
if (!zip || sha(zip) !== SHA256) {
  console.log(`Downloading ${URL}`);
  const response = await fetch(URL);
  if (!response.ok) throw new Error(`Download failed: HTTP ${response.status}`);
  zip = Buffer.from(await response.arrayBuffer());
  mkdirSync(dirname(cache), { recursive: true });
  writeFileSync(cache, zip);
}
if (sha(zip) !== SHA256) throw new Error('Python embeddable zip SHA-256 mismatch');

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
execFileSync('tar', ['-xf', cache, '-C', target]);
writeFileSync(join(target, `.version-${VERSION}`), '');
console.log(`Python ${VERSION} unpacked to ${target}`);
