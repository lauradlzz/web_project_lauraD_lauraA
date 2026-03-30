
import re
import requests
from typing import List, Tuple
from rdflib import Graph

NT_FILE      = 'expanded_kb.nt'
OLLAMA_URL   = 'http://localhost:11434/api/generate'
MODEL_NAME   = 'gemma:2b'
MAX_PREDICATES = 80
MAX_CLASSES    = 40
SAMPLE_TRIPLES = 20

def ask_local_llm(prompt, model=MODEL_NAME):
    payload = {'model': model, 'prompt': prompt, 'stream': False}
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    return r.json().get('response', '') if r.status_code == 200 else ''

def load_graph(path):
    g = Graph()
    fmt = 'nt' if path.endswith('.nt') else 'turtle'
    g.parse(path, format=fmt)
    print(f'Loaded {len(g)} triples from {path}')
    return g

def build_schema_summary(g):
    preds = [str(r.p) for r in g.query(f'SELECT DISTINCT ?p WHERE {{ ?s ?p ?o }} LIMIT {MAX_PREDICATES}')]
    clss  = [str(r.cls) for r in g.query(f'SELECT DISTINCT ?cls WHERE {{ ?s a ?cls }} LIMIT {MAX_CLASSES}')]
    samps = [(str(r.s), str(r.p), str(r.o)) for r in g.query(f'SELECT ?s ?p ?o WHERE {{ ?s ?p ?o }} LIMIT {SAMPLE_TRIPLES}')]
    ns    = {p: str(ns) for p, ns in g.namespace_manager.namespaces()}
    for k, v in [('wd','http://www.wikidata.org/entity/'),('wdt','http://www.wikidata.org/prop/direct/')]:
        ns.setdefault(k, v)
    prefixes     = chr(10).join(sorted(f'PREFIX {p}: <{n}>' for p, n in ns.items()))
    pred_lines   = chr(10).join(f'- {p}' for p in preds)
    class_lines  = chr(10).join(f'- {c}' for c in clss)
    sample_lines = chr(10).join(f'- {s} {p} {o}' for s,p,o in samps)
    return f'{prefixes}\n\n# Predicates\n{pred_lines}\n\n# Classes\n{class_lines}\n\n# Samples\n{sample_lines}'

CODE_BLOCK_RE = re.compile(r'```(?:sparql)?\s*(.*?)```', re.IGNORECASE | re.DOTALL)

def extract_sparql(text):
    m = CODE_BLOCK_RE.search(text)
    if m:
        sparql = m.group(1).strip()
        last_brace = sparql.rfind("}")
        if last_brace != -1:
            sparql = sparql[:last_brace + 1].strip()
        return sparql
    lines = []
    in_sparql = False
    for line in text.strip().splitlines():
        upper = line.upper().strip()
        if upper.startswith("SELECT") or upper.startswith("PREFIX"):
            in_sparql = True
        if in_sparql:
            lines.append(line)
        if in_sparql and line.strip() == "}":
            break
    return "\n".join(lines).strip() or text.strip()

SPARQL_INSTRUCTIONS = """You are a SPARQL generator. Convert the QUESTION into a valid SPARQL 1.1 SELECT query.
IMPORTANT PROPERTIES for Michael Jackson (wd:Q2831):
- music genre    -> wdt:P136
- record label   -> wdt:P264
- award received -> wdt:P166
- date of birth  -> wdt:P569
- date of death  -> wdt:P570
- occupation     -> wdt:P106
- influenced by  -> wdt:P737
EXAMPLE:
Q: What is the music genre of Michael Jackson?
SELECT ?genre WHERE { wd:Q2831 wdt:P136 ?genre . }
Return only a sparql code block, nothing after the closing backticks."""

def generate_sparql(question, schema):
    raw = ask_local_llm(f'{SPARQL_INSTRUCTIONS}\n\nSCHEMA:\n{schema}\n\nQUESTION:\n{question}')
    return extract_sparql(raw)

def run_sparql(g, query):
    prefixes = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""
    lines = [l for l in query.splitlines() if not l.strip().upper().startswith("PREFIX")]
    full_query = prefixes + "\n".join(lines).strip()
    res = g.query(full_query)
    return [str(v) for v in res.vars], [tuple(str(c) for c in r) for r in res]

def repair_sparql(schema, question, bad_query, error):
    prompt = f'Fix this SPARQL query.\nSCHEMA:\n{schema}\nQUESTION:\n{question}\nBAD SPARQL:\n{bad_query}\nERROR:\n{error}\nReturn only corrected SPARQL in a code block.'
    return extract_sparql(ask_local_llm(prompt))

def rag_answer(g, schema, question):
    sparql = generate_sparql(question, schema)
    try:
        return run_sparql(g, sparql), sparql, False
    except Exception as e:
        fixed = repair_sparql(schema, question, sparql, str(e))
        try:
            return run_sparql(g, fixed), fixed, True
        except:
            return ([], []), fixed, True

if __name__ == '__main__':
    g = load_graph(NT_FILE)
    schema = build_schema_summary(g)
    print('Michael Jackson KB Chatbot — type quit to exit')
    while True:
        q = input('\nQuestion: ').strip()
        if q.lower() == 'quit': break
        print('\n[Baseline]', ask_local_llm(f'Answer: {q}')[:200])
        (vars_, rows), sparql, repaired = rag_answer(g, schema, q)
        print(f'\n[RAG] (repaired={repaired})')
        print(sparql)
        if rows:
            print(' | '.join(vars_))
            for r in rows[:10]: print(' | '.join(r))
        else:
            print('No results.')
