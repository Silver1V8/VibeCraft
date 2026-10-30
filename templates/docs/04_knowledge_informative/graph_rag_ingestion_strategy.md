---
id: "graph-rag-ingestion-strategy-v1.0"
title: "Razionale Strategico — Perché la Pipeline di Ingestion Graph-RAG è Progettata Così"
project: "cross-project"
version: "1.0.1"
date: "2026-10-30"
status: "ENFORCED"
classification: "METHODOLOGY"
path: "docs/04_knowledge_informative/graph_rag_ingestion_strategy.md"
graph_rag:
  node_type: "METHODOLOGY"
  node_id: "graph-rag-ingestion-strategy-v1.0"
  scope: "Motivazioni progettuali e trade-off dietro i requisiti vincolanti di spec_graph_rag_ingestion.md"
  edges:
    - type: "DERIVA_DA"
      target: "spec-graph-rag-ingestion-v2.0"
      note: "Questo documento non ridefinisce le regole normative: ne spiega il perché. Per i vincoli vincolanti fare riferimento esclusivamente alla spec normativa."
    - type: "REQUISITO_METODOLOGICO"
      target: "TUTTI_I_COMPITI_DI_SVILUPPO"
tags:
  - methodology
  - graph-rag
  - ingestion
  - design-rationale
  - vibecraft
---

# Razionale Strategico — Perché la Pipeline di Ingestion Graph-RAG è Progettata Così

---

> **Nota sulla relazione con la spec normativa**
>
> I requisiti vincolanti (REGOLA-*, soglie numeriche, tassonomia degli identificatori, sequenza della pipeline) sono definiti in modo esclusivo in [`spec_graph_rag_ingestion.md`](../02_specs_normative/spec_graph_rag_ingestion.md), authority 0.87, `status: ENFORCED`. Questo documento è informativo (`classification: METHODOLOGY`): non contiene regole enforceable e non deve essere citato come fonte di un vincolo. Il suo scopo è spiegare **perché** la spec impone quei vincoli, così che chi la modifica capisca quali compromessi sta toccando.

## 1. Perché un ibrido Qdrant + NetworkX invece di un solo vector store

Un vector store puro (solo Qdrant) risponde bene a "trova il testo più simile", ma non risponde a "quali regole dipendono da questa entità" o "quali documenti verrebbero invalidati se cambio questo nodo". Il grafo NetworkX esiste per rispondere a quelle domande di secondo ordine — query multi-hop del tipo entità → regola → documento — che un retrieval puramente denso non può esprimere. Da qui derivano i requisiti di generazione automatica degli archi impliciti e di rivalidazione delle dipendenze descritti nella spec (Sezioni 3 e 5): non sono burocrazia, sono la condizione minima perché il grafo resti una rappresentazione fedele delle relazioni reali tra i documenti, e non solo una collezione di vettori isolati.

## 2. Perché il limite di chunking è ~1500 caratteri (non 500, non 4000)

Il compromesso è tra due failure mode opposti:
- **Chunk troppo grandi** → l'embedding "media" concetti eterogenei nello stesso vettore, diluendo la firma semantica (il rischio che la spec chiama diluizione nel Dense Retrieval).
- **Chunk troppo piccoli** → si perde il contesto necessario perché il chunk sia comprensibile da solo, il che è fatale per i blocchi atomici (definizioni di entità, safeguard, scenari BDD) che devono restare interi.

1500 caratteri è stato scelto empiricamente come la soglia oltre la quale BGE-M3 comincia a perdere precisione su testo normativo denso in italiano; 2500 è il punto oltre il quale si preferisce bloccare l'ingestion (severity `WARNING`) piuttosto che accettare una compressione lossy che potrebbe silenziosamente alterare il significato di una regola.

Le regole che fissano questi limiti sono [REGOLA-VAL-02] e [REGOLA-VAL-06] della spec di ingestion: qui se ne spiega solo il perché.

## 3. Perché la segmentazione è a cascata e non "sempre per paragrafo"

Tagliare sempre per paragrafo è semplice ma ignora la struttura logica del documento: un blocco atomico spezzato a metà (es. una tabella di vincoli) produce due chunk che, presi singolarmente, sono fuorvianti o inutili. La cascata (blocchi atomici → H2 → H3 → paragrafi) applica il taglio più "grossolano" possibile prima di scendere a quello più fine, in modo che l'unità semantica minima coincida il più possibile con l'unità di significato del documento, non con un artefatto tipografico.

## 4. Perché l'authority è moltiplicativa e non additiva

Se l'authority fosse additiva, un documento a bassa autorità con altissima rilevanza lessicale (alto score ColBERT) potrebbe comunque scavalcare in ranking un documento di sicurezza a piena autorità ma meno "colloquiale" nel linguaggio. Il moltiplicatore impone che nessun documento possa mai superare in ranking un documento di authority superiore, indipendentemente da quanto bene ne combaci il testo con la query — è la garanzia che i `safeguards` e le spec `ENFORCED` restino sempre sopra ai testi descrittivi nel context window, coerentemente con la gerarchia normativa del progetto.

## 5. Perché il version bump è bloccante e non un warning

L'alternativa (permettere l'ingestion senza bump di versione) porta silenziosamente a uno stato in cui Qdrant/NetworkX riflettono contenuto diverso da quanto dichiarato nel frontmatter del documento sorgente — un disallineamento non rilevabile finché qualcuno non lo scopre a valle, tipicamente durante un audit o un incidente. Bloccare con `VERSION_NOT_BUMPED` sposta il costo dell'errore dal momento peggiore (produzione, tempo dopo) al momento migliore (ingestion, subito).

## 6. Boilerplate strutturale e igiene del grafo semantico

Ogni documento normativo di VibeCraft condivide lo stesso pattern di apertura (titolo H1 + sottotitolo di progetto). Se quel sottotitolo fosse un'intestazione H2, la cascata di segmentazione (Sezione 3 sopra) lo tratterebbe come una sezione a sé stante — identica testualmente in decine di documenti, e quindi rilevata dalla Semantic Map come falso positivo di duplicazione ad alta similarità pur non essendo contenuto normativo. Per questo il sottotitolo di progetto va scritto come testo semplice (es. corsivo), mai come intestazione: la scelta tipografica non è estetica, è un vincolo di igiene del chunking.
