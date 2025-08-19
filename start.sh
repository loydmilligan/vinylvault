#!/bin/bash
# VinylVault development start script

echo "Starting VinylVault development server..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Check if dependencies are installed
python3 -c "import flask" 2>/dev/null || {
    echo "Dependencies not found. Installing..."
    pip install -r requirements.txt
}

# Set development environment
export FLASK_ENV=development
export FLASK_DEBUG=1

# Start the application
python3 run.py