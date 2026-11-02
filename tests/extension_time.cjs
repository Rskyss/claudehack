// Run the real extension in isolated realms; the host selects TZ per process.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { resolveObjectURL } = require('node:buffer');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../extension/shield.js'), 'utf8');

const probe = `JSON.stringify((() => {
  const dates = ['2026-07-01T07:00:00Z', '2026-11-02T07:00:00Z',
    '2026-03-08T07:00:00Z', '2026-11-01T06:00:00Z', '2026-12-31T23:30:00Z'];
  return dates.map(value => {
    const d = new Date(value);
    const local = new Date(d.getFullYear(), d.getMonth(), d.getDate(),
      d.getHours(), d.getMinutes(), d.getSeconds());
    return { text: d.toString(), time: d.toTimeString(), date: d.toDateString(),
      hour: d.getHours(), offset: d.getTimezoneOffset(), rebuilt: local.getTime(),
      formatted: d.toLocaleString('en-US'),
      zone: Intl.DateTimeFormat().resolvedOptions().timeZone };
  });
})())`;

function realm(globals = {}) {
  const ctx = vm.createContext(globals);
  vm.runInContext('window = globalThis; self = globalThis;', ctx);
  return ctx;
}

async function main() {
  let failures = 0;
  async function check(name, fn) {
    try { await fn(); console.log('PASS ' + name); }
    catch (error) { failures++; console.error('FAIL ' + name + ': ' + error.message); }
  }
  await check('main realm preserves native date results including DST and year boundary', () => {
    const ctx = realm();
    const before = vm.runInContext(probe, ctx);
    vm.runInContext(source, ctx);
    assert.equal(vm.runInContext(probe, ctx), before);
  });
  await check('inherited DateTimeFormat options are honored', () => {
    const ctx = realm();
    vm.runInContext(source, ctx);
    assert.equal(vm.runInContext(`new Intl.DateTimeFormat('en-US',
      Object.create({year:'numeric'})).format(new Date('2026-07-01T12:00:00Z'))`, ctx), '2026');
  });
  await check('DateTimeFormat subclasses retain their prototype', () => {
    const ctx = realm();
    vm.runInContext(source, ctx);
    assert.equal(vm.runInContext(`(() => { class Formatter extends Intl.DateTimeFormat {}
      return new Formatter('en-US') instanceof Formatter; })()`, ctx), true);
  });
  await check('explicit timezone and invalid date preserve native behavior', () => {
    const ctx = realm();
    const expression = `JSON.stringify([new Intl.DateTimeFormat('en-US',
      {timeZone:'Pacific/Auckland', hour:'2-digit', hourCycle:'h23'}).format(
      new Date('2026-11-02T07:00:00Z')), new Date(NaN).toString(),
      Number.isNaN(new Date(NaN).getTimezoneOffset())])`;
    const before = vm.runInContext(expression, ctx);
    vm.runInContext(source, ctx);
    assert.equal(vm.runInContext(expression, ctx), before);
  });
  await check('generated Worker bootstrap preserves native date results', async () => {
    // Only the browser Worker launch boundary is replaced. Execute the actual
    // generated Blob script with real Date/Intl in a fresh worker-like realm.
    const ctx = realm({ Blob, URL, setTimeout() {}, Worker: class {
      constructor(url) { this.scriptURL = url; }
    } });
    vm.runInContext(source, ctx);
    const url = vm.runInContext(`new Worker('blob:original-worker').scriptURL`, ctx);
    try {
      const bootstrap = await resolveObjectURL(url).text();
      let imported;
      const worker = realm({ importScripts(url) { imported = url; } });
      const before = vm.runInContext(probe, worker);
      vm.runInContext(bootstrap, worker);
      assert.equal(imported, 'blob:original-worker');
      assert.equal(vm.runInContext(probe, worker), before);
    } finally { URL.revokeObjectURL(url); }
  });
  process.exitCode = failures ? 1 : 0;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
