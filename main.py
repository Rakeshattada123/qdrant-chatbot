# main.py

import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# --- CORS Support ---
from fastapi.middleware.cors import CORSMiddleware

# --- LlamaIndex Components ---
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding

# --- Async Qdrant Client ---
from qdrant_client import AsyncQdrantClient, models # <<< NEW: Import 'models'

# Load Environment Variables
load_dotenv()

# Global State
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--- Server Starting Up ---")
    try:
        # 1. Configure LLM + Embedding
        print("1. Configuring LlamaIndex settings...")
        Settings.llm = Gemini(
            model_name="models/gemini-1.5-flash",
            api_key=os.getenv("GOOGLE_API_KEY")
        )
        # Your embedding model name 'models/embedding-001' is correct.
        # This model has a vector size of 768.
        Settings.embed_model = GeminiEmbedding(
            model_name="models/embedding-001",
            api_key=os.getenv("GOOGLE_API_KEY")
        )

        # 2. Connect to Async Qdrant
        print("2. Initializing Async Qdrant client...")
        qdrant_host = os.getenv("QDRANT_HOST")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        collection_name = "qdrant"

        if not all([qdrant_host, qdrant_api_key]):
            raise RuntimeError("Missing QDRANT_HOST or QDRANT_API_KEY in environment.")

        qdrant_client = AsyncQdrantClient(url=qdrant_host, api_key=qdrant_api_key)

        # <<< NEW CODE BLOCK START >>>
        # 2.5. Verify collection exists, create if not
        print("2.5. Verifying Qdrant collection...")
        try:
            await qdrant_client.get_collection(collection_name=collection_name)
            print(f"Collection '{collection_name}' already exists.")
        except Exception:
            print(f"Collection '{collection_name}' not found. Creating it now...")
            await qdrant_client.recreate_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=768,  # Gemini 'embedding-001' uses 768 dimensions
                    distance=models.Distance.COSINE,
                ),
            )
            print(f"Collection '{collection_name}' created successfully.")
        # <<< NEW CODE BLOCK END >>>

        # 3. Load vector store and index
        print("3. Loading vector store and index...")
        vector_store = QdrantVectorStore(
            collection_name=collection_name,
            aclient=qdrant_client
        )
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store)

        # 4. Set up chat engine
        print("4. Creating chat engine...")
        app_state["chat_engine"] = index.as_chat_engine(
            chat_mode="context",
            llm=Settings.llm,
            verbose=False
        )
        print("✅ Startup complete.")

    except Exception as e:
        print(f"❌ An error occurred during startup: {e}")
        # This will stop the server from starting if something goes wrong
        raise RuntimeError(f"Server startup failed: {e}")

    yield
    print("--- Server Shutting Down ---")
    app_state.clear()

# Initialize FastAPI
app = FastAPI(
    title="RAG Chatbot API",
    lifespan=lifespan
)

# Add CORS
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Add your deployed frontend URL here when you have it
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# --- Endpoints ---

class QueryRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    answer: str

@app.post("/chat", response_model=ChatResponse)
async def chat_with_bot(request: Request, query_request: QueryRequest):
    if "chat_engine" not in app_state:
        raise HTTPException(status_code=503, detail="Chat engine is not available due to a startup error.")
    if not query_request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
        chat_engine = app_state["chat_engine"]
        response = await chat_engine.achat(query_request.query)
        if not response or not response.response:
            raise HTTPException(status_code=500, detail="Failed to get a valid response from the chat engine.")
        return ChatResponse(answer=response.response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@app.get("/")
def read_root():
    return {
        "status": "ok",
        "message": "Chatbot API is running and ready for frontend connections."
    }
