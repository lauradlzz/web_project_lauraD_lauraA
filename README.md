# RAG with RDF/SPARQL and Local LLM

## Requirements
- Python >= 3.9
- `pip install rdflib requests pandas`
- [Ollama](https://ollama.com) installed and running

## Setup
1. Start Ollama service: `ollama serve`
2. Download a model: `ollama pull gemma:2b`
3. Place `expanded_kb.nt` in the same folder

## Run
```bash
python lab_rag_sparql_gen.py
```

## Model configuration
Edit `MODEL_NAME` in the script to change the LLM:
- `gemma:2b` (default)
- `deepseek-r1:1.5b`
- `llama3.2:1b`

## Architecture
1. Load RDF graph (expanded_kb.nt)
2. Build schema summary (prefixes, predicates, classes, sample triples)
3. User asks a question in natural language
4. LLM generates SPARQL from question + schema
5. Execute SPARQL on local graph with rdflib
6. If SPARQL fails → self-repair loop
7. Return grounded results
