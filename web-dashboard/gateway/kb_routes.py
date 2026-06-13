"""
Knowledge Base Management API Routes.
========================================
Endpoints for uploading, indexing, deleting, searching documents,
and viewing retrieval logs.
"""
import json
import os
import shutil
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse

from .config import DASHBOARD_DATA
from .rag_engine import (
    ensure_initialized, get_stats, search, search_all, search_with_tier,
    index_single_file, delete_document, rebuild_all,
    get_retrieval_logs, KB_DIR, MAINT_KB_DIR, COLLECTION_NAMES,
)

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


# ── Helpers ────────────────────────────────────────────────────────────

def _ensure_dirs():
    """Ensure knowledge base directories exist."""
    KB_DIR.mkdir(parents=True, exist_ok=True)
    MAINT_KB_DIR.mkdir(parents=True, exist_ok=True)


def _get_collection_dir(collection: str) -> Path:
    """Get the document directory for a collection."""
    if collection == "maint_kb":
        return MAINT_KB_DIR
    # For sys_docs and fault_cases, files are in project root / auto-generated
    return KB_DIR / collection


def _list_docs_in_dir(directory: Path) -> list:
    """List document files in a directory."""
    if not directory.exists():
        return []
    docs = []
    for ext in ALLOWED_EXTENSIONS:
        for fp in directory.glob(f"*{ext}"):
            docs.append({
                "name": fp.name,
                "path": str(fp),
                "size_kb": round(fp.stat().st_size / 1024, 1),
                "extension": ext,
                "modified": datetime.fromtimestamp(fp.stat().st_mtime).isoformat(),
            })
    docs.sort(key=lambda d: d["name"])
    return docs


# ── Routes ─────────────────────────────────────────────────────────────

@router.get("/stats")
async def kb_stats():
    """Get knowledge base statistics."""
    try:
        ensure_initialized()
        stats = get_stats()
        return JSONResponse({"success": True, **stats})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/documents")
async def list_documents(collection: str = "sys_docs"):
    """List documents in a knowledge base collection."""
    try:
        ensure_initialized()
        stats = get_stats()

        # Get Chroma-indexed documents
        coll_stats = stats.get("collections", {}).get(collection, {})
        indexed_docs = set(coll_stats.get("documents", []))

        # Get filesystem documents
        doc_dir = _get_collection_dir(collection)
        fs_docs = _list_docs_in_dir(doc_dir)

        # Also add sys_docs from project root
        if collection == "sys_docs":
            from .rag_engine import SYS_DOC_FILES, PROJECT_ROOT
            for rel_path in SYS_DOC_FILES:
                fp = PROJECT_ROOT / rel_path
                if fp.exists():
                    indexed_docs.add(rel_path)
                    # Check if already in fs_docs
                    if not any(d["name"] == fp.name for d in fs_docs):
                        fs_docs.append({
                            "name": rel_path,
                            "path": str(fp),
                            "size_kb": round(fp.stat().st_size / 1024, 1),
                            "extension": fp.suffix,
                            "modified": datetime.fromtimestamp(fp.stat().st_mtime).isoformat(),
                        })

        # Also add auto-generated fault cases
        if collection == "fault_cases":
            fs_docs.append({
                "name": "log.csv (auto-generated)",
                "path": "auto-generated",
                "size_kb": 0,
                "extension": ".csv",
                "modified": "",
                "auto_generated": True,
            })

        # Mark which docs are indexed
        for doc in fs_docs:
            doc["indexed"] = doc["name"] in indexed_docs or any(
                doc["name"] in idx for idx in indexed_docs
            )

        return JSONResponse({
            "success": True,
            "collection": collection,
            "total_count": len(fs_docs),
            "chunk_count": coll_stats.get("chunk_count", 0),
            "documents": fs_docs,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form("maint_kb"),
):
    """Upload a document to a knowledge base collection."""
    # Validate extension
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse({
            "success": False,
            "error": f"不支持的文件格式 '{ext}'。支持: {', '.join(ALLOWED_EXTENSIONS)}",
        }, status_code=400)

    if collection not in COLLECTION_NAMES:
        return JSONResponse({
            "success": False,
            "error": f"Invalid collection '{collection}'. Valid: {COLLECTION_NAMES}",
        }, status_code=400)

    _ensure_dirs()

    # Determine target directory
    if collection == "maint_kb":
        target_dir = MAINT_KB_DIR
    else:
        target_dir = KB_DIR / collection
    target_dir.mkdir(parents=True, exist_ok=True)

    # Check file size (10MB limit)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        return JSONResponse({
            "success": False,
            "error": "文件过大（最大10MB）。请分割后上传。",
        }, status_code=400)

    # Save file
    target_path = target_dir / filename
    if target_path.exists():
        # Add timestamp to avoid overwrite
        stem = target_path.stem
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = target_dir / f"{stem}_{ts}{ext}"

    with open(target_path, "wb") as f:
        f.write(content)

    # Index the file
    try:
        ensure_initialized()
        n_chunks = index_single_file(str(target_path), collection)
        return JSONResponse({
            "success": True,
            "filename": target_path.name,
            "path": str(target_path),
            "size_kb": round(len(content) / 1024, 1),
            "chunks_indexed": n_chunks,
            "collection": collection,
            "message": f"文件已上传并索引，切分为 {n_chunks} 个块。",
        })
    except Exception as e:
        # File saved but indexing failed
        return JSONResponse({
            "success": True,
            "filename": target_path.name,
            "path": str(target_path),
            "size_kb": round(len(content) / 1024, 1),
            "chunks_indexed": 0,
            "collection": collection,
            "warning": f"文件已保存但索引失败: {str(e)}",
        })


