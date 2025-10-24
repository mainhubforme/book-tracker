.book-card {
            display: flex; flex-direction: column;
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 16px; overflow: hidden;
            transition: all 0.25s; cursor: pointer;
        }
        .book-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4);
            border-color: var(--primary);
        }#!/usr/bin/env python3
"""
Book Tracker Web Interface - Modern UI with Supabase persistence
"""
import os, tempfile, json
from pathlib import Path
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
from dotenv import load_dotenv
from book_tracker3 import DatabaseManager, ImageProcessor, BookEnricher

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
FAMILY_PASSWORD = os.environ.get('BOOK_TRACKER_PASSWORD', 'bookfamily2024')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

db = DatabaseManager()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def format_publish_date(date_str):
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
    genres = set()
    for book in books:
        g1 = book.get('genres')
        g2 = book.get('genre')
        if g1 and g1 != 'Unknown':
            for genre in g1.split(','):
                genre = genre.strip()
                if genre and genre not in ['Unknown', 'N/A']:
                    genres.add(genre)
        elif g2 and g2 not in ['Unknown', 'N/A']:
            genres.add(g2.strip())
    return sorted(list(genres))

@app.route('/api/add-book', methods=['POST'])
def add_book_api():
    user = request.form.get('user_name', 'Unknown')
    file = request.files.get('image')
    if not file:
        return jsonify({"error": "No image"}), 400

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    file.save(tmp.name)

    processor = ImageProcessor()
    enricher = BookEnricher()

    book_info = processor.extract_book_info(tmp.name)
    if not book_info:
        os.unlink(tmp.name)
        return jsonify({"error": "Failed to extract book info"}), 500

    enriched = enricher.enrich_book_data(book_info)
    enriched["added_by"] = user
    enriched["is_read"] = False

    try:
        image_url = db.upload_image(tmp.name)
        enriched["image_url"] = image_url
    except Exception as e:
        print("Image upload failed:", e)

    db.add_book(enriched)
    os.unlink(tmp.name)

    return jsonify({"success": True, "book": enriched})

