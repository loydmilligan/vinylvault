# VinylVault

A personal vinyl collection manager designed for touch-optimized browsing on Raspberry Pi devices.

## Features

- **Touch-optimized interface** - Designed for tablets and touch devices
- **Discogs integration** - Sync your collection from Discogs
- **Offline browsing** - Cached data works without internet
- **Fast search** - Quick album and artist search
- **Random discovery** - Instant random album selection
- **Collection statistics** - Detailed stats about your collection
- **Mobile-first design** - Responsive layout for all screen sizes

## Quick Start

### Using Docker (Recommended)

```bash
# Clone or extract the project
cd vinylvault

# Start with Docker Compose
docker-compose up -d

# Access at http://localhost:5000
```

### Manual Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python3 init_db.py

# Start development server
python3 run.py
```

### Quick Start Script

```bash
# Make executable and run
chmod +x start.sh
./start.sh
```

## Initial Setup

1. Open http://localhost:5000 in your browser
2. You'll be redirected to the setup page
3. Enter your Discogs username and user token
4. Click "Complete Setup"
5. Go to the Sync page to import your collection

### Getting a Discogs Token

1. Log into your Discogs account
2. Go to Settings → Developers
3. Click "Generate new token"
4. Copy the token for use in VinylVault

## Usage

### Main Collection View (`/`)
- Browse your entire vinyl collection in a grid layout
- Sort by title, artist, year, or date added
- Search albums and artists
- Touch-optimized cards for easy browsing

### Album Details (`/album/<id>`)
- View detailed album information
- See tracklist, genres, and styles
- Play count tracking
- Swipe navigation on mobile

### Random Album (`/random`)
- Instantly get a random album from your collection
- Optimized for quick discovery
- Keyboard shortcut: Press 'R'

### Statistics (`/stats`)
- Collection overview and statistics
- Top artists and decade breakdown
- Visual charts and graphs

### Sync (`/sync`)
- Manual sync with Discogs
- Import new albums and update existing ones
- Progress tracking and status updates

## API Endpoints

- `GET /api/collection` - JSON collection data
- `GET /api/album/<id>` - Individual album data
- `GET /health` - Health check for Docker

## Configuration

Edit `config.py` to customize:

- Cache settings and directories
- Image sizes and quality
- Pagination and display options
- Touch target sizes
- Rate limiting

## File Structure

```
vinylvault/
├── app.py              # Main Flask application
├── config.py           # Configuration settings
├── init_db.py          # Database initialization
├── run.py              # Startup script
├── requirements.txt    # Python dependencies
├── templates/          # HTML templates
├── static/            # Static assets (CSS, JS, images)
├── cache/             # Database and cached images
└── logs/              # Application logs
```

## Development

### Running Tests
```bash
source venv/bin/activate
python3 -c "from app import app; print('Import test passed')"
```

### Database Management
```bash
# Initialize fresh database
python3 init_db.py

# Reset database (removes all data)
rm cache/vinylvault.db
python3 init_db.py
```

## Docker Deployment

### Build and Run
```bash
# Build image
docker build -t vinylvault .

# Run container
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/cache:/app/cache \
  --name vinylvault \
  vinylvault
```

### Health Monitoring
The application includes a health check endpoint at `/health` for monitoring.

## Security Notes

- User tokens are encrypted before database storage
- Rate limiting prevents API abuse
- CSRF protection on forms
- Secure headers for XSS protection

## Troubleshooting

### Common Issues

**"No module named 'flask'"**
- Activate virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

**"Database locked" errors**
- Stop the application
- Remove cache/vinylvault.db
- Restart and re-sync

**Sync fails with API errors**
- Check your Discogs token is valid
- Verify username is correct
- Check internet connection

### Logs
Application logs are written to `vinylvault.log` and console output.

## Performance Tips

- Run on SSD storage for better database performance
- Use Docker for consistent performance
- Adjust cache settings in config.py for your storage capacity
- Consider nginx reverse proxy for production

## License

This project is for personal use. Discogs integration subject to Discogs API terms of service.