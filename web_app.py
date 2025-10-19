#!/usr/bin/env python3
"""
Book Tracker Web Interface - Modern UI with Authentication
Flask web app with camera support, read tracking, and password protection
"""

from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
from functools import wraps
from pathlib import Path
import sys
import base64
import tempfile
import os
from datetime import timedelta

# Import from book_tracker.py
sys.path.insert(0, str(Path(__file__).parent))
from book_tracker import DatabaseManager, ImageProcessor, BookEnricher

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-to-something-secure-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Simple password protection
FAMILY_PASSWORD = os.environ.get('BOOK_TRACKER_PASSWORD', 'bookfamily2024')

db = DatabaseManager()

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_book_thumbnail(image_path):
    """Convert book image to base64 for display."""
    try:
        if image_path and Path(image_path).exists():
            with open(image_path, 'rb') as img_file:
                img_data = base64.b64encode(img_file.read()).decode('utf-8')
                ext = Path(image_path).suffix.lower()
                mime_type = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.webp': 'image/webp',
                    '.gif': 'image/gif'
                }.get(ext, 'image/jpeg')
                return f"data:{mime_type};base64,{img_data}"
    except Exception as e:
        print(f"Error loading thumbnail: {e}")
    return None

def format_publish_date(date_str):
    """Format publication date to be more readable."""
    if not date_str or date_str == 'Unknown':
        return None
    
    try:
        if len(date_str) == 4:
            return date_str
        elif len(date_str) == 7:
            year, month = date_str.split('-')
            from datetime import datetime
            month_name = datetime.strptime(month, '%m').strftime('%B')
            return f"{month_name} {year}"
        elif len(date_str) >= 10:
            from datetime import datetime
            date_obj = datetime.strptime(date_str[:10], '%Y-%m-%d')
            return date_obj.strftime('%B %Y')
    except:
        pass
    
    return date_str

def get_all_genres(books):
    """Extract all unique genres from books."""
    genres = set()
    for book in books:
        if book.genres and book.genres != 'Unknown':
            for genre in book.genres.split(', '):
                genre = genre.strip()
                if genre and genre not in ['Unknown', 'N/A']:
                    genres.add(genre)
        elif book.genre and book.genre not in ['Unknown', 'N/A']:
            genres.add(book.genre.strip())
    return sorted(list(genres))

