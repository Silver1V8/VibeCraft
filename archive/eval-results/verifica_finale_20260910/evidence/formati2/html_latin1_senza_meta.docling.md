# Guida installazione

Requisiti per la città di Forĺ: perché serve Python ≥ 3.14?

## Passaggi

1. Scarica il pacchetto
2. Configura
    - Porta 8000

### Parametri

| Nome    | Valore   |
|---------|----------|
| timeout | 300 s    |
| soglia  | 0,35     |

```
uv sync --frozen
uv run python server.py
```

Dettagli nella [documentazione ufficiale](https://example.org/docs) .

schema