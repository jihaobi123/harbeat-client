# SongFormer and MuQ deployment notice

HarBeat's annotation Pilot uses the official [ASLP-lab SongFormer repository](https://github.com/ASLP-lab/SongFormer) at revision `139b2aa3b14bd1c6d961d0994e9fc975f1ef7fd5`. The installer follows the upstream checkpoint fetch flow and verifies `src/SongFormer/ckpts/md5sum.txt` before inference.

The SongFormer feature pipeline also uses the official [Tencent AI Lab MuQ implementation](https://github.com/tencent-ailab/muq) and the `OpenMuQ/MuQ-MuLan-large` weights. The MuQ source code is MIT licensed, while the official MuQ model weights are published under CC BY-NC 4.0.

This deployment is therefore restricted to the current research and annotation Pilot. It is not represented as cleared for commercial product inference. Before any commercial use, the team must obtain an appropriate model-weight license or replace the encoder with a commercially compatible alternative. Preserve upstream attribution, revision identifiers, and downloaded weight hashes in every deployment record.

The HarBeat residual section-label classifier is not included in this deployment. Its runtime switch remains explicitly disabled until separately trained weights pass the agreed locked evaluation gate.

