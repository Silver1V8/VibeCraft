"""Logica pura del sistema Graph-RAG: retrieval, graph ops, pipeline, indicizzazione
e chunking. Nessuna dipendenza da FastAPI — importabile e testabile in isolamento.
Le risorse a runtime (grafo, Qdrant, modello di embedding, sidecar) sono passate come
parametri espliciti dalle funzioni chiamanti (dependency injection), non lette da globali."""
