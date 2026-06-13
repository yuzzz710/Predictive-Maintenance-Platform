"""
RAG Engine — Lightweight document retrieval for AI Copilot.
================================================================
Architecture:
  - Embedding: BAAI/bge-small-zh-v1.5 (local, ~100MB, Chinese-optimized)
  - Vector DB: Chroma (persistent local storage, no server needed)
  - Three knowledge base collections: sys_docs, maint_kb, fault_cases
  - Fallback: DeepSeek Embedding API if BGE model unavailable

Flow:
  User question → classify → embed → Chroma.search() → top-K chunks → inject into LLM prompt
"""

import os
import re
import json
import time
import hashlib
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .config import DASHBOARD_DATA, PROJECT_ROOT, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

# ── Lazy imports (heavy) ──────────────────────────────────────────────────
_chroma_client = None
_embedding_model = None
_embedding_fn = None  # resolved at init time
_last_embedding_latency_ms = 0
_collections = {}     # name → Chroma collection

# ── Paths ──────────────────────────────────────────────────────────────────
KB_DIR = DASHBOARD_DATA / "knowledge_base"
CHROMA_DIR = KB_DIR / "chroma"
MAINT_KB_DIR = KB_DIR / "maintenance"
SYS_DOC_DIR = PROJECT_ROOT   # root has all .md files
LOG_PATH = DASHBOARD_DATA / "rag_log.jsonl"

COLLECTION_NAMES = ["sys_docs", "maint_kb", "fault_cases"]

# ── Embedding model config ─────────────────────────────────────────────────
BGE_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIM = 512
CHUNK_SIZE = 800       # characters per chunk
CHUNK_OVERLAP = 100    # character overlap between chunks
RELEVANCE_THRESHOLD = 0.30  # minimum cosine similarity to include result

# ── Document definitions ───────────────────────────────────────────────────
# System docs: key .md files distributed across the project
SYS_DOC_FILES = [
    "CLAUDE.md",
    "项目介绍.md",
    "项目说明文档-完整版.md",
    "SENSOR_UPGRADE_ROADMAP.md",
    "RUL改进方案.md",
    "skills/predictive-maintenance-data-prep/SKILL.md",
    "skills/predictive-maintenance-stat-inference/SKILL.md",
    "skills/predictive-maintenance-ml-inference/SKILL.md",
    "skills/predictive-maintenance-diagnosis/SKILL.md",
    "skills/predictive-maintenance-decision/SKILL.md",
    "数据探索分析/figure_documentation_master.md",
    "基线分析和确定/BASELINE_DEVELOPMENT_DOC.md",
    "预测性维护模型/model_development_doc.md",
    "预测性维护模型_v2/model_development_doc_v2.md",
    "预测性维护模型_v3/predictive_maintenance_system_design.md",
    "agent-mcp架构/mcp-adapter-guide.md",
]

# ── Retrieval log ──────────────────────────────────────────────────────────
_log_lock = threading.Lock()


def _log_retrieval(query: str, collection: str, n_results: int, elapsed_ms: float):
    """Append a retrieval record to the JSONL log file."""
    try:
        KB_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now().isoformat(),
            "query": query[:200],
            "collection": collection,
            "n_results": n_results,
            "elapsed_ms": round(elapsed_ms, 1),
        }
        with _log_lock:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging is best-effort


def get_retrieval_logs(limit: int = 50) -> List[Dict]:
    """Return recent retrieval log entries."""
    if not LOG_PATH.exists():
        return []
    logs = []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        return []
    return logs[-limit:][::-1]  # newest first


# ═══════════════════════════════════════════════════════════════════════════
# Embedding Functions
# ═══════════════════════════════════════════════════════════════════════════

def _init_bge_model():
    """Lazy-load the BGE embedding model with mirror fallback."""
    global _embedding_model, _embedding_fn
    if _embedding_model is not None:
        return True

    # Force offline — skip HF connectivity checks, use local cache
    os.environ["HF_HUB_OFFLINE"] = "1"

    # Strategy: local cache → HF mirror → TF-IDF
    from sentence_transformers import SentenceTransformer

    # Try 0: Load from local cache (no network, instant if cached)
    try:
        _embedding_model = SentenceTransformer(BGE_MODEL_NAME, local_files_only=True)
        _embedding_fn = _embed_bge
        print(f"[rag_engine] BGE model loaded from local cache (no network)")
        return True
    except Exception as e:
        print(f"[rag_engine] BGE local cache miss: {e}")

    # Try 1: Load from HuggingFace with mirror endpoint
    mirrors = [
        "https://hf-mirror.com",       # Chinese mirror
        "https://huggingface.co",       # Official (may be blocked)
    ]

    for mirror in mirrors:
        try:
            os.environ["HF_ENDPOINT"] = mirror
            print(f"[rag_engine] Trying BGE model via {mirror}...")
            _embedding_model = SentenceTransformer(
                BGE_MODEL_NAME,
                trust_remote_code=False,
            )
            _embedding_fn = _embed_bge
            print(f"[rag_engine] BGE model loaded successfully via {mirror}")
            return True
        except Exception as e:
            print(f"[rag_engine] BGE via {mirror} failed: {str(e)[:120]}")
            continue

    # Try 2: DeepSeek Embedding API
    print("[rag_engine] BGE model unavailable, trying DeepSeek embedding API...")
    try:
        import httpx
        # The DeepSeek API doesn't have a separate embeddings endpoint,
        # but we can test connectivity and check for the endpoint
        if DEEPSEEK_API_KEY:
            _embedding_fn = _embed_deepseek
            print("[rag_engine] Using DeepSeek Embedding API as embedding backend")
            return True
    except Exception:
        pass

    # Try 3: TF-IDF fallback (always works, lower quality)
    print("[rag_engine] Using TF-IDF fallback (lower quality but functional)")
    _embedding_fn = _fallback_tfidf
    return True


def _embed_bge(texts: List[str]) -> List[List[float]]:
    """Embed texts using local BGE model."""
    global _embedding_model
    if _embedding_model is None:
        return []
    embeddings = _embedding_model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return embeddings.tolist()


def _embed_deepseek(texts: List[str]) -> List[List[float]]:
    """Embed texts using DeepSeek Embedding API (fallback).
    Note: DeepSeek's primary API is chat completions. The embeddings endpoint
    may not be available on all deployments. Falls back to TF-IDF on failure.
    """
    import httpx
    try:
        resp = httpx.post(
            f"{DEEPSEEK_BASE_URL}/v1/embeddings",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "input": texts,
            },
            timeout=5.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            if items:
                items.sort(key=lambda x: x.get("index", 0))
                return [item.get("embedding", []) for item in items]
            else:
                print(f"[rag_engine] DeepSeek embedding API returned empty data")
                return _fallback_tfidf(texts)
        else:
            print(f"[rag_engine] DeepSeek embedding API error: {resp.status_code}")
            return _fallback_tfidf(texts)
    except Exception as e:
        print(f"[rag_engine] DeepSeek embedding API exception: {e}")
        return _fallback_tfidf(texts)


def _fallback_tfidf(texts: List[str]) -> List[List[float]]:
    """
    Minimal TF-IDF fallback when no embedding model is available.
    Uses character bigram features — works for Chinese too.
    Returns normalized sparse-like vectors padded to EMBEDDING_DIM.
    """
    # Build vocabulary from all texts
    vocab = {}
    for text in texts:
        for i in range(len(text) - 1):
            bigram = text[i:i + 2]
            vocab[bigram] = vocab.get(bigram, 0) + 1

    # Filter to top terms
    sorted_terms = sorted(vocab.items(), key=lambda x: -x[1])[:EMBEDDING_DIM]
    term_to_idx = {t: i for i, (t, _) in enumerate(sorted_terms)}

    vectors = []
    for text in texts:
        vec = [0.0] * min(len(term_to_idx), EMBEDDING_DIM)
        for i in range(len(text) - 1):
            bigram = text[i:i + 2]
            if bigram in term_to_idx:
                idx = term_to_idx[bigram]
                if idx < EMBEDDING_DIM:
                    vec[idx] += 1.0
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        # Pad to EMBEDDING_DIM
        while len(vec) < EMBEDDING_DIM:
            vec.append(0.0)
        vectors.append(vec)

    return vectors


def embed(texts: List[str]) -> List[List[float]]:
    """Embed texts using whichever backend is available."""
    global _embedding_fn, _last_embedding_latency_ms
    t0 = time.perf_counter()
    if _embedding_fn is None:
        if not _init_bge_model():
            result = _fallback_tfidf(texts)
            _last_embedding_latency_ms = round((time.perf_counter() - t0) * 1000)
            return result
    result = _embedding_fn(texts)
    _last_embedding_latency_ms = round((time.perf_counter() - t0) * 1000)
    return result


def embed_query(text: str) -> List[float]:
    """Embed a single query string."""
    results = embed([text])
    return results[0] if results else [0.0] * EMBEDDING_DIM


# ═══════════════════════════════════════════════════════════════════════════
# Chroma Vector Store
# ═══════════════════════════════════════════════════════════════════════════

def _init_chroma():
    """Lazy-load Chroma client and collections."""
    global _chroma_client, _collections
    if _chroma_client is not None:
        return

    try:
        import chromadb
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        settings = chromadb.Settings(
            anonymized_telemetry=False,
            allow_reset=True,
        )
        _chroma_client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=settings,
        )
        # Get or create collections
        for name in COLLECTION_NAMES:
            try:
                _collections[name] = _chroma_client.get_collection(name)
            except Exception:
                _collections[name] = _chroma_client.create_collection(
                    name=name,
                    metadata={"description": f"Knowledge base: {name}",
                              "hnsw:space": "cosine"},
                )
        print(f"[rag_engine] Chroma initialized at {CHROMA_DIR}")
    except Exception as e:
        print(f"[rag_engine] Chroma init failed: {e}")
        _chroma_client = None
        _collections = {}


def _get_collection(name: str):
    """Get a Chroma collection by name, initializing if needed."""
    if name not in _collections:
        _init_chroma()
    return _collections.get(name)


# ═══════════════════════════════════════════════════════════════════════════
# Document Loading & Chunking
# ═══════════════════════════════════════════════════════════════════════════

