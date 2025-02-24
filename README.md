# YouTube Video Downloader

A modern YouTube video downloader with a clean GUI built using PyQt5. Download videos in various qualities and convert them to MP3.

## Features

- Download YouTube videos in multiple quality options (144p to 1080p)
- Convert videos to MP3
- Support for multiple video downloads
- Clean and modern user interface
- Progress tracking with download speed and ETA
- Option to delete video after MP3 conversion

## Requirements

- Python 3.8 or higher
- FFmpeg
- Required Python packages (install using `pip install -r requirements.txt`):
  - PyQt5
  - yt-dlp
  - ffmpeg-python

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/youtube-downloader.git
cd youtube-downloader
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Download FFmpeg:

Go to https://github.com/BtbN/FFmpeg-Builds/releases
Download ffmpeg-master-latest-win64-gpl.zip
Extract the zip file and copy the ffmpeg.exe file to the root directory of the project

## Usage

1. Run the application:

```bash
python Youtube_Dowlowder.py
```

2. Enter the YouTube video URL and select the quality you want to download

3. Click the "Download" button to start the download

4. The download will start and the progress will be displayed in the GUI
