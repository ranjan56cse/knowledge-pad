"""
Milvus Lite Vector Database Implementation
Handles PDF text extraction, chunking, and semantic search
"""
from pymilvus import MilvusClient, DataType
from sentence_transformers import SentenceTransformer
import PyPDF2
import os
import hashlib
from typing import List, Dict

class KnowledgePadVectorDB:
    def __init__(self, db_path="./milvus_knowledge_pad.db"):
        """
        Initialize Milvus Lite with embedding model
        
        Args:
            db_path: Path to store Milvus Lite database
        """
        # Initialize Milvus Lite (embedded version)
        self.client = MilvusClient(db_path)
        
        # Initialize embedding model
        # all-MiniLM-L6-v2: Fast, 384 dimensions, good quality
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.embedding_dim = 384
        
        # Collection name
        self.collection_name = "knowledge_documents"
        
        # Create collection if not exists
        self._create_collection()
        print("✓ Vector database initialized")
    
    def _create_collection(self):
        """Create Milvus collection with schema"""
        
        # Check if collection exists
        if self.client.has_collection(self.collection_name):
            print(f"✓ Collection '{self.collection_name}' already exists")
            return
        
        # Define schema
        schema = self.client.create_schema(
            auto_id=True,
            enable_dynamic_field=True
        )
        
        # Add fields
        schema.add_field(
            field_name="id",
            datatype=DataType.INT64,
            is_primary=True,
            auto_id=True
        )
        schema.add_field(
            field_name="embedding",
            datatype=DataType.FLOAT_VECTOR,
            dim=self.embedding_dim
        )
        schema.add_field(
            field_name="text_chunk",
            datatype=DataType.VARCHAR,
            max_length=2000
        )
        schema.add_field(
            field_name="pdf_filename",
            datatype=DataType.VARCHAR,
            max_length=255
        )
        schema.add_field(
            field_name="page_number",
            datatype=DataType.INT64
        )
        schema.add_field(
            field_name="chunk_id",
            datatype=DataType.VARCHAR,
            max_length=64
        )
        
        # Create index for vector search
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="FLAT",  # For small datasets; use IVF_FLAT for large
            metric_type="COSINE"  # Cosine similarity
        )
        
        # Create collection
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params
        )
        
        print(f"✓ Created collection '{self.collection_name}'")
    
    def extract_text_from_pdf(self, pdf_path: str) -> List[Dict]:
        """
        Extract text from PDF and split into chunks
        
        Returns:
            List of dicts with page_number and text
        """
        chunks = []
        
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                for page_num, page in enumerate(pdf_reader.pages, start=1):
                    text = page.extract_text()
                    
                    if text.strip():  # Only if page has text
                        chunks.append({
                            'page_number': page_num,
                            'text': text
                        })
            
            print(f"✓ Extracted {len(chunks)} pages from PDF")
            return chunks
            
        except Exception as e:
            print(f"✗ PDF extraction failed: {e}")
            return []
    
    def chunk_text(self, text: str, chunk_size=500, overlap=50) -> List[str]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Input text
            chunk_size: Characters per chunk
            overlap: Overlapping characters between chunks
        
        Returns:
            List of text chunks
        """
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]
            
            # Try to break at sentence boundary
            if end < text_length:
                # Look for sentence end
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                break_point = max(last_period, last_newline)
                
                if break_point > chunk_size * 0.5:  # At least 50% into chunk
                    chunk = text[start:start + break_point + 1]
                    end = start + break_point + 1
            
            chunks.append(chunk.strip())
            start = end - overlap  # Overlap for context
        
        return chunks
    
    def generate_chunk_id(self, pdf_filename: str, page_num: int, chunk_idx: int) -> str:
        """Generate unique ID for chunk"""
        content = f"{pdf_filename}_{page_num}_{chunk_idx}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def add_pdf_to_db(self, pdf_path: str, pdf_filename: str = None):
        """
        Process PDF and add to vector database
        
        Args:
            pdf_path: Path to PDF file
            pdf_filename: Name to store in DB (if None, uses basename)
        """
        if pdf_filename is None:
            pdf_filename = os.path.basename(pdf_path)
        
        print(f"\n📄 Processing: {pdf_filename}")
        
        # Extract text from PDF
        page_chunks = self.extract_text_from_pdf(pdf_path)
        
        if not page_chunks:
            print("✗ No text extracted from PDF")
            return
        
        # Prepare data for insertion
        embeddings = []
        text_chunks = []
        pdf_filenames = []
        page_numbers = []
        chunk_ids = []
        
        total_chunks = 0
        
        for page_data in page_chunks:
            page_num = page_data['page_number']
            page_text = page_data['text']
            
            # Split page into chunks
            chunks = self.chunk_text(page_text, chunk_size=500, overlap=50)
            
            for chunk_idx, chunk in enumerate(chunks):
                if len(chunk) < 50:  # Skip very small chunks
                    continue
                
                # Generate embedding
                embedding = self.embedding_model.encode(chunk).tolist()
                
                # Generate unique chunk ID
                chunk_id = self.generate_chunk_id(pdf_filename, page_num, chunk_idx)
                
                # Append to lists
                embeddings.append(embedding)
                text_chunks.append(chunk[:2000])  # Limit to max length
                pdf_filenames.append(pdf_filename)
                page_numbers.append(page_num)
                chunk_ids.append(chunk_id)
                
                total_chunks += 1
        
        # Insert into Milvus
        if embeddings:
            data = [
                {
                    "embedding": emb,
                    "text_chunk": txt,
                    "pdf_filename": pdf_fn,
                    "page_number": pg_num,
                    "chunk_id": ch_id
                }
                for emb, txt, pdf_fn, pg_num, ch_id in zip(
                    embeddings, text_chunks, pdf_filenames, 
                    page_numbers, chunk_ids
                )
            ]
            
            self.client.insert(
                collection_name=self.collection_name,
                data=data
            )
            
            print(f"✓ Added {total_chunks} chunks to vector DB")
        else:
            print("✗ No valid chunks generated")
    
    def search(self, query: str, top_k=5, filter_pdf=None) -> List[Dict]:
        """
        Search for similar content
        
        Args:
            query: Search query
            top_k: Number of results to return
            filter_pdf: Optional PDF filename filter
        
        Returns:
            List of matching results with metadata
        """
        # Generate query embedding
        query_embedding = self.embedding_model.encode(query).tolist()
        
        # Build filter if needed
        filter_expr = None
        if filter_pdf:
            filter_expr = f'pdf_filename == "{filter_pdf}"'
        
        # Search
        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_embedding],
            limit=top_k,
            search_params={"metric_type": "COSINE"},
            output_fields=["text_chunk", "pdf_filename", "page_number", "chunk_id"],
            filter=filter_expr
        )
        
        # Format results
        formatted_results = []
        
        if results and len(results) > 0:
            for hit in results[0]:
                formatted_results.append({
                    'text': hit['entity']['text_chunk'],
                    'pdf_filename': hit['entity']['pdf_filename'],
                    'page_number': hit['entity']['page_number'],
                    'similarity_score': hit['distance'],  # Cosine similarity
                    'chunk_id': hit['entity']['chunk_id']
                })
        
        return formatted_results
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        stats = self.client.get_collection_stats(self.collection_name)
        return {
            'total_chunks': stats.get('row_count', 0),
            'collection_name': self.collection_name,
            'embedding_dimension': self.embedding_dim
        }
