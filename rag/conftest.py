"""Configurazione pytest: mette rag/ su sys.path così che i test possano importare
index / server / code_index (che usano import fratelli: `from index import ...`)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
