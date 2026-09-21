"""Read-only empirical check of global versus per-document model batches."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

RESULTS = Path(__file__).resolve().parents[2]
FROZEN = RESULTS / 'sidecar_delta_post_20260921_docs_n10/sandbox/experiment/rag'
sys.path.insert(0, str(FROZEN))
from core.indexing import _encode_chunks_to_points
from core.retrieval import colbert_maxsim
from FlagEmbedding import BGEM3FlagModel

db = FROZEN / 'database'
source = db / 'versions' / (db / 'CURRENT').read_text().strip() / 'chunks.json'
raw = source.read_bytes()
chunks = [dict(chunk_id=k, metadata={}, **v) for k, v in json.loads(raw).items()]
model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=False, devices='cpu')
global_points, global_colbert, _, global_dense = _encode_chunks_to_points(model, chunks)
individual_points, individual_colbert, individual_dense = [], {}, []
for chunk in chunks:
    points, vectors, _, dense = _encode_chunks_to_points(model, [chunk])
    individual_points.extend(points)
    individual_colbert.update(vectors)
    individual_dense.extend(dense)
rows = []
for i, chunk in enumerate(chunks):
    key = chunk['chunk_id']
    a, b = global_colbert[key], individual_colbert[key]
    rows.append(dict(chunk_id=key, shape=list(a.shape), fp16_equal=np.array_equal(a, b),
                     fp16_changed_values=int(np.count_nonzero(a != b)),
                     fp16_max_abs_difference=float(np.max(np.abs(a.astype('float32') - b.astype('float32')))),
                     dense_equal=np.array_equal(global_dense[i], individual_dense[i]),
                     dense_max_abs_difference=float(np.max(np.abs(global_dense[i] - individual_dense[i]))),
                     point_equal=global_points[i].model_dump() == individual_points[i].model_dump()))
queries = []
for text in ('prenotazione evento posti', 'pagamenti accettati', 'notifiche prenotazione'):
    q = model.encode([text], return_colbert_vecs=True)['colbert_vecs'][0]
    before = {key: colbert_maxsim(q, value) for key, value in global_colbert.items()}
    after = {key: colbert_maxsim(q, value) for key, value in individual_colbert.items()}
    queries.append(dict(query=text, scores_equal=before == after, before=before, after=after,
                        ranking_equal=sorted(before, key=lambda k: (-before[k], k)) == sorted(after, key=lambda k: (-after[k], k))))
assert source.read_bytes() == raw
result = dict(status='completed', source=str(source), source_sha256=hashlib.sha256(raw).hexdigest(),
              chunks=rows, queries=queries,
              limits='Encoding grouping experiment only, not NPY reader parity or full retrieval; no Qdrant mutation.')
target = Path(__file__).with_suffix('.json')
with target.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2)
print(json.dumps(dict(chunks=len(rows), fp16_equal=all(r['fp16_equal'] for r in rows),
                      point_equal=all(r['point_equal'] for r in rows),
                      scores_equal=all(q['scores_equal'] for q in queries),
                      ranking_equal=all(q['ranking_equal'] for q in queries))))
