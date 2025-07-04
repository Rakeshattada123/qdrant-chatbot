# setup_index.py

import os
from dotenv import load_dotenv

from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    StorageContext,
    Settings
)
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding

from qdrant_client import QdrantClient

# --- 1. Load Environment Variables and API Keys ---
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_HOST = os.getenv("QDRANT_HOST")  # e.g., "https://your-qdrant-instance.cloud.qdrant.io"

if not all([GOOGLE_API_KEY, QDRANT_API_KEY, QDRANT_HOST]):
    raise ValueError("Missing required environment variables in .env file.")

# --- 2. Configure LlamaIndex Global Settings ---
print("Configuring LlamaIndex settings...")
llm = Gemini(
    model_name="models/gemini-1.5-flash", 
    api_key=GOOGLE_API_KEY
)

embed_model = GeminiEmbedding(
    model_name="models/embedding-001", 
    api_key=GOOGLE_API_KEY
)

Settings.llm = llm
Settings.embed_model = embed_model
Settings.chunk_size = 1000
Settings.chunk_overlap = 50

# --- 3. Initialize Qdrant Client ---
collection_name = "qdrant"
embedding_dimension = 768

print("Connecting to Qdrant...")
qdrant_client = QdrantClient(
    url=QDRANT_HOST,
    api_key=QDRANT_API_KEY,
)

# Create collection if not exists
if not qdrant_client.collection_exists(collection_name=collection_name):
    print(f"Creating Qdrant collection: {collection_name}")
    qdrant_client.recreate_collection(
        collection_name=collection_name,
        vectors_config={"size": embedding_dimension, "distance": "Cosine"}
    )
    print("Collection created.")
else:
    print(f"Qdrant collection '{collection_name}' already exists. Skipping creation.")

# --- 4. Load Documents ---
pdf_path = "/home/rakesh/Downloads/qdrant-backend/thebook.pdf"
if not os.path.exists(pdf_path):
    raise FileNotFoundError(f"The file '{pdf_path}' was not found.")

print(f"Loading documents from '{pdf_path}'...")
documents = SimpleDirectoryReader(input_files=[pdf_path]).load_data()
print(f"✅ Loaded {len(documents)} document chunks.")

# --- 5. Store in Qdrant ---
print("Creating storage context and vector store...")
vector_store = QdrantVectorStore(client=qdrant_client, collection_name=collection_name)
storage_context = StorageContext.from_defaults(vector_store=vector_store)

print("Creating index and storing embeddings in Qdrant...")
index = VectorStoreIndex.from_documents(
    documents,
    storage_context=storage_context,
    show_progress=True
)

print("\n✅ Setup complete! Your PDF has been indexed and stored in Qdrant.")
print("Run the FastAPI app with: uvicorn main:app --reload")
