`python
import hashlib
import json
import psycopg2
import redis
import requests
from typing import List, Dict, Any, Optional, Tuple
from django.conf import settings


CONNECTION_STRING = getattr(
    settings,
    "VECTOR_DB_CONNECTION_STRING",
    "postgresql://rag_chatbot_app:rag_chatbot_local_pass@localhost:5432/rag_chatbot",
)
DEFAULT_COLLECTION_NAME = getattr(settings, "VECTOR_DB_DEFAULT_COLLECTION", "prd_documents")


class AIService:
    def __init__(self):
        self.ollama_base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        self.embed_model = getattr(settings, "OLLAMA_EMBED_MODEL", "qwenemb1024latest")
        self.llm_model = getattr(settings, "OLLAMA_LLM_MODEL", "qwen2.5:7b")
        self.temperature = float(getattr(settings, "OLLAMA_LLM_TEMPERATURE", 0.1))
        self.num_predict = int(getattr(settings, "OLLAMA_LLM_NUM_PREDICT", 500))
        self.top_k = int(getattr(settings, "RAG_RETRIEVE_TOP_K", 10))
        self.conn_string = CONNECTION_STRING
        self.collection_name = DEFAULT_COLLECTION_NAME

        self.redis_client = None
        if getattr(settings, "CACHE_ENABLED", False):
            try:
                redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
                self.redis_client = redis.from_url(redis_url)
                self.redis_client.ping()
            except Exception:
                self.redis_client = None

    def _get_embedding(self, text: str) -> List[float]:
        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text},
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception:
            return []

    def _search_vectors(self, query_embedding: List[float], k: int = 10) -> List[Dict]:
        try:
            conn = psycopg2.connect(self.conn_string)
            cur = conn.cursor()
            cur.execute("""
                SELECT document, embedding <=> %s::vector AS distance
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                WHERE c.name = %s
                ORDER BY distance ASC
                LIMIT %s
            """, (query_embedding, self.collection_name, k))
            results = cur.fetchall()
            cur.close()
            conn.close()
            return [{"content": row[0], "distance": row[1]} for row in results]
        except Exception:
            return []

    def _generate_answer(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.llm_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.num_predict,
                    }
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            return f"Ошибка: {str(e)}"

    def _get_cache_key(self, question: str) -> str:
        normalized = question.strip().lower()
        hash_key = hashlib.sha256(normalized.encode()).hexdigest()
        return f"rag_answer:{hash_key}"

    def ask_question(
        self,
        question: str,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        q = (question or "").strip()
        if not q:
            return "Вопрос не может быть пустым", [], None

        if self.redis_client:
            cache_key = self._get_cache_key(q)
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    return data.get("answer", ""), data.get("sources", []), None
            except Exception:
                pass

        query_embedding = self._get_embedding(q)
        if not query_embedding:
            return "Не удалось создать эмбеддинг для вопроса", [], None

        results = self._search_vectors(query_embedding, k=self.top_k)
        if not results:
            return "По вашему вопросу ничего не найдено в документах.", [], None

        context_parts = []
        sources = []

        for idx, row in enumerate(results[:self.top_k], start=1):
            content = row.get("content", "")
            distance = row.get("distance", 1.0)
            source_name = f"Документ {idx}"

            sources.append({
                "title": source_name,
                "source": source_name,
                "score": round(1.0 - distance, 4),
                "preview": content[:300] + ("..." if len(content) > 300 else ""),
            })

            context_parts.append(f"[{source_name}]\n{content}\n")

        context = "\n\n".join(context_parts)

        prompt = f"""Ты — помощник по программе МКАДД. Отвечай ТОЛЬКО на основе КОНТЕКСТА.
Если в контексте нет ответа — скажи: "Информация по вашему вопросу не найдена в документах".
Не используй свои знания, только контекст.

КОНТЕКСТ:
{context}

ВОПРОС:
{q}

ОТВЕТ (только на основе контекста):"""

        answer = self._generate_answer(prompt)

        if self.redis_client and answer:
            cache_key = self._get_cache_key(q)
            try:
                self.redis_client.setex(
                    cache_key,
                    3600,
                    json.dumps({"answer": answer, "sources": sources})
                )
            except Exception:
                pass

        return answer, sources, None