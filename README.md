# RAG Document Assistant
A Retrieval-Augmented Generation (RAG) system for document search, question answering, and evaluation, built with state-of-the-art NLP technologies.

## Technology Stack
- Framework : LangChain for orchestrating the RAG pipeline
- UI : Streamlit for interactive web interface
- Embedding Model : Sentence Transformers (all-MiniLM-L6-v2)
- Vector Database : FAISS for efficient similarity search
- LLM : OpenAI GPT-3.5 Turbo for answer generation

- Document Processing :
  - PyPDF for PDF documents
  - Unstructured for Word and Excel documents
  - Built-in parsers for TXT and CSV files

- Evaluation : Custom metrics including ROUGE, BERTScore, and semantic similarity
- Configuration : YAML-based configuration with dotenv for environment variables

- Visualization : Matplotlib and Pandas for metrics visualization
-
  ## Project Structure
```plaintext
rag-document-assistant/
│
├── src/                # Core application logic
│   ├── retriever.py    # Document retrieval and question answering
│   ├── embedding.py    # Document embedding and vector store management
│   ├── query_optimization.py # Query enhancement for better retrieval
│   ├── evaluator.py    # Performance evaluation metrics
│   └── config.py       # Configuration management
│
├── config/             # Configuration management
│   └── config.yaml     # Central configuration file
│
├── data/               # Document and vector store storage
│   ├── documents/      # Original document storage
│   └── vector_store/   # ChromaDB vector database
│
├── tests/              # Unit and integration tests
│   ├── test_retrieval.py
│   ├── test_embedding.py
│   └── test_query_optimization.py
│
├── .env                # Environment variables (API keys)
├── requirements.txt    # Project dependencies
└── main.py             # Streamlit application entry point
 ```


## Technical Details
### Document Processing Pipeline
1. Document Loading : Support for multiple document formats (PDF, TXT, DOCX, CSV, XLSX)
2. Text Chunking : Recursive character text splitting with 1000-character chunks and 200-character overlap
3. Embedding Generation : Sentence Transformer model (all-MiniLM-L6-v2) with 384-dimensional embeddings
4. Vector Storage : ChromaDB with cosine similarity metric for efficient retrieval

### Retrieval System
1. Query Processing : Optional query optimization using LLM-based expansion and variation generation
2. Semantic Search : Top-k retrieval (default k=5) with similarity threshold of 0.7
3. Answer Generation : GPT-3.5 Turbo with temperature 0.3 and 500 max tokens
4. System Prompt : "You are a helpful assistant that answers questions based on the provided documents."

### Evaluation Framework
Comprehensive evaluation metrics:

- Precision : Accuracy of retrieved documents
- Recall : Coverage of relevant documents
- F1 Score : Harmonic mean of precision and recall
- MRR (Mean Reciprocal Rank) : Ranking quality assessment
- ROUGE Score : N-gram overlap between generated and reference answers
- Semantic Similarity : Embedding-based similarity measurement

## Features
- Document Management : Upload, process, and manage document collections
- Semantic Search : Find relevant document sections based on meaning
- Query Optimization : LLM-based query expansion and variation generation
- Answer Generation : Contextual answers based on retrieved documents
- Performance Evaluation : Comprehensive metrics for system assessment
- Interactive UI : User-friendly interface with visualization capabilities

## Getting Started
### Prerequisites
- Python 3.8+
- OpenAI API key (for GPT-3.5 Turbo)
- LangChain API key
### Installation
1. Clone the repository:
```bash
git clone https://github.com/yourusername/rag-document-assistant.git
cd rag-document-assistant
```

2. Install dependencies:
```bash
pip install -r requirements.txt
 ```

3. Set up environment variables:
   - Create a .env file in the project root
   - Add your OpenAI API key: OPENAI_API_KEY=your_key_here

### Running the Application
Start the Streamlit application:

```bash
streamlit run main.py
 ```

The application will be available at http://localhost:8501

## Usage
### Document Management
1. Navigate to the "Document Management" page
2. Upload documents using the file uploader
3. Process documents to add them to the vector store
### Search & Query
1. Navigate to the "Search & Query" page
2. Enter your question or search query
3. Toggle query optimization if needed
4. View the generated answer and supporting documents
### Evaluation
1. Navigate to the "Evaluation" page
2. Enter evaluation queries and reference answers
3. View performance metrics and visualizations
## Configuration
The system behavior can be customized by editing the config/config.yaml file:

- Embedding : Model selection and dimensionality
- Vector Store : Storage path and similarity metrics
- Chunking : Size, overlap, and strategy parameters
- Retrieval : Top-k value, similarity threshold, and reranking options
- LLM : Model selection, temperature, and token limits
- Evaluation : Metric selection and parameters

