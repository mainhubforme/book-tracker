#!/usr/bin/env python3
"""
Book Tracker - AI-powered reading list manager
Enhanced with read tracking and better data sources
"""

import os
import sys
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
from openai import OpenAI
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, or_
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from tabulate import tabulate
import pandas as pd
# ============= ADD THIS ENTIRE SECTION =============
# Remove ALL proxy-related environment variables
proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 
              'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy']
for var in proxy_vars:
    os.environ.pop(var, None)

# Monkey-patch OpenAI to ignore proxy arguments
_original_openai_init = OpenAI.__init__

def _patched_openai_init(self, **kwargs):
    # Remove any proxy-related kwargs
    kwargs.pop('proxies', None)
    kwargs.pop('proxy', None)
    kwargs.pop('http_client', None)
    return _original_openai_init(self, **kwargs)

OpenAI.__init__ = _patched_openai_init
# ============= END OF ADDITION =============
# CONFIGURATION
# ============================================================================

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "books.db"
DATA_DIR.mkdir(exist_ok=True)

# API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"
GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"

# Database
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Processing
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
SUPPORTED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

# ============================================================================
# DATABASE MODELS
# ============================================================================

Base = declarative_base()

class Book(Base):
    """Book model representing a book in the reading list."""
    
    __tablename__ = 'books'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    author = Column(String(300), nullable=False)
    genre = Column(String(200))
    genres = Column(Text)
    summary = Column(Text)
    date_published = Column(String(50))
    date_entered = Column(DateTime, default=datetime.utcnow)
    part_of_series = Column(String(200))
    series_number = Column(String(50))
    goodreads_score = Column(Float)
    major_awards = Column(Text)
    image_path = Column(String(500))
    isbn = Column(String(20))
    page_count = Column(Integer)
    publisher = Column(String(300))
    goodreads_url = Column(String(500))
    added_by = Column(String(100))
    is_read = Column(Boolean, default=False)
    read_date = Column(DateTime, nullable=True)
    read_by = Column(String(100), nullable=True)
    
    def __repr__(self):
        return f"<Book(title='{self.title}', author='{self.author}')>"
    
    def to_dict(self):
        """Convert book object to dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'author': self.author,
            'genre': self.genre,
            'genres': self.genres,
            'summary': self.summary,
            'date_published': self.date_published,
            'date_entered': self.date_entered.strftime('%Y-%m-%d') if self.date_entered else None,
            'part_of_series': self.part_of_series,
            'series_number': self.series_number,
            'goodreads_score': self.goodreads_score,
            'major_awards': self.major_awards,
            'isbn': self.isbn,
            'page_count': self.page_count,
            'publisher': self.publisher,
            'goodreads_url': self.goodreads_url,
            'image_path': self.image_path,
            'added_by': self.added_by,
            'is_read': self.is_read,
            'read_date': self.read_date.strftime('%Y-%m-%d') if self.read_date else None,
            'read_by': self.read_by
        }

# ============================================================================
# DATABASE MANAGER
# ============================================================================

class DatabaseManager:
    """Manages all database operations."""
    
    def __init__(self, database_url: str = DATABASE_URL):
        """Initialize database connection and create tables."""
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()
    
    def add_book(self, book_data: dict) -> Book:
        """Add a new book to the database."""
        session = self.get_session()
        try:
            book = Book(**book_data)
            session.add(book)
            session.commit()
            session.refresh(book)
            return book
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def update_book(self, book_id: int, updates: dict) -> Optional[Book]:
        """Update a book's information."""
        session = self.get_session()
        try:
            book = session.query(Book).filter(Book.id == book_id).first()
            if book:
                for key, value in updates.items():
                    setattr(book, key, value)
                session.commit()
                session.refresh(book)
                return book
            return None
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def mark_as_read(self, book_id: int, read_by: str) -> Optional[Book]:
        """Mark a book as read."""
        return self.update_book(book_id, {
            'is_read': True,
            'read_date': datetime.utcnow(),
            'read_by': read_by
        })
    
    def mark_as_unread(self, book_id: int) -> Optional[Book]:
        """Mark a book as unread."""
        return self.update_book(book_id, {
            'is_read': False,
            'read_date': None,
            'read_by': None
        })
    
    def delete_book(self, book_id: int) -> bool:
        """Delete a book from the database."""
        session = self.get_session()
        try:
            book = session.query(Book).filter(Book.id == book_id).first()
            if book:
                # Optionally delete the image file
                if book.image_path and Path(book.image_path).exists():
                    try:
                        Path(book.image_path).unlink()
                    except Exception as e:
                        print(f"Warning: Could not delete image file: {e}")
                
                session.delete(book)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def get_all_books(self, filters: dict = None) -> List[Book]:
        """Retrieve all books from the database with optional filters."""
        session = self.get_session()
        try:
            query = session.query(Book)
            
            if filters:
                if 'added_by' in filters:
                    query = query.filter(Book.added_by == filters['added_by'])
                if 'read_by' in filters:
                    query = query.filter(Book.read_by == filters['read_by'])
                if 'is_read' in filters:
                    query = query.filter(Book.is_read == filters['is_read'])
                if 'genre' in filters:
                    query = query.filter(or_(
                        Book.genre.ilike(f"%{filters['genre']}%"),
                        Book.genres.ilike(f"%{filters['genre']}%")
                    ))
                if 'year' in filters:
                    query = query.filter(Book.date_published.like(f"{filters['year']}%"))
            
            return query.order_by(Book.date_entered.desc()).all()
        finally:
            session.close()
    
    def get_book_by_id(self, book_id: int) -> Optional[Book]:
        """Get a book by its ID."""
        session = self.get_session()
        try:
            return session.query(Book).filter(Book.id == book_id).first()
        finally:
            session.close()
    
    def search_books(self, query: str) -> List[Book]:
        """Search books by title, author, genre, or person."""
        session = self.get_session()
        try:
            search_pattern = f"%{query}%"
            return session.query(Book).filter(
                or_(
                    Book.title.ilike(search_pattern),
                    Book.author.ilike(search_pattern),
                    Book.genre.ilike(search_pattern),
                    Book.genres.ilike(search_pattern),
                    Book.part_of_series.ilike(search_pattern),
                    Book.added_by.ilike(search_pattern),
                    Book.read_by.ilike(search_pattern)
                )
            ).all()
        finally:
            session.close()
    
    def export_to_csv(self, filepath: str):
        """Export all books to a CSV file."""
        books = self.get_all_books()
        books_data = [book.to_dict() for book in books]
        df = pd.DataFrame(books_data)
        df.to_csv(filepath, index=False)
        return filepath
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        session = self.get_session()
        try:
            total_books = session.query(Book).count()
            read_books = session.query(Book).filter(Book.is_read == True).count()
            genres = session.query(Book.genre).distinct().all()
            series_count = session.query(Book.part_of_series).filter(
                Book.part_of_series.isnot(None),
                Book.part_of_series != 'Unknown',
                Book.part_of_series != 'No'
            ).distinct().count()
            
            avg_rating = session.query(Book.goodreads_score).filter(
                Book.goodreads_score.isnot(None)
            ).all()
            
            avg_rating_value = None
            if avg_rating:
                valid_ratings = [r[0] for r in avg_rating if r[0] is not None]
                if valid_ratings:
                    avg_rating_value = sum(valid_ratings) / len(valid_ratings)
            
            users_added = session.query(Book.added_by).distinct().all()
            users_read = session.query(Book.read_by).filter(Book.read_by.isnot(None)).distinct().all()
            
            return {
                'total_books': total_books,
                'read_books': read_books,
                'unread_books': total_books - read_books,
                'unique_genres': len([g[0] for g in genres if g[0] and g[0] != 'Unknown']),
                'series_count': series_count,
                'average_rating': round(avg_rating_value, 2) if avg_rating_value else None,
                'users_added': [u[0] for u in users_added if u[0]],
                'users_read': [u[0] for u in users_read if u[0]]
            }
        finally:
            session.close()
    
    def get_user_stats(self, username: str) -> dict:
        """Get statistics for a specific user."""
        session = self.get_session()
        try:
            added_count = session.query(Book).filter(Book.added_by == username).count()
            read_count = session.query(Book).filter(Book.read_by == username).count()
            
            return {
                'username': username,
                'books_added': added_count,
                'books_read': read_count
            }
        finally:
            session.close()

# ============================================================================
# IMAGE PROCESSOR
# ============================================================================

class ImageProcessor:
    """Handles image processing and book information extraction."""
    def __init__(self):
        """Initialize the OpenAI client."""
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found. Please set it in your .env file")
        self.client = OpenAI(api_key=OPENAI_API_KEY)    
    
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
                max_completion_tokens=500
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
        """
        Search Goodreads for book metadata including rating, summary, and sub-genres.
        IMPROVED: Filters out study guides, summaries, and analyses to find the actual book.
        """
        try:
            self._rate_limit()

            query = f"{title} {author}" if author else title
            search_url = f"https://www.goodreads.com/search?q={quote(query)}"

            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Find ALL book title links, not just the first
            book_links = soup.find_all("a", class_="bookTitle", limit=10)
            
            if not book_links:
                print("  [!] No books found in search results")
                return None

            # IMPROVED: Filter out study guides, summaries, analyses
            skip_keywords = [
                'study guide',
                'book analysis',
                'summary',
                'sparknotes',
                'cliffsnotes',
                'reader\'s guide',
                'companion',
                'critical analysis',
                'detailed summary',
                'litcharts'
            ]
            
            selected_link = None
            for link in book_links:
                link_text = link.get_text(strip=True).lower()
                link_title = link.get('title', '').lower() if link.get('title') else ''
                combined_text = f"{link_text} {link_title}"
                
                # Skip if it looks like a study guide
                if any(keyword in combined_text for keyword in skip_keywords):
                    print(f"  [~] Skipping: {link.get_text(strip=True)[:60]}...")
                    continue
                
                # This looks like the actual book
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

            # --- Extract rating ---
            rating_elem = book_soup.find("div", class_="RatingStatistics__rating")
            if rating_elem:
                try:
                    result["goodreads_score"] = float(rating_elem.text.strip())
                except ValueError:
                    pass

            # --- Extract summary ---
            summary = None
            desc_section = (
                book_soup.find("div", class_="DetailsLayoutRightParagraph")
                or book_soup.find("div", {"data-testid": "description"})
                or book_soup.find("span", {"data-testid": "contentReview"})
            )

            if desc_section:
                text_block = desc_section.get_text(separator=" ", strip=True)
                if text_block and len(text_block) > 40:
                    # Get first sentence
                    summary = re.split(r"(?<=[.!?])\s+", text_block)[0]
            
            if not summary:
                meta = book_soup.find("meta", {"property": "og:description"})
                if meta and meta.get("content"):
                    summary = meta["content"].split(".")[0] + "."

            if summary:
                result["summary"] = summary.strip()

            # --- Extract sub-genres with MULTIPLE STRATEGIES ---
            genres = []
            
            # Strategy 1: data-testid approach (most current)
            genre_labels = book_soup.find_all("span", {"data-testid": "genreActionLabel"})
            for label in genre_labels[:10]:
                genre_text = label.get_text(strip=True)
                if genre_text and 2 < len(genre_text) < 50:
                    genres.append(genre_text)
            
            # Strategy 2: BookPageMetadataSection with Button labels
            if not genres:
                genre_section = book_soup.find("div", class_="BookPageMetadataSection__genres")
                if genre_section:
                    buttons = genre_section.find_all("span", class_="Button__labelItem")
                    for btn in buttons[:10]:
                        genre_text = btn.get_text(strip=True)
                        if genre_text and genre_text not in genres and 2 < len(genre_text) < 50:
                            genres.append(genre_text)
            
            # Strategy 3: Links containing '/genres/'
            if not genres:
                genre_links = book_soup.find_all("a", href=lambda x: x and "/genres/" in x, limit=15)
                for link in genre_links[:10]:
                    genre_text = link.get_text(strip=True)
                    # Clean up
                    genre_text = re.sub(r'\s*\d+\s*users?.*$', '', genre_text, flags=re.IGNORECASE)
                    genre_text = re.sub(r'\s*›.*$', '', genre_text)
                    
                    # Filter noise
                    if genre_text and genre_text not in genres and 2 < len(genre_text) < 50:
                        skip_words = ['shelf', 'to-read', 'want', 'currently', 'more genres', 'add', 'vote']
                        if not any(skip in genre_text.lower() for skip in skip_words):
                            genres.append(genre_text)
            
            # Strategy 4: Old elementList (fallback)
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

            # --- Publication date ---
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
        if OPENAI_API_KEY:
            self.client = OpenAI(api_key=OPENAI_API_KEY)
        else:
            self.client = None
    
    def identify_major_awards(self, title: str, author: str, date_published: str) -> Optional[str]:
        """Use LLM to identify if the book won any major literary awards."""
        try:
            # Use the instance client instead of creating a new one
            if not self.client:
                print("  Note: OpenAI API key not available for award identification")
                return "TBD"
            
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

            response = self.client.chat.completions.create(
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
    
    # Add book command
    add_parser = subparsers.add_parser('add', help='Add a book from an image')
    add_parser.add_argument('image', help='Path to book cover image')
    add_parser.add_argument('--no-goodreads', action='store_true', help='Skip Goodreads lookup')
    add_parser.add_argument('--added-by', help='Name of person adding the book')
    
    # Batch add command
    batch_parser = subparsers.add_parser('batch', help='Add multiple books from a folder')
    batch_parser.add_argument('folder', help='Path to folder containing book cover images')
    batch_parser.add_argument('--no-goodreads', action='store_true', help='Skip Goodreads lookup')
    batch_parser.add_argument('--added-by', help='Name of person adding the books')
    
    # List books command
    list_parser = subparsers.add_parser('list', help='List all books')
    list_parser.add_argument('--added-by', help='Filter by user who added')
    list_parser.add_argument('--read-by', help='Filter by user who read')
    list_parser.add_argument('--unread', action='store_true', help='Show only unread books')
    list_parser.add_argument('--genre', help='Filter by genre')
    
    # Mark read command
    read_parser = subparsers.add_parser('read', help='Mark a book as read')
    read_parser.add_argument('book_id', type=int, help='Book ID')
    read_parser.add_argument('--read-by', help='Name of person who read it')
    
    # Mark unread command
    unread_parser = subparsers.add_parser('unread', help='Mark a book as unread')
    unread_parser.add_argument('book_id', type=int, help='Book ID')
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete a book')
    delete_parser.add_argument('book_id', type=int, help='Book ID')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search for books')
    search_parser.add_argument('query', help='Search query')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export books to CSV')
    export_parser.add_argument('filepath', help='Output CSV file path')
    
    # Stats command
    subparsers.add_parser('stats', help='Show library statistics')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize database
    db = DatabaseManager()
    
    # Execute commands
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
