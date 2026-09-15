"""Run on RK against staged or installed engine. Never opens a sound stream."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

sys.path.insert(0, '/home/cat/cypher/audio-engine')
sys.path.insert(0, '/home/cat/harbeat-mixing-v1/engine-patch')
import engine as mod


class CacheTests(unittest.TestCase):
    def setUp(self):
        mod._RT_PINNED_CACHE.clear()
        mod._PREFETCH_CACHE.clear()
        self.audio = np.ones((10000,2),dtype=np.float32)

    def test_deck_clear_does_not_destroy_pinned_audio(self):
        mod._store_prefetch_cache('rtv1-test',self.audio,{})
        d=mod.Deck()
        d.load('rtv1-test',load_stems=False)
        self.assertIs(d.audio,self.audio)
        d.clear()
        self.assertIs(mod._RT_PINNED_CACHE['rtv1-test']['audio'],self.audio)

    def test_second_load_does_not_read_disk(self):
        mod._store_prefetch_cache('rtv1-test',self.audio,{})
        d=mod.Deck()
        d.load('rtv1-test',load_stems=False)
        d.clear()
        with patch.object(mod,'_load_wav_stereo',side_effect=AssertionError('disk read')):
            d.load('rtv1-test',load_stems=False)

    def test_prefetch_reuses_pinned_identity(self):
        mod._store_prefetch_cache('rtv1-test',self.audio,{})
        mod._PREFETCH_CACHE.clear()
        with patch.object(mod,'_load_wav_stereo',side_effect=AssertionError('disk read')):
            self.assertTrue(mod.engine.prefetch(['rtv1-test'],wait=True,load_stems=False)['all_ready'])

    def test_legacy_not_pinned(self):
        mod._store_prefetch_cache('101',self.audio,{})
        self.assertEqual(mod._RT_PINNED_CACHE,{})

    def test_stems_not_pinned(self):
        mod._store_prefetch_cache('rtv1-test',self.audio,{'vocals':self.audio})
        self.assertEqual(mod._RT_PINNED_CACHE,{})

    def test_transformed_audio_not_pinned(self):
        mod._store_prefetch_cache('rtv1-test@/sample.wav',self.audio,{})
        self.assertEqual(mod._RT_PINNED_CACHE,{})

    def test_count_limit(self):
        for i in range(8):
            mod._store_prefetch_cache('rtv1-'+str(i),self.audio,{})
        with self.assertRaisesRegex(ValueError,'budget'):
            mod._store_prefetch_cache('rtv1-ninth',self.audio,{})

    def test_byte_limit(self):
        with patch.object(mod,'_RT_PIN_MAX_BYTES',self.audio.nbytes-1):
            with self.assertRaisesRegex(ValueError,'budget'):
                mod._store_prefetch_cache('rtv1-test',self.audio,{})

    def test_stats(self):
        mod._store_prefetch_cache('rtv1-test',self.audio,{})
        self.assertEqual(mod._realtime_cache_state()['realtime_pinned_bytes'],self.audio.nbytes)


class TempoCacheTests(unittest.TestCase):
    def setUp(self):
        mod.engine.deck_a.clear()
        mod.engine.deck_b.clear()
        mod._RTV2_CACHE.clear()
        mod._PREFETCH_CACHE.clear()
        self.audio=np.ones((10000,2),dtype=np.float32)

    def test_clear_keeps_buffer(self):
        mod._store_prefetch_cache('rtv2-test',self.audio,{})
        d=mod.Deck(); d.load('rtv2-test',load_stems=False); d.clear()
        self.assertIs(mod._RTV2_CACHE['rtv2-test']['audio'],self.audio)

    def test_eviction_keeps_both_live_decks(self):
        for i in range(10):
            mod._store_prefetch_cache('rtv2-'+str(i),self.audio.copy(),{})
        mod.engine.deck_a.load('rtv2-0',load_stems=False)
        mod.engine.deck_b.load('rtv2-1',load_stems=False)
        mod._store_prefetch_cache('rtv2-new',self.audio,{})
        self.assertIn('rtv2-0',mod._RTV2_CACHE)
        self.assertIn('rtv2-1',mod._RTV2_CACHE)
        self.assertNotIn('rtv2-2',mod._RTV2_CACHE)
        self.assertNotIn('rtv2-2',mod._PREFETCH_CACHE)
        self.assertEqual(len(mod._RTV2_CACHE),10)

    def test_repeated_load_without_decode(self):
        mod._store_prefetch_cache('rtv2-test',self.audio,{})
        mod._PREFETCH_CACHE.clear()
        with patch.object(mod,'_load_wav_stereo',side_effect=AssertionError('decode')):
            d=mod.Deck(); d.load('rtv2-test',load_stems=False)
            self.assertTrue(mod.engine.prefetch(['rtv2-test'],wait=True,load_stems=False)['all_ready'])


if __name__=='__main__':
    unittest.main()
