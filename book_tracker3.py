#!/usr/bin/env python3
"""
Book Tracker - AI-powered reading list manager
Enhanced with read tracking and better data sources
"""

import os
import sys

# ============= ULTRA-AGGRESSIVE PROXY FIX FOR RENDER =============
# This MUST come before ANY imports

# Step 1: Clear ALL proxy environment variables
proxy_vars = [
    'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
    'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy',
    'REQUESTS_PROXY', 'requests_proxy'
]
for var in proxy_vars:
    os.environ.pop(var, None)

# Step 2: Import and patch httpx BEFORE openai
import httpx

# Store original classes
_OriginalHttpxClient = httpx.Client
_OriginalAsyncClient = httpx.AsyncClient

class PatchedHttpxClient(_OriginalHttpxClient):
    """Httpx client that completely ignores proxy arguments."""
    def __init__(self, *args, **kwargs):
        # Nuclear option: remove ALL potentially problematic kwargs
        kwargs.pop('proxies', None)
        kwargs.pop('proxy', None)
        kwargs.pop('mounts', None)
        kwargs.pop('trust_env', None)
        
        # Force trust_env to False
        kwargs['trust_env'] = False
        
        super().__init__(*args, **kwargs)

class PatchedAsyncClient(_OriginalAsyncClient):
    """Async httpx client that completely ignores proxy arguments."""
    def __init__(self, *args, **kwargs):
        kwargs.pop('proxies', None)
        kwargs.pop('proxy', None)
        kwargs.pop('mounts', None)
        kwargs.pop('trust_env', None)
        kwargs['trust_env'] = False
        super().__init__(*args, **kwargs)

# Replace globally BEFORE any other imports
httpx.Client = PatchedHttpxClient
httpx.AsyncClient = PatchedAsyncClient

# Step 3: Now import openai (which will use our patched httpx)
import openai
from openai import OpenAI

# Step 4: Additional safety - create a custom http_client factory
def create_safe_http_client():
    """Create an httpx client with no proxy support."""
    return PatchedHttpxClient(
        timeout=httpx.Timeout(60.0),
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=100),
        trust_env=False
    )

# ============= END PROXY FIX =============

# Now import everything else
import json
import base64
import argparse
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup
from tabulate import tabulate
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client
import uuid

# ✅ Load environment AFTER proxy patch
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o-mini"
GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"

# DO NOT create a global supabase client here.
# The DatabaseManager below handles that safely.

def create_safe_http_client():
    """Create an httpx client with no proxy support."""
    return PatchedHttpxClient(
        timeout=httpx.Timeout(60.0),
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=100),
        trust_env=False
    )
# ============================================================================
# CONFIGURATION
# ============================================================================

# Paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "books.db"
DATA_DIR.mkdir(exist_ok=True)

# API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o-mini"
GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


# Database
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Processing
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
SUPPORTED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

# ============================================================================
# DATABASE MODELS
# ============================================================================

# ============================================================================
# DATABASE MANAGER
# ============================================================================

# ============================================================================
# SUPABASE DATABASE MANAGER (replaces SQLAlchemy)
# ============================================================================
from supabase import create_client, Client
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


class DatabaseManager:
    """Handles all Supabase database operations."""

    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials missing. Check .env or Render env vars.")
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    def upload_image(self, file_path):
        """Upload an image to Supabase Storage and return its public URL."""
        try:
            file_name = f"{uuid.uuid4().hex}_{os.path.basename(file_path)}"
            with open(file_path, "rb") as f:
                self.supabase.storage.from_("book_covers").upload(
                    file_name,
                    f,
                    {"content-type": "image/jpeg"}
                )
            return f"{SUPABASE_URL}/storage/v1/object/public/book_covers/{file_name}"
        except Exception as e:
            print("❌ Upload exception:", e)
            return None
    # ---------------------- Core CRUD ----------------------

    def add_book(self, book_data: dict):
        """Insert a new book."""
        response = self.supabase.table("books").insert(book_data).execute()
        return response.data

    def update_book(self, book_id: str, updates: dict):
        """Update a book's info."""
        response = self.supabase.table("books").update(updates).eq("id", book_id).execute()
        return response.data

    def delete_book(self, book_id: str):
        """Delete a book."""
        self.supabase.table("books").delete().eq("id", book_id).execute()
        return True

    def get_all_books(self, filters: dict = None):
        query = self.supabase.table("books").select("*")
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        result = query.order("created_at", desc=True).execute()
        # Return list of dicts, not Book objects
        return result.data or []

    def get_book_by_id(self, book_id: str):
        """Fetch one book by id."""
        result = self.supabase.table("books").select("*").eq("id", book_id).limit(1).execute()
        return result.data[0] if result.data else None

    def search_books(self, query: str):
        """Search by title, author, or genre."""
        like = f"%{query}%"
        result = (
            self.supabase.table("books")
            .select("*")
            .or_(f"title.ilike.{like},author.ilike.{like},genres.ilike.{like}")
            .execute()
        )
        return result.data

    # ---------------------- Stats ----------------------

    def get_stats(self):
        """Simple aggregate stats."""
        books = self.get_all_books()
        if not books:
            return {
                "total_books": 0,
                "read_books": 0,
                "unread_books": 0,
                "unique_genres": 0,
                "average_rating": None,
            }

        total_books = len(books)
        read_books = len([b for b in books if b.get("is_read")])
        genres = {b.get("genre") for b in books if b.get("genre")}
        ratings = [b["rating"] for b in books if b.get("rating")]

        return {
            "total_books": total_books,
            "read_books": read_books,
            "unread_books": total_books - read_books,
            "unique_genres": len(genres),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        }

    def mark_as_read(self, book_id: str, read_by: str):
        """Mark book as read."""
        return self.update_book(book_id, {
            "is_read": True,
            "read_date": datetime.utcnow().isoformat(),
            "read_by": read_by
        })

    def mark_as_unread(self, book_id: str):
        """Mark book as unread."""
        return self.update_book(book_id, {
            "is_read": False,
            "read_date": None,
            "read_by": None
        })
# ============================================================================
# IMAGE PROCESSOR
# ============================================================================

class ImageProcessor:
    """Handles image processing and book information extraction."""
    
    def __init__(self):
        """Initialize the OpenAI client."""
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found. Please set it in your .env file")
        
        # Create OpenAI client with custom http_client to avoid proxy issues
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            http_client=create_safe_http_client()
        )
    
    def validate_image(self, image_path: str) -> bool:
        """Validate image file format and size."""
        path = Path(image_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        if path.suffix.lower() not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(
                f"Unsupported image format: {path.suffix}. "
                f"Supported formats: {SUPPORTED_IMAGE_FORMATS}"
            )
        
        if path.stat().st_size > MAX_IMAGE_SIZE:
            raise ValueError(
                f"Image file too large: {path.stat().st_size / 1024 / 1024:.2f}MB. "
                f"Maximum size: {MAX_IMAGE_SIZE / 1024 / 1024}MB"
            )
        
        return True
    
    def encode_image(self, image_path: str) -> str:
        """Encode image to base64."""
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def extract_book_info(self, image_path: str) -> Optional[Dict]:
        """Extract book information from an image using OpenAI Vision API."""
        self.validate_image(image_path)
        
        image_data = self.encode_image(image_path)
        
        prompt = """Analyze this book cover image and extract the basic information. Respond ONLY with valid JSON.

{
  "title": "full book title including subtitle",
  "author": "author name(s)",
  "series_name": "if this is part of a series, the series name; otherwise null",
  "series_number": "if part of a series, the book number (e.g., '1', '2', '3'); otherwise null"
}

INSTRUCTIONS:
1. **Title**: Extract the complete title including subtitle if present
2. **Author**: Extract author name(s) exactly as shown
3. **Series**: Look for indicators like "Book 1", "#2", "Volume 3", "First in the...", series name, etc.

DO NOT try to determine genre or summary from the cover image.
RETURN ONLY THE RAW JSON. No markdown, no code blocks, no explanations."""
        
        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            response_text = response.choices[0].message.content.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            
            book_info = json.loads(response_text)
            book_info['image_path'] = str(Path(image_path).absolute())
            
            book_info['genre'] = None
            book_info['genres'] = None
            book_info['summary'] = None
            
            if book_info.get('series_name'):
                book_info['part_of_series'] = book_info['series_name']
                book_info['series_number'] = book_info.get('series_number', 'Unknown')
            else:
                book_info['part_of_series'] = 'No'
                book_info['series_number'] = None
            
            book_info.pop('series_name', None)
            
            return book_info
            
        except json.JSONDecodeError as e:
            print(f"Error parsing OpenAI response: {e}")
            print(f"Response was: {response_text}")
            return None
        except Exception as e:
            print(f"Error processing image: {e}")
            import traceback
            traceback.print_exc()
            return None

# ============================================================================
# GOODREADS SCRAPER
# ============================================================================
class GoodreadsScraper:
    """Scrapes Goodreads for book ratings, summary, and genres."""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.last_request_time = 0
        self.min_delay = 2

    def _rate_limit(self):
        """Throttle requests to avoid hitting Goodreads aggressively."""
        current_time = time.time()
        wait_time = self.min_delay - (current_time - self.last_request_time)
        if wait_time > 0:
            time.sleep(wait_time)
        self.last_request_time = time.time()

    def search_goodreads(self, title: str, author: str = None) -> Optional[Dict]:
        """Search Goodreads for book metadata."""
        try:
            self._rate_limit()

            query = f"{title} {author}" if author else title
            search_url = f"https://www.goodreads.com/search?q={quote(query)}"

            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            book_links = soup.find_all("a", class_="bookTitle", limit=10)
            
            if not book_links:
                print("  [!] No books found in search results")
                return None

            skip_keywords = [
                'study guide', 'book analysis', 'summary', 'sparknotes',
                'cliffsnotes', 'reader\'s guide', 'companion', 'critical analysis',
                'detailed summary', 'litcharts'
            ]
            
            selected_link = None
            for link in book_links:
                link_text = link.get_text(strip=True).lower()
                link_title = link.get('title', '').lower() if link.get('title') else ''
                combined_text = f"{link_text} {link_title}"
                
                if any(keyword in combined_text for keyword in skip_keywords):
                    print(f"  [~] Skipping: {link.get_text(strip=True)[:60]}...")
                    continue
                
                selected_link = link
                print(f"  [+] Selected: {link.get_text(strip=True)[:60]}")
                break
            
            if not selected_link:
                print("  [!] Only found study guides, using first result anyway")
                selected_link = book_links[0]

            book_url = f"https://www.goodreads.com{selected_link['href']}"
            self._rate_limit()

            book_page = requests.get(book_url, headers=self.headers, timeout=10)
            book_page.raise_for_status()
            book_soup = BeautifulSoup(book_page.text, "html.parser")

            result = {"goodreads_url": book_url}

            # Extract rating
            rating_elem = book_soup.find("div", class_="RatingStatistics__rating")
            if rating_elem:
                try:
                    result["goodreads_score"] = float(rating_elem.text.strip())
                except ValueError:
                    pass

            # Extract summary
            summary = None
            desc_section = (
                book_soup.find("div", class_="DetailsLayoutRightParagraph")
                or book_soup.find("div", {"data-testid": "description"})
                or book_soup.find("span", {"data-testid": "contentReview"})
            )

            if desc_section:
                text_block = desc_section.get_text(separator=" ", strip=True)
                if text_block and len(text_block) > 40:
                    sentences = re.split(r"(?<=[.!?])\s+", text_block)
                    summary = " ".join(sentences[:3])  # adjust number as needed
            
            if not summary:
                meta = book_soup.find("meta", {"property": "og:description"})
                if meta and meta.get("content"):
                    summary = meta["content"].split(".")[0] + "."

            if summary:
                result["summary"] = summary.strip()

            # Extract genres
            genres = []
            
            genre_labels = book_soup.find_all("span", {"data-testid": "genreActionLabel"})
            for label in genre_labels[:10]:
                genre_text = label.get_text(strip=True)
                if genre_text and 2 < len(genre_text) < 50:
                    genres.append(genre_text)
            
            if not genres:
                genre_section = book_soup.find("div", class_="BookPageMetadataSection__genres")
                if genre_section:
                    buttons = genre_section.find_all("span", class_="Button__labelItem")
                    for btn in buttons[:10]:
                        genre_text = btn.get_text(strip=True)
                        if genre_text and genre_text not in genres and 2 < len(genre_text) < 50:
                            genres.append(genre_text)
            
            if not genres:
                genre_links = book_soup.find_all("a", href=lambda x: x and "/genres/" in x, limit=15)
                for link in genre_links[:10]:
                    genre_text = link.get_text(strip=True)
                    genre_text = re.sub(r'\s*\d+\s*users?.*$', '', genre_text, flags=re.IGNORECASE)
                    genre_text = re.sub(r'\s*â€º.*$', '', genre_text)
                    
                    if genre_text and genre_text not in genres and 2 < len(genre_text) < 50:
                        skip_words = ['shelf', 'to-read', 'want', 'currently', 'more genres', 'add', 'vote']
                        if not any(skip in genre_text.lower() for skip in skip_words):
                            genres.append(genre_text)
            
            if not genres:
                element_list = book_soup.find("div", class_="elementList")
                if element_list:
                    links = element_list.find_all("a", class_="actionLinkLite", limit=10)
                    for link in links:
                        genre_text = link.get_text(strip=True)
                        if genre_text and 2 < len(genre_text) < 50:
                            genres.append(genre_text)

            if genres:
                result["genres"] = ", ".join(genres)
                result["genre"] = genres[0]
                print(f"  [+] Found {len(genres)} genres: {result['genre']}")
            else:
                print(f"  [!] No genres found on page")

            # Publication date
            details = book_soup.find("p", {"data-testid": "publicationInfo"})
            if details:
                match = re.search(r"(\w+ \d+, \d{4}|\w+ \d{4}|\d{4})", details.get_text())
                if match:
                    result["date_published"] = match.group(1)
                    print(f"  [+] Publication date: {result['date_published']}")

            return result

        except Exception as e:
            print(f"  [X] Goodreads fetch failed: {e}")
            import traceback
            traceback.print_exc()
            return None

# ============================================================================
# BOOK ENRICHER
# ============================================================================

class BookEnricher:
    """Enriches book data with additional information from external APIs."""
    
    def __init__(self):
        self.goodreads = GoodreadsScraper()
    
    def identify_major_awards(self, title: str, author: str, date_published: str) -> Optional[str]:
        """Use LLM to identify if the book won any major literary awards."""
        try:
            client = OpenAI(
                api_key=OPENAI_API_KEY,
                http_client=create_safe_http_client()
            )
            
            prompt = f"""Does this book have any major literary awards? List ONLY the actual awards won (not nominations).

Title: {title}
Author: {author}
Published: {date_published}

Major awards include:
- Pulitzer Prize
- National Book Award
- Booker Prize / Man Booker Prize
- Nobel Prize in Literature
- Hugo Award
- Nebula Award
- Edgar Award
- Newbery Medal
- Caldecott Medal
- Costa Book Awards
- PEN/Faulkner Award
- National Book Critics Circle Award
- Andrew Carnegie Medal

If the book won awards, respond with a comma-separated list like: "Pulitzer Prize for Fiction (2007), National Book Award"
If the book won NO major awards, respond with exactly: "None"
Be factually accurate. Only list awards you are certain about."""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1
            )
            
            awards = response.choices[0].message.content.strip()
            if awards and awards.lower() not in ['none', 'unknown', 'n/a', 'no awards']:
                print(f"  [+] Awards: {awards}")
                return awards
            return "None"
            
        except Exception as e:
            print(f"  Note: Could not identify awards: {e}")
            return "TBD"
    
    def search_google_books(self, title: str, author: str = None) -> Optional[Dict]:
        """Search Google Books API for book information."""
        query_parts = [title]
        if author and author.lower() != 'unknown':
            query_parts.append(author)
        
        query = ' '.join(query_parts)
        params = {'q': query, 'maxResults': 1}
        
        try:
            response = requests.get(GOOGLE_BOOKS_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'items' not in data or len(data['items']) == 0:
                return None
            
            book_data = data['items'][0]['volumeInfo']
            
            enriched_data = {
                'date_published': book_data.get('publishedDate', 'Unknown'),
                'publisher': book_data.get('publisher', 'Unknown'),
                'page_count': book_data.get('pageCount'),
            }
            
            if 'industryIdentifiers' in book_data:
                for identifier in book_data['industryIdentifiers']:
                    if identifier['type'] in ['ISBN_13', 'ISBN_10']:
                        enriched_data['isbn'] = identifier['identifier']
                        break
            
            if 'categories' in book_data and book_data['categories']:
                all_categories = book_data['categories']
                enriched_data['genre'] = all_categories[0]
                enriched_data['genres'] = ', '.join(all_categories)
            
            description = None
            if 'description' in book_data and book_data['description']:
                description = book_data['description']
            elif 'textSnippet' in book_data and book_data['textSnippet']:
                description = book_data['textSnippet']
            
            if description:
                enriched_data['summary'] = description
                print(f"  [+] Found summary ({len(description)} chars)")
            else:
                print(f"  [!] No summary available from Google Books")
            
            return enriched_data
            
        except Exception as e:
            print(f"  Note: Could not fetch Google Books data: {e}")
            return None
    
    def enrich_book_data(self, book_info: Dict, use_goodreads: bool = True) -> Dict:
        """Enrich book data with additional information."""
        title = book_info.get('title', '')
        author = book_info.get('author', '')
        
        if use_goodreads:
            print("  -> Fetching from Goodreads...")
            goodreads_data = self.goodreads.search_goodreads(title, author)
            if goodreads_data:
                for key, value in goodreads_data.items():
                    if value and value not in ['Unknown', 'None', '']:
                        book_info[key] = value
                
                if goodreads_data.get('goodreads_score'):
                    print(f"  [+] Goodreads rating: {goodreads_data['goodreads_score']}/5")
        
        missing_data = (
            not book_info.get('summary') or 
            not book_info.get('genres') or 
            not book_info.get('date_published')
        )
        
        if missing_data:
            print("  -> Filling gaps with Google Books...")
            enriched = self.search_google_books(title, author)
            
            if enriched:
                for key, value in enriched.items():
                    if key not in book_info or book_info[key] in [None, 'Unknown', '']:
                        book_info[key] = value
        
        if author and author != 'Unknown':
            print("  -> Identifying major awards...")
            date_pub = book_info.get('date_published', 'Unknown')
            awards = self.identify_major_awards(title, author, date_pub)
            if awards:
                book_info['major_awards'] = awards
        
        defaults = {
            'date_published': 'Unknown',
            'part_of_series': 'No',
            'series_number': None,
            'major_awards': 'None',
            'publisher': 'Unknown',
            'goodreads_score': None,
            'is_read': False,
            'genre': 'Unknown',
            'genres': 'Unknown',
            'summary': 'No summary available'
        }
        
        for key, default_value in defaults.items():
            if key not in book_info or book_info[key] in [None, '']:
                book_info[key] = default_value
        
        return book_info

# ============================================================================
# CLI FUNCTIONS
# ============================================================================

def add_book(image_path: str, db: DatabaseManager, use_goodreads: bool = True, added_by: str = None):
    """Add a book from an image."""
    print(f"\nProcessing: {Path(image_path).name}")
    print("=" * 60)
    
    print("-> Analyzing image with AI...")
    processor = ImageProcessor()
    book_info = processor.extract_book_info(image_path)
    
    if not book_info:
        print("[X] Failed to extract book information")
        return False
    
    print(f"[+] Found: {book_info.get('title', 'Unknown')}")
    print(f"  Author: {book_info.get('author', 'Unknown')}")
    if book_info.get('part_of_series') != 'No':
        series_info = book_info.get('part_of_series')
        if book_info.get('series_number'):
            series_info += f" #{book_info.get('series_number')}"
        print(f"  Series: {series_info}")
    
    print("-> Enriching data...")
    enricher = BookEnricher()
    enriched_data = enricher.enrich_book_data(book_info, use_goodreads)
    
    if enriched_data.get('genres') and enriched_data['genres'] != 'Unknown':
        print(f"  Genres: {enriched_data['genres']}")
    if enriched_data.get('summary') and enriched_data['summary'] != 'No summary available':
        summary_preview = enriched_data['summary'][:100] + "..." if len(enriched_data['summary']) > 100 else enriched_data['summary']
        print(f"  Summary: {summary_preview}")
    
    if added_by:
        enriched_data['added_by'] = added_by
    else:
        enriched_data['added_by'] = os.getenv('USER') or os.getenv('USERNAME') or 'Unknown'
    
    print("-> Saving to database...")
    book = db.add_book(enriched_data)
    
    print(f"\n[+] Book #{book.id} added successfully!")
    print(f"  Added by: {book.added_by}")
    print("-" * 60)
    return True

def batch_add(folder_path: str, db: DatabaseManager, use_goodreads: bool = True, added_by: str = None):
    """Add multiple books from a folder of images."""
    folder = Path(folder_path)
    
    if not folder.exists() or not folder.is_dir():
        print(f"Error: {folder_path} is not a valid directory")
        return
    
    image_files = []
    for ext in SUPPORTED_IMAGE_FORMATS:
        image_files.extend(folder.glob(f"*{ext}"))
        image_files.extend(folder.glob(f"*{ext.upper()}"))
    
    if not image_files:
        print(f"No image files found in {folder_path}")
        return
    
    print(f"\nFound {len(image_files)} image(s) to process")
    print("=" * 60)
    
    successful = 0
    failed = 0
    
    for i, image_path in enumerate(image_files, 1):
        print(f"\n[{i}/{len(image_files)}]")
        if add_book(str(image_path), db, use_goodreads, added_by):
            successful += 1
        else:
            failed += 1
        
        if use_goodreads and i < len(image_files):
            time.sleep(2)
    
    print("\n" + "=" * 60)
    print(f"Batch complete: {successful} successful, {failed} failed")

def list_books(db: DatabaseManager, filters: dict = None):
    """List all books in the database."""
    books = db.get_all_books(filters)
    
    if not books:
        print("No books found matching your filters.")
        return
    
    headers = ["ID", "Title", "Author", "Genres", "Rating", "Added By", "Status"]
    rows = []
    
    for book in books:
        genres_display = book.genres or book.genre or "-"
        if len(genres_display) > 30:
            genres_display = genres_display[:27] + "..."
        
        status = "[+] Read" if book.is_read else "Unread"
        if book.is_read and book.read_by:
            status += f" ({book.read_by})"
        
        rows.append([
            book.id,
            book.title[:35] + "..." if len(book.title) > 35 else book.title,
            book.author[:25] + "..." if len(book.author) > 25 else book.author,
            genres_display,
            f"{book.goodreads_score}/5" if book.goodreads_score else "-",
            book.added_by or "-",
            status
        ])
    
    print(f"\n{len(books)} book(s) in your library:\n")
    print(tabulate(rows, headers=headers, tablefmt="grid"))

def mark_read(book_id: int, db: DatabaseManager, read_by: str = None):
    """Mark a book as read."""
    if not read_by:
        read_by = os.getenv('USER') or os.getenv('USERNAME') or 'Unknown'
    
    book = db.mark_as_read(book_id, read_by)
    if book:
        print(f"[+] '{book.title}' marked as read by {read_by}")
    else:
        print(f"[X] Book #{book_id} not found")

def mark_unread(book_id: int, db: DatabaseManager):
    """Mark a book as unread."""
    book = db.mark_as_unread(book_id)
    if book:
        print(f"[+] '{book.title}' marked as unread")
    else:
        print(f"[X] Book #{book_id} not found")

def delete_book_cli(book_id: int, db: DatabaseManager):
    """Delete a book from CLI."""
    book = db.get_book_by_id(book_id)
    if not book:
        print(f"[X] Book #{book_id} not found")
        return
    
    confirm = input(f"Are you sure you want to delete '{book.title}'? (yes/no): ")
    if confirm.lower() in ['yes', 'y']:
        if db.delete_book(book_id):
            print(f"[+] '{book.title}' deleted successfully")
        else:
            print(f"[X] Failed to delete book")
    else:
        print("Deletion cancelled")

def search_books(query: str, db: DatabaseManager):
    """Search for books."""
    books = db.search_books(query)
    
    if not books:
        print(f"No books found matching '{query}'")
        return
    
    print(f"\nFound {len(books)} book(s) matching '{query}':\n")
    
    for book in books:
        print(f"ID: {book.id}")
        print(f"Title: {book.title}")
        print(f"Author: {book.author}")
        if book.part_of_series and book.part_of_series not in ['No', 'Unknown']:
            series_info = book.part_of_series
            if book.series_number:
                series_info += f" (Book {book.series_number})"
            print(f"Series: {series_info}")
        print(f"Genre: {book.genres or book.genre}")
        print(f"Published: {book.date_published}")
        print(f"Rating: {book.goodreads_score}/5" if book.goodreads_score else "Rating: N/A")
        print(f"Added by: {book.added_by}")
        if book.is_read:
            print(f"Status: [+] Read by {book.read_by} on {book.read_date.strftime('%Y-%m-%d')}")
        else:
            print(f"Status: Unread")
        if book.goodreads_url:
            print(f"Goodreads: {book.goodreads_url}")
        if book.summary:
            print(f"Summary: {book.summary[:200]}..." if len(book.summary) > 200 else f"Summary: {book.summary}")
        print("-" * 80)

def export_books(filepath: str, db: DatabaseManager):
    """Export books to CSV."""
    print(f"Exporting books to {filepath}...")
    result = db.export_to_csv(filepath)
    print(f"[+] Exported successfully to {result}")

def show_stats(db: DatabaseManager):
    """Show database statistics."""
    stats = db.get_stats()
    print("\nLibrary Statistics:")
    print("=" * 40)
    print(f"  Total Books: {stats['total_books']}")
    print(f"  Read: {stats['read_books']}")
    print(f"  Unread: {stats['unread_books']}")
    print(f"  Unique Genres: {stats['unique_genres']}")
    print(f"  Series: {stats['series_count']}")
    if stats['average_rating']:
        print(f"  Average Rating: {stats['average_rating']}/5")
    
    if stats['users_added']:
        print(f"\nUsers who added books: {', '.join(stats['users_added'])}")
    if stats['users_read']:
        print(f"Users who read books: {', '.join(stats['users_read'])}")
    print("=" * 40)

# ============================================================================
# MAIN CLI
# ============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Book Tracker - AI-powered reading list manager"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    add_parser = subparsers.add_parser('add', help='Add a book from an image')
    add_parser.add_argument('image', help='Path to book cover image')
    add_parser.add_argument('--no-goodreads', action='store_true', help='Skip Goodreads lookup')
    add_parser.add_argument('--added-by', help='Name of person adding the book')
    
    batch_parser = subparsers.add_parser('batch', help='Add multiple books from a folder')
    batch_parser.add_argument('folder', help='Path to folder containing book cover images')
    batch_parser.add_argument('--no-goodreads', action='store_true', help='Skip Goodreads lookup')
    batch_parser.add_argument('--added-by', help='Name of person adding the books')
    
    list_parser = subparsers.add_parser('list', help='List all books')
    list_parser.add_argument('--added-by', help='Filter by user who added')
    list_parser.add_argument('--read-by', help='Filter by user who read')
    list_parser.add_argument('--unread', action='store_true', help='Show only unread books')
    list_parser.add_argument('--genre', help='Filter by genre')
    
    read_parser = subparsers.add_parser('read', help='Mark a book as read')
    read_parser.add_argument('book_id', type=int, help='Book ID')
    read_parser.add_argument('--read-by', help='Name of person who read it')
    
    unread_parser = subparsers.add_parser('unread', help='Mark a book as unread')
    unread_parser.add_argument('book_id', type=int, help='Book ID')
    
    delete_parser = subparsers.add_parser('delete', help='Delete a book')
    delete_parser.add_argument('book_id', type=int, help='Book ID')
    
    search_parser = subparsers.add_parser('search', help='Search for books')
    search_parser.add_argument('query', help='Search query')
    
    export_parser = subparsers.add_parser('export', help='Export books to CSV')
    export_parser.add_argument('filepath', help='Output CSV file path')
    
    subparsers.add_parser('stats', help='Show library statistics')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    db = DatabaseManager()
    
    if args.command == 'add':
        add_book(args.image, db, not args.no_goodreads, args.added_by)
    
    elif args.command == 'batch':
        batch_add(args.folder, db, not args.no_goodreads, args.added_by)
    
    elif args.command == 'list':
        filters = {}
        if args.added_by:
            filters['added_by'] = args.added_by
        if args.read_by:
            filters['read_by'] = args.read_by
        if args.unread:
            filters['is_read'] = False
        if args.genre:
            filters['genre'] = args.genre
        list_books(db, filters if filters else None)
    
    elif args.command == 'read':
        mark_read(args.book_id, db, args.read_by)
    
    elif args.command == 'unread':
        mark_unread(args.book_id, db)
    
    elif args.command == 'delete':
        delete_book_cli(args.book_id, db)
    
    elif args.command == 'search':
        search_books(args.query, db)
    
    elif args.command == 'export':
        export_books(args.filepath, db)
    
    elif args.command == 'stats':
        show_stats(db)

if __name__ == '__main__':
    main()
