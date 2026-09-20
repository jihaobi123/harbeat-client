"""ARM adapter: Essentia's own preprocessing, TensorFlow Python graph execution.

Uses the same public preprocessing algorithms and frozen model nodes as the
Essentia TensorflowPredict wrappers. Kept separate from the default backend.
"""
import math

import essentia
import essentia.streaming as streaming
import numpy as np
import tensorflow as tf


def patches(audio, size, hop):
    pool = essentia.Pool()
    source = streaming.VectorInput(np.asarray(audio, dtype=np.float32))
    frames = streaming.FrameCutter(frameSize=512, hopSize=256)
    mel = streaming.TensorflowInputMusiCNN()
    pack = streaming.VectorRealToTensor(shape=[-1, 1, size, 96],
                                       patchHopSize=hop, lastPatchMode='repeat')
    source.data >> frames.signal
    frames.frame >> mel.frame
    mel.bands >> pack.frame
    pack.tensor >> (pool, 'patches')
    essentia.run(source)
    return np.concatenate(pool['patches'], axis=0)[:, 0]


class Graph:
    def __init__(self, path, input_node, output_node):
        self.graph = tf.Graph()
        graph_def = tf.compat.v1.GraphDef()
        graph_def.ParseFromString(path.read_bytes())
        with self.graph.as_default():
            tf.import_graph_def(graph_def, name='')
        self.input = self.graph.get_tensor_by_name(input_node + ':0')
        self.output = self.graph.get_tensor_by_name(output_node if ':' in output_node else output_node + ':0')
        config = tf.compat.v1.ConfigProto(intra_op_parallelism_threads=2,
                                         inter_op_parallelism_threads=1,
                                         device_count={'GPU': 0})
        self.session = tf.compat.v1.Session(graph=self.graph, config=config)

    def __call__(self, values):
        result = []
        fixed = self.input.shape.as_list()[0]
        batch = fixed or 64
        for start in range(0, len(values), batch):
            block = np.asarray(values[start:start+batch], dtype=np.float32)
            n = len(block)
            if fixed and n < fixed:
                block = np.pad(block, [(0, fixed-n)] + [(0, 0)]*(block.ndim-1))
            result.append(self.session.run(self.output, {self.input: block})[:n])
        return np.concatenate(result)


def predictors(root, kind):
    if kind == 'emotion':
        backbone = Graph(root/'msd-musicnn-1.pb', 'model/Placeholder', 'model/dense/BiasAdd')
        head = Graph(root/'deam-msd-musicnn-2.pb', 'model/Placeholder', 'model/Identity')
        return lambda audio: backbone(patches(audio, 187, 93)), head
    backbone = Graph(root/'discogs-effnet-bs64-1.pb', 'serving_default_melspectrogram', 'PartitionedCall:1')
    head = (Graph(root/'genre_discogs400-discogs-effnet-1.pb', 'serving_default_model_Placeholder', 'PartitionedCall:0')
            if kind == 'genre' else Graph(root/'mtg_jamendo_instrument-discogs-effnet-1.pb', 'model/Placeholder', 'model/Sigmoid'))
    def embedding(audio):
        # Essentia's lastBatchMode=same pads the waveform, then drops padded
        # predictions. Padding mel patches instead changes the final real patch.
        original_count = len(patches(audio, 128, 62))
        extra = (math.ceil(original_count/64)*64-original_count)*62*256
        values = patches(np.pad(audio, (0, extra)), 128, 62) if extra else patches(audio, 128, 62)
        return backbone(values)[:original_count]
    return embedding, head
