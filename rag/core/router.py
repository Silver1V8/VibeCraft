"""Router deterministico M2: sceglie la strategia di risposta di /ask PRIMA del retrieval.

Funzione pura, zero LLM, zero accesso al grafo: solo regole lessicali (regex) sulla
domanda. Le regole sono derivate dagli intent di core.graph_ops.graph_query e dai 6 casi
"structural" del report M1 (eval/results/multihop_20260721_110336.json, trigger M2
scattato: tutti e 6 falliti dalla baseline retrieval A e risolti esattamente dal grafo B).

Principio CONSERVATIVO: una domanda va su "graph" solo se matcha una formulazione
strutturale inequivocabile osservata in M1; in ogni altro caso (incluse le domande
multihop, che richiedono sintesi LLM su più documenti) si resta su "hybrid". Il vincolo
di accettazione è zero falsi positivi sul golden set classico (eval/golden_set.yaml):
meglio un structural mancato (degrada al percorso attuale) che una domanda semantica
risposta con un elenco di nodi.

Ogni regola documenta il caso M1 che la giustifica.
"""
import re

# Regole (nome, pattern) valutate in OR: al primo match la strategia è "graph".
# I pattern lavorano sulla domanda lowercase/strip; \w con Unicode copre le accentate
# ("entità" matcha entit\w*).
_GRAPH_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Caso M1: "quali documenti esistono nel corpus?" (A recall 0.23 — 26 documenti non
    # stanno in top-10; B intent "documenti" exact). Enumerazione globale dei nodi
    # type=document: proprietà del grafo, non di un chunk.
    ("enum-documenti", re.compile(r"\bquali\s+documenti\b.*\besist\w*")),
    # Caso M1: "quali entità del dominio esistono?" (A recall 0.67; B intent "entità"
    # exact, 196 nodi). Enumerazione globale dei nodi type=entity. NON basta la parola
    # "entità" da sola: il golden set classico ha domande semantiche come "definizione e
    # attributi dell'entità EVENTO" che devono restare "hybrid" — serve anche "esist*".
    ("enum-entita", re.compile(r"\bquali\s+entit\w*\b.*\besist\w*")),
    # Casi M1: "quali relazioni ha la specifica di autenticazione?" (A 0.60) e "quali
    # relazioni ha lo standard di codifica?" (A 0.25); B intent "relazioni" exact su
    # entrambi. La forma "relazioni <preposizione> X" chiede gli archi di un nodo. La
    # keyword "relazion" da sola (come in graph_query) sarebbe troppo larga: si richiede
    # che sia retta da un complemento.
    # ALLARGATA 2026-07-22: la forma originale imponeva l'attacco "quali relazioni ha",
    # e mancava le formulazioni altrettanto inequivocabili "quali sono le relazioni DI X"
    # e "relazioni DI X" (entrambe nel golden multihop riscritto). Falsi positivi
    # verificati prima dell'allargamento: 0 su 49 casi del golden set classico e 0 sugli
    # 8 multihop, che devono restare "hybrid".
    ("relazioni-di-nodo", re.compile(r"\brelazioni\s+(?:ha|di|del|della|dello|dei|delle)\b")),
    # Caso M1: "cosa viene impattato se modifico le safeguard di sicurezza?" (A recall
    # 0.14 — il primo anello d'impatto non emerge dal retrieval; B intent "impatto"
    # exact, BFS 349 nodi). Servono ENTRAMBE le radici "impatt*" E "modific*": il solo
    # "impatt" (keyword di graph_query) matcherebbe formulazioni semantiche, e il golden
    # set classico contiene molti "cosa succede se..." che restano "hybrid".
    ("impatto-modifica", re.compile(r"(?=.*\bimpatt)(?=.*\bmodific)")),
    # AGGIUNTA 2026-07-22: "cosa impatta X?" è la forma diretta della stessa domanda, ma
    # non nomina la modifica, quindi la regola sopra (che richiede ENTRAMBE le radici) la
    # mancava. L'attacco "cosa impatt*" è comunque inequivocabile: chiede il fan-out di un
    # nodo. Resta distinto dal generico "impatt", che da solo matcherebbe formulazioni
    # semantiche. Falsi positivi verificati: 0 su 49 casi classici e 0 sugli 8 multihop.
    ("impatto-diretto", re.compile(r"\bcosa\s+impatt\w*")),
    # Caso M1: "dammi i nodi adiacenti alla matrice dei permessi" (A recall 0.60; B
    # intent "vicini" exact, 78 nodi). Lessico esplicito da teoria dei grafi ("nodo/i
    # adiacente/i"): non compare in nessuna domanda semantica del golden set classico.
    ("nodi-adiacenti", re.compile(r"\bnod[oi]\s+adiacent\w*")),
)


def route_question(q: str) -> str:
    """Ritorna "graph" se la domanda è strutturale (risposta = nodi/archi esatti del
    grafo, via graph_ops.graph_query, senza LLM), altrimenti "hybrid" (percorso
    retrieval + sintesi LLM invariato). Deterministica e conservativa: in dubbio
    ⇒ "hybrid"."""
    ql = q.lower().strip()
    for _name, pattern in _GRAPH_RULES:
        if pattern.search(ql):
            return "graph"
    return "hybrid"
