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
# In production, set via environment variable: BOOK_TRACKER_PASSWORD
FAMILY_PASSWORD = os.environ.get('BOOK_TRACKER_PASSWORD', 'bookfamily2024')

# FIX #3: Persistent database - use absolute path
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "books.db"

db = DatabaseManager(database_url=f"sqlite:///{DB_PATH}")

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

# ============================================================================
# LOGIN PAGE
# ============================================================================

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Book Tracker - Login</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
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
        
        .form-group {
            margin-bottom: 20px;
        }
        
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
        
        button:active {
            transform: translateY(0);
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

# ============================================================================
# MAIN PAGE TEMPLATE
# ============================================================================

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Book Tracker</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }
        
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #8b5cf6;
            --accent: #ec4899;
            --background: #0f172a;
            --surface: #1e293b;
            --surface-light: #334155;
            --text: #f8fafc;
            --text-secondary: #94a3b8;
            --border: #334155;
            --success: #10b981;
            --warning: #f59e0b;
            --error: #ef4444;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--background);
            color: var(--text);
            min-height: 100vh;
            padding: 20px;
            padding-bottom: 100px;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        /* Header */
        header {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            backdrop-filter: blur(10px);
        }
        
        .header-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            flex-wrap: wrap;
            gap: 12px;
        }
        
        h1 {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 50%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 2em;
            font-weight: 700;
            margin: 0;
        }
        
        .header-actions {
            display: flex;
            gap: 12px;
            align-items: center;
        }
        
        .user-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            background: var(--surface-light);
            color: var(--text);
            padding: 10px 18px;
            border-radius: 12px;
            font-size: 0.9em;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            border: 1px solid var(--border);
        }
        
        .user-badge:hover {
            background: var(--primary);
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(99, 102, 241, 0.3);
        }
        
        #current-user-avatar {
            font-size: 1.3em;
        }
        
        .logout-btn {
            background: transparent;
            color: var(--text-secondary);
            border: 1px solid var(--border);
            padding: 10px 18px;
            border-radius: 12px;
            font-size: 0.9em;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        
        .logout-btn:hover {
            background: var(--error);
            color: white;
            border-color: var(--error);
            transform: translateY(-2px);
        }
        
        .subtitle {
            color: var(--text-secondary);
            font-size: 1em;
        }
        
        /* Stats */
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        
        .stat-card {
            background: linear-gradient(135deg, var(--surface) 0%, var(--surface-light) 100%);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            transition: all 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.4);
        }
        
        .stat-number {
            font-size: 2.5em;
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .stat-label {
            color: var(--text-secondary);
            margin-top: 8px;
            font-size: 0.9em;
            font-weight: 500;
        }
        
        /* Controls */
        .controls {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
        }
        
        .controls-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 12px;
        }
        
        .controls-title {
            font-size: 1.1em;
            font-weight: 600;
            color: var(--text);
        }
        
        .controls-actions {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        
        .view-density-btn {
            background: var(--surface-light);
            color: var(--text);
            border: 1px solid var(--border);
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 0.85em;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .view-density-btn.active {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }
        
        .view-density-btn:hover {
            background: var(--primary);
            color: white;
            transform: translateY(-1px);
        }
        
        .clear-filters-btn {
            background: transparent;
            color: var(--text-secondary);
            border: 1px solid var(--border);
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 0.85em;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .clear-filters-btn:hover {
            background: var(--surface-light);
            color: var(--text);
        }
        
        .search-bar {
            margin-bottom: 20px;
        }
        
        .search-bar input {
            width: 100%;
            padding: 14px 16px;
            background: var(--background);
            border: 1px solid var(--border);
            border-radius: 12px;
            font-size: 1em;
            color: var(--text);
            transition: all 0.2s;
        }
        
        .search-bar input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
        
        .search-bar input::placeholder {
            color: var(--text-secondary);
        }
        
        .filters-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }
        
        .filter-group {
            display: flex;
            flex-direction: column;
        }
        
        .filter-group label {
            color: var(--text-secondary);
            font-size: 0.85em;
            font-weight: 500;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .filter-group select {
            width: 100%;
            padding: 10px 12px;
            background: var(--background);
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 0.95em;
            color: var(--text);
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .filter-group select:hover {
            border-color: var(--primary);
        }
        
        .filter-group select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
        
        .filter-chips {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .chip {
            display: inline-flex;
            align-items: center;
            padding: 8px 16px;
            background: var(--surface-light);
            color: var(--text-secondary);
            border: 1px solid var(--border);
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .chip.active {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }
        
        .chip:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
        }
        
        /* Books Grid - Multiple Density Options */
        .books-grid {
            display: grid;
            gap: 24px;
            margin-bottom: 24px;
            transition: all 0.3s;
        }
        
        .books-grid.comfortable {
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        }
        
        .books-grid.compact {
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 16px;
        }
        
        .books-grid.compact .book-card {
            font-size: 0.9em;
        }
        
        .books-grid.compact .book-thumbnail {
            height: 220px;
        }
        
        .books-grid.compact .book-content {
            padding: 16px;
        }
        
        .books-grid.compact .book-title {
            font-size: 1.1em;
        }
        
        .books-grid.cozy {
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
        }
        
        .books-grid.cozy .book-thumbnail {
            height: 250px;
        }
        
        .books-grid.cozy .book-content {
            padding: 20px;
        }
        
        /* List View for Mobile */
        .books-grid.list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .books-grid.list .book-card {
            display: flex;
            flex-direction: row;
            border-radius: 12px;
            overflow: visible;
            max-height: 140px;
        }
        
        .books-grid.list .book-thumbnail {
            width: 90px;
            min-width: 90px;
            height: 140px;
            border-radius: 12px 0 0 12px;
        }
        
        .books-grid.list .book-content {
            padding: 12px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            flex: 1;
            overflow: hidden;
        }
        
        .books-grid.list .book-title {
            font-size: 1em;
            margin-bottom: 4px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        
        .books-grid.list .book-author {
            font-size: 0.85em;
            margin-bottom: 4px;
        }
        
        .books-grid.list .book-publish-date,
        .books-grid.list .book-summary,
        .books-grid.list .read-more,
        .books-grid.list .book-awards,
        .books-grid.list .expand-genres-btn {
            display: none;
        }
        
        .books-grid.list .book-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            margin-bottom: 6px;
        }
        
        .books-grid.list .badge {
            font-size: 0.65em;
            padding: 2px 6px;
        }
        
        .books-grid.list .genres-container.collapsed .badge-genre:nth-child(n+3) {
            display: none;
        }
        
        .books-grid.list .book-footer {
            padding-top: 0;
            border-top: none;
            font-size: 0.75em;
            margin-top: auto;
        }
        
        .books-grid.list .book-actions {
            display: none;
        }
        
        .books-grid.list .read-badge {
            top: 6px;
            right: 6px;
            font-size: 0.65em;
            padding: 4px 8px;
        }
        
        .book-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
            transition: all 0.3s;
            position: relative;
        }
        
        .book-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
            border-color: var(--primary);
        }
        
        .book-card.read {
            opacity: 0.8;
        }
        
        .book-thumbnail {
            width: 100%;
            height: 280px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 3em;
            position: relative;
            overflow: hidden;
        }
        
        .book-thumbnail img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.3s;
        }
        
        .book-card:hover .book-thumbnail img {
            transform: scale(1.05);
        }
        
        .read-badge {
            position: absolute;
            top: 12px;
            right: 12px;
            background: var(--success);
            color: white;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.75em;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
            backdrop-filter: blur(10px);
        }
        
        .book-content {
            padding: 24px;
        }
        
        .book-title {
            font-size: 1.3em;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 8px;
            line-height: 1.3;
        }
        
        .book-author {
            color: var(--primary);
            font-size: 1em;
            margin-bottom: 8px;
            font-weight: 500;
        }
        
        .book-publish-date {
            color: var(--text-secondary);
            font-size: 0.85em;
            margin-bottom: 12px;
        }
        
        .book-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 12px;
            position: relative;
        }
        
        .genres-container {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            width: 100%;
        }
        
        .genres-container.collapsed .badge-genre:nth-child(n+4) {
            display: none;
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
            white-space: nowrap;
        }
        
        .expand-genres-btn:hover {
            background: var(--primary);
            color: white;
            transform: scale(1.05);
        }
        
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.75em;
            font-weight: 600;
            border: 1px solid;
        }
        
        .badge-genre {
            background: rgba(99, 102, 241, 0.1);
            color: var(--primary);
            border-color: var(--primary);
            cursor: pointer;
        }
        
        .badge-genre:hover {
            background: var(--primary);
            color: white;
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4);
        }
        
        .badge-series {
            background: rgba(139, 92, 246, 0.1);
            color: var(--secondary);
            border-color: var(--secondary);
        }
        
        .badge-rating {
            background: rgba(245, 158, 11, 0.1);
            color: var(--warning);
            border-color: var(--warning);
        }
        
        .goodreads-link {
            color: var(--warning);
            text-decoration: none;
            font-weight: 600;
        }
        
        .goodreads-link:hover {
            text-decoration: underline;
        }
        
        .book-awards {
            background: rgba(245, 158, 11, 0.1);
            border-left: 3px solid var(--warning);
            padding: 10px 14px;
            margin: 12px 0;
            font-size: 0.85em;
            color: var(--warning);
            border-radius: 6px;
        }
        
        .book-summary {
            color: var(--text-secondary);
            font-size: 0.9em;
            line-height: 1.6;
            margin-bottom: 16px;
        }
        
        .book-summary.collapsed {
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        
        .read-more {
            color: var(--primary);
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 600;
            margin-top: 8px;
            display: inline-block;
        }
        
        .read-more:hover {
            text-decoration: underline;
        }
        
        .book-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-top: 16px;
            border-top: 1px solid var(--border);
            font-size: 0.85em;
            color: var(--text-secondary);
        }
        
        .book-actions {
            display: flex;
            gap: 8px;
        }
        
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 8px;
            font-size: 0.9em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-block;
        }
        
        .btn-read {
            background: var(--success);
            color: white;
        }
        
        .btn-read:hover {
            background: #059669;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(16, 185, 129, 0.3);
        }
        
        .btn-unread {
            background: var(--warning);
            color: white;
        }
        
        .btn-unread:hover {
            background: #d97706;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(245, 158, 11, 0.3);
        }
        
        .btn-delete {
            background: var(--error);
            color: white;
        }
        
        .btn-delete:hover {
            background: #dc2626;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(239, 68, 68, 0.3);
        }
        
        .fab {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 64px;
            height: 64px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2em;
            box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
            cursor: pointer;
            transition: all 0.3s;
            z-index: 1000;
            border: none;
        }
        
        .fab:hover {
            transform: scale(1.1) rotate(90deg);
            box-shadow: 0 12px 32px rgba(99, 102, 241, 0.6);
        }
        
        .fab:active {
            transform: scale(0.95);
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(4px);
            z-index: 2000;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
            max-width: 500px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }
        
        .modal-header h2 {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 1.5em;
        }
        
        .close-btn {
            background: none;
            border: none;
            font-size: 1.8em;
            cursor: pointer;
            color: var(--text-secondary);
            transition: all 0.2s;
        }
        
        .close-btn:hover {
            color: var(--text);
            transform: rotate(90deg);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            color: var(--text-secondary);
            margin-bottom: 8px;
            font-weight: 500;
            font-size: 0.9em;
        }
        
        .form-group input,
        .form-group select {
            width: 100%;
            padding: 12px;
            background: var(--background);
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 1em;
            color: var(--text);
            transition: all 0.2s;
        }
        
        .form-group input:focus,
        .form-group select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
        
        .camera-input {
            display: none;
        }
        
        .camera-btn {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 1.1em;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            transition: all 0.2s;
        }
        
        .camera-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(99, 102, 241, 0.4);
        }
        
        .preview-image {
            width: 100%;
            max-width: 150px;
            max-height: 200px;
            object-fit: cover;
            border-radius: 8px;
            margin: 10px 10px 0 0;
            display: inline-block;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }
        
        #preview-container {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        
        .preview-wrapper {
            position: relative;
            display: inline-block;
        }
        
        .preview-remove {
            position: absolute;
            top: 8px;
            right: 8px;
            background: var(--error);
            color: white;
            border: none;
            border-radius: 50%;
            width: 28px;
            height: 28px;
            cursor: pointer;
            font-size: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            transition: all 0.2s;
        }
        
        .preview-remove:hover {
            background: #dc2626;
            transform: scale(1.1);
        }
        
        .processing {
            text-align: center;
            padding: 20px;
            color: var(--primary);
        }
        
        .spinner {
            border: 3px solid var(--border);
            border-top: 3px solid var(--primary);
            border-radius: 50%;
            width: 48px;
            height: 48px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .empty-state {
            text-align: center;
            padding: 80px 20px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
        }
        
        .empty-state h2 {
            color: var(--primary);
            margin-bottom: 16px;
            font-size: 1.8em;
        }
        
        .empty-state p {
            color: var(--text-secondary);
            font-size: 1.1em;
        }
        
        /* Avatar Emoji Picker */
        .emoji-picker {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 12px;
            margin: 20px 0;
        }
        
        .emoji-option {
            font-size: 2.5em;
            cursor: pointer;
            text-align: center;
            padding: 12px;
            border-radius: 12px;
            background: var(--surface-light);
            border: 2px solid transparent;
            transition: all 0.2s;
        }
        
        .emoji-option:hover {
            background: var(--primary);
            transform: scale(1.1);
        }
        
        .emoji-option.selected {
            background: var(--primary);
            border-color: var(--accent);
        }
                /* FIX #1: Avatar on cards */
        .user-avatar-small {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 0.9em;
        }
        
        .user-avatar-small .avatar-emoji {
            font-size: 1.1em;
        }
        
        /* FIX #2: Clickable list view */
        .books-grid.list .book-card {
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .books-grid.list .book-card:hover {
            background: var(--surface-light);
            transform: translateX(4px);
        }
        
        /* Book detail modal */
        .book-detail-modal .modal-content {
            max-width: 700px;
        }
        
        .book-detail-header {
            display: flex;
            gap: 24px;
            margin-bottom: 24px;
        }
        
        .book-detail-cover {
            width: 200px;
            min-width: 200px;
            height: 300px;
            border-radius: 12px;
            overflow: hidden;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 4em;
        }
        
        .book-detail-cover img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .book-detail-info {
            flex: 1;
        }
        
        .book-detail-title {
            font-size: 1.8em;
            font-weight: 700;
            margin-bottom: 8px;
            color: var(--text);
        }
        
        .book-detail-author {
            font-size: 1.2em;
            color: var(--primary);
            margin-bottom: 12px;
        }
        
        .book-detail-meta {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-bottom: 16px;
        }
        
        .book-detail-meta-item {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-secondary);
            font-size: 0.9em;
        }
        
        .book-detail-section {
            margin-bottom: 20px;
        }
        
        .book-detail-section-title {
            font-weight: 600;
            color: var(--primary);
            margin-bottom: 8px;
            font-size: 0.95em;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .book-detail-section-content {
            color: var(--text-secondary);
            line-height: 1.6;
        }
        
        .book-detail-actions {
            display: flex;
            gap: 12px;
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
            flex-wrap: wrap;
        }
        
        @media (max-width: 768px) {
            body {
                padding: 10px;
                padding-bottom: 100px;
            }
            
            h1 {
                font-size: 1.6em;
            }
            
            .header-top {
                flex-direction: column;
                align-items: flex-start;
                gap: 12px;
            }
            
            .header-actions {
                align-self: flex-end;
            }
            
            .books-grid,
            .books-grid.comfortable,
            .books-grid.cozy,
            .books-grid.compact {
                grid-template-columns: 1fr !important;
                gap: 16px;
            }
            
            .books-grid.list {
                gap: 12px;
            }
            
            .stats {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .filters-grid {
                grid-template-columns: 1fr;
            }
            
            .controls-header {
                flex-direction: column;
                align-items: flex-start;
            }
            
            .controls-actions {
                width: 100%;
                justify-content: space-between;
            }
            
            .emoji-picker {
                grid-template-columns: repeat(4, 1fr);
                gap: 8px;
            }
            
            .emoji-option {
                font-size: 2em;
                padding: 8px;
            }
            .book-detail-header {
                flex-direction: column;
                align-items: center;
                text-align: center; 
            }                   
            .book-detail-cover {
                width: 180px;
                height: 270px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-top">
                <h1>📚 Book Tracker</h1>
                <div class="header-actions">
                    <div class="user-badge" onclick="openModal('profile-modal')" id="current-user-badge">
                        <span id="current-user-avatar">👤</span> <span id="current-user-name">Set Your Name</span>
                    </div>
                    <a href="/logout" class="logout-btn">
                        🚪 Logout
                    </a>
                </div>
            </div>
            <p class="subtitle">Your modern family reading library</p>
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
                <span class="controls-title">🔍 Filter & Sort</span>
                <div class="controls-actions">
                    <button class="view-density-btn" data-density="comfortable" title="Comfortable View">
                        <span>▢</span>
                    </button>
                    <button class="view-density-btn active" data-density="cozy" title="Cozy View">
                        <span>▦</span>
                    </button>
                    <button class="view-density-btn" data-density="compact" title="Compact View">
                        <span>▪</span>
                    </button>
                    <button class="view-density-btn" data-density="list" title="List View (Mobile)">
                        <span>☰</span>
                    </button>
                    <button class="clear-filters-btn" onclick="clearAllFilters()">Clear All</button>
                </div>
            </div>
            
            <div class="search-bar">
                <input type="text" id="search" placeholder="🔎 Search by title, author, genre, person...">
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
                    <label>Read By</label>
                    <select id="filter-read-by">
                        <option value="">All Users</option>
                        {% for user in stats.users_read %}
                        <option value="{{ user }}">{{ user }}</option>
                        {% endfor %}
                    </select>
                </div>
                
                <div class="filter-group">
                    <label>Sort By</label>
                    <select id="sort-by">
                        <option value="date-desc">Date Added (Newest)</option>
                        <option value="date-asc">Date Added (Oldest)</option>
                        <option value="title-asc">Title (A-Z)</option>
                        <option value="title-desc">Title (Z-A)</option>
                        <option value="author-asc">Author (A-Z)</option>
                        <option value="rating-desc">Rating (High-Low)</option>
                        <option value="rating-asc">Rating (Low-High)</option>
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
        <div class="books-grid cozy" id="books-grid">
            {% for book in books %}
            <div class="book-card {% if book.is_read %}read{% endif %}" 
                 data-id="{{ book.id }}"
                 data-title="{{ book.title }}"
                 data-author="{{ book.author }}"
                 data-added-by="{{ book.added_by or '' }}" 
                 data-read-by="{{ book.read_by or '' }}"
                 data-read="{{ 'true' if book.is_read else 'false' }}"
                 data-genres="{{ book.genres or book.genre or '' }}"
                 data-rating="{{ book.goodreads_score or 0 }}"
                 data-date="{{ book.date_entered }}">
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
                    <div class="book-publish-date">📅 Published {{ book.formatted_date }}</div>
                    {% elif book.date_published and book.date_published != 'Unknown' %}
                    <div class="book-publish-date">📅 Published {{ book.date_published }}</div>
                    {% endif %}
                    
                    <div class="book-meta">
                        <div class="genres-container collapsed" id="genres-{{ book.id }}">
                            {% if book.genres and book.genres != 'Unknown' %}
                                {% for genre in book.genres.split(', ') %}
                                <span class="badge badge-genre" onclick="filterByGenre('{{ genre }}')" title="Click to filter">{{ genre }}</span>
                                {% endfor %}
                            {% elif book.genre and book.genre != 'Unknown' %}
                            <span class="badge badge-genre" onclick="filterByGenre('{{ book.genre }}')" title="Click to filter">{{ book.genre }}</span>
                            {% endif %}
                        </div>
                        
                        {% if book.genres and book.genres.split(', ')|length > 3 %}
                        <button class="expand-genres-btn" onclick="toggleGenres({{ book.id }})">
                            +{{ book.genres.split(', ')|length - 3 }} more
                        </button>
                        {% endif %}
                        
                        {% if book.part_of_series and book.part_of_series not in ['No', 'Unknown'] %}
                        <span class="badge badge-series">
                            {{ book.part_of_series }}{% if book.series_number %} #{{ book.series_number }}{% endif %}
                        </span>
                        {% endif %}
                        
                        {% if book.goodreads_score %}
                        <a href="{{ book.goodreads_url }}" target="_blank" class="badge badge-rating goodreads-link" style="text-decoration: none;">
                            ⭐ {{ book.goodreads_score }}/5
                        </a>
                        {% endif %}
                    </div>
                    
                    {% if book.major_awards and book.major_awards not in ['TBD', 'Unknown', 'None', 'none', 'N/A'] %}
                    <div class="book-awards">
                        <strong>🏆 Awards:</strong> {{ book.major_awards }}
                    </div>
                    {% endif %}
                    
                    {% if book.summary and book.summary != 'Unknown' and book.summary != 'No summary available' %}
                    <div class="book-summary collapsed" id="summary-{{ book.id }}">{{ book.summary }}</div>
                    <span class="read-more" onclick="toggleSummary({{ book.id }})">Read more</span>
                    {% endif %}
                    
                    <div class="book-footer">
                        <div>
                            {% if book.added_by %}
                            <span class="user-avatar-small">
                                <span class="avatar-emoji" data-username="{{ book.added_by }}">👤</span>
                                {{ book.added_by }}
                            </span>
                            {% endif %}
                            {% if book.is_read and book.read_by %}
                            <br>
                            <span class="user-avatar-small">
                                ✓ <span class="avatar-emoji" data-username="{{ book.read_by }}">👤</span>
                                {{ book.read_by }}
                            </span>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="empty-state">
            <h2>📖 No books yet!</h2>
            <p>Tap the + button to add your first book</p>
        </div>
        {% endif %}
    </div>
    
    <!-- Add Book Modal -->
    <div class="modal" id="add-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Add New Book</h2>
                <button class="close-btn" onclick="closeModal('add-modal')">&times;</button>
            </div>
            <form id="add-book-form" enctype="multipart/form-data">
                <div class="form-group">
                    <label>Your Name</label>
                    <input type="text" id="user-name" name="user_name" placeholder="Enter your name" required>
                </div>
                <div class="form-group">
                    <label>Book Cover Photo</label>
                    <input type="file" id="book-image" name="image" accept="image/*" class="camera-input" multiple required>
                    <button type="button" class="camera-btn" onclick="document.getElementById('book-image').click()">
                        📷 Take Photo or Select from Library
                    </button>
                    <div id="preview-container" style="margin-top: 15px;"></div>
                </div>
                <div class="form-group">
                    <button type="submit" class="btn camera-btn" id="submit-books-btn" disabled style="opacity: 0.5;">Add Book(s)</button>
                </div>
            </form>
            <div id="processing-status" class="processing" style="display: none;">
                <div class="spinner"></div>
                <p>Processing...</p>
            </div>
        </div>
    </div>
    
    <!-- Mark Read Modal -->
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
    
    <!-- Profile Modal -->
    <div class="modal" id="profile-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Your Profile</h2>
                <button class="close-btn" onclick="closeModal('profile-modal')">&times;</button>
            </div>
            <form id="profile-form">
                <div class="form-group">
                    <label>Choose Your Avatar</label>
                    <div class="emoji-picker">
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
                        <div class="emoji-option" data-emoji="🦆">🦆</div>
                        <div class="emoji-option" data-emoji="🦉">🦉</div>
                        <div class="emoji-option" data-emoji="🦄">🦄</div>
                        <div class="emoji-option" data-emoji="🐝">🐝</div>
                        <div class="emoji-option" data-emoji="🦋">🦋</div>
                        <div class="emoji-option" data-emoji="🐌">🐌</div>
                    </div>
                    <input type="hidden" id="selected-avatar" value="👤">
                </div>
                <div class="form-group">
                    <label>Your Name</label>
                    <input type="text" id="profile-name" placeholder="Enter your name" required>
                </div>
                <div class="form-group">
                    <button type="submit" class="btn camera-btn">Save Profile</button>
                </div>
            </form>
        </div>
     </div>
        <!-- FIX #2: Book Detail Modal -->
    <div class="modal book-detail-modal" id="book-detail-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Book Details</h2>
                <button class="close-btn" onclick="closeModal('book-detail-modal')">&times;</button>
            </div>
            <div id="book-detail-content">
                <!-- Content populated by JavaScript -->
            </div>
        </div>
    </div>
    <button class="fab" onclick="openModal('add-modal')">+</button>
    
<script>
    // Define global functions FIRST (before DOMContentLoaded) for inline onclick
    let selectedFiles = [];
    
    function openModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) modal.classList.add('active');
    }
    
    function closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('active');
            if (modalId === 'add-modal') {
                const form = document.getElementById('add-book-form');
                if (form) form.reset();
                const preview = document.getElementById('preview-container');
                if (preview) preview.innerHTML = '';
                selectedFiles = [];
                updateSubmitButton();
            }
        }
    }
    
    function toggleGenres(bookId) {
        const container = document.getElementById('genres-' + bookId);
        const btn = event.target;
        if (!container) return;
        
        if (container.classList.contains('collapsed')) {
            container.classList.remove('collapsed');
            btn.textContent = 'Show less';
        } else {
            container.classList.add('collapsed');
            const hiddenCount = container.querySelectorAll('.badge-genre').length - 3;
            btn.textContent = `+${hiddenCount} more`;
        }
    }
    
    function filterByGenre(genre) {
        const genreSelect = document.getElementById('filter-genre');
        if (genreSelect) {
            genreSelect.value = genre;
            filterAndSortBooks();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }
    
    function toggleSummary(bookId) {
        const summary = document.getElementById('summary-' + bookId);
        const readMore = event.target;
        if (!summary) return;
        
        if (summary.classList.contains('collapsed')) {
            summary.classList.remove('collapsed');
            readMore.textContent = 'Read less';
        } else {
            summary.classList.add('collapsed');
            readMore.textContent = 'Read more';
        }
    }
    
    async function markUnread(bookId) {
        if (!confirm('Mark as unread?')) return;
        const response = await fetch('/api/mark-unread', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ book_id: bookId })
        });
        if (response.ok) location.reload();
    }
    
    async function deleteBook(bookId, bookTitle) {
        if (!confirm(`Delete "${bookTitle}"?`)) return;
        const response = await fetch('/api/delete-book', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ book_id: bookId })
        });
        if (response.ok) location.reload();
    }
    
    function showReadModal(bookId, bookTitle) {
        document.getElementById('read-book-id').value = bookId;
        document.getElementById('read-book-title').textContent = bookTitle;
        openModal('read-modal');
    }
    
    function clearAllFilters() {
        const searchInput = document.getElementById('search');
        const filterGenre = document.getElementById('filter-genre');
        const filterAddedBy = document.getElementById('filter-added-by');
        const filterReadBy = document.getElementById('filter-read-by');
        const sortBy = document.getElementById('sort-by');
        
        if (searchInput) searchInput.value = '';
        if (filterGenre) filterGenre.selectedIndex = 0;
        if (filterAddedBy) filterAddedBy.selectedIndex = 0;
        if (filterReadBy) filterReadBy.selectedIndex = 0;
        if (sortBy) sortBy.selectedIndex = 0;
        
        document.querySelectorAll('.chip').forEach(chip => {
            chip.classList.remove('active');
            if (chip.dataset.filter === 'all') chip.classList.add('active');
        });
        filterAndSortBooks();
    }
    
    function filterAndSortBooks() {
        const booksGrid = document.getElementById('books-grid');
        if (!booksGrid) return;
        
        const searchInput = document.getElementById('search');
        const filterGenre = document.getElementById('filter-genre');
        const filterAddedBy = document.getElementById('filter-added-by');
        const filterReadBy = document.getElementById('filter-read-by');
        const sortBy = document.getElementById('sort-by');
        
        const query = searchInput ? searchInput.value.toLowerCase() : '';
        const genre = filterGenre ? filterGenre.value : '';
        const addedBy = filterAddedBy ? filterAddedBy.value : '';
        const readBy = filterReadBy ? filterReadBy.value : '';
        const sortOption = sortBy ? sortBy.value : 'date-desc';
        const activeChip = document.querySelector('.chip.active');
        const readFilter = activeChip ? activeChip.dataset.filter : 'all';
        
        const books = Array.from(document.querySelectorAll('.book-card'));
        
        const filteredBooks = books.filter(book => {
            const text = book.textContent.toLowerCase();
            const bookGenres = book.dataset.genres.toLowerCase();
            const bookAddedBy = book.dataset.addedBy;
            const bookReadBy = book.dataset.readBy;
            const isRead = book.dataset.read === 'true';
            
            if (query && !text.includes(query)) return false;
            if (genre && !bookGenres.includes(genre.toLowerCase())) return false;
            if (addedBy && bookAddedBy !== addedBy) return false;
            if (readBy && bookReadBy !== readBy) return false;
            if (readFilter === 'read' && !isRead) return false;
            if (readFilter === 'unread' && isRead) return false;
            
            return true;
        });
        
        filteredBooks.sort((a, b) => {
            switch(sortOption) {
                case 'date-desc': return new Date(b.dataset.date) - new Date(a.dataset.date);
                case 'date-asc': return new Date(a.dataset.date) - new Date(b.dataset.date);
                case 'title-asc': return a.dataset.title.localeCompare(b.dataset.title);
                case 'title-desc': return b.dataset.title.localeCompare(a.dataset.title);
                case 'author-asc': return a.dataset.author.localeCompare(b.dataset.author);
                case 'rating-desc': return parseFloat(b.dataset.rating) - parseFloat(a.dataset.rating);
                case 'rating-asc': return parseFloat(a.dataset.rating) - parseFloat(b.dataset.rating);
                default: return 0;
            }
        });
        
        books.forEach(book => book.style.display = 'none');
        filteredBooks.forEach(book => {
            book.style.display = 'block';
            booksGrid.appendChild(book);
        });
    }
    
    function updateSubmitButton() {
        const btn = document.getElementById('submit-books-btn');
        if (!btn) return;
        
        const count = selectedFiles.length;
        if (count === 0) {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.textContent = 'Add Book(s)';
        } else {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.textContent = count === 1 ? 'Add 1 Book' : `Add ${count} Books`;
        }
    }
    // FIX #2: Show book details in modal
    function showBookDetail(bookId) {
        const bookCard = document.querySelector(`.book-card[data-id="${bookId}"]`);
        if (!bookCard) return;
        
        const title = bookCard.dataset.title;
        const author = bookCard.dataset.author;
        const genres = bookCard.dataset.genres;
        const rating = bookCard.dataset.rating;
        const addedBy = bookCard.dataset.addedBy;
        const readBy = bookCard.dataset.readBy;
        const isRead = bookCard.dataset.read === 'true';
    
        const thumbnail = bookCard.querySelector('.book-thumbnail img')?.src || null;
        const publishDate = bookCard.querySelector('.book-publish-date')?.textContent.replace('📅 Published ', '') || 'Unknown';
        const summary = bookCard.querySelector('.book-summary')?.textContent || 'No summary available';
        const awards = bookCard.querySelector('.book-awards')?.textContent.replace('🏆 Awards: ', '') || null;
        const series = bookCard.querySelector('.badge-series')?.textContent || null;
        const goodreadsLink = bookCard.querySelector('.goodreads-link')?.href || null;
    
        const addedByAvatar = getUserAvatar(addedBy);
        const readByAvatar = readBy ? getUserAvatar(readBy) : null;
    
        const content = `
            <div class="book-detail-header">
                <div class="book-detail-cover">
                    ${thumbnail ? `<img src="${thumbnail}" alt="${title}">` : '📚'}
                </div>
                <div class="book-detail-info">
                    <div class="book-detail-title">${title}</div>
                    <div class="book-detail-author">by ${author}</div>
                    <div class="book-detail-meta">
                        ${publishDate !== 'Unknown' ? `<div class="book-detail-meta-item">📅 ${publishDate}</div>` : ''}
                        ${rating > 0 ? `<div class="book-detail-meta-item">⭐ ${rating}/5 Rating</div>` : ''}
                        ${series ? `<div class="book-detail-meta-item">📖 ${series}</div>` : ''}
                        ${isRead ? `<div class="book-detail-meta-item">✓ Read by ${readByAvatar} ${readBy}</div>` : '<div class="book-detail-meta-item">📚 Unread</div>'}
                        <div class="book-detail-meta-item">${addedByAvatar} Added by ${addedBy}</div>
                    </div>
                </div>
            </div>
        
            ${genres && genres !== 'Unknown' ? `
            <div class="book-detail-section">
                <div class="book-detail-section-title">Genres</div>
                <div class="book-detail-section-content">
                    ${genres.split(', ').map(g => `<span class="badge badge-genre" style="margin-right: 6px; margin-bottom: 6px;">${g}</span>`).join('')}
                </div>
            </div>
            ` : ''}
        
            ${awards ? `
            <div class="book-detail-section">
                <div class="book-detail-section-title">Awards</div>
                <div class="book-awards">${awards}</div>
            </div>
            ` : ''}
        
            <div class="book-detail-section">
                <div class="book-detail-section-title">Summary</div>
                <div class="book-detail-section-content">${summary}</div>
            </div>
        
            ${goodreadsLink ? `
            <div class="book-detail-section">
                <a href="${goodreadsLink}" target="_blank" class="goodreads-link">View on Goodreads →</a>
            </div>
            ` : ''}
        
            <div class="book-detail-actions">
                ${!isRead ? `<button class="btn btn-read" onclick="closeModal('book-detail-modal'); showReadModal(${bookId}, '${title.replace(/'/g, "\\'")}');">Mark as Read</button>` : `<button class="btn btn-unread" onclick="closeModal('book-detail-modal'); markUnread(${bookId});">Mark Unread</button>`}
                <button class="btn btn-delete" onclick="closeModal('book-detail-modal'); deleteBook(${bookId}, '${title.replace(/'/g, "\\'")}');">Delete Book</button>
            </div>
        `;
    
        document.getElementById('book-detail-content').innerHTML = content;
        openModal('book-detail-modal');
    }

    // FIX #1: Get user avatar emoji from localStorage
    function getUserAvatar(username) {
        if (!username) return '👤';
        const avatarMap = JSON.parse(localStorage.getItem('bookTrackerAvatarMap') || '{}');
        return avatarMap[username] || '👤';
    }

    function updateAvatarMap(username, avatar) {
        const avatarMap = JSON.parse(localStorage.getItem('bookTrackerAvatarMap') || '{}');
        avatarMap[username] = avatar;
        localStorage.setItem('bookTrackerAvatarMap', JSON.stringify(avatarMap));
    }

    function updateAllAvatars() {
        document.querySelectorAll('.avatar-emoji').forEach(el => {
            const username = el.dataset.username;
            if (username) {
                el.textContent = getUserAvatar(username);
            }
        });
    }    
    // NOW setup event listeners after DOM loads
    document.addEventListener('DOMContentLoaded', function() {
        const booksGrid = document.getElementById('books-grid');
        
        // View density buttons
        if (booksGrid) {
            document.querySelectorAll('.view-density-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    document.querySelectorAll('.view-density-btn').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    const density = this.dataset.density;
                    booksGrid.className = 'books-grid ' + density;
                    localStorage.setItem('bookTrackerDensity', density);
                });
            });
            
            const savedDensity = localStorage.getItem('bookTrackerDensity') || 'cozy';
            booksGrid.className = 'books-grid ' + savedDensity;
            const activeBtn = document.querySelector(`.view-density-btn[data-density="${savedDensity}"]`);
            if (activeBtn) activeBtn.classList.add('active');
        }
        
        // File input
        const bookImageInput = document.getElementById('book-image');
        if (bookImageInput) {
            bookImageInput.addEventListener('change', function(e) {
                const newFiles = Array.from(e.target.files);
                selectedFiles = newFiles;
                const previewContainer = document.getElementById('preview-container');
                if (!previewContainer) return;
                
                previewContainer.innerHTML = '';
                
                selectedFiles.forEach((file, index) => {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        const wrapper = document.createElement('div');
                        wrapper.className = 'preview-wrapper';
                        wrapper.dataset.fileIndex = index;
                        
                        const img = document.createElement('img');
                        img.src = e.target.result;
                        img.className = 'preview-image';
                        
                        const removeBtn = document.createElement('button');
                        removeBtn.type = 'button';
                        removeBtn.className = 'preview-remove';
                        removeBtn.innerHTML = '×';
                        removeBtn.onclick = function(evt) {
                            evt.preventDefault();
                            const idx = parseInt(wrapper.dataset.fileIndex);
                            selectedFiles = selectedFiles.filter((_, i) => i !== idx);
                            
                            previewContainer.innerHTML = '';
                            selectedFiles.forEach((f, i) => {
                                const r = new FileReader();
                                r.onload = function(ev) {
                                    const w = document.createElement('div');
                                    w.className = 'preview-wrapper';
                                    w.dataset.fileIndex = i;
                                    
                                    const im = document.createElement('img');
                                    im.src = ev.target.result;
                                    im.className = 'preview-image';
                                    
                                    const rb = document.createElement('button');
                                    rb.type = 'button';
                                    rb.className = 'preview-remove';
                                    rb.innerHTML = '×';
                                    rb.onclick = removeBtn.onclick;
                                    
                                    w.appendChild(im);
                                    w.appendChild(rb);
                                    previewContainer.appendChild(w);
                                };
                                r.readAsDataURL(f);
                            });
                            updateSubmitButton();
                        };
                        
                        wrapper.appendChild(img);
                        wrapper.appendChild(removeBtn);
                        previewContainer.appendChild(wrapper);
                    };
                    reader.readAsDataURL(file);
                });
                updateSubmitButton();
            });
        }
        
        // Add book form
        const addBookForm = document.getElementById('add-book-form');
        if (addBookForm) {
            addBookForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                if (selectedFiles.length === 0) return;
                
                const userName = document.getElementById('user-name').value;
                addBookForm.style.display = 'none';
                const processingDiv = document.getElementById('processing-status');
                if (processingDiv) {
                    processingDiv.style.display = 'block';
                    processingDiv.innerHTML = `
                        <div class="spinner"></div>
                        <p>Processing ${selectedFiles.length} book${selectedFiles.length > 1 ? 's' : ''}...</p>
                        <p id="progress-text">0 of ${selectedFiles.length} complete</p>
                    `;
                }
                
                for (let i = 0; i < selectedFiles.length; i++) {
                    const formData = new FormData();
                    formData.append('image', selectedFiles[i]);
                    formData.append('user_name', userName);
                    
                    try {
                        const response = await fetch('/api/add-book', {
                            method: 'POST',
                            body: formData
                        });
                        const result = await response.json();
                        
                        if (!result.success) {
                            console.error('Failed to add book:', result.error);
                            alert(`Failed to add book ${i + 1}: ${result.error}`);
                        } else {
                            console.log(`Book ${i + 1} added successfully:`, result.book_id);
                        }
                    } catch (error) {
                        console.error('Network error:', error);
                        alert(`Network error on book ${i + 1}: ${error.message}`);
                    }
                    const progressText = document.getElementById('progress-text');
                    if (progressText) {
                        progressText.textContent = `${i + 1} of ${selectedFiles.length} complete`;
                    }
                }
                window.location.href = '/';
            });
        }
        
        // Mark read form
        const markReadForm = document.getElementById('mark-read-form');
        if (markReadForm) {
            markReadForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                const bookId = document.getElementById('read-book-id').value;
                const readBy = document.getElementById('read-by-name').value;
                
                const response = await fetch('/api/mark-read', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ book_id: bookId, read_by: readBy })
                });
                if (response.ok) location.reload();
            });
        }
        
        // Search and filters
        const searchInput = document.getElementById('search');
        const filterGenre = document.getElementById('filter-genre');
        const filterAddedBy = document.getElementById('filter-added-by');
        const filterReadBy = document.getElementById('filter-read-by');
        const sortBy = document.getElementById('sort-by');
        
        if (searchInput) searchInput.addEventListener('input', filterAndSortBooks);
        if (filterGenre) filterGenre.addEventListener('change', filterAndSortBooks);
        if (filterAddedBy) filterAddedBy.addEventListener('change', filterAndSortBooks);
        if (filterReadBy) filterReadBy.addEventListener('change', filterAndSortBooks);
        if (sortBy) sortBy.addEventListener('change', filterAndSortBooks);
        
        document.querySelectorAll('.chip').forEach(chip => {
            chip.addEventListener('click', function() {
                document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
                this.classList.add('active');
                filterAndSortBooks();
            });
        });
        // FIX #2: Make list view cards clickable
        document.addEventListener('click', function(e) {
            const card = e.target.closest('.book-card');
            if (!card) return;
            
            const isListView = document.getElementById('books-grid')?.classList.contains('list');
            if (!isListView) return;
            
            if (e.target.closest('.book-actions') || 
                e.target.closest('.badge-genre') ||
                e.target.closest('.btn')) return;
            
            const bookId = card.dataset.id;
            showBookDetail(bookId);
        });
        
        // FIX #1: Update all avatars on page load
        updateAllAvatars();
        // Modal click outside to close
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', function(e) {
                if (e.target === this) this.classList.remove('active');
            });
        });
        
        // Avatar emoji selection
        document.querySelectorAll('.emoji-option').forEach(option => {
            option.addEventListener('click', function() {
                document.querySelectorAll('.emoji-option').forEach(o => o.classList.remove('selected'));
                this.classList.add('selected');
                document.getElementById('selected-avatar').value = this.dataset.emoji;
            });
        });
        
        // User profile with avatar
        function updateUserProfile() {
            const savedName = localStorage.getItem('bookTrackerUserName');
            const savedAvatar = localStorage.getItem('bookTrackerUserAvatar') || '👤';
            
            if (savedName) {
                const els = [
                    {el: document.getElementById('current-user-name'), isInput: false, isAvatar: false},
                    {el: document.getElementById('current-user-avatar'), isInput: false, isAvatar: true},
                    {el: document.getElementById('user-name'), isInput: true, isAvatar: false},
                    {el: document.getElementById('read-by-name'), isInput: true, isAvatar: false},
                    {el: document.getElementById('profile-name'), isInput: true, isAvatar: false}
                ];
                
                els.forEach(item => {
                    if (item.el) {
                        if (item.isAvatar) {
                            item.el.textContent = savedAvatar;
                        } else if (item.isInput) {
                            item.el.value = savedName;
                        } else {
                            item.el.textContent = savedName;
                        }
                    }
                });
                
                // Set selected avatar in picker
                const selectedOption = document.querySelector(`.emoji-option[data-emoji="${savedAvatar}"]`);
                if (selectedOption) {
                    selectedOption.classList.add('selected');
                    document.getElementById('selected-avatar').value = savedAvatar;
                }
            }
        }
        
        updateUserProfile();
        const profileForm = document.getElementById('profile-form');
        if (profileForm) {
            profileForm.addEventListener('submit', function(e) {
                e.preventDefault();
                const name = document.getElementById('profile-name').value.trim();
                const avatar = document.getElementById('selected-avatar').value || '👤';
                
                if (name) {
                    localStorage.setItem('bookTrackerUserName', name);
                    localStorage.setItem('bookTrackerUserAvatar', avatar);
                    updateAvatarMap(name, avatar);  // FIX: Save to avatar map
                    updateUserProfile();
                    updateAllAvatars();  // FIX: Update all cards
                    closeModal('profile-modal');
                }
            });
        }        
    });
</script>
</body>
</html>
"""

# ============================================================================
# ROUTES
# ============================================================================

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

@app.route('/api/books')
@login_required
def api_books():
    """API endpoint to get all books as JSON."""
    books = db.get_all_books()
    return jsonify([book.to_dict() for book in books])

@app.route('/api/stats')
@login_required
def api_stats():
    """API endpoint to get library statistics."""
    return jsonify(db.get_stats())

@app.route('/api/search')
@login_required
def api_search():
    """API endpoint to search books."""
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    books = db.search_books(query)
    return jsonify([book.to_dict() for book in books])

@app.route('/api/add-book', methods=['POST'])
@login_required
def api_add_book():
    """API endpoint to add a new book from uploaded image."""
    try:
        print("=== ADD BOOK API CALLED ===")
        
        if 'image' not in request.files:
            print("ERROR: No image in request")
            return jsonify({'success': False, 'error': 'No image provided'})
        
        file = request.files['image']
        user_name = request.form.get('user_name', 'Unknown')
        
        print(f"File: {file.filename}, User: {user_name}")
        
        if file.filename == '':
            print("ERROR: Empty filename")
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Save to temp file
        temp_dir = tempfile.mkdtemp()
        temp_path = Path(temp_dir) / file.filename
        file.save(str(temp_path))
        print(f"Saved to: {temp_path}")
        
        # Process image
        print("Initializing ImageProcessor...")
        processor = ImageProcessor()
        
        print("Extracting book info from image...")
        book_info = processor.extract_book_info(str(temp_path))
        
        if not book_info:
            print("ERROR: Failed to extract book info")
            return jsonify({'success': False, 'error': 'Failed to extract book information from image'})
        
        print(f"Extracted: {book_info.get('title')} by {book_info.get('author')}")
        
        # Enrich data
        print("Enriching book data...")
        enricher = BookEnricher()
        enriched_data = enricher.enrich_book_data(book_info, use_goodreads=True)
        enriched_data['added_by'] = user_name
        
        print("Saving to database...")
        book = db.add_book(enriched_data)
        
        print(f"SUCCESS: Book #{book.id} added!")
        return jsonify({'success': True, 'book_id': book.id})
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR in api_add_book:")
        print(error_details)
        return jsonify({
            'success': False, 
            'error': str(e),
            'details': error_details
        })

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

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("🚀 Starting Book Tracker Web Interface...")
    print("📚 Modern UI with Authentication!")
    print("🔒 Password:", FAMILY_PASSWORD)
    print("🌐 Access at: http://localhost:5001")
    print("\nPress Ctrl+C to stop")
    
    # Use PORT environment variable for cloud deployment
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)
