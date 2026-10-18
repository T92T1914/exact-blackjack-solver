import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const script = await readFile(new URL('../site/appearance.js', import.meta.url), 'utf8');
function fixture(saved, blocked = false, appearance = 'auto') {
  const values = new Map(saved ? [['exact-blackjack-solver.appearance.v1', saved]] : []);
  const root = {dataset: {appearance}};
  let ready, change;
  const control = {disabled: true, addEventListener: (_, listener) => { change = listener; }};
  vm.runInNewContext(script, {
    document: {documentElement: root, addEventListener: (_, listener) => { ready = listener; },
      getElementById: () => control},
    localStorage: {
      getItem: key => { if (blocked) throw Error('blocked'); return values.get(key); },
      setItem: (key, value) => { if (blocked) throw Error('blocked'); values.set(key, value); },
      removeItem: key => { if (blocked) throw Error('blocked'); values.delete(key); }
    }
  });
  ready();
  return {root, control, values, select(value) { control.value = value; change(); }};
}

test('the page default is used until a valid saved choice takes precedence', () => {
  assert.equal(fixture(null, false, 'obscur').root.dataset.appearance, 'obscur');
  assert.equal(fixture('arbitrary', false, 'obscur').root.dataset.appearance, 'obscur');
  assert.equal(fixture('arbitrary').root.dataset.appearance, 'auto');
  for (const choice of ['auto', 'clair', 'obscur']) {
    const f = fixture(choice, false, 'obscur');
    assert.equal(f.root.dataset.appearance, choice);
    assert.equal(f.control.value, choice);
  }
});

test('explicit appearance and Auto persist without changing unrelated storage', () => {
  const f = fixture('obscur', false, 'obscur');
  assert.equal(f.root.dataset.appearance, 'obscur');
  assert.equal(f.control.disabled, false);
  f.values.set('unrelated', 'keep');
  f.select('clair');
  assert.equal(f.values.get('exact-blackjack-solver.appearance.v1'), 'clair');
  f.select('auto');
  assert.equal(f.root.dataset.appearance, 'auto');
  assert.equal(f.values.get('unrelated'), 'keep');
  assert.equal(f.values.get('exact-blackjack-solver.appearance.v1'), 'auto');
  const reopened = fixture(f.values.get('exact-blackjack-solver.appearance.v1'), false, 'obscur');
  assert.equal(reopened.root.dataset.appearance, 'auto');
  assert.equal(reopened.control.value, 'auto');
});

test('failed storage keeps the page default and allows memory-only switching', () => {
  const f = fixture(null, true, 'obscur');
  assert.equal(f.root.dataset.appearance, 'obscur');
  f.select('clair');
  assert.equal(f.root.dataset.appearance, 'clair');
  f.select('auto');
  assert.equal(f.root.dataset.appearance, 'auto');
  assert.equal(f.values.size, 0);
  assert.equal(fixture(null, true, 'obscur').root.dataset.appearance, 'obscur');
});
