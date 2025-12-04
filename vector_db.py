"""
ChromaDB Vector Database Implementation
Handles PDF text extraction, chunking, and semantic search
"""
import chromadb
from chromadb.utils import embedding_functions
import PyPDF2
import os
import hashlib
from typing import List, Dict


class KnowledgePadVectorDB:
    def __init__(self):
        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(path="./chroma_db")
        self.collection_name = "knowledge_documents"
        
        # Use ChromaDB's default embedding function (lighter weight)
        default_ef = embedding_functions.DefaultEmbeddingFunction()
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=default_ef,
            metadata={"hnsw:space": "cosine"}
        )
        
        print("✓ Vector database initialized")
    
    def extract_text_from_pdf(self, pdf_path: str) -> List[Dict]:
        """Extract text from PDF and split into chunks"""
        chunks = []
        
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                for page_num, page in enumerate(pdf_reader.pages, start=1):
                    text = page.extract_text()
                    
                    if text.strip():
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
        """Split text into overlapping chunks"""
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]
            
            if end < text_length:
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                break_point = max(last_period, last_newline)
                
                if break_point > chunk_size * 0.5:
                    chunk = text[start:start + break_point + 1]
                    end = start + break_point + 1
            
            chunks.append(chunk.strip())
            start = end - overlap
        
        return chunks
    
    def generate_chunk_id(self, pdf_filename: str, page_num: int, chunk_idx: int) -> str:
        """Generate unique ID for chunk"""
        content = f"{pdf_filename}_{page_num}_{chunk_idx}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def add_pdf_to_db(self, pdf_path: str, pdf_filename: str = None):
        """Process PDF and add to vector database"""
        if pdf_filename is None:
            pdf_filename = os.path.basename(pdf_path)
        
        print(f"\n📄 Processing: {pdf_filename}")
        
        page_chunks = self.extract_text_from_pdf(pdf_path)
        
        if not page_chunks:
            print("✗ No text extracted from PDF")
            return
        
        documents = []
        metadatas = []
        ids = []
        total_chunks = 0
        
        for page_data in page_chunks:
            page_num = page_data['page_number']
            page_text = page_data['text']
            
            chunks = self.chunk_text(page_text, chunk_size=500, overlap=50)
            
            for chunk_idx, chunk in enumerate(chunks):
                if len(chunk) < 50:
                    continue
                
                chunk_id = self.generate_chunk_id(pdf_filename, page_num, chunk_idx)
                
                documents.append(chunk)
                metadatas.append({
                    'pdf_filename': pdf_filename,
                    'page_number': page_num,
                    'chunk_index': chunk_idx
                })
                ids.append(chunk_id)
                total_chunks += 1
        
        if documents:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            print(f"✓ Added {total_chunks} chunks to vector DB")
        else:
            print("✗ No valid chunks generated")
    
    def search(self, query: str, top_k=5, filter_pdf=None) -> List[Dict]:
        """Search for similar content"""
        where_filter = None
        if filter_pdf:
            where_filter = {"pdf_filename": filter_pdf}
        
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter
        )
        
        formatted_results = []
        
        if results and results['documents'] and len(results['documents']) > 0:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if 'distances' in results else 0
                
                formatted_results.append({
                    'text': doc,
                    'pdf_filename': metadata.get('pdf_filename', ''),
                    'page_number': metadata.get('page_number', 0),
                    'similarity_score': 1 - distance,
                    'chunk_id': results['ids'][0][i]
                })
        
        return formatted_results
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        count = self.collection.count()
        return {
            'total_chunks': count,
            'collection_name': self.collection_name
        }