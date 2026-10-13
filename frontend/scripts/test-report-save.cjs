const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(require('node:path').join(__dirname, '../src/services/report-save.ts'), 'utf8');
const context = { exports: {}, DOMException };
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, context);
const { saveReport } = context.exports;
const blob = new Blob(['report']);

test('createWritable permission denial falls back with the complete blob', async () => {
  let count = 0;
  const result = await saveReport(blob, 'report.docx', async () => ({
    createWritable: async () => { throw new DOMException('denied', 'NotAllowedError'); },
  }), (value, name) => { assert.equal(value, blob); assert.equal(name, 'report.docx'); count++; });
  assert.equal(result, 'fallback'); assert.equal(count, 1);
});
test('picker cancellation does not download', async () => {
  assert.equal(await saveReport(blob, 'report.docx', async () => {
    throw new DOMException('cancelled', 'AbortError');
  }, () => assert.fail('must not download')), 'cancelled');
});
test('successful write verifies size without a second download', async () => {
  assert.equal(await saveReport(blob, 'report.docx', async () => ({
    createWritable: async () => ({ write: async value => assert.equal(value, blob), close: async () => {} }),
    getFile: async () => blob,
  }), () => assert.fail('must not download')), 'saved');
});
test('unsupported picker uses normal download', async () => {
  let count = 0;
  assert.equal(await saveReport(blob, 'report.docx', undefined, () => count++), 'download');
  assert.equal(count, 1);
});
test('failed write aborts before falling back', async () => {
  let aborted = false;
  assert.equal(await saveReport(blob, 'report.docx', async () => ({
    createWritable: async () => ({ write: async () => { throw new Error('disk error'); }, abort: async () => { aborted = true; } }),
  }), () => assert.equal(aborted, true)), 'fallback');
});
