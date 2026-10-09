#!/usr/bin/env python3
"""Offline retrieval evaluation for the HAVEN documentation RAG.

Purpose: one fixed question set with gold documents, the same corpus, and a
grid of retrieval variants -- so every proposed improvement is measured
against the baseline (the behaviour of rag_service as deployed) before it is
allowed into the service.

Runs inside the rag_service image (torch, sentence-transformers, numpy,
rank-bm25, networkx available). With --stub it uses a hashing embedder so the
logic can be tested without model downloads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------- corpus --

TEXT_EXT = {".md", ".markdown", ".txt", ".mmd"}
PROMPT_RE = re.compile(r"(^|/)(prompts?)(/|$)|prompt[^/]*\.md$|\.prompt$", re.I)


def load_docs(root: Path, include_prompts: bool = False):
    docs = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        rel = p.relative_to(root).as_posix()
        if not include_prompts and PROMPT_RE.search(rel):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if not text.strip():
            continue
        docs.append({"path": rel, "text": text, "title": p.stem})
    return docs


# --------------------------------------------------------------- chunkers --

HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
TAG_RE = re.compile(r"<[^>]+>")


def chunk_base(doc, target_words=350, overlap_words=40):
    """Exactly the deployed app/rag/ingest/chunker.py behaviour."""
    text = doc["text"]
    ms = list(HEAD_RE.finditer(text))
    sections = []
    if not ms:
        sections = [(None, text)]
    else:
        for i, m in enumerate(ms):
            end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
            sections.append((m.group(2).strip(), text[m.end():end].strip()))
    out = []
    for title, body in sections:
        body = body.strip()
        if not body:
            continue
        words = body.split()
        if len(words) <= target_words:
            out.append({"heading": title, "content": body, "embed": body, "lex": body})
            continue
        i = 0
        while i < len(words):
            w = words[i:i + target_words]
            if not w:
                break
            c = " ".join(w)
            out.append({"heading": title, "content": c, "embed": c, "lex": c})
            if i + target_words >= len(words):
                break
            i = max(0, i + target_words - overlap_words)
    return out


def _clean_heading(h: str) -> str:
    return TAG_RE.sub("", h).strip()


def _split_blocks(body: str):
    """Split a section body into blocks, keeping fenced code blocks whole."""
    blocks, cur, in_code = [], [], False
    for line in body.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            cur.append(line)
            if not in_code:
                blocks.append("\n".join(cur)); cur = []
            continue
        if in_code:
            cur.append(line); continue
        if not line.strip():
            if cur:
                blocks.append("\n".join(cur)); cur = []
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def chunk_ctx(doc, target_words=220, min_words=60, max_words=380, with_context=True):
    """Heading-path aware chunking.

    - the heading hierarchy is tracked, so each chunk knows 'Doc > H2 > H3'
    - text before the first heading is kept (the deployed chunker drops it)
    - small sibling sections are merged until they reach min_words
    - long sections are split on paragraph/code-block boundaries
    - the text that is embedded and lexically indexed is prefixed with the
      document title and heading path
    """
    text = doc["text"]
    title = doc["title"].replace("_", " ")
    ms = list(HEAD_RE.finditer(text))
    sections = []  # (path list, body)
    if ms and text[:ms[0].start()].strip():
        sections.append(([], text[:ms[0].start()].strip()))
    if not ms:
        sections.append(([], text))
    stack = []
    for i, m in enumerate(ms):
        level = len(m.group(1))
        h = _clean_heading(m.group(2))
        stack = [(l, t) for (l, t) in stack if l < level] + [(level, h)]
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        sections.append(([t for _, t in stack], text[m.end():end].strip()))

    # split long sections into pieces on block boundaries
    pieces = []  # (path, text)
    for path, body in sections:
        if not body:
            # heading without body: keep as a tiny piece so its words survive
            if path:
                pieces.append((path, ""))
            continue
        nw = len(body.split())
        if nw <= max_words:
            pieces.append((path, body)); continue
        cur, cw = [], 0
        for b in _split_blocks(body):
            bw = len(b.split())
            if bw > max_words:  # giant block: hard split by words
                if cur:
                    pieces.append((path, "\n\n".join(cur))); cur, cw = [], 0
                ws = b.split()
                for j in range(0, len(ws), target_words):
                    pieces.append((path, " ".join(ws[j:j + target_words])))
                continue
            if cw + bw > target_words and cw >= min_words:
                pieces.append((path, "\n\n".join(cur))); cur, cw = [], 0
            cur.append(b); cw += bw
        if cur:
            pieces.append((path, "\n\n".join(cur)))

    def _common(a, b):
        out = []
        for x, y in zip(a, b):
            if x != y:
                break
            out.append(x)
        return out

    # Merge small neighbours that are siblings or parent/child. A group keeps the
    # pieces it was built from; its path is their common heading prefix, and each
    # piece that sits deeper than that prefix carries its own heading as a label
    # line, so no heading text is lost by merging.
    groups: list = []
    for path, body in pieces:
        n_words = len(body.split())
        if groups:
            g_path, g_pieces, g_words = groups[-1]
            cp = _common(g_path, path)
            related = len(cp) >= len(path) - 1 and len(cp) >= len(g_path) - 1
            if related and (g_words < min_words or n_words < min_words) and g_words + n_words <= max_words:
                groups[-1] = (cp, g_pieces + [(path, body)], g_words + n_words)
                continue
        groups.append((path, [(path, body)], n_words))

    merged: list = []
    for g_path, g_pieces, g_words in groups:
        if len(g_pieces) == 1:
            merged.append((g_path, g_pieces[0][1], g_words))
            continue
        parts = []
        for p_path, p_body in g_pieces:
            label = " > ".join(p_path[len(g_path):])
            if label and p_body.strip():
                parts.append(f"{label}\n{p_body}")
            elif label:
                parts.append(label)
            elif p_body.strip():
                parts.append(p_body)
        merged.append((g_path, "\n\n".join(parts).strip(), g_words))

    out = []
    for path, body, nw in merged:
        if not body.strip() and not path:
            continue
        hp = " > ".join(path)
        ctx = f"{title}" + (f" > {hp}" if hp else "")
        emb = f"{ctx}\n{body}" if with_context else body
        out.append({"heading": path[-1] if path else None, "heading_path": hp,
                    "content": body, "embed": emb, "lex": emb})
    return out


def chunk_ctx_nocontext(doc):
    return chunk_ctx(doc, with_context=False)


def chunk_ctx_large(doc):
    return chunk_ctx(doc, target_words=320, min_words=90, max_words=520)


def chunk_ctx_small(doc):
    return chunk_ctx(doc, target_words=140, min_words=40, max_words=240)


CHUNKERS = {"base": chunk_base, "ctx": chunk_ctx, "ctxnc": chunk_ctx_nocontext, "ctxL": chunk_ctx_large,
            "ctxS": chunk_ctx_small}

# -------------------------------------------------------------- embedders --

MODELS = {
    "minilm": ("sentence-transformers/all-MiniLM-L6-v2", "", ""),
    "mmini": ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "", ""),
    "me5": ("intfloat/multilingual-e5-small", "query: ", "passage: "),
}


class StubEmbedder:
    """Deterministic hashing bag-of-words embedder (logic tests only)."""
    def __init__(self, dim=384):
        self.dim = dim

    def encode(self, texts):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in tokenize(t):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


class STEmbedder:
    def __init__(self, name):
        from sentence_transformers import SentenceTransformer
        self.m = SentenceTransformer(name)

    def encode(self, texts):
        return np.asarray(self.m.encode(texts, normalize_embeddings=True, batch_size=32,
                                        show_progress_bar=False), dtype=np.float32)


_emb_cache = {}


def get_embedder(key, stub):
    if key not in _emb_cache:
        _emb_cache[key] = StubEmbedder() if stub else STEmbedder(MODELS[key][0])
    return _emb_cache[key]


def embed_corpus(key, texts, cache_dir: Path, tag: str, stub: bool):
    h = hashlib.sha1(("\x00".join(texts)).encode("utf-8", "replace")).hexdigest()[:16]
    f = cache_dir / f"emb_{'stub' if stub else key}_{tag}_{h}.npy"
    if f.exists():
        return np.load(f)
    pp = MODELS[key][2]
    t0 = time.time()
    vec = get_embedder(key, stub).encode([pp + t for t in texts])
    np.save(f, vec)
    print(f"  embedded {len(texts)} chunks with {key} in {time.time()-t0:.0f}s", flush=True)
    return vec


# ---------------------------------------------------------------- lexical --

TOK_RE = re.compile(r"[A-Za-zÀ-ÿ0-9_]+")
CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokenize(t: str, split_ident: bool = False):
    toks = [x.lower() for x in TOK_RE.findall(t)]
    if split_ident:
        extra = []
        for raw in TOK_RE.findall(t):
            parts = [p for p in re.split(r"_", CAMEL_RE.sub("_", raw)) if p]
            if len(parts) > 1:
                extra += [p.lower() for p in parts]
        toks += extra
    return toks


STOP = set("""a an the of to in on for and or is are be as at by it this that with from how what which why when
where do does can i you we my our your not no if then than into about should must will would there their
hva hvordan hvorfor hvilke hvilken hvilket når hvor er en et den det de som på i til av for og eller med
fra om kan skal må vil ikke jeg du vi man seg sin sitt sine har ha å at så bare også blir bli være var
""".split())


class LexAnd:
    """Emulates plainto_tsquery('simple', q): every query token must be present."""
    def __init__(self, texts):
        self.sets = [set(tokenize(t)) for t in texts]
        self.toks = [tokenize(t) for t in texts]

    def search(self, q, k):
        qt = list(dict.fromkeys(tokenize(q)))
        if not qt:
            return []
        res = []
        for i, s in enumerate(self.sets):
            if all(t in s for t in qt):
                tf = sum(self.toks[i].count(t) for t in qt)
                res.append((i, min(0.1, 0.01 * tf / max(1, len(qt)))))  # ts_rank_cd-like small values
        res.sort(key=lambda x: (-x[1], x[0]))
        return res[:k]


class LexBM25:
    """OR semantics with BM25 ranking (what an OR-tsquery + rank gives)."""
    def __init__(self, texts, split_ident=True, k1=1.2, b=0.75):
        self.split = split_ident
        self.docs = [tokenize(t, split_ident) for t in texts]
        self.N = len(self.docs)
        self.avg = sum(len(d) for d in self.docs) / max(1, self.N)
        self.k1, self.b = k1, b
        self.post = defaultdict(list)
        for i, d in enumerate(self.docs):
            tf = defaultdict(int)
            for t in d:
                tf[t] += 1
            for t, c in tf.items():
                self.post[t].append((i, c))
        self.len = [len(d) for d in self.docs]

    def search(self, q, k):
        qt = [t for t in dict.fromkeys(tokenize(q, self.split)) if t not in STOP]
        sc = defaultdict(float)
        for t in qt:
            pl = self.post.get(t)
            if not pl:
                continue
            idf = math.log(1 + (self.N - len(pl) + 0.5) / (len(pl) + 0.5))
            for i, c in pl:
                sc[i] += idf * c * (self.k1 + 1) / (c + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        res = sorted(sc.items(), key=lambda x: (-x[1], x[0]))
        return res[:k]


# ------------------------------------------------------------------ graph --

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")
WIKI_RE = re.compile(r"\[\[([^\]|#]+)")
CODE_RE = re.compile(r"`([^`\n]{3,80})`")
PATHISH_RE = re.compile(r"[\w./-]+\.(?:md|json|swift|py|sh)")


def build_graph(docs, symbols=True):
    """Document graph from the documentation itself.

    Edges: markdown links, [[wikilinks]], mentions of another document's file
    name, and shared rare identifiers (backticked symbols that occur in 2..6
    documents). Returns adjacency dict doc_index -> {neighbor: weight}.
    """
    by_path = {d["path"]: i for i, d in enumerate(docs)}
    by_name = defaultdict(list)
    for i, d in enumerate(docs):
        by_name[Path(d["path"]).name.lower()].append(i)
        by_name[Path(d["path"]).stem.lower()].append(i)
    adj = defaultdict(lambda: defaultdict(float))

    def add(a, b, w):
        if a != b:
            adj[a][b] += w; adj[b][a] += w * 0.7

    sym_docs = defaultdict(set)
    for i, d in enumerate(docs):
        base = Path(d["path"]).parent
        for m in LINK_RE.finditer(d["text"]):
            href = m.group(1)
            if "://" in href:
                continue
            tgt = os.path.normpath((base / href).as_posix())
            j = by_path.get(tgt)
            if j is None:
                c = by_name.get(Path(href).name.lower(), [])
                j = c[0] if len(c) == 1 else None
            if j is not None:
                add(i, j, 1.0)
        for m in WIKI_RE.finditer(d["text"]):
            c = by_name.get(m.group(1).strip().lower(), [])
            if len(c) == 1:
                add(i, c[0], 1.0)
        for m in PATHISH_RE.finditer(re.sub(r"https?://\S+", " ", d["text"])):
            c = by_name.get(Path(m.group(0)).name.lower(), [])
            if len(c) == 1:
                add(i, c[0], 0.6)
        for m in CODE_RE.finditer(d["text"]):
            s = m.group(1).strip()
            if " " in s or len(s) < 5:
                continue
            sym_docs[s].add(i)
    n_sym = 0
    for s, ds in (sym_docs.items() if symbols else []):
        if 2 <= len(ds) <= 6:
            ds = sorted(ds)
            n_sym += 1
            for a in ds:
                for b in ds:
                    if a < b:
                        add(a, b, 0.25)
    n_edges = sum(len(v) for v in adj.values()) // 2
    return adj, {"edges": n_edges, "symbol_groups": n_sym, "docs_with_edges": len(adj)}


def ppr(adj, seeds: dict, alpha=0.5, iters=12):
    """Personalised PageRank over the doc graph (power iteration, sparse)."""
    tot = sum(seeds.values()) or 1.0
    p0 = {k: v / tot for k, v in seeds.items()}
    p = dict(p0)
    for _ in range(iters):
        nxt = defaultdict(float)
        for u, pu in p.items():
            nb = adj.get(u)
            if not nb:
                nxt[u] += pu * (1 - alpha); continue
            s = sum(nb.values())
            for v, w in nb.items():
                nxt[v] += pu * (1 - alpha) * w / s
        for k, v in p0.items():
            nxt[k] += alpha * v
        p = nxt
    return p


# --------------------------------------------------------------- pipeline --

def rrf(rankings, k=60, weights=None):
    sc = defaultdict(float)
    for r_i, r in enumerate(rankings):
        w = weights[r_i] if weights else 1.0
        for rank, (cid, _) in enumerate(r):
            sc[cid] += w / (k + rank + 1)
    return sorted(sc.items(), key=lambda x: (-x[1], x[0]))


def pack(ranked, chunk_doc, top_k=12, per_doc=3):
    out, cnt = [], defaultdict(int)
    for cid, s in ranked:
        d = chunk_doc[cid]
        if cnt[d] >= per_doc:
            continue
        cnt[d] += 1
        out.append((cid, s))
        if len(out) >= top_k:
            break
    return out


class Index:
    def __init__(self, docs, chunker, model, cache, stub, lex_kind):
        self.docs = docs
        self.chunks, self.chunk_doc = [], []
        for di, d in enumerate(docs):
            for c in CHUNKERS[chunker](d):
                self.chunks.append(c); self.chunk_doc.append(di)
        self.model, self.stub = model, stub
        self.vec = embed_corpus(model, [c["embed"] for c in self.chunks], cache, chunker, stub)
        self.lex = LexAnd([c["lex"] for c in self.chunks]) if lex_kind == "and" else LexBM25([c["lex"] for c in self.chunks])
        self.doc_chunks = defaultdict(list)
        for ci, di in enumerate(self.chunk_doc):
            self.doc_chunks[di].append(ci)

    def qvec(self, q):
        return get_embedder(self.model, self.stub).encode([MODELS[self.model][1] + q])[0]


_rerankers = {}


def rerank(q, cands, index, name, n=30):
    if name not in _rerankers:
        from sentence_transformers import CrossEncoder
        _rerankers[name] = CrossEncoder(name, max_length=384)
    head = cands[:n]
    scores = _rerankers[name].predict([(q, index.chunks[c]["embed"][:1600]) for c, _ in head], show_progress_bar=False)
    re_r = sorted(zip([c for c, _ in head], [float(s) for s in scores]), key=lambda x: -x[1])
    return re_r + cands[n:]


def retrieve(q, index: Index, cfg, graph=None):
    qv = index.qvec(q)
    sims = index.vec @ qv
    kv, kl = cfg.get("kv", 50), cfg.get("kl", 50)
    top = np.argsort(-sims)[:kv]
    vec_r = [(int(i), float(sims[i])) for i in top]
    lex_r = index.lex.search(q, kl)
    if cfg["fusion"] == "max":
        best = {}
        for cid, s in vec_r + lex_r:
            if cid not in best or s > best[cid]:
                best[cid] = s
        ranked = sorted(best.items(), key=lambda x: (-x[1], x[0]))
    else:
        ranked = rrf([vec_r, lex_r], weights=cfg.get("w"))

    if cfg.get("rerank"):
        ranked = rerank(q, ranked, index, cfg["rerank"], cfg.get("rr_n", 30))

    g = cfg.get("graph")
    if g and graph is not None:
        # seed docs from the fused ranking
        seeds = defaultdict(float)
        for rank, (cid, s) in enumerate(ranked[:cfg.get("g_seed", 20)]):
            seeds[index.chunk_doc[cid]] += 1.0 / (10 + rank)
        if g == "ppr":
            pr = ppr(graph, seeds, alpha=cfg.get("g_alpha", 0.5))
            docs_r = sorted(pr.items(), key=lambda x: -x[1])[:cfg.get("g_docs", 15)]
            # third ranking: for each graph-ranked doc, its best chunk by vector similarity
            g_rank = []
            for di, s in docs_r:
                cs = index.doc_chunks[di]
                if not cs:
                    continue
                best = max(cs, key=lambda c: sims[c])
                g_rank.append((best, s))
            w = (cfg.get("w") or [1.0, 1.0]) + [cfg.get("g_w", 0.5)]
            ranked = rrf([vec_r, lex_r, g_rank], weights=w)
        elif g == "expand":
            # Reserved-slot expansion: the fused ranking is packed as usual into
            # top_k - g_add places; documents linked from the top documents then get
            # their best chunk in the last g_add places. Nothing above is moved.
            top_k = cfg.get("top_k", 12)
            base = pack(ranked, index.chunk_doc, top_k, cfg.get("per_doc", 3))
            head_docs, present = [], []
            for cid, _ in base:
                d = index.chunk_doc[cid]
                if d not in present:
                    present.append(d)
            head_docs = present[:cfg.get("g_head", 4)]
            add = {}
            for hd in head_docs:
                for nb, w in sorted(graph.get(hd, {}).items(), key=lambda x: -x[1])[:cfg.get("g_fan", 4)]:
                    if nb in present or not index.doc_chunks[nb]:
                        continue
                    best = max(index.doc_chunks[nb], key=lambda c: sims[c])
                    if float(sims[best]) < cfg.get("g_min_sim", 0.0):
                        continue
                    add[best] = max(add.get(best, 0.0), float(sims[best]) * min(1.0, w))
            extra = sorted(add.items(), key=lambda x: -x[1])[:cfg.get("g_add", 2)]
            if not extra:
                return base
            return pack(ranked, index.chunk_doc, top_k - len(extra), cfg.get("per_doc", 3)) + extra
    return pack(ranked, index.chunk_doc, cfg.get("top_k", 12), cfg.get("per_doc", 3))


# ---------------------------------------------------------------- metrics --

def evaluate(gold, index, cfg, graph):
    path_idx = {d["path"]: i for i, d in enumerate(index.docs)}
    rows = []
    for g in gold:
        gd = [path_idx.get(p) for p in g["gold_paths"]]
        if gd[0] is None:
            rows.append({"id": g["id"], "skip": "gold doc not in corpus"}); continue
        res = retrieve(g["question"], index, cfg, graph)
        docs_ranked = []
        for cid, _ in res:
            d = index.chunk_doc[cid]
            if d not in docs_ranked:
                docs_ranked.append(d)
        first = next((r for r, d in enumerate(docs_ranked) if d in gd), None)
        # answer-chunk: a retrieved chunk from the first gold doc containing a must_term
        ans_rank = None
        for r, (cid, _) in enumerate(res):
            if index.chunk_doc[cid] == gd[0]:
                txt = index.chunks[cid]["embed"]
                if any(t in txt for t in g.get("must_terms", [])):
                    ans_rank = r; break
        all_gold = all(d in docs_ranked for d in gd if d is not None)
        rows.append({"id": g["id"], "lang": g["lang"], "type": g["type"], "doc_rank": first,
                     "ans_rank": ans_rank, "all_gold": all_gold,
                     "top_docs": [index.docs[d]["path"] for d in docs_ranked[:5]]})
    return rows


def summarize(rows):
    ok = [r for r in rows if "skip" not in r]

    def agg(rs):
        n = len(rs) or 1
        f = lambda k: round(100 * sum(1 for r in rs if r["doc_rank"] is not None and r["doc_rank"] < k) / n, 1)
        a = lambda k: round(100 * sum(1 for r in rs if r["ans_rank"] is not None and r["ans_rank"] < k) / n, 1)
        mrr = round(sum(1 / (r["doc_rank"] + 1) for r in rs if r["doc_rank"] is not None) / n, 3)
        return {"n": len(rs), "doc@1": f(1), "doc@3": f(3), "doc@5": f(5), "doc@12": f(99), "mrr": mrr,
                "ans@5": a(5), "ans@12": a(99)}

    s = {"all": agg(ok), "skipped": len(rows) - len(ok)}
    for lang in ("no", "en"):
        s[lang] = agg([r for r in ok if r["lang"] == lang])
    for t in ("lookup", "howto", "symbol", "concept", "multihop"):
        s[t] = agg([r for r in ok if r["type"] == t])
    mh = [r for r in ok if r["type"] == "multihop"]
    s["multihop_all_gold@12"] = round(100 * sum(1 for r in mh if r["all_gold"]) / (len(mh) or 1), 1)
    return s


# ------------------------------------------------------------------- main --

MM_RR = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

VARIANTS = {
    # name: (chunker, model, lexical, cfg)
    "V0_baseline_deployed": ("base", "minilm", "and", {"fusion": "max"}),
    "V1_rrf": ("base", "minilm", "and", {"fusion": "rrf"}),
    "V2_rrf_bm25": ("base", "minilm", "bm25", {"fusion": "rrf"}),
    "V3_ctxchunks_max_and": ("ctx", "minilm", "and", {"fusion": "max"}),
    "V4_ctx_rrf_bm25": ("ctx", "minilm", "bm25", {"fusion": "rrf"}),
    "V5_ctx_rrf_bm25_mmini": ("ctx", "mmini", "bm25", {"fusion": "rrf"}),
    "V6_ctx_rrf_bm25_me5": ("ctx", "me5", "bm25", {"fusion": "rrf"}),
    "V7_me5_graph_ppr": ("ctx", "me5", "bm25", {"fusion": "rrf", "graph": "ppr"}),
    "V8_me5_graph_expand": ("ctx", "me5", "bm25", {"fusion": "rrf", "graph": "expand"}),
    "V9_me5_rerank": ("ctx", "me5", "bm25", {"fusion": "rrf", "rerank": MM_RR}),
    "V10_me5_rerank_graph_expand": ("ctx", "me5", "bm25", {"fusion": "rrf", "rerank": MM_RR, "graph": "expand"}),
    "V11_base_me5_only": ("base", "me5", "and", {"fusion": "max"}),
    "V12_minilm_graph_ppr": ("ctx", "minilm", "bm25", {"fusion": "rrf", "graph": "ppr"}),
    "V13_minilm_graph_expand": ("ctx", "minilm", "bm25", {"fusion": "rrf", "graph": "expand"}),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--gold", required=True, nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default="/tmp/ragcache")
    ap.add_argument("--variants", default="all")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--extra", default="", help="JSON file with additional variants")
    a = ap.parse_args()

    cache = Path(a.cache); cache.mkdir(parents=True, exist_ok=True)
    docs = load_docs(Path(a.corpus))
    gold = []
    for f in a.gold:
        gold += [json.loads(l) for l in Path(f).read_text().splitlines() if l.strip()]
    variants = dict(VARIANTS)
    if a.extra:
        for k, v in json.loads(Path(a.extra).read_text()).items():
            variants[k] = tuple(v)
    names = list(variants) if a.variants == "all" else a.variants.split(",")
    graph, gstats = build_graph(docs)
    graph_links, gl_stats = build_graph(docs, symbols=False)
    print(f"docs={len(docs)} gold={len(gold)} graph={gstats} links_only={gl_stats}", flush=True)

    out_path = Path(a.out)
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    results["_meta"] = {"docs": len(docs), "gold": len(gold), "graph": gstats, "stub": a.stub}
    idx_cache = {}
    for name in names:
        ch, model, lexk, cfg = variants[name]
        key = (ch, model, lexk)
        t0 = time.time()
        try:
            if key not in idx_cache:
                idx_cache[key] = Index(docs, ch, model, cache, a.stub, lexk)
            idx = idx_cache[key]
            rows = evaluate(gold, idx, cfg, graph_links if cfg.get("g_kind") == "links" else graph)
            s = summarize(rows)
            s["chunks"] = len(idx.chunks)
            s["avg_words"] = round(sum(len(c["content"].split()) for c in idx.chunks) / len(idx.chunks), 1)
            s["sec_per_q"] = round((time.time() - t0) / max(1, len(gold)), 3)
            results[name] = {"summary": s, "rows": rows, "cfg": [ch, model, lexk, cfg]}
            a_ = s["all"]
            print(f"{name:34s} doc@1={a_['doc@1']:5} doc@5={a_['doc@5']:5} doc@12={a_['doc@12']:5} mrr={a_['mrr']:.3f} "
                  f"ans@5={a_['ans@5']:5} ans@12={a_['ans@12']:5} | no@5={s['no']['doc@5']:5} en@5={s['en']['doc@5']:5} "
                  f"mh_all={s['multihop_all_gold@12']:5} chunks={s['chunks']} {s['sec_per_q']}s/q", flush=True)
        except Exception as e:  # keep going; a failed variant is a result too
            results[name] = {"error": repr(e)}
            print(f"{name}: ERROR {e!r}", flush=True)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