def _load_text_file(path: Path) -> Optional[str]:
    """Load text content from a file (.md, .txt)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="gbk") as f:
                return f.read()
        except Exception:
            return None
    except Exception:
        return None


def _chunk_markdown(text: str, source: str, chunk_size: int = CHUNK_SIZE,
                    overlap: int = CHUNK_OVERLAP) -> List[Dict]:
    """
    Chunk markdown text semantically.
    - Splits on ## section headers first
    - If a section is still too long, splits on double-newlines (paragraphs)
    - If a paragraph is still too long, splits at chunk_size with overlap
    """
    chunks = []
    chunk_idx = 0  # unique counter per document

    # Step 1: Split on ## headers
    sections = re.split(r'\n(?=## )', text)
    current_section_title = ""

    for section in sections:
        # Extract section title if present
        header_match = re.match(r'^##\s+(.+)', section)
        if header_match:
            current_section_title = header_match.group(1).strip()
        elif not current_section_title:
            # Try # header
            h1_match = re.match(r'^#\s+(.+)', section)
            if h1_match:
                current_section_title = h1_match.group(1).strip()

        # Step 2: Split section into paragraphs (double newlines)
        paragraphs = re.split(r'\n\n+', section)

        buffer = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Try to fit paragraph into current buffer
            if buffer and len(buffer) + len(para) + 2 <= chunk_size:
                buffer += "\n\n" + para
            elif len(para) <= chunk_size:
                # Flush buffer, start new one
                if buffer:
                    chunks.append(_make_chunk(buffer, source, current_section_title, chunk_idx))
                    chunk_idx += 1
                buffer = para
            else:
                # Paragraph is longer than chunk_size — split by character
                if buffer:
                    chunks.append(_make_chunk(buffer, source, current_section_title, chunk_idx))
                    chunk_idx += 1
                    buffer = ""

                # Split long paragraph with overlap
                start = 0
                while start < len(para):
                    end = min(start + chunk_size, len(para))
                    # Try to break at sentence boundary (。！？\n)
                    if end < len(para):
                        for break_char in ['。', '！', '？', '\n', '；', '，']:
                            last_break = para.rfind(break_char, start + chunk_size // 2, end)
                            if last_break > start:
                                end = last_break + 1
                                break
                    sub = para[start:end].strip()
                    if sub:
                        chunks.append(_make_chunk(sub, source, current_section_title, chunk_idx))
                        chunk_idx += 1
                    start = end - overlap if end - overlap > start else end

        # Flush remaining buffer
        if buffer:
            chunks.append(_make_chunk(buffer, source, current_section_title, chunk_idx))
            chunk_idx += 1

    return chunks


def _make_chunk(text: str, source: str, section: str, chunk_idx: int = 0) -> Dict:
    """Create a chunk dict with metadata."""
    # More unique ID: source + section + chunk index + content hash
    unique_str = f"{source}_{section}_{chunk_idx}_{len(text)}"
    content_hash = hashlib.md5(unique_str.encode("utf-8")).hexdigest()[:8]
    safe_source = source.replace('\\', '/').replace('.md', '').replace('/', '_')[:40]
    return {
        "id": f"{safe_source}_{content_hash}",
        "content": text,
        "metadata": {
            "source": source,
            "section": section or "",
            "char_count": len(text),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Indexing
# ═══════════════════════════════════════════════════════════════════════════

def _index_files(file_paths: List[Path], collection_name: str, base_dir: Path):
    """Index a list of files into a Chroma collection."""
    collection = _get_collection(collection_name)
    if collection is None:
        print(f"[rag_engine] Chroma not available, skipping index of {collection_name}")
        return 0

    all_chunks = []
    for fp in file_paths:
        if not fp.exists():
            continue
        text = _load_text_file(fp)
        if text is None or not text.strip():
            continue

        # Relative path for display
        try:
            rel_path = str(fp.relative_to(base_dir))
        except ValueError:
            rel_path = str(fp)

        chunks = _chunk_markdown(text, source=rel_path)
        all_chunks.extend(chunks)

    if not all_chunks:
        return 0

    # Clear existing and rebuild
    try:
        # Get existing IDs and delete them
        existing = collection.get()
        if existing and existing.get("ids"):
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    # Batch insert (Chroma recommends batches of ~100)
    batch_size = 100
    total = len(all_chunks)
    for i in range(0, total, batch_size):
        batch = all_chunks[i:i + batch_size]
        ids = [c["id"] for c in batch]
        contents = [c["content"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        # Embed
        embeddings = embed(contents)
        if not embeddings or len(embeddings) != len(contents):
            print(f"[rag_engine] Embedding failed for batch {i // batch_size}")
            continue

        collection.add(
            ids=ids,
            documents=contents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    print(f"[rag_engine] Indexed {total} chunks into '{collection_name}' from {len(file_paths)} files")
    return total


def index_system_docs() -> int:
    """Index all system documentation files."""
    file_paths = [SYS_DOC_DIR / f for f in SYS_DOC_FILES]
    return _index_files(file_paths, "sys_docs", SYS_DOC_DIR)


def index_maintenance_kb() -> int:
    """Index maintenance knowledge base files."""
    if not MAINT_KB_DIR.exists():
        return 0
    file_paths = list(MAINT_KB_DIR.glob("*.md")) + list(MAINT_KB_DIR.glob("*.txt"))
    return _index_files(file_paths, "maint_kb", MAINT_KB_DIR)


def index_fault_cases() -> int:
    """Auto-generate fault case entries from log.csv and index them."""
    log_csv = DASHBOARD_DATA / "log.csv"
    if not log_csv.exists():
        # Try alternative path
        log_csv = DASHBOARD_DATA.parent / "原始数据集" / "MACHINE_LOG_DATA._2025.csv"

    if not log_csv.exists():
        print(f"[rag_engine] log.csv not found at {log_csv}")
        return 0

    import pandas as pd
    df = pd.read_csv(log_csv)
    # Handle both possible column name formats
    fault_col = "Failure.Equipment.Type" if "Failure.Equipment.Type" in df.columns else "Failure.Type"
    volt_col = "Op.Voltage" if "Op.Voltage" in df.columns else "Voltage"
    amp_col = "Op.Amperage" if "Op.Amperage" in df.columns else "Amperage"
    temp_col = "Op.Temperature" if "Op.Temperature" in df.columns else "Temperature"
    rpm_col = "Rotor Speed" if "Rotor Speed" in df.columns else "Rotor.Speed"

    # Filter to failure rows only (Failure.Type != 0)
    fail_df = df[df[fault_col] != 0].copy()
    if fail_df.empty:
        return 0

    # Group by equipment + failure type for case summaries
    cases = []
    for (mid, ftype), group in fail_df.groupby(["Equipment.Id", fault_col]):
        group = group.sort_values("Date") if "Date" in group.columns else group
        first_row = group.iloc[0]
        last_row = group.iloc[-1]

        voltage_vals = group[volt_col].dropna()
        amperage_vals = group[amp_col].dropna()
        temp_vals = group[temp_col].dropna()
        rpm_vals = group[rpm_col].dropna() if rpm_col in group.columns else None

        fault_group = "Normal"
        ftype_int = int(ftype)
        if ftype_int in (1, 2):
            fault_group = "Subtle"
        elif ftype_int in (3, 6, 7, 8, 9):
            fault_group = "Thermal"
        elif ftype_int in (4, 5):
            fault_group = "High-Voltage"

        case_text = (
            f"## 故障案例: {mid} — Type {ftype_int} ({fault_group})\n\n"
            f"**设备**: {mid}\n"
            f"**故障类型**: Type {ftype_int} ({fault_group})\n"
            f"**发生时间**: {first_row.get('Date', 'N/A')}\n"
            f"**传感器读数**: 电压={voltage_vals.mean():.1f}V, "
            f"电流={amperage_vals.mean():.1f}A, "
            f"温度={temp_vals.mean():.1f}°C"
        )
        if rpm_vals is not None and len(rpm_vals) > 0:
            case_text += f", 转速={rpm_vals.mean():.0f} RPM"
        case_text += "\n"
        case_text += f"**参数范围**: 电压[{voltage_vals.min():.1f}-{voltage_vals.max():.1f}]V, "
        case_text += f"电流[{amperage_vals.min():.1f}-{amperage_vals.max():.1f}]A, "
        case_text += f"温度[{temp_vals.min():.1f}-{temp_vals.max():.1f}]°C\n"
        case_text += f"**出现次数**: {len(group)}次\n"
        case_text += f"**故障分组**: {fault_group}\n"

        cases.append({
            "id": f"fault_case_{mid}_type{ftype_int}",
            "content": case_text,
            "metadata": {
                "source": "log.csv (auto-generated)",
                "section": f"故障案例",
                "machine_id": mid,
                "fault_type": f"Type {ftype_int}",
                "fault_group": fault_group,
            },
        })

    # Index into Chroma
    collection = _get_collection("fault_cases")
    if collection is None:
        return 0

    try:
        existing = collection.get()
        if existing and existing.get("ids"):
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    batch_size = 100
    for i in range(0, len(cases), batch_size):
        batch = cases[i:i + batch_size]
        ids = [c["id"] for c in batch]
        contents = [c["content"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        embeddings = embed(contents)
        if not embeddings:
            continue

        collection.add(
            ids=ids,
            documents=contents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    print(f"[rag_engine] Indexed {len(cases)} fault cases into 'fault_cases'")
    return len(cases)


def rebuild_all() -> Dict[str, int]:
    """Rebuild all three knowledge base collections."""
    counts = {}
    counts["sys_docs"] = index_system_docs()
    counts["maint_kb"] = index_maintenance_kb()
    counts["fault_cases"] = index_fault_cases()
    return counts


# ═══════════════════════════════════════════════════════════════════════════
# Search & Retrieval
# ═══════════════════════════════════════════════════════════════════════════

def search(query: str, collection_name: str, k: int = 5) -> Dict:
    """
    Semantic search within a single knowledge base collection.
    Returns: { "query": str, "results": [...], "total_found": int }
    """
    collection = _get_collection(collection_name)
    if collection is None:
        return {"query": query, "results": [], "total_found": 0,
                "error": f"Collection '{collection_name}' not available"}

    t0 = time.time()

    try:
        query_embedding = embed_query(query)
        # Chroma query
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        _log_retrieval(query, collection_name, 0, elapsed)
        return {"query": query, "results": [], "total_found": 0,
                "error": f"Search error: {str(e)}"}

    elapsed = (time.time() - t0) * 1000

    items = []
    if results and results.get("documents") and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            distance = results["distances"][0][i] if results.get("distances") else 0
            # Chroma returns L2 distance for normalized vectors by default
            # For unit vectors: L2² = 2(1 - cos) → cos = 1 - L2²/2
            d = float(distance)
            score = max(0.0, 1.0 - (d * d) / 2.0)

            # Filter by relevance threshold
            if score < RELEVANCE_THRESHOLD:
                continue

            items.append({
                "rank": len(items) + 1,
                "score": round(score, 4),
                "source": meta.get("source", "unknown"),
                "section": meta.get("section", ""),
                "collection": collection_name,
                "content": doc[:600] + ("..." if len(doc) > 600 else ""),
                "full_content": doc,
            })

    _log_retrieval(query, collection_name, len(items), elapsed)

    return {
        "query": query,
        "results": items,
        "total_found": len(items),
        "elapsed_ms": round(elapsed, 1),
    }


def search_all(query: str, k: int = 5) -> Dict:
    """Search across all three knowledge bases and return merged results."""
    all_results = []
    summary = {}

    for coll_name in COLLECTION_NAMES:
        result = search(query, coll_name, k=max(2, k // 2))
        summary[coll_name] = result.get("total_found", 0)
        for item in result.get("results", []):
            item["collection"] = coll_name
            all_results.append(item)

    # Sort by score, keep top K overall
    all_results.sort(key=lambda x: -x["score"])
    all_results = all_results[:k]

    # Build context string for injection into LLM prompt
    context_parts = []
    for i, item in enumerate(all_results):
        context_parts.append(
            f"[{i + 1}] 来源: {item['source']}"
            + (f" > {item['section']}" if item.get('section') else "")
            + f" | 相关度: {item['score']:.2f}\n"
            + f"{item['content']}"
        )
    context_str = "\n\n---\n\n".join(context_parts) if context_parts else ""

    return {
        "query": query,
        "results": all_results,
        "total_found": len(all_results),
        "context_string": context_str,
        "summary_per_collection": summary,
    }


def search_with_tier(query: str, tier: str, k: int = 5) -> Dict:
    """
    Force-degrade to a specific embedding tier and search.
    Used by the degradation simulation UI.
    BGE: normal Chroma vector search.
    DeepSeek API: vector search with DeepSeek embeddings (falls back gracefully if no API key).
    TF-IDF: keyword-based text search against chunk content (bypasses Chroma — demonstrates degraded but functional retrieval).
    """
    global _embedding_fn
    t0 = time.perf_counter()
    original_fn = _embedding_fn

    try:
        if tier == "bge_local":
            _init_bge_model()
            result = search_all(query, k=k)

        elif tier == "deepseek_api":
            if not DEEPSEEK_API_KEY:
                elapsed = round((time.perf_counter() - t0) * 1000)
                return {"tier": tier, "query": query, "results": [],
                        "total_found": 0, "elapsed_ms": elapsed,
                        "note": "DeepSeek API Key 未配置，无法使用云端嵌入"}
            _embedding_fn = _embed_deepseek
            result = search_all(query, k=k)
            # If all results were threshold-filtered, note it
            if result.get("total_found", 0) == 0:
                result["note"] = "DeepSeek 嵌入向量空间与 BGE 索引不兼容，语义检索不可用（这正是降级场景的真实表现）"

        elif tier == "tfidf_fallback":
            # TF-IDF cannot meaningfully search a BGE-indexed Chroma collection.
            # Instead, do a keyword-match search against raw chunk content —
            # this simulates the real TF-IDF fallback: slower, less accurate, but always works.
            _init_chroma()
            query_terms = set(query)
            # Also add bigrams for Chinese matching
            for i in range(len(query) - 1):
                query_terms.add(query[i:i + 2])
            keyword_results = []
            for coll_name in COLLECTION_NAMES:
                coll = _collections.get(coll_name)
                if not coll:
                    continue
                try:
                    count = coll.count()
                    existing = coll.get(include=["metadatas", "documents"], limit=min(count, 200))
                    if existing and existing.get("ids"):
                        for idx, chunk_id in enumerate(existing["ids"]):
                            content = existing.get("documents", [""])[idx] if idx < len(existing.get("documents", [])) else ""
                            meta = existing.get("metadatas", [{}])[idx] if idx < len(existing.get("metadatas", [])) else {}
                            # Simple TF scoring: count overlapping terms
                            score = 0
                            for term in query_terms:
                                if term in content:
                                    score += 1
                            if score > 0:
                                norm_score = min(score / max(len(query_terms), 1), 1.0)
                                keyword_results.append({
                                    "source": meta.get("source", ""),
                                    "section": meta.get("section", meta.get("source", "")),
                                    "collection": coll_name,
                                    "content": content[:300],
                                    "score": round(norm_score, 4),
                                })
                except Exception:
                    pass
            keyword_results.sort(key=lambda x: -x["score"])
            total = len(keyword_results)
            keyword_results = keyword_results[:k]
            elapsed = round((time.perf_counter() - t0) * 1000)
            return {
                "tier": tier, "query": query, "results": keyword_results,
                "total_found": total, "elapsed_ms": elapsed,
            }
        else:
            return {"error": f"Unknown tier: {tier}"}

        elapsed = round((time.perf_counter() - t0) * 1000)
        result["elapsed_ms"] = result.get("elapsed_ms", elapsed)
        result["tier"] = tier
        return result
    finally:
        _embedding_fn = original_fn


def search_all_as_context(query: str, k: int = 5) -> str:
    """
    Convenience: search all collections and return formatted context string
    ready to inject into the LLM system prompt.
    Returns empty string if no relevant results found.
    """
    result = search_all(query, k=k)
    return result.get("context_string", "")


# ═══════════════════════════════════════════════════════════════════════════
# Knowledge Base Management
# ═══════════════════════════════════════════════════════════════════════════

def get_stats() -> Dict:
    """Get statistics for all knowledge base collections."""
    _init_chroma()
    # Detect current embedding tier
    tier = "tfidf_fallback"
    if _embedding_model is not None:
        tier = "bge_local"
    elif _embedding_fn is not None:
        fn_name = getattr(_embedding_fn, '__name__', '')
        if 'deepseek' in fn_name:
            tier = "deepseek_api"
        elif 'tfidf' in fn_name:
            tier = "tfidf_fallback"
    stats = {
        "engine_available": _embedding_fn is not None or _init_bge_model(),
        "chroma_available": _chroma_client is not None,
        "embedding_tier": tier,
        "embedding_latency_ms": _last_embedding_latency_ms,
        "collections": {},
    }
    for name in COLLECTION_NAMES:
        coll = _collections.get(name)
        if coll:
            try:
                count = coll.count()
                # Get unique sources from metadata
                existing = coll.get(include=["metadatas"], limit=min(count, 10000))
                sources = set()
                if existing and existing.get("metadatas"):
                    for meta in existing["metadatas"]:
                        src = meta.get("source", "")
                        if src:
                            sources.add(src)
                stats["collections"][name] = {
                    "chunk_count": count,
                    "document_count": len(sources),
                    "documents": sorted(sources),
                }
            except Exception as e:
                stats["collections"][name] = {"error": str(e)}
        else:
            stats["collections"][name] = {"chunk_count": 0, "document_count": 0, "documents": []}
    return stats


def delete_document(source: str, collection_name: str) -> int:
    """Delete all chunks for a given source document from a collection."""
    collection = _get_collection(collection_name)
    if collection is None:
        return 0

    try:
        existing = collection.get(include=["metadatas"])
        if not existing or not existing.get("ids"):
            return 0

        ids_to_delete = []
        for i, meta in enumerate(existing["metadatas"]):
            if meta.get("source") == source:
                ids_to_delete.append(existing["ids"][i])

        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            print(f"[rag_engine] Deleted {len(ids_to_delete)} chunks for '{source}' from '{collection_name}'")
        return len(ids_to_delete)
    except Exception as e:
        print(f"[rag_engine] Delete error: {e}")
        return 0


def index_single_file(file_path: str, collection_name: str) -> int:
    """Index a single file into a collection."""
    fp = Path(file_path)
    if not fp.exists():
        return -1  # file not found

    # Determine base directory
    if str(fp).startswith(str(MAINT_KB_DIR)):
        base_dir = MAINT_KB_DIR
    else:
        base_dir = PROJECT_ROOT

    return _index_files([fp], collection_name, base_dir)


# ── Startup: eager init ────────────────────────────────────────────────────

_initialized = False
_init_lock = threading.Lock()


def ensure_initialized():
    """Idempotent initialization — safe to call at startup and on every request.
    Uses try-lock to avoid blocking: if another thread is already initializing,
    returns immediately (callers should handle engine-not-ready gracefully)."""
    global _initialized
    if _initialized:
        return

    # Try to acquire lock without blocking
    acquired = _init_lock.acquire(blocking=False)
    if not acquired:
        # Another thread is initializing — just return
        return

    try:
        if _initialized:
            return

        print("[rag_engine] Initializing RAG engine...")
        _init_chroma()
        _init_bge_model()

        # Check if we need to index (collections empty)
        for name in COLLECTION_NAMES:
            coll = _collections.get(name)
            if coll and coll.count() == 0:
                print(f"[rag_engine] Collection '{name}' is empty, indexing...")
                if name == "sys_docs":
                    index_system_docs()
                elif name == "maint_kb":
                    index_maintenance_kb()
                elif name == "fault_cases":
                    index_fault_cases()

        _initialized = True
        stats = get_stats()
        total_chunks = sum(c.get("chunk_count", 0) for c in stats.get("collections", {}).values())
        print(f"[rag_engine] Initialization complete — {total_chunks} chunks indexed across {len(COLLECTION_NAMES)} collections")
    finally:
        _init_lock.release()
