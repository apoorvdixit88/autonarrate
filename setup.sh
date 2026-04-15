#!/bin/bash

# Auto-Narrated Video Tool - Setup Script
# This script sets up the development environment

set -e  # Exit on error

echo "=========================================="
echo "  Auto-Narrated Video Tool - Setup"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check Python version
echo "Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 10 ]; then
        print_status "Python $PYTHON_VERSION found"
    else
        print_error "Python 3.10+ required, found $PYTHON_VERSION"
        exit 1
    fi
else
    print_error "Python 3 not found. Please install Python 3.10+"
    exit 1
fi

# Check FFmpeg
echo ""
echo "Checking FFmpeg..."
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n1 | awk '{print $3}')
    print_status "FFmpeg $FFMPEG_VERSION found"
else
    print_warning "FFmpeg not found. Installing..."

    # Detect OS and install FFmpeg
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install ffmpeg
            print_status "FFmpeg installed via Homebrew"
        else
            print_error "Homebrew not found. Please install FFmpeg manually:"
            echo "  brew install ffmpeg"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y ffmpeg
            print_status "FFmpeg installed via apt"
        elif command -v yum &> /dev/null; then
            sudo yum install -y ffmpeg
            print_status "FFmpeg installed via yum"
        else
            print_error "Please install FFmpeg manually"
            exit 1
        fi
    else
        print_error "Please install FFmpeg manually for your OS"
        exit 1
    fi
fi

# Check for Claude Code or Ollama
echo ""
echo "Checking AI backend..."
CLAUDE_AVAILABLE=false
OLLAMA_AVAILABLE=false

if command -v claude &> /dev/null; then
    print_status "Claude Code CLI found"
    CLAUDE_AVAILABLE=true
fi

if command -v ollama &> /dev/null; then
    print_status "Ollama found"
    OLLAMA_AVAILABLE=true
fi

if [ "$CLAUDE_AVAILABLE" = false ] && [ "$OLLAMA_AVAILABLE" = false ]; then
    print_warning "No AI backend found. You need one of:"
    echo ""
    echo "  Option 1 - Claude Code (Recommended):"
    echo "    npm install -g @anthropic-ai/claude-code"
    echo ""
    echo "  Option 2 - Ollama (Free, Local):"
    echo "    curl -fsSL https://ollama.com/install.sh | sh"
    echo "    ollama pull llama3.2-vision"
    echo ""
    read -p "Continue setup anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create virtual environment
echo ""
echo "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_status "Virtual environment created"
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate
print_status "Virtual environment activated"

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
print_status "Dependencies installed"

# Create .env file if it doesn't exist
echo ""
echo "Setting up configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env

    # Set backend based on what's available
    if [ "$CLAUDE_AVAILABLE" = true ]; then
        sed -i.bak 's/VISION_BACKEND=.*/VISION_BACKEND=claude_code/' .env 2>/dev/null || \
        sed -i '' 's/VISION_BACKEND=.*/VISION_BACKEND=claude_code/' .env
    elif [ "$OLLAMA_AVAILABLE" = true ]; then
        sed -i.bak 's/VISION_BACKEND=.*/VISION_BACKEND=ollama/' .env 2>/dev/null || \
        sed -i '' 's/VISION_BACKEND=.*/VISION_BACKEND=ollama/' .env
    fi

    rm -f .env.bak
    print_status "Configuration file created (.env)"
else
    print_status "Configuration file already exists"
fi

# Create projects directory
mkdir -p projects
print_status "Projects directory ready"

# Done!
echo ""
echo "=========================================="
echo -e "${GREEN}  Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "To start the server:"
echo ""
echo "  source venv/bin/activate"
echo "  python run.py"
echo ""
echo "Then open http://localhost:3005 in your browser"
echo ""

# Offer to start the server
read -p "Start the server now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting server..."
    python run.py
fi