@app.route('/')
@login_required
def index():
    books = db.get_all_books() or []
    for book in books:
        book['formatted_date'] = format_publish_date(book.get('date_published'))
        if book.get('image_url'):
            book['thumbnail'] = book['image_url']
        # Convert to JSON for safe JavaScript embedding
        book['genres_json'] = json.dumps(book.get('genres', '').split(', ') if book.get('genres') else [])

    all_genres = get_all_genres(books)
    
    stats = {
        "total_books": len(books),
        "read_books": len([b for b in books if b.get('is_read')]),
        "unread_books": len([b for b in books if not b.get('is_read')]),
        "average_rating": (
            round(sum([b.get('goodreads_score', 0) or 0 for b in books if b.get('goodreads_score')]) / 
                len([b for b in books if b.get('goodreads_score')]), 2)
            if any(b.get('goodreads_score') for b in books) else 0
        ),
        "users_added": sorted({b.get('added_by') for b in books if b.get('added_by')}),
        "users_read": sorted({b.get('read_by') for b in books if b.get('read_by')}),
    }
    return render_template_string(PAGE_TEMPLATE, books=books, stats=stats, all_genres=all_genres)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == FAMILY_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        error = "Incorrect password"
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/mark-read', methods=['POST'])
def mark_read():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"error": "No data provided"}), 400
        
        book_id = body.get("book_id")
        read_by = body.get("read_by")
        
        if not book_id or not read_by:
            return jsonify({"error": "Missing book_id or read_by"}), 400
        
        db.mark_as_read(book_id, read_by)  # Changed from mark_read to mark_as_read
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error marking book as read: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/mark-unread', methods=['POST'])
def mark_unread():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"error": "No data provided"}), 400
        
        book_id = body.get("book_id")
        if not book_id:
            return jsonify({"error": "Missing book_id"}), 400
        
        db.mark_as_unread(book_id)  # Changed from mark_unread to mark_as_unread
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error marking book as unread: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete-book', methods=['POST'])
def delete_book():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"error": "No data provided"}), 400
        
        book_id = body.get("book_id")
        if not book_id:
            return jsonify({"error": "Missing book_id"}), 400
        
        db.delete_book(book_id)
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting book: {e}")
        return jsonify({"error": str(e)}), 500

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Booky McBookerton - Login</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; display: flex; align-items: center;
            justify-content: center; padding: 20px;
        }
        .login-container {
            background: white; border-radius: 20px; padding: 40px;
            max-width: 400px; width: 100%; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { text-align: center; color: #667eea; margin-bottom: 10px; font-size: 2.5em; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; color: #333; margin-bottom: 8px; font-weight: 500; }
        input {
            width: 100%; padding: 14px; border: 2px solid #e0e0e0;
            border-radius: 10px; font-size: 1em; transition: all 0.2s;
        }
        input:focus {
            outline: none; border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        button {
            width: 100%; padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; border-radius: 10px;
            font-size: 1.1em; font-weight: 600; cursor: pointer; transition: all 0.2s;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 8px 16px rgba(102, 126, 234, 0.3); }
        .error {
            background: #fee; color: #c33; padding: 12px;
            border-radius: 8px; margin-bottom: 20px; text-align: center;
        }
        .info {
            background: #e3f2fd; color: #1976d2; padding: 12px;
            border-radius: 8px; margin-top: 20px; font-size: 0.9em; text-align: center;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>📚</h1>
        <h1>Booky McBookerton</h1>
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
        <div class="info">💡 Ask a family member for the password</div>
    </div>
</body>
</html>
"""

# Now the main template with complete styling - using safe JSON for genres
PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Booky McBookerton</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #6366f1; --secondary: #8b5cf6; --accent: #ec4899;
            --background: #0f172a; --surface: #1e293b; --surface-light: #334155;
            --text: #f8fafc; --text-secondary: #94a3b8; --border: #334155;
            --success: #10b981; --warning: #f59e0b; --error: #ef4444;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--background); color: var(--text);
            min-height: 100vh; padding: 20px 20px 100px;
        }
        .container { max-width: 1600px; margin: 0 auto; }
        header {
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 16px; padding: 24px; margin-bottom: 24px;
        }
        .header-top {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 16px; flex-wrap: wrap; gap: 12px;
        }
        h1 {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 50%, var(--accent) 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            font-size: 2em; font-weight: 700;
        }
        .header-actions { display: flex; gap: 12px; align-items: center; }
        .user-badge {
            display: flex; align-items: center; gap: 8px;
            background: var(--surface-light); padding: 10px 18px;
            border-radius: 12px; font-size: 0.9em; cursor: pointer;
            border: 1px solid var(--border); transition: all 0.2s;
        }
        .user-badge:hover {
            background: var(--primary); transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(99, 102, 241, 0.3);
        }
        .logout-btn {
            background: transparent; color: var(--text-secondary);
            border: 1px solid var(--border); padding: 10px 18px;
            border-radius: 12px; text-decoration: none; transition: all 0.2s;
        }
        .logout-btn:hover {
            background: var(--error); color: white;
            border-color: var(--error); transform: translateY(-2px);
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 16px; margin-bottom: 24px;
        }
        .stat-card {
            background: linear-gradient(135deg, var(--surface) 0%, var(--surface-light) 100%);
            border: 1px solid var(--border); border-radius: 12px;
            padding: 20px; text-align: center; transition: all 0.3s;
        }
        .stat-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.4);
        }
        .stat-number {
            font-size: 2.5em; font-weight: 700;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .stat-label {
            color: var(--text-secondary); margin-top: 8px;
            font-size: 0.9em; font-weight: 500;
        }
        .controls {
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 16px; padding: 24px; margin-bottom: 24px;
        }
        .controls-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 20px; flex-wrap: wrap; gap: 12px;
        }
        .controls-actions { display: flex; gap: 8px; }
        .view-density-btn {
            background: var(--surface-light); padding: 6px 12px;
            border: 1px solid var(--border); border-radius: 8px;
            cursor: pointer; transition: all 0.2s;
        }
        .view-density-btn.active, .view-density-btn:hover {
            background: var(--primary); color: white;
        }
        .search-bar input {
            width: 100%; padding: 14px 16px;
            background: var(--background); border: 1px solid var(--border);
            border-radius: 12px; color: var(--text); margin-bottom: 20px;
        }
        .search-bar input:focus {
            outline: none; border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
        .filters-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px; margin-bottom: 20px;
        }
        .filter-group select {
            width: 100%; padding: 10px 12px;
            background: var(--background); border: 1px solid var(--border);
            border-radius: 8px; color: var(--text); cursor: pointer;
        }
        .filter-chips { display: flex; gap: 10px; flex-wrap: wrap; }
        .chip {
            padding: 8px 16px; background: var(--surface-light);
            border: 1px solid var(--border); border-radius: 20px;
            font-size: 0.85em; cursor: pointer; transition: all 0.2s;
        }
        .chip.active {
            background: var(--primary); color: white;
            border-color: var(--primary);
        }
        .books-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 24px;
        }
        .books-grid.compact {
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 16px;
        }
        .books-grid.compact .book-card {
            max-height: none;
        }
        .books-grid.compact .book-thumbnail {
            height: 200px;
        }
        .books-grid.compact .book-content {
            padding: 14px;
        }
        .books-grid.compact .book-title {
            font-size: 1em;
            margin-bottom: 6px;
        }
        .books-grid.compact .book-author {
            font-size: 0.9em;
        }
        .books-grid.compact .book-meta {
            display: none;
        }
        .books-grid.compact .book-footer {
            padding-top: 12px;
            gap: 8px;
        }
        .books-grid.list { 
            grid-template-columns: 1fr; 
        }
        .books-grid.list .book-card {
            flex-direction: row;
            max-height: 180px;
            cursor: default;
        }
        .books-grid.list .book-card:hover {
            transform: translateY(-2px);
        }
        .books-grid.list .book-thumbnail {
            width: 120px;
            min-width: 120px;
            height: 180px;
            cursor: pointer;
        }
        .books-grid.list .book-content {
            display: flex;
            flex-direction: row;
            gap: 16px;
            padding: 14px 16px;
        }
        .books-grid.list .book-info {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }
        .books-grid.list .book-title {
            font-size: 1.1em;
            margin-bottom: 4px;
        }
        .books-grid.list .book-author {
            font-size: 0.95em;
            margin-bottom: 6px;
        }
        .books-grid.list .book-meta {
            margin-bottom: 6px;
            gap: 4px;
        }
        .books-grid.list .book-meta .badge {
            font-size: 0.7em;
            padding: 3px 8px;
        }
        .books-grid.list .book-footer {
            width: 180px;
            min-width: 180px;
            border-top: none;
            border-left: 1px solid var(--border);
            padding-left: 16px;
            margin-top: 0;
            padding-top: 0;
        }
        .books-grid.list .book-footer-top {
            flex-direction: column;
            align-items: flex-start;
            gap: 10px;
        }
        .books-grid.list .book-actions {
            flex-direction: column;
            width: 100%;
            gap: 6px;
        }
        .books-grid.list .book-actions .btn {
            width: 100%;
            margin-right: 0;
            padding: 8px 10px;
            font-size: 0.8em;
        }
        .books-grid.list .thumbs-up-section {
            display: none;
        }
        .books-grid.list #summary-container {
            display: none;
        }
        .book-thumbnail {
            width: 100%; height: 250px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            display: flex; align-items: center; justify-content: center;
            font-size: 3em; position: relative;
        }
        .book-thumbnail img {
            width: 100%; height: 100%; object-fit: cover;
        }
        .read-badge {
            position: absolute; top: 12px; right: 12px;
            background: var(--success); color: white;
            padding: 6px 14px; border-radius: 20px;
            font-size: 0.75em; font-weight: 600;
        }
        .book-content {
            padding: 20px; flex: 1;
            display: flex; flex-direction: column;
        }
        .book-title {
            font-size: 1.2em; font-weight: 700;
            margin-bottom: 8px; line-height: 1.3;
        }
        .book-author {
            color: var(--primary); font-size: 1em;
            margin-bottom: 8px; font-weight: 500;
        }
        .book-meta {
            display: flex; flex-wrap: wrap;
            gap: 6px; margin-bottom: 12px;
        }
        .badge {
            padding: 4px 10px; border-radius: 6px;
            font-size: 0.75em; font-weight: 600;
            border: 1px solid;
        }
        .badge-genre {
            background: rgba(99, 102, 241, 0.1);
            color: var(--primary); border-color: var(--primary);
            cursor: pointer;
        }
        .badge-genre:hover {
            background: var(--primary); color: white;
        }
        .expand-genres-btn {
            background: var(--surface-light);
            color: var(--primary);
            border: 1px solid var(--primary);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.75em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .expand-genres-btn:hover {
            background: var(--primary);
            color: white;
        }
        .book-footer {
            display: flex; flex-direction: column;
            gap: 12px; padding-top: 16px;
            margin-top: auto; border-top: 1px solid var(--border);
        }
        .book-footer-top {
            display: flex; justify-content: space-between;
            align-items: center;
        }
        .avatar-circle {
            width: 24px; height: 24px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 0.9em; color: white;
            border: 2px solid var(--surface);
        }
        .book-actions { display: flex; gap: 8px; }
        .btn {
            padding: 6px 12px; border: none;
            border-radius: 8px; font-size: 0.85em;
            font-weight: 600; cursor: pointer;
            transition: all 0.2s;
        }
        .btn-read { background: var(--success); color: white; }
        .btn-unread { background: var(--warning); color: white; }
        .btn-delete { background: var(--error); color: white; }
        .thumbs-up-section {
            display: flex; align-items: center; gap: 8px;
            padding-top: 12px; border-top: 1px solid var(--border);
        }
        .thumbs-up-btn {
            background: rgba(99, 102, 241, 0.1);
            color: var(--primary); border: 1px solid var(--primary);
            padding: 6px 12px; border-radius: 8px;
            display: flex; align-items: center; gap: 6px;
            cursor: pointer; transition: all 0.2s;
        }
        .thumbs-up-btn.liked {
            background: var(--primary); color: white;
        }
        .thumbs-up-avatars { display: flex; }
        .thumbs-up-avatars .avatar-circle {
            width: 20px; height: 20px;
            font-size: 0.7em; margin-left: -8px;
        }
        .thumbs-up-avatars .avatar-circle:first-child { margin-left: 0; }
        .fab {
            position: fixed; bottom: 24px; right: 24px;
            width: 64px; height: 64px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white; border-radius: 50%; border: none;
            display: flex; align-items: center; justify-content: center;
            font-size: 2em; box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
            cursor: pointer; transition: all 0.3s; z-index: 1000;
        }
        .fab:hover {
            transform: scale(1.1) rotate(90deg);
            box-shadow: 0 12px 32px rgba(99, 102, 241, 0.6);
        }
        .modal {
            display: none; position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            z-index: 2000; align-items: center;
            justify-content: center; padding: 20px;
        }
        .modal.active { display: flex; }
        .modal-content {
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 16px; padding: 28px;
            max-width: 500px; width: 100%;
            max-height: 90vh; overflow-y: auto;
        }
        .modal-header {
            display: flex; justify-content: space-between;
            align-items: center; margin-bottom: 24px;
        }
        .close-btn {
            background: none; border: none;
            font-size: 1.8em; cursor: pointer;
            color: var(--text-secondary);
        }
        .form-group { margin-bottom: 20px; }
        .form-group label {
            display: block; color: var(--text-secondary);
            margin-bottom: 8px;
        }
        .form-group input {
            width: 100%; padding: 12px;
            background: var(--background); border: 1px solid var(--border);
            border-radius: 8px; color: var(--text);
        }
        .camera-input { display: none; }
        .camera-btn {
            width: 100%; padding: 16px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white; border: none; border-radius: 12px;
            font-size: 1.1em; font-weight: 600;
            cursor: pointer; display: flex;
            align-items: center; justify-content: center; gap: 10px;
        }
        .preview-wrapper { position: relative; display: inline-block; }
        .preview-image {
            max-width: 150px; max-height: 200px;
            object-fit: cover; border-radius: 8px; margin: 10px 10px 0 0;
        }
        .preview-remove {
            position: absolute; top: 8px; right: 8px;
            background: var(--error); color: white;
            border: none; border-radius: 50%;
            width: 28px; height: 28px; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
        }
        .emoji-option {
            background: var(--surface-light);
            border: 2px solid var(--border);
            border-radius: 12px; padding: 12px;
            font-size: 2em; text-align: center;
            cursor: pointer; transition: all 0.2s;
        }
        .emoji-option.selected {
            background: var(--primary);
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        }
        .spinner {
            border: 3px solid var(--border);
            border-top: 3px solid var(--primary);
            border-radius: 50%; width: 48px; height: 48px;
            animation: spin 1s linear infinite; margin: 20px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        @media (max-width: 768px) {
            .books-grid, .books-grid.cozy {
                grid-template-columns: 1fr !important;
            }
            .books-grid.compact {
                grid-template-columns: repeat(2, 1fr) !important;
                gap: 12px;
            }
            .books-grid.compact .book-thumbnail {
                height: 160px;
            }
            .books-grid.compact .book-content {
                padding: 10px;
            }
            .books-grid.compact .book-title {
                font-size: 0.9em;
            }
            .books-grid.list .book-card {
                flex-direction: column;
                max-height: none;
            }
            .books-grid.list .book-thumbnail {
                width: 100%;
                height: 200px;
            }
            .books-grid.list .book-content {
                flex-direction: column;
                padding: 14px;
            }
            .books-grid.list .book-footer {
                width: 100%;
                border-left: none;
                border-top: 1px solid var(--border);
                padding-left: 0;
                padding-top: 12px;
                margin-top: 12px;
            }
            .books-grid.list .book-footer-top {
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
            }
            .books-grid.list .book-actions {
                flex-direction: row;
                width: auto;
                gap: 8px;
            }
            .books-grid.list .book-actions .btn {
                width: auto;
                padding: 6px 12px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-top">
                <h1>📚 Booky McBookerton</h1>
                <div class="header-actions">
                    <div class="user-badge" onclick="openModal('profile-modal')">
                        <span id="current-user-emoji">👤</span>
                        <span id="current-user-name">Set Your Name</span>
                    </div>
                    <a href="/logout" class="logout-btn">🚪 Logout</a>
                </div>
            </div>
            <p style="color: var(--text-secondary);">Your modern family reading library</p>
        </header>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{{ stats.total_books }}</div>
                <div class="stat-label">Total Books</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ stats.read_books }}</div>
                <div class="stat-label">Read</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ stats.unread_books }}</div>
                <div class="stat-label">Unread</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ stats.average_rating or 'N/A' }}</div>
                <div class="stat-label">Avg Rating</div>
            </div>
        </div>
        
        <div class="controls">
            <div class="controls-header">
                <span>🔍 Filter & Sort</span>
                <div class="controls-actions">
                    <button class="view-density-btn" data-density="cozy">▦</button>
                    <button class="view-density-btn" data-density="compact">▪</button>
                    <button class="view-density-btn active" data-density="list">☰</button>
                    <button class="view-density-btn" onclick="clearAllFilters()" style="background: transparent;">Clear</button>
                </div>
            </div>
            
            <div class="search-bar">
                <input type="text" id="search" placeholder="🔎 Search by title, author, genre...">
            </div>
            
            <div class="filters-grid">
                <div class="filter-group">
                    <label>Genre</label>
                    <select id="filter-genre">
                        <option value="">All Genres</option>
                        {% for genre in all_genres %}
                        <option value="{{ genre }}">{{ genre }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="filter-group">
                    <label>Added By</label>
                    <select id="filter-added-by">
                        <option value="">All Users</option>
                        {% for user in stats.users_added %}
                        <option value="{{ user }}">{{ user }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="filter-group">
                    <label>Sort By</label>
                    <select id="sort-by">
                        <option value="date-desc">Date Added (Newest)</option>
                        <option value="title-asc">Title (A-Z)</option>
                        <option value="author-asc">Author (A-Z)</option>
                        <option value="rating-desc">Rating (High-Low)</option>
                    </select>
                </div>
            </div>
            
            <div class="filter-chips">
                <div class="chip active" data-filter="all">All Books</div>
                <div class="chip" data-filter="unread">Unread</div>
                <div class="chip" data-filter="read">Read</div>
            </div>
        </div>
        
        {% if books %}
        <div class="books-grid list" id="books-grid">
            {% for book in books %}
            <div class="book-card {% if book.is_read %}read{% endif %}" 
                 data-id="{{ book.id }}"
                 data-title="{{ book.title }}"
                 data-author="{{ book.author }}"
                 data-added-by="{{ book.added_by or '' }}"
                 data-read="{{ 'true' if book.is_read else 'false' }}"
                 data-genres="{{ book.genres or book.genre or '' }}"
                 data-genres-json='{{ book.genres_json|safe }}'
                 data-rating="{{ book.goodreads_score or 0 }}"
                 data-date="{{ book.date_entered }}"
                 onclick="expandCard(event, '{{ book.id }}')">
                
                <div class="book-thumbnail">
                    {% if book.thumbnail %}
                    <img src="{{ book.thumbnail }}" alt="{{ book.title }}">
                    {% else %}
                    📚
                    {% endif %}
                    {% if book.is_read %}
                    <div class="read-badge">✓ Read</div>
                    {% endif %}
                </div>
                
                <div class="book-content">
                    <div class="book-title">{{ book.title }}</div>
                    <div class="book-author">by {{ book.author }}</div>
                    {% if book.formatted_date %}
                    <div style="color: var(--text-secondary); font-size: 0.85em; margin-bottom: 12px;">
                        📅 Published {{ book.formatted_date }}
                    </div>
                    {% elif book.date_published and book.date_published != 'Unknown' %}
                    <div style="color: var(--text-secondary); font-size: 0.85em; margin-bottom: 12px;">
                        📅 Published {{ book.date_published }}
                    </div>
                    {% endif %}
                    
                    <div class="book-meta">
                        <div id="genres-{{ book.id }}" style="display: flex; flex-wrap: wrap; gap: 6px; width: 100%;"></div>
                        {% if book.part_of_series and book.part_of_series not in ['No', 'Unknown'] %}
                        <span class="badge" style="background: rgba(139, 92, 246, 0.1); color: var(--secondary); border-color: var(--secondary);">
                            {{ book.part_of_series }}{% if book.series_number %} #{{ book.series_number }}{% endif %}
                        </span>
                        {% endif %}
                        {% if book.goodreads_score %}
                        <a href="https://www.goodreads.com/search?q={{ book.title|urlencode }}+{{ book.author|urlencode }}" target="_blank" rel="noopener noreferrer" style="text-decoration: none;" onclick="event.stopPropagation();">
                            <span class="badge" style="background: rgba(245, 158, 11, 0.1); color: var(--warning); border-color: var(--warning); cursor: pointer;">
                                ⭐ {{ book.goodreads_score }}/5
                            </span>
                        </a>
                        {% endif %}
                    </div>
                    
                    {% if book.major_awards and book.major_awards not in ['TBD', 'Unknown', 'None', 'none', 'N/A'] %}
                    <div style="background: rgba(245, 158, 11, 0.1); border-left: 3px solid var(--warning); padding: 10px 14px; margin: 12px 0; font-size: 0.85em; color: var(--warning); border-radius: 6px;">
                        <strong>🏆 Awards:</strong> {{ book.major_awards }}
                    </div>
                    {% endif %}
                    
                    {% if book.summary and book.summary != 'Unknown' and book.summary != 'No summary available' %}
                    <div id="summary-{{ book.id }}" style="color: var(--text-secondary); font-size: 0.9em; line-height: 1.6; margin-bottom: 16px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;">
                        {{ book.summary }}
                    </div>
                    <span style="color: var(--primary); cursor: pointer; font-size: 0.85em; font-weight: 600; margin-top: 8px; display: inline-block;" 
                          onclick="toggleSummary(event, '{{ book.id }}')">Read more</span>
                    {% endif %}
                    
                    <div class="book-footer">
                        <div class="book-footer-top">
                            <div style="display: flex; flex-direction: column; gap: 6px;">
                                <div style="display: flex; align-items: center; gap: 6px;">
                                    <div class="avatar-circle" style="background: #6366f1;">
                                        <span class="user-avatar-emoji" data-user="{{ book.added_by }}">👤</span>
                                    </div>
                                    <span style="font-size: 0.8em; color: var(--text-secondary);">{{ book.added_by or 'Unknown' }}</span>
                                </div>
                                {% if book.date_entered %}
                                <div style="font-size: 0.75em; color: var(--text-secondary); opacity: 0.7;">
                                    Added {{ book.date_entered.strftime('%b %d, %Y') }}
                                </div>
                                {% endif %}
                            </div>
                            <div class="book-actions">
                                {% if book.is_read %}
                                <button class="btn btn-unread" onclick="event.stopPropagation(); markUnread('{{ book.id }}')">Unread</button>
                                {% else %}
                                <button class="btn btn-read" onclick="event.stopPropagation(); showReadModal('{{ book.id }}', '{{ book.title|replace("'", "\\'") }}')">Read</button>
                                {% endif %}
                                <button class="btn btn-delete" onclick="event.stopPropagation(); deleteBook('{{ book.id }}', '{{ book.title|replace("'", "\\'") }}')">Delete</button>
                            </div>
                        </div>
                        
                        <div class="thumbs-up-section">
                            <button class="thumbs-up-btn" id="thumbs-{{ book.id }}" 
                                    onclick="toggleThumbsUp('{{ book.id }}')">
                                👍 <span id="thumbs-count-{{ book.id }}">0</span>
                            </button>
                            <div class="thumbs-up-avatars" id="thumbs-avatars-{{ book.id }}"></div>
                        </div>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div style="text-align: center; padding: 80px 20px; background: var(--surface); border-radius: 16px;">
            <h2 style="color: var(--primary); margin-bottom: 16px;">📖 No books yet!</h2>
            <p style="color: var(--text-secondary);">Tap the + button to add your first book</p>
        </div>
        {% endif %}
    </div>
    
    <!-- Modals -->
    <div class="modal" id="add-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Add New Book</h2>
                <button class="close-btn" onclick="closeModal('add-modal')">&times;</button>
            </div>
            <form id="add-book-form" enctype="multipart/form-data">
                <div class="form-group">
                    <label>Your Name</label>
                    <input type="text" id="user-name" name="user_name" required>
                </div>
                <div class="form-group">
                    <label>Book Cover Photo</label>
                    <input type="file" id="book-image" name="image" accept="image/*" class="camera-input" multiple required>
                    <button type="button" class="camera-btn" onclick="document.getElementById('book-image').click()">
                        📷 Take Photo or Upload
                    </button>
                    <div id="preview-container" style="margin-top: 15px;"></div>
                </div>
                <div class="form-group">
                    <button type="submit" class="btn camera-btn" id="submit-books-btn" disabled style="opacity: 0.5;">Add Book(s)</button>
                </div>
            </form>
            <div id="processing-status" style="display: none; text-align: center; padding: 20px;">
                <div class="spinner"></div>
                <p>Processing...</p>
            </div>
        </div>
    </div>
    
    <div class="modal" id="read-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Mark as Read</h2>
                <button class="close-btn" onclick="closeModal('read-modal')">&times;</button>
            </div>
            <form id="mark-read-form">
                <input type="hidden" id="read-book-id">
                <div class="form-group">
                    <label>Book: <span id="read-book-title"></span></label>
                </div>
                <div class="form-group">
                    <label>Who read this book?</label>
                    <input type="text" id="read-by-name" name="read_by" required>
                </div>
                <div class="form-group">
                    <button type="submit" class="btn camera-btn">Mark as Read</button>
                </div>
            </form>
        </div>
    </div>
    
    <div class="modal" id="profile-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Your Profile</h2>
                <button class="close-btn" onclick="closeModal('profile-modal')">&times;</button>
            </div>
            <form id="profile-form">
                <div class="form-group">
                    <label>Your Name</label>
                    <input type="text" id="profile-name" required>
                </div>
                <div class="form-group">
                    <label>Choose Your Avatar</label>
                    <div style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-top: 10px;">
                        <div class="emoji-option" data-emoji="🐶">🐶</div>
                        <div class="emoji-option" data-emoji="🐱">🐱</div>
                        <div class="emoji-option" data-emoji="🐭">🐭</div>
                        <div class="emoji-option" data-emoji="🐹">🐹</div>
                        <div class="emoji-option" data-emoji="🐰">🐰</div>
                        <div class="emoji-option" data-emoji="🦊">🦊</div>
                        <div class="emoji-option" data-emoji="🐻">🐻</div>
                        <div class="emoji-option" data-emoji="🐼">🐼</div>
                        <div class="emoji-option" data-emoji="🐨">🐨</div>
                        <div class="emoji-option" data-emoji="🐯">🐯</div>
                        <div class="emoji-option" data-emoji="🦁">🦁</div>
                        <div class="emoji-option" data-emoji="🐮">🐮</div>
                        <div class="emoji-option" data-emoji="🐷">🐷</div>
                        <div class="emoji-option" data-emoji="🐸">🐸</div>
                        <div class="emoji-option" data-emoji="🐵">🐵</div>
                        <div class="emoji-option" data-emoji="🐔">🐔</div>
                        <div class="emoji-option" data-emoji="🐧">🐧</div>
                        <div class="emoji-option" data-emoji="🐦">🐦</div>
                        <div class="emoji-option" data-emoji="🐤">🐤</div>
                        <div class="emoji-option" data-emoji="🦄">🦄</div>
                        <div class="emoji-option" data-emoji="🐝">🐝</div>
                        <div class="emoji-option" data-emoji="🦋">🦋</div>
                        <div class="emoji-option" data-emoji="🐌">🐌</div>
                        <div class="emoji-option" data-emoji="🐙">🐙</div>
                        <div class="emoji-option" data-emoji="🦀">🦀</div>
                        <div class="emoji-option" data-emoji="🐠">🐠</div>
                        <div class="emoji-option" data-emoji="🐡">🐡</div>
                        <div class="emoji-option" data-emoji="🦆">🦆</div>
                        <div class="emoji-option" data-emoji="🦉">🦉</div>
                        <div class="emoji-option" data-emoji="🦇">🦇</div>
                        <div class="emoji-option" data-emoji="🐺">🐺</div>
                        <div class="emoji-option" data-emoji="🦝">🦝</div>
                        <div class="emoji-option" data-emoji="🦘">🦘</div>
                        <div class="emoji-option" data-emoji="🦙">🦙</div>
                        <div class="emoji-option" data-emoji="🦒">🦒</div>
                        <div class="emoji-option" data-emoji="🦔">🦔</div>
                    </div>
                    <input type="hidden" id="profile-emoji" value="👤">
                </div>
                <div class="form-group">
                    <button type="submit" class="btn camera-btn">Save Profile</button>
                </div>
            </form>
        </div>
    </div>
    
    <button class="fab" onclick="openModal('add-modal')">+</button>
    
    <script>
        let userAvatars = JSON.parse(localStorage.getItem('bookTrackerUserAvatars') || '{}');
        let thumbsUpData = JSON.parse(localStorage.getItem('bookThumbsUp') || '{}');
        let selectedFiles = [];
        
        // Initialize genres for each book card
        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('.book-card').forEach(card => {
                const bookId = card.dataset.id;
                const genresJson = card.dataset.genresJson;
                const genresContainer = document.getElementById('genres-' + bookId);
                
                if (genresJson && genresContainer) {
                    try {
                        const genres = JSON.parse(genresJson);
                        const visibleGenres = genres.slice(0, 3);
                        const hiddenGenres = genres.slice(3);
                        
                        visibleGenres.forEach(genre => {
                            if (genre && genre !== 'Unknown') {
                                const badge = document.createElement('span');
                                badge.className = 'badge badge-genre';
                                badge.textContent = genre;
                                badge.onclick = function() { filterByGenre(genre); };
                                genresContainer.appendChild(badge);
                            }
                        });
                        
                        if (hiddenGenres.length > 0) {
                            const btn = document.createElement('button');
                            btn.className = 'expand-genres-btn';
                            btn.textContent = '+' + hiddenGenres.length + ' more';
                            btn.onclick = function(e) {
                                e.stopPropagation();
                                const extraDiv = document.getElementById('genres-extra-' + bookId);
                                if (extraDiv) {
                                    if (extraDiv.style.display === 'none') {
                                        extraDiv.style.display = 'flex';
                                        btn.textContent = 'Show less';
                                    } else {
                                        extraDiv.style.display = 'none';
                                        btn.textContent = '+' + hiddenGenres.length + ' more';
                                    }
                                }
                            };
                            genresContainer.appendChild(btn);
                            
                            const extraDiv = document.createElement('div');
                            extraDiv.id = 'genres-extra-' + bookId;
                            extraDiv.style.display = 'none';
                            extraDiv.style.flexWrap = 'wrap';
                            extraDiv.style.gap = '6px';
                            extraDiv.style.width = '100%';
                            
                            hiddenGenres.forEach(genre => {
                                if (genre && genre !== 'Unknown') {
                                    const badge = document.createElement('span');
                                    badge.className = 'badge badge-genre';
                                    badge.textContent = genre;
                                    badge.onclick = function() { filterByGenre(genre); };
                                    extraDiv.appendChild(badge);
                                }
                            });
                            
                            genresContainer.appendChild(extraDiv);
                        }
                    } catch (e) {
                        console.error('Error parsing genres:', e);
                    }
                }
                
                updateThumbsUpDisplay(bookId);
            });
            
            updateUserName();
        });
        
        function getUserAvatar(name) {
            return userAvatars[name] || '👤';
        }
        
        function getAvatarColor(name) {
            if (!name) return '#6366f1';
            const colors = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#14b8a6'];
            let hash = 0;
            for (let i = 0; i < name.length; i++) {
                hash = name.charCodeAt(i) + ((hash << 5) - hash);
            }
            return colors[Math.abs(hash) % colors.length];
        }
        
        function getCurrentUserName() {
            return localStorage.getItem('bookTrackerUserName') || 'Guest';
        }
        
        function toggleThumbsUp(bookId) {
            const userName = getCurrentUserName();
            const key = 'book_' + bookId;
            
            if (!thumbsUpData[key]) thumbsUpData[key] = [];
            
            const userIndex = thumbsUpData[key].indexOf(userName);
            if (userIndex > -1) {
                thumbsUpData[key].splice(userIndex, 1);
            } else {
                thumbsUpData[key].push(userName);
            }
            
            localStorage.setItem('bookThumbsUp', JSON.stringify(thumbsUpData));
            updateThumbsUpDisplay(bookId);
        }
        
        function updateThumbsUpDisplay(bookId) {
            const key = 'book_' + bookId;
            const users = thumbsUpData[key] || [];
            const userName = getCurrentUserName();
            
            const btn = document.getElementById('thumbs-' + bookId);
            const count = document.getElementById('thumbs-count-' + bookId);
            const avatars = document.getElementById('thumbs-avatars-' + bookId);
            
            if (!btn || !count || !avatars) return;
            
            count.textContent = users.length;
            btn.classList.toggle('liked', users.includes(userName));
            
            avatars.innerHTML = '';
            users.forEach(user => {
                const avatar = document.createElement('div');
                avatar.className = 'avatar-circle';
                avatar.style.backgroundColor = getAvatarColor(user);
                avatar.textContent = getUserAvatar(user);
                avatar.title = user;
                avatars.appendChild(avatar);
            });
        }
        
        function filterByGenre(genre) {
            document.getElementById('filter-genre').value = genre;
            filterAndSortBooks();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        
        function toggleSummary(e, bookId) {
            e.stopPropagation();
            const summary = document.getElementById('summary-' + bookId);
            const btn = e.target;
            
            if (summary.style.webkitLineClamp === '3') {
                summary.style.webkitLineClamp = 'unset';
                summary.style.display = 'block';
                btn.textContent = 'Read less';
            } else {
                summary.style.webkitLineClamp = '3';
                summary.style.display = '-webkit-box';
                btn.textContent = 'Read more';
            }
        }
        
        function expandCard(e, bookId) {
            // Don't expand if clicking on interactive elements
            if (e.target.closest('button') || e.target.closest('a') || e.target.closest('.badge-genre')) {
                return;
            }
            
            const card = document.querySelector(`[data-id="${bookId}"]`);
            const summary = document.getElementById('summary-' + bookId);
            
            if (card && summary) {
                // Toggle expanded state
                if (summary.style.webkitLineClamp === '3') {
                    summary.style.webkitLineClamp = 'unset';
                    summary.style.display = 'block';
                    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                } else {
                    summary.style.webkitLineClamp = '3';
                    summary.style.display = '-webkit-box';
                }
            }
        }
        
        function openModal(id) {
            document.getElementById(id).classList.add('active');
        }
        
        function closeModal(id) {
            document.getElementById(id).classList.remove('active');
            if (id === 'add-modal') {
                document.getElementById('add-book-form').reset();
                document.getElementById('preview-container').innerHTML = '';
                selectedFiles = [];
                updateSubmitButton();
            }
        }
        
        function updateSubmitButton() {
            const btn = document.getElementById('submit-books-btn');
            const count = selectedFiles.length;
            if (count === 0) {
                btn.disabled = true;
                btn.style.opacity = '0.5';
                btn.textContent = 'Add Book(s)';
            } else {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.textContent = count === 1 ? 'Add 1 Book' : 'Add ' + count + ' Books';
            }
        }
        
        document.getElementById('book-image').addEventListener('change', function(e) {
            selectedFiles = Array.from(e.target.files);
            const container = document.getElementById('preview-container');
            container.innerHTML = '';
            
            selectedFiles.forEach((file, index) => {
                const reader = new FileReader();
                reader.onload = function(e) {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'preview-wrapper';
                    
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    img.className = 'preview-image';
                    
                    const removeBtn = document.createElement('button');
                    removeBtn.type = 'button';
                    removeBtn.className = 'preview-remove';
                    removeBtn.innerHTML = '×';
                    removeBtn.onclick = function() {
                        selectedFiles.splice(index, 1);
                        wrapper.remove();
                        updateSubmitButton();
                    };
                    
                    wrapper.appendChild(img);
                    wrapper.appendChild(removeBtn);
                    container.appendChild(wrapper);
                };
                reader.readAsDataURL(file);
            });
            updateSubmitButton();
        });
        
        document.getElementById('add-book-form').addEventListener('submit', async function(e) {
            e.preventDefault();
            if (selectedFiles.length === 0) return;
            
            const userName = document.getElementById('user-name').value;
            document.getElementById('add-book-form').style.display = 'none';
            const processingDiv = document.getElementById('processing-status');
            processingDiv.style.display = 'block';
            processingDiv.innerHTML = '<div class="spinner"></div><p>Processing ' + selectedFiles.length + ' book(s)...</p><p id="progress-text">0 of ' + selectedFiles.length + ' complete</p>';
            
            for (let i = 0; i < selectedFiles.length; i++) {
                const formData = new FormData();
                formData.append('image', selectedFiles[i]);
                formData.append('user_name', userName);
                
                try {
                    await fetch('/api/add-book', {
                        method: 'POST',
                        body: formData
                    });
                } catch (error) {
                    console.error(error);
                }
                document.getElementById('progress-text').textContent = (i + 1) + ' of ' + selectedFiles.length + ' complete';
            }
            window.location.href = '/';
        });
        
        function showReadModal(bookId, bookTitle) {
            event.stopPropagation(); // Stop card expansion
            document.getElementById('read-book-id').value = bookId;
            document.getElementById('read-book-title').textContent = bookTitle;
            openModal('read-modal');
        }
        
        document.getElementById('mark-read-form').addEventListener('submit', async function(e) {
            e.preventDefault();
            const bookId = document.getElementById('read-book-id').value;
            const readBy = document.getElementById('read-by-name').value;
            
            console.log('Form submitted with:', { bookId, readBy });
            
            if (!bookId || !readBy) {
                alert('Please fill in all fields');
                return;
            }
            
            try {
                const payload = { 
                    book_id: bookId,  // Don't parse UUID as integer!
                    read_by: readBy 
                };
                console.log('Sending payload:', payload);
                
                const response = await fetch('/api/mark-read', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                
                console.log('Response status:', response.status);
                
                if (response.ok) {
                    location.reload();
                } else {
                    const error = await response.json();
                    console.error('Server error:', error);
                    alert('Error marking book as read: ' + (error.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Failed to mark book as read. Please try again.');
            }
        });
        
        async function markUnread(bookId) {
            if (!confirm('Mark as unread?')) return;
            try {
                const response = await fetch('/api/mark-unread', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ book_id: bookId })  // Keep as string UUID
                });
                if (response.ok) {
                    location.reload();
                } else {
                    const error = await response.json();
                    alert('Error marking book as unread: ' + (error.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Failed to mark book as unread. Please try again.');
            }
        }
        
        async function deleteBook(bookId, bookTitle) {
            if (!confirm('Delete "' + bookTitle + '"?')) return;
            try {
                const response = await fetch('/api/delete-book', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ book_id: bookId })  // Keep as string UUID
                });
                if (response.ok) {
                    location.reload();
                } else {
                    const error = await response.json();
                    alert('Error deleting book: ' + (error.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Failed to delete book. Please try again.');
            }
        }
        
        function filterAndSortBooks() {
            const query = (document.getElementById('search')?.value || '').toLowerCase();
            const genre = document.getElementById('filter-genre')?.value || '';
            const addedBy = document.getElementById('filter-added-by')?.value || '';
            const sortOption = document.getElementById('sort-by')?.value || 'date-desc';
            const activeChip = document.querySelector('.chip.active');
            const readFilter = activeChip?.dataset.filter || 'all';
            
            const grid = document.getElementById('books-grid');
            if (!grid) return;
            
            const books = Array.from(document.querySelectorAll('.book-card'));
            
            const filtered = books.filter(book => {
                const text = book.textContent.toLowerCase();
                const bookGenres = book.dataset.genres.toLowerCase();
                const bookAddedBy = book.dataset.addedBy;
                const isRead = book.dataset.read === 'true';
                
                if (query && !text.includes(query)) return false;
                if (genre && !bookGenres.includes(genre.toLowerCase())) return false;
                if (addedBy && bookAddedBy !== addedBy) return false;
                if (readFilter === 'read' && !isRead) return false;
                if (readFilter === 'unread' && isRead) return false;
                
                return true;
            });
            
            filtered.sort((a, b) => {
                switch(sortOption) {
                    case 'date-desc': return new Date(b.dataset.date) - new Date(a.dataset.date);
                    case 'date-asc': return new Date(a.dataset.date) - new Date(b.dataset.date);
                    case 'title-asc': return a.dataset.title.localeCompare(b.dataset.title);
                    case 'author-asc': return a.dataset.author.localeCompare(b.dataset.author);
                    case 'rating-desc': return parseFloat(b.dataset.rating) - parseFloat(a.dataset.rating);
                    default: return 0;
                }
            });
            
            books.forEach(book => book.style.display = 'none');
            filtered.forEach(book => {
                book.style.display = 'block';
                grid.appendChild(book);
            });
        }
        
        function clearAllFilters() {
            document.getElementById('search').value = '';
            document.getElementById('filter-genre').selectedIndex = 0;
            document.getElementById('filter-added-by').selectedIndex = 0;
            document.getElementById('sort-by').selectedIndex = 0;
            document.querySelectorAll('.chip').forEach(chip => {
                chip.classList.toggle('active', chip.dataset.filter === 'all');
            });
            filterAndSortBooks();
        }
        
        function updateUserName() {
            const savedName = localStorage.getItem('bookTrackerUserName');
            const savedEmoji = localStorage.getItem('bookTrackerUserEmoji') || '👤';
            
            document.getElementById('current-user-emoji').textContent = savedEmoji;
            
            if (savedName) {
                document.getElementById('current-user-name').textContent = savedName;
                document.getElementById('user-name').value = savedName;
                document.getElementById('read-by-name').value = savedName;
                document.getElementById('profile-name').value = savedName;
                userAvatars[savedName] = savedEmoji;
                localStorage.setItem('bookTrackerUserAvatars', JSON.stringify(userAvatars));
            }
            
            document.getElementById('profile-emoji').value = savedEmoji;
            document.querySelectorAll('.emoji-option').forEach(opt => {
                opt.classList.toggle('selected', opt.dataset.emoji === savedEmoji);
            });
            
            document.querySelectorAll('.user-avatar-emoji').forEach(el => {
                const userName = el.dataset.user;
                if (userName) el.textContent = getUserAvatar(userName);
            });
        }
        
        document.querySelectorAll('.emoji-option').forEach(option => {
            option.addEventListener('click', function() {
                document.querySelectorAll('.emoji-option').forEach(opt => opt.classList.remove('selected'));
                this.classList.add('selected');
                document.getElementById('profile-emoji').value = this.dataset.emoji;
                document.getElementById('current-user-emoji').textContent = this.dataset.emoji;
            });
        });
        
        document.getElementById('profile-form').addEventListener('submit', function(e) {
            e.preventDefault();
            const name = document.getElementById('profile-name').value.trim();
            const emoji = document.getElementById('profile-emoji').value;
            if (name) {
                localStorage.setItem('bookTrackerUserName', name);
                localStorage.setItem('bookTrackerUserEmoji', emoji);
                userAvatars[name] = emoji;
                localStorage.setItem('bookTrackerUserAvatars', JSON.stringify(userAvatars));
                updateUserName();
                closeModal('profile-modal');
            }
        });
        
        document.querySelectorAll('.view-density-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                if (this.textContent === 'Clear') return;
                document.querySelectorAll('.view-density-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                const grid = document.getElementById('books-grid');
                grid.className = 'books-grid ' + this.dataset.density;
            });
        });
        
        document.getElementById('search')?.addEventListener('input', filterAndSortBooks);
        document.getElementById('filter-genre')?.addEventListener('change', filterAndSortBooks);
        document.getElementById('filter-added-by')?.addEventListener('change', filterAndSortBooks);
        document.getElementById('sort-by')?.addEventListener('change', filterAndSortBooks);
        
        document.querySelectorAll('.chip').forEach(chip => {
            chip.addEventListener('click', function() {
                document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
                this.classList.add('active');
                filterAndSortBooks();
            });
        });
        
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', function(e) {
                if (e.target === this) closeModal(this.id);
            });
        });
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    print("🚀 Starting Book Tracker Web Interface...")
    print("📚 Booky McBookerton!")
    print("🔑 Password:", FAMILY_PASSWORD)
    print("🌐 Access at: http://localhost:5001")
    print("\nPress Ctrl+C to stop")
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)