@router.post("/reindex")
async def reindex_documents(data: dict):
    """Reindex a specific collection or all collections."""
    collection = data.get("collection", "")
    source = data.get("source", "")  # optional: single file to reindex

    try:
        ensure_initialized()

        if source:
            # Reindex single file
            from .rag_engine import PROJECT_ROOT
            if collection == "sys_docs":
                fp = PROJECT_ROOT / source
            elif collection == "maint_kb":
                fp = MAINT_KB_DIR / source
            else:
                fp = KB_DIR / collection / source

            if not fp.exists():
                return JSONResponse({"success": False, "error": f"File not found: {source}"}, status_code=404)

            delete_document(str(fp.relative_to(PROJECT_ROOT) if str(fp).startswith(str(PROJECT_ROOT)) else source), collection)
            n = index_single_file(str(fp), collection)
            return JSONResponse({
                "success": True,
                "source": source,
                "collection": collection,
                "chunks_indexed": n,
                "message": f"已重新索引「{source}」，{n} 个块。",
            })

        elif collection and collection in COLLECTION_NAMES:
            # Rebuild entire collection
            counts = {}
            if collection == "sys_docs":
                from .rag_engine import index_system_docs
                counts["sys_docs"] = index_system_docs()
            elif collection == "maint_kb":
                from .rag_engine import index_maintenance_kb
                counts["maint_kb"] = index_maintenance_kb()
            elif collection == "fault_cases":
                from .rag_engine import index_fault_cases
                counts["fault_cases"] = index_fault_cases()

            n = counts.get(collection, 0)
            return JSONResponse({
                "success": True,
                "collection": collection,
                "chunks_indexed": n,
                "message": f"已重建「{collection}」，共 {n} 个块。",
            })

        else:
            # Rebuild all
            counts = rebuild_all()
            total = sum(counts.values())
            return JSONResponse({
                "success": True,
                "counts": counts,
                "total_chunks": total,
                "message": f"已重建全部知识库，共 {total} 个块。",
            })

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.delete("/documents")
async def delete_kb_document(data: dict):
    """Delete a document from a collection (and Chroma index)."""
    source = data.get("source", "")
    collection = data.get("collection", "")

    if not source or not collection:
        return JSONResponse({"success": False, "error": "source and collection are required"}, status_code=400)

    if collection not in COLLECTION_NAMES:
        return JSONResponse({"success": False, "error": f"Invalid collection: {collection}"}, status_code=400)

    try:
        ensure_initialized()

        # Delete from Chroma
        n_deleted = delete_document(source, collection)

        # Delete file if in maint_kb or upload dir
        file_path = None
        if collection == "maint_kb" and MAINT_KB_DIR.exists():
            file_path = MAINT_KB_DIR / source
        elif (KB_DIR / collection / source).exists():
            file_path = KB_DIR / collection / source

        file_deleted = False
        if file_path and file_path.exists() and file_path.is_file():
            file_path.unlink()
            file_deleted = True

        return JSONResponse({
            "success": True,
            "source": source,
            "collection": collection,
            "chunks_deleted": n_deleted,
            "file_deleted": file_deleted,
            "message": f"已删除「{source}」（{n_deleted} 个块" + ("，文件已删除" if file_deleted else "") + "）。",
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/search")
async def kb_search_test(q: str = "", collection: str = "", k: int = 5):
    """Test search endpoint for knowledge base."""
    if not q:
        return JSONResponse({"success": False, "error": "query parameter 'q' is required"}, status_code=400)

    try:
        ensure_initialized()
        if collection and collection in COLLECTION_NAMES:
            result = search(q, collection, k=k)
        else:
            result = search_all(q, k=k)
        return JSONResponse({"success": True, **result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/logs")
async def kb_logs(limit: int = 50):
    """Get recent retrieval logs."""
    try:
        logs = get_retrieval_logs(limit=limit)
        return JSONResponse({"success": True, "count": len(logs), "logs": logs})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/rebuild-all")
async def kb_rebuild_all():
    """Rebuild all knowledge base collections from scratch."""
    try:
        ensure_initialized()
        counts = rebuild_all()
        total = sum(counts.values())
        return JSONResponse({
            "success": True,
            "counts": counts,
            "total_chunks": total,
            "message": f"已重建全部知识库：sys_docs={counts.get('sys_docs',0)}块, maint_kb={counts.get('maint_kb',0)}块, fault_cases={counts.get('fault_cases',0)}块，共{total}块。",
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/degrade-test")
async def kb_degrade_test(req: Request):
    """Run search across all 3 embedding tiers for comparison."""
    try:
        body = await req.json()
        query = body.get("query", "").strip()
        if not query:
            return JSONResponse({"success": False, "error": "query is required"}, status_code=400)
        ensure_initialized()
        results = []
        for tier in ["bge_local", "deepseek_api", "tfidf_fallback"]:
            r = search_with_tier(query, tier, k=5)
            results.append({
                "tier": tier,
                "total_found": r.get("total_found", 0),
                "results": r.get("results", [])[:5],
                "elapsed_ms": r.get("elapsed_ms", 0),
                "note": r.get("note", ""),
            })
        return JSONResponse({"success": True, "query": query, "results": results})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/document-content")
async def get_document_content(source: str = "", collection: str = ""):
    """Get the full content of a knowledge base document by source path.

    Used by the RAG citation preview modal's "查看完整文档" button.
    Resolves the source path relative to the appropriate base directory
    and returns the raw markdown/text content.
    """
    if not source:
        return JSONResponse({"success": False, "error": "source parameter is required"}, status_code=400)

    from .rag_engine import PROJECT_ROOT

    # Determine possible file paths based on collection and source
    candidates = []

    # Normalize path separators
    source_normalized = source.replace('\\', '/')

    if collection == "sys_docs":
        candidates.append(PROJECT_ROOT / source_normalized)
    elif collection == "maint_kb":
        candidates.append(MAINT_KB_DIR / Path(source_normalized).name)
        candidates.append(MAINT_KB_DIR / source_normalized)
    elif collection == "fault_cases":
        return JSONResponse({
            "success": True,
            "source": source,
            "collection": collection,
            "content": "",
            "content_type": "auto-generated",
            "message": "故障案例为自动生成，无独立文档文件。请查看检索片段。",
        })
    else:
        candidates.append(PROJECT_ROOT / source_normalized)
        if MAINT_KB_DIR.exists():
            candidates.append(MAINT_KB_DIR / Path(source_normalized).name)
            candidates.append(MAINT_KB_DIR / source_normalized)
        for subdir in KB_DIR.iterdir():
            if subdir.is_dir():
                candidates.append(subdir / Path(source_normalized).name)

    # Try each candidate
    import os
    for fp in candidates:
        try:
            fp = Path(str(fp))
            if fp.exists() and fp.is_file():
                content = ""
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        content = f.read()
                except UnicodeDecodeError:
                    with open(fp, "r", encoding="gbk") as f:
                        content = f.read()
                except Exception:
                    continue

                file_size_kb = round(fp.stat().st_size / 1024, 1)
                return JSONResponse({
                    "success": True,
                    "source": source,
                    "resolved_path": str(fp),
                    "collection": collection,
                    "content": content,
                    "content_type": "markdown" if fp.suffix in (".md", ".markdown") else "text",
                    "size_kb": file_size_kb,
                })
        except Exception:
            continue

    return JSONResponse({
        "success": False,
        "error": f"Document not found: {source}",
        "tried_paths": [str(c) for c in candidates],
    }, status_code=404)
