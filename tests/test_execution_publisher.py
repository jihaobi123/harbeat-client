import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
from analysis_platform.device_export import export_track
from analysis_platform.execution_publisher import ready_track
from metric_mix.prepare import sha


class PublisherEvidenceTests(unittest.TestCase):
    def fixture(self,root):
        paths={}
        for name in ['master','drums','bass','other','vocals']:
            paths[name]=root/(name+'.wav');sf.write(paths[name],np.zeros((8000,2)),8000)
        proof={'trackId':'track-test','runId':'run-test','manifestSha256':'a'*64,'reportSha256':'b'*64,
               'assets':{k:{'sha256':sha(v)} for k,v in paths.items()}}
        provenance={'runId':'run-test','masterSha256':proof['assets']['master']['sha256'],
                    'reportSha256':'b'*64,'vocalSha256':proof['assets']['vocals']['sha256']}
        with patch('analysis_platform.device_export.source_assets',return_value=(paths,proof)):
            entry=export_track({'id':'track-test','reportId':'b'*64,'alignment':{'bars':[]}},root,root,root/'out')
        track=json.loads((root/'out/tracks/track-test.json').read_text())
        return track,entry,{'track-test':provenance}

    def test_only_current_profile_and_exact_shared_grid_are_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);track,entry,bindings=self.fixture(root)
            self.assertGreater(ready_track(track,entry,bindings,root/'out/objects',root/'out/profiles'),0)
            stale=copy.deepcopy(track);stale['profile']['sha256']='f'*64
            with self.assertRaisesRegex(ValueError,'profile descriptor'):
                ready_track(stale,entry,bindings,root/'out/objects',root/'out/profiles')
            bad=copy.deepcopy(track);bad['stems']['other']['segments'][0]['endFrame']-=1
            with self.assertRaisesRegex(ValueError,'source mapping|sample grid'):
                ready_track(bad,entry,bindings,root/'out/objects',root/'out/profiles')
            for field in ['start','end']:
                bad=copy.deepcopy(track);bad['stems']['bass']['segments'][0][field]=float('nan')
                with self.assertRaises(ValueError):ready_track(bad,entry,bindings,root/'out/objects',root/'out/profiles',verify_objects=False)
            bad=copy.deepcopy(track);bad['stems']['bass']['segments'][0]['asset']['duration']=float('nan')
            with self.assertRaises(ValueError):ready_track(bad,entry,bindings,root/'out/objects',root/'out/profiles',verify_objects=False)

    def test_corrupt_encoded_asset_is_never_advertised(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);track,entry,bindings=self.fixture(root)
            checksum=track['stems']['bass']['segments'][0]['asset']['sha256']
            (root/'out/objects'/(checksum+'.flac')).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'corrupt execution object'):
                ready_track(track,entry,bindings,root/'out/objects',root/'out/profiles')
