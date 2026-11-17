import test from 'node:test';
import assert from 'node:assert/strict';
import { paperFilmPhase, posterStripVertex, feedPaperVertex } from '../paper-film.js';

test('four film shots stretch deterministically to the complete scene duration', () => {
  assert.equal(paperFilmPhase(0, 8).name, 'tear');
  assert.equal(paperFilmPhase(.6, 8).name, 'cascade');
  assert.equal(paperFilmPhase(2.6, 8).name, 'shredder');
  assert.equal(paperFilmPhase(5.1, 8).name, 'rebuild');
  assert.deepEqual(paperFilmPhase(11.2, 16), paperFilmPhase(5.6, 8));
  assert.throws(() => paperFilmPhase(0, 7.9), /至少需要 8 秒/);
});

test('final poster strips reunite without losing or reversing the print UV', () => {
  const phase = paperFilmPhase(7.999, 8);
  for (let i = 0; i < 22; i++) {
    const left = posterStripVertex(i, 0, .5, phase), right = posterStripVertex(i, 1, .5, phase);
    assert.equal(left.x, -1); assert.equal(right.x, 1);
    assert.equal(left.texU, 0); assert.equal(right.texU, 1);
    assert.ok(Math.abs(left.y - (1.5 - (i + .5) * 3 / 22)) < 1e-10);
    if (i < 21) {
      const lowerEdge = posterStripVertex(i, .5, 0, phase);
      const nextTop = posterStripVertex(i + 1, .5, 1, phase);
      assert.ok(Math.abs(lowerEdge.texV - nextTop.texV) < 1e-10);
      assert.ok(Math.abs(lowerEdge.y - nextTop.y) < 1e-10);
      assert.equal(lowerEdge.z, nextTop.z);
    }
  }
});

test('tearing and rebuilding seek directly to the same non-planar geometry', () => {
  const phase = paperFilmPhase(.45, 8);
  const first = posterStripVertex(5, .25, .5, phase);
  posterStripVertex(5, .25, .5, paperFilmPhase(7.99, 8));
  assert.deepEqual(posterStripVertex(5, .25, .5, phase), first);
  assert.ok(Math.abs(first.x) > 1.2);
  const a = posterStripVertex(0, .25, .5, phase), b = posterStripVertex(0, .75, .5, phase);
  assert.notEqual(a.z, b.z);
});

test('feed consumes the bottom first and output strips keep their original print', () => {
  const fed = 1.8;
  for (let lane = 0; lane < 26; lane++) {
    const nip = feedPaperVertex(lane, .5, 0, fed, .9);
    const tail = feedPaperVertex(lane, .5, 1, fed, .9);
    assert.equal(nip.texV, fed / 3); assert.equal(tail.texV, 0);
    assert.ok(tail.y < nip.y);
    assert.equal(nip.texU, (lane + .5) / 26);
    if (lane < 25) assert.equal(feedPaperVertex(lane, 1, .5, fed, .9).texU, feedPaperVertex(lane + 1, 0, .5, fed, .9).texU);
  }
});
