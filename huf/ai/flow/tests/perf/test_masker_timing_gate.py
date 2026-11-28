"""H-W2-12 timing gate: how long the PII masker takes over the 1k synthetic corpus.

DEFERRED to the pre-PR gate; needs no site data and runs only with ``HUF_W2_12_MASKER_GATE=1``:

    HUF_W2_12_MASKER_GATE=1 bench --site <site> run-tests --app huf \
        --module huf.ai.flow.tests.perf.test_masker_timing_gate

The plan sets no time limit, so the timing is only reported. Set ``HUF_W2_12_MASKER_MAX_MS`` to also fail when the
mean time per record is above it.
"""

from __future__ import annotations

import os
import time
import unittest

from huf.ai.flow.support.pii_mask import mask_pii
from huf.ai.flow.tests.test_flow_pii_masker import HASH_ID, _record

GATE_ENV = "HUF_W2_12_MASKER_GATE"
LIMIT_ENV = "HUF_W2_12_MASKER_MAX_MS"
CORPUS = 1_000


@unittest.skipUnless(os.environ.get(GATE_ENV) == "1", f"DEFERRED to the pre-PR gate: set {GATE_ENV}=1")
class TestMaskerTimingGate(unittest.TestCase):
	def test_corpus_timing(self):
		records = [_record(i) for i in range(CORPUS)]
		timings = []
		for record in records:
			started = time.perf_counter()
			masked = mask_pii(record)
			timings.append((time.perf_counter() - started) * 1000)
			text = str(masked)
			self.assertNotIn(record["phone"], text)
			self.assertIn(HASH_ID, text)
		# one value holding the whole corpus: the name pattern grows with the number of names
		started = time.perf_counter()
		self.assertIsNotNone(mask_pii(records))
		whole = time.perf_counter() - started

		timings.sort()
		mean = sum(timings) / CORPUS
		print(f"W2_12_GATE records {CORPUS} total_ms {sum(timings):.1f} mean_ms {mean:.3f}")
		print(f"W2_12_GATE p99_ms {timings[CORPUS * 99 // 100]:.3f} whole_corpus_seconds {whole:.3f}")
		if os.environ.get(LIMIT_ENV):
			self.assertLess(mean, float(os.environ[LIMIT_ENV]))
