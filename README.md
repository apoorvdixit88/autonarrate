# AutoNarrate

Transform any screen recording or product demo into an engaging, professionally narrated video - automatically.

## What It Does

1. **Upload a video** - Any screen recording, product demo, or tutorial
2. **AI analyzes each scene** - Detects scene changes, reads on-screen text (OCR), understands what's happening
3. **Generates narration** - Creates natural, flowing voiceover script
4. **Synthesizes speech** - Converts script to high-quality voice using Edge TTS
5. **Renders final video** - Combines everything with smart freeze-frames when narration is longer than the video segment

## Features

- **🤖 Claude Code Integration** - Uses your local Claude CLI for vision analysis (no API keys needed!)
- **Ollama Support** - Or use Ollama for fully local, free processing
- **Smart Scene Detection** - Automatically segments video based on visual changes
- **Multiple Voice Options** - Choose from various natural-sounding voices
- **Freeze Frame Support** - Video pauses on last frame when narration extends beyond segment
- **Live Preview** - Preview narration with video before rendering
- **Edit & Customize** - Modify narration text, regenerate specific segments
- **No Audio Cutoff** - Narration always plays completely, video adapts

## Screenshots

<p align="center">
  <img src="screenshots/upload.png" width="700" alt="Upload Page">
  <br><em>Upload your video and select a voice</em>
</p>

<p align="center">
  <img src="screenshots/processing.png" width="700" alt="Processing Pipeline">
  <br><em>AI analyzes your video and generates narration</em>
</p>

<p align="center">
  <img src="screenshots/editor.png" width="700" alt="Editor">
  <br><em>Edit narration, preview with video, and render</em>
</p>

## Quick Start

### Option 1: Automated Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/apoorvdixit88/autonarrate.git
cd autonarrate

# Run setup script
chmod +x setup.sh
./setup.sh
```

### Option 2: Manual Setup

#### Prerequisites

1. **Python 3.10+**
   ```bash
   python3 --version  # Should be 3.10 or higher
   ```

2. **FFmpeg** (required for video processing)
   ```bash
   # macOS
   brew install ffmpeg

   # Ubuntu/Debian
   sudo apt update && sudo apt install ffmpeg

   # Windows (using chocolatey)
   choco install ffmpeg
   ```

3. **Claude Code CLI** (for AI narration) - Choose one:

   **Option A: Claude Code (Recommended)**
   ```bash
   # Install Claude Code CLI
   npm install -g @anthropic-ai/claude-code

   # Verify installation
   claude --version
   ```

   **Option B: Ollama (Free, Local)**
   ```bash
   # Install Ollama
   curl -fsSL https://ollama.com/install.sh | sh

   # Pull a vision model
   ollama pull llama3.2-vision
   ```

#### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env

# Edit .env if needed (optional)
nano .env
```

#### Run the Server

```bash
# Activate virtual environment (if not already)
source venv/bin/activate

# Start the server
python run.py
```

Open http://localhost:3005 in your browser.

## Configuration

Edit `.env` to customize:

```env
# Server settings
HOST=0.0.0.0
PORT=3005
DEBUG=true

# Vision backend: "claude_code" or "ollama"
VISION_BACKEND=claude_code

# Ollama settings (if using ollama backend)
OLLAMA_MODEL=llama3.2-vision
OLLAMA_HOST=http://localhost:11434

# Default TTS voice
TTS_VOICE=en-US-EmmaNeural

# Paths
PROJECTS_DIR=./projects
CLAUDE_CODE_PATH=claude
```

## Usage

### 1. Upload Video

- Go to http://localhost:3005
- Upload your video (MP4, MOV, MKV, WebM, AVI supported)
- Optionally add context about your product/video

### 2. Wait for Processing

The pipeline will:
- Detect scenes and segment the video
- Extract key frames from each segment
- Analyze frames with AI (OCR + visual understanding)
- Generate narration script
- Synthesize voiceover audio

### 3. Edit & Preview

- Click on a segment to edit narration
- Use "Preview" to hear individual segments
- Use "Preview All" to watch full video with narration
- Adjust voice from the dropdown

### 4. Render & Download

- Click "Render Video" to create final output
- Download your narrated video

## Available Voices

| Voice | Accent | Style |
|-------|--------|-------|
| Emma | US | Friendly, conversational |
| Libby | UK | Professional, clear |
| Jenny | US | Warm, engaging |
| Guy | US | Authoritative, calm |
| Ryan | UK | Professional, neutral |
| Christopher | US | Clear, instructional |

## How Freeze Frames Work

When narration is longer than a video segment:

1. Video plays normally until segment end
2. **Video freezes** on the last frame
3. Narration continues playing
4. When narration finishes, video resumes
5. Next segment begins

This ensures narration is never cut off mid-sentence.

## Project Structure

```
autonarrate/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration settings
│   ├── models.py            # Data models
│   ├── pipeline.py          # Processing pipeline
│   ├── services/
│   │   ├── video_service.py     # Video ingestion
│   │   ├── vision_service.py    # AI frame analysis
│   │   ├── narration_service.py # Script generation
│   │   ├── tts_service.py       # Text-to-speech
│   │   └── audio_service.py     # Audio processing
│   └── utils/
│       ├── ffmpeg.py        # FFmpeg operations
│       └── logger.py        # Logging
├── static/
│   ├── index.html           # Upload page
│   └── editor.html          # Video editor
├── projects/                # Generated project files
├── requirements.txt
├── setup.sh                 # Automated setup script
├── run.py                   # Server entry point
└── .env.example
```

## Troubleshooting

### FFmpeg not found
```bash
# Verify FFmpeg is installed
ffmpeg -version

# If not found, install it (see Prerequisites)
```

### Claude Code not working
```bash
# Check if Claude Code is installed
claude --version

# If using Ollama instead, update .env:
VISION_BACKEND=ollama
```

### Port already in use
```bash
# Change port in .env
PORT=3006
```

### Video processing fails
- Ensure video is a supported format (MP4 recommended)
- Check FFmpeg is properly installed
- Look at terminal logs for specific errors

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - feel free to use for personal or commercial projects.

---

Built with Claude Code
