"""
Knowledge Pad - Flask Application
Main web interface for searching PDFs stored in Cloudflare R2
"""
from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
from functools import wraps
from vector_db import KnowledgePadVectorDB
from r2_storage import CloudflareR2Storage
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Initialize services
vector_db = KnowledgePadVectorDB()
r2_storage = CloudflareR2Storage()

# Authentication credentials from environment
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'change_this_password')

def check_auth(username, password):
    """Verify username and password"""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def authenticate():
    """Send 401 response for authentication"""
    return Response(
        'Access denied. Please provide valid credentials.',
        401,
        {'WWW-Authenticate': 'Basic realm="Knowledge Pad Login"'}
    )

def requires_auth(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

@app.route('/')
@requires_auth
def index():
    """Main search page"""
    return render_template('search.html')

@app.route('/api/search', methods=['POST'])
@requires_auth
def search():
    """
    Search endpoint
    
    Request JSON:
        {
            "query": "search text",
            "top_k": 5,
            "pdf_filter": "optional_filename.pdf"
        }
    
    Response JSON:
        {
            "results": [...],
            "query": "...",
            "total_results": 5,
            "search_time": 0.123
        }
    """
    start_time = datetime.now()
    
    data = request.json
    query = data.get('query', '')
    top_k = data.get('top_k', 10)
    pdf_filter = data.get('pdf_filter', None)
    
    if not query:
        return jsonify({'error': 'Query is required'}), 400
    
    try:
        # Search vector database
        results = vector_db.search(
            query=query,
            top_k=top_k,
            filter_pdf=pdf_filter
        )
        
        # Add PDF URLs to results
        for result in results:
            pdf_url = r2_storage.get_pdf_url(result['pdf_filename'])
            result['pdf_url'] = pdf_url if pdf_url else '#'
        
        search_time = (datetime.now() - start_time).total_seconds()
        
        return jsonify({
            'results': results,
            'query': query,
            'total_results': len(results),
            'search_time': search_time
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
@requires_auth
def upload_pdf():
    """
    Upload PDF endpoint
    
    Expects multipart/form-data with 'file' field
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files are allowed'}), 400
    
    try:
        # Save temporarily
        temp_dir = os.getenv('TEMP_DIR', '/tmp')
        temp_path = os.path.join(temp_dir, file.filename)
        file.save(temp_path)
        
        # Upload to R2
        success = r2_storage.upload_pdf(temp_path, file.filename)
        
        if success:
            # Add to vector database
            vector_db.add_pdf_to_db(temp_path, file.filename)
            
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return jsonify({
                'success': True,
                'message': f'Successfully uploaded and indexed {file.filename}',
                'filename': file.filename
            })
        else:
            return jsonify({'error': 'Upload to storage failed'}), 500
            
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({'error': str(e)}), 500

@app.route('/api/list-pdfs', methods=['GET'])
@requires_auth
def list_pdfs():
    """List all PDFs in storage"""
    try:
        pdfs = r2_storage.list_pdfs()
        return jsonify({
            'pdfs': pdfs,
            'total': len(pdfs)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
@requires_auth
def get_stats():
    """Get database statistics"""
    try:
        stats = vector_db.get_stats()
        pdf_count = len(r2_storage.list_pdfs())
        stats['total_pdfs'] = pdf_count
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint (no auth required)"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    # Development server
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
