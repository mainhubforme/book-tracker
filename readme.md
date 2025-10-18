# Book Tracker

AI-powered book tracking system that extracts book information from images and maintains a structured database of your reading list.

## Features

✅ **Phase 2 - Current Implementation:**
- Extract book information from cover images using Claude Vision API
- Automatic data enrichment from Google Books API
- SQLite database with full CRUD operations
- CLI interface for easy management
- Export to CSV
- Search and filter capabilities
- Database statistics

🔜 **Phase 3 - Planned Features:**
- Goodreads rating integration (web scraping)
- Literary awards database integration
- Series detection (automatic identification of book series)
- Enhanced OCR for physical book spines
- Duplicate detection
- Reading progress tracking
- Book recommendations

## Architecture

Modular design with clear separation of concerns:

```
src/
├── models.py          # Database schema (SQLAlchemy ORM)
├── database.py        # Database operations layer
├── image_processor.py # Claude Vision API integration
├── book_enricher.py   # External API data enrichment
├── config.py          # Configuration management
└── main.py           # CLI interface
```

## Installation

1. **Create project directory:**
```bash
cd /pprojects
mkdir book-tracker
cd book-tracker
```

2. **Create virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Create directory structure:**
```bash
mkdir src data
touch src/__init__.py
```

4. **Install dependencies:**
```bash
pip install -r requirements.txt
```

5. **Configure API key:**

Create a `.env` file in the project root:
```bash
ANTHROPIC_API_KEY=your_api_key_here
```

Get your API key from: https://console.anthropic.com/

## Usage

### Add a book from an image
```bash
python src/main.py add /path/to/book-cover.jpg
```

### List all books
```bash
python src/main.py list
```

### Search for books
```bash
python src/main.py search "tolkien"
python src/main.py search "science fiction"
```

### Export to CSV
```bash
python src/main.py export my_books.csv
```

### View statistics
```bash
python src/main.py stats
```

## Database Schema

```sql
books (
    id INTEGER PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    author VARCHAR(300) NOT NULL,
    genre VARCHAR(200),
    summary TEXT,
    date_published VARCHAR(50),
    date_entered DATETIME,
    part_of_series VARCHAR(200),
    goodreads_score FLOAT,
    major_awards TEXT,
    image_path VARCHAR(500),
    isbn VARCHAR(20),
    page_count INTEGER,
    publisher VARCHAR(300)
)
```

## Migration Path

### Phase 3 Enhancement Plan:

1. **Goodreads Integration**
   - Implement web scraping module
   - Add rate limiting and caching
   - Update database with accurate ratings

2. **Awards Database**
   - Create awards lookup table
   - Integrate major literary awards (Pulitzer, Hugo, Nebula, Man Booker, etc.)
   - Automatic award detection

3. **Series Detection**
   - Enhance AI prompts for series identification
   - Create series relationship table
   - Track reading order

4. **Advanced Features**
   - Duplicate detection (fuzzy matching)
   - Reading status (to-read, reading, completed)
   - Personal notes and tags
   - Reading statistics and insights

### Phase 4 Production Ready:

- PostgreSQL migration
- Web interface (Flask/FastAPI)
- User authentication
- Cloud deployment (AWS/Heroku)
- Mobile app
- API endpoints

## Development

### Running Tests
```bash
# Coming in Phase 3
pytest tests/
```

### Adding New Data Sources

To add a new data enrichment source:

1. Create new method in `BookEnricher` class
2. Add API configuration to `config.py`
3. Update `enrich_book_data()` to call new method
4. Update database model if new fields needed

### Database Migrations

Currently using SQLAlchemy's `create_all()` for schema management. For production:

```bash
# Phase 4: Use Alembic for migrations
alembic init alembic
alembic revision --autogenerate -m "migration message"
alembic upgrade head
```

## Troubleshooting

### API Key Issues
```bash
# Verify .env file exists and contains key
cat .env

# Test API key
python -c "from src.config import validate_config; validate_config()"
```

### Image Processing Errors
- Ensure image is < 5MB
- Supported formats: .jpg, .jpeg, .png, .webp
- Image should clearly show book title and author

### Database Issues
```bash
# Reset database (WARNING: deletes all data)
rm data/books.db
python src/main.py list  # Creates new database
```

## Contributing

This is a personal project, but the modular architecture makes it easy to extend:

1. Each module is independent
2. Clear interfaces between components
3. Easy to swap implementations (e.g., database backend)
4. Add new features without modifying existing code

## License

Personal project - use freely for your own book tracking needs!

## Acknowledgments

- Claude AI by Anthropic for vision capabilities
- Google Books API for book metadata
- SQLAlchemy for database ORM