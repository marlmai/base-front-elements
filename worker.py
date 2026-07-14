``python
import requests
import psycopg2
from django.conf import settings

class SimpleAIService:
    def __init__(self):
        self.embed_model = "qwenemb1024latest"
        self.llm_model = "qwen2.5:7b"
        self.conn = psycopg2.connect(settings.VECTOR_DB_CONNECTION_STRING)

    def get_embedding(self, text):
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/embeddings",
            json={"model": self.embed_model, "prompt": text}
        )
        return response.json()["embedding"]

    def search(self, query, k=5):
        query_embedding = self.get_embedding(query)
        cur = self.conn.cursor()
        cur.execute("""
            SELECT content, metadata, embedding <=> %s AS distance
            FROM documents
            ORDER BY distance ASC
            LIMIT %s
        """, (query_embedding, k))
        return cur.fetchall()

    def ask(self, question):
        results = self.search(question)
        context = "\n\n".join([r[0] for r in results])
        prompt = f"Контекст:\n{context}\n\nВопрос:\n{question}\n\nОтвет:"
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={"model": self.llm_model, "prompt": prompt, "stream": False}
        )
        return response.json()["response"]
```