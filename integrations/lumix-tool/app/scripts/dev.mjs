import { createServer } from 'vite';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const server = await createServer();
await server.listen();
server.printUrls();
const env = { ...process.env, LUMIXTOOL_DEV_URL: 'http://127.0.0.1:5173' };
delete env.ELECTRON_RUN_AS_NODE;
const child = spawn(require('electron'), ['.'], { env, stdio: 'inherit' });
let stopping = false;
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  if (child.exitCode === null) child.kill();
  await server.close();
  process.exitCode = code;
}
child.once('error', error => { console.error(error); void stop(1); });
child.once('exit', (code, signal) => void stop(code ?? (signal ? 1 : 0)));
process.once('SIGINT', () => void stop());
process.once('SIGTERM', () => void stop());
