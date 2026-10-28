// Drives web3270's tn5250 session class (an independent 5250 client, debugged
// against a real IBM i) against a running Silverlake and prints what it saw as
// JSON. Usage: node web3270_client.mjs <port> [devname]
// web3270 is found next to this repo, or via SILVERLAKE_WEB3270.
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = process.env.SILVERLAKE_WEB3270 || path.resolve(here, '../../../web3270');
const { default: Tn5250Session } = await import(
  pathToFileURL(path.join(root, 'Bridge_server/tn5250/session.js')).href);

const port = Number(process.argv[2]);
const luName = process.argv[3] || null;
const COLS = 80;

const ses = new Tn5250Session({ wsId: 'interop', host: '127.0.0.1', port, useTls: false, luName });
ses.on('error', e => { console.error('client error:', e.message); process.exit(1); });

const nextScreen = () => new Promise((resolve, reject) => {
  const t = setTimeout(() => reject(new Error('timed out waiting for a screen')), 5000);
  ses.once('screen', s => { clearTimeout(t); resolve(s); });
});

const summarize = s => ({
  text: s.rows.map(r => r.map(c => c.char).join('').trimEnd()).filter(Boolean),
  inputs: s.fields.filter(f => !f.protected).map(f => ({
    row: Math.floor((f.startAddr + 1) / COLS), col: (f.startAddr + 1) % COLS,
    length: f.length, nondisplay: f.nondisplay,
  })),
  cursor: [s.cursorRow, s.cursorCol],
});

try {
  const first = nextScreen();
  ses.connect();
  const s1 = await first;

  ses.typeAt(5, 52, 'tester', false);
  ses.typeAt(6, 52, 'secret', false);
  const sent = ses.getModifiedFields();
  const second = nextScreen();
  ses.sendAid('ENTER', sent);
  const s2 = await second;

  console.log(JSON.stringify({
    first: summarize(s1),
    sent: sent.map(f => ({ addr: f.addr, data: f.data })),
    second: summarize(s2),
  }));
  ses.disconnect('done');
  process.exit(0);
} catch (e) {
  console.error('interop failed:', e.message);
  process.exit(1);
}