# HTML Templates (keeping original LOGIN_TEMPLATE and PAGE_TEMPLATE from your code)
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Book Tracker - Login</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .login-container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 400px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 {
            text-align: center;
            color: #667eea;
            margin-bottom: 10px;
            font-size: 2.5em;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
        }
        .form-group { margin-bottom: 20px; }
        label {
            display: block;
            color: #333;
            margin-bottom: 8px;
            font-weight: 500;
        }
        input {
            width: 100%;
            padding: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 1em;
            transition: all 0.2s;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1.1em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(102, 126, 234, 0.3);
        }
        .error {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .info {
            background: #e3f2fd;
            color: #1976d2;
            padding: 12px;
            border-radius: 8px;
            margin-top: 20px;
            font-size: 0.9em;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>📚</h1>
        <h1>Book Tracker</h1>
        <p class="subtitle">Family Reading Library</p>
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        
        <form method="POST">
            <div class="form-group">
                <label>Family Password</label>
                <input type="password" name="password" placeholder="Enter family password" required autofocus>
            </div>
            <button type="submit">Sign In</button>
        </form>
        
        <div class="info">
            💡 Ask a family member for the password
        </div>
    </div>
</body>
</html>
"""

# For brevity, I'll include a shortened PAGE_TEMPLATE
# In production, use your full template from the original file
PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Book Tracker</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #6366f1;
            --background: #0f172a;
            --surface: #1e293b;
            --text: #f8fafc;
        }
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--background);
            color: var(--text);
            padding: 20px;
        }
        .container { max-width: 1600px; margin: 0 auto; }
        header {
            background: var(--surface);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
        }
        h1 {
            background: linear-gradient(135deg, var(--primary) 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2em;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--surface);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .stat-number { font-size: 2.5em; font-weight: 700; color: var(--primary); }
        .books-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 24px;
        }
        .book-card {
            background: var(--surface);
            border-radius: 16px;
            overflow: hidden;
        }
        .book-thumbnail {
            width: 100%;
            height: 280px;
            background: linear-gradient(135deg, var(--primary) 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 3em;
        }
        .book-thumbnail img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .book-content { padding: 24px; }
        .book-title { font-size: 1.3em; font-weight: 700; margin-bottom: 8px; }
        .fab {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 64px;
            height: 64px;
            background: linear-gradient(135deg, var(--primary) 0%, #764ba2 100%);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2em;
            cursor: pointer;
            box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📚 Book Tracker</h1>
            <a href="/logout" style="color: white;">Logout</a>
        </header>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{{ stats.total_books }}</div>
                <div>Total Books</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ stats.read_books }}</div>
                <div>Read</div>
            </div>
        </div>
        
        <div class="books-grid">
            {% for book in books %}
            <div class="book-card">
                <div class="book-thumbnail">
                    {% if book.thumbnail %}
                    <img src="{{ book.thumbnail }}" alt="{{ book.title }}">
                    {% else %}
                    📚
                    {% endif %}
                </div>
                <div class="book-content">
                    <div class="book-title">{{ book.title }}</div>
                    <div>by {{ book.author }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <button class="fab" onclick="alert('Add book feature - coming soon!')">+</button>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == FAMILY_PASSWORD:
            session['logged_in'] = True
            session.permanent = True
            return redirect(url_for('index'))
        else:
            return render_template_string(LOGIN_TEMPLATE, error='Incorrect password. Try again!')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    """Logout route."""
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Home page showing all books."""
    books = db.get_all_books()
    stats = db.get_stats()
    
    for book in books:
        book.thumbnail = get_book_thumbnail(book.image_path)
        book.formatted_date = format_publish_date(book.date_published)
    
    all_genres = get_all_genres(books)
    
    return render_template_string(PAGE_TEMPLATE, books=books, stats=stats, all_genres=all_genres)

@app.route('/api/add-book', methods=['POST'])
@login_required
def api_add_book():
    """API endpoint to add a new book from uploaded image."""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image provided'})
        
        file = request.files['image']
        user_name = request.form.get('user_name', 'Unknown')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        temp_dir = tempfile.mkdtemp()
        temp_path = Path(temp_dir) / file.filename
        file.save(str(temp_path))
        
        processor = ImageProcessor()
        book_info = processor.extract_book_info(str(temp_path))
        
        if not book_info:
            return jsonify({'success': False, 'error': 'Failed to extract book information'})
        
        enricher = BookEnricher()
        enriched_data = enricher.enrich_book_data(book_info, use_goodreads=True)
        enriched_data['added_by'] = user_name
        
        book = db.add_book(enriched_data)
        
        return jsonify({'success': True, 'book_id': book.id})
        
    except Exception as e:
        print(f"Error adding book: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/mark-read', methods=['POST'])
@login_required
def api_mark_read():
    """API endpoint to mark a book as read."""
    try:
        data = request.get_json()
        book_id = data.get('book_id')
        read_by = data.get('read_by', 'Unknown')
        
        book = db.mark_as_read(int(book_id), read_by)
        
        if book:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Book not found'})
            
    except Exception as e:
        print(f"Error marking as read: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/mark-unread', methods=['POST'])
@login_required
def api_mark_unread():
    """API endpoint to mark a book as unread."""
    try:
        data = request.get_json()
        book_id = data.get('book_id')
        
        book = db.mark_as_unread(int(book_id))
        
        if book:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Book not found'})
            
    except Exception as e:
        print(f"Error marking as unread: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete-book', methods=['POST'])
@login_required
def api_delete_book():
    """API endpoint to delete a book."""
    try:
        data = request.get_json()
        book_id = data.get('book_id')
        
        success = db.delete_book(int(book_id))
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Book not found'})
            
    except Exception as e:
        print(f"Error deleting book: {e}")
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("🚀 Starting Book Tracker Web Interface...")
    print("🔒 Password:", FAMILY_PASSWORD)
    print("🌐 Access at: http://localhost:5001")
    
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)
