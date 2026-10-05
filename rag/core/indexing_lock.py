"""One process-wide slot for HTTP indexing, independently of project writer locks."""
from threading import Lock

# ponytail: serialize CPU/GPU indexing across projects; use a bounded worker queue if throughput requires it.
indexing_lock = Lock()
