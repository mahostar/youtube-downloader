import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, 
                            QTextEdit, QProgressBar, QFileDialog, QMessageBox, 
                            QScrollBar, QFrame, QGroupBox, QMenu, QComboBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap
from queue import Queue
from yt_dlp import YoutubeDL
import threading
import os
import ffmpeg

class DownloadThread(QThread):
    progress_signal = pyqtSignal(tuple)
    
    def __init__(self, app, urls, save_path):
        super().__init__()
        self.app = app
        self.urls = urls
        self.save_path = save_path
        self.is_running = True
        self.ydl = None  # Add this to store YoutubeDL instance
        self.current_percentage = 0  # Add this to track progress
        self.max_total_bytes = 0     # Add this to track max file size
        
    def run(self):
        try:
            total_videos = len(self.urls)
            for index, url in enumerate(self.urls, 1):
                if not self.is_running:  # Check if we should stop
                    break
                self.progress_signal.emit(('status', f"Processing video {index} of {total_videos}"))
                self.download_video(url)
                
            if self.is_running:  # Only emit completion if we weren't stopped
                self.progress_signal.emit(('complete', f"Completed downloading {total_videos} videos!"))
        except Exception as e:
            self.progress_signal.emit(('error', str(e)))

    def stop(self):
        """Safely stop the thread"""
        self.is_running = False
        if self.ydl:  # Add this to cancel download
            self.ydl.cancel_download()

    def download_video(self, url):
        def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    # Get raw values
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                    speed = d.get('speed', 0)
                    eta = d.get('eta', 0)

                    # Update max total size if new total is larger
                    if total > self.max_total_bytes:
                        self.max_total_bytes = total

                    # Calculate percentage using max total size
                    if self.max_total_bytes > 0:
                        percentage = (downloaded / self.max_total_bytes) * 100
                    else:
                        percentage = 0

                    # Only emit progress if it's higher than current
                    if percentage > self.current_percentage:
                        self.current_percentage = percentage
                        formatted_data = {
                            'percent': f"{percentage:.1f}%",
                            'size': self.format_size(self.max_total_bytes),
                            'speed': self.format_speed(speed),
                            'eta': self.format_time(eta)
                        }
                        self.progress_signal.emit(('progress', formatted_data))

                except Exception as e:
                    print(f"Error in progress_hook: {e}")

            elif d['status'] == 'finished':
                self.progress_signal.emit(('status', 'Finalizing download...'))
                # Reset progress tracking for next video
                self.current_percentage = 0
                self.max_total_bytes = 0

        try:
            ydl_opts = {
                'outtmpl': f'{self.save_path}/%(title)s.%(ext)s',
                'format': self.get_format_string(),  # Use the selected quality
                'merge_output_format': 'mp4',
                'quiet': True,
                'progress_hooks': [progress_hook],
                'noprogress': False,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                }
            }
                
            self.ydl = YoutubeDL(ydl_opts)  # Store the YoutubeDL instance
            if not self.is_running:  # Check if stopped
                return
                
            info = self.ydl.extract_info(url, download=True)
            if not self.is_running:  # Check if stopped
                return
                
            video_path = self.ydl.prepare_filename(info)
            
            if self.app.convert_mp3_check.isChecked() and self.is_running:
                self.app.convert_to_mp3_file(video_path)
                    
        except Exception as e:
            if self.is_running:  # Only emit error if not stopped
                self.progress_signal.emit(('error', str(e)))
        finally:
            self.ydl = None  # Clear the reference

    def format_size(self, bytes_size):
        """Convert bytes to human readable format"""
        if bytes_size == 0:
            return "N/A"
        units = ['B', 'KB', 'MB', 'GB']
        size = float(bytes_size)
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"

    def format_speed(self, bytes_per_second):
        """Convert speed to human readable format"""
        if not bytes_per_second:
            return "N/A"
        return f"{self.format_size(bytes_per_second)}/s"

    def format_time(self, seconds):
        """Convert seconds to human readable time format"""
        if not seconds:
            return "N/A"
        minutes, seconds = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def get_format_string(self):
        """Get the format string based on selected quality"""
        quality = self.app.quality_combo.currentText()
        
        if quality == "Best Quality":
            return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        
        # Extract the numeric value from quality string
        height = quality.replace('p', '')
        
        return f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best'

class YouTubeDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Video Downloader")
        self.setMinimumWidth(800)
        
        # Set window icon
        try:
            self.setWindowIcon(QIcon('icon.ico'))
        except Exception as e:
            print(f"Warning: Could not load icon.ico: {e}")
        
        # Setup fonts
        self.title_font = QFont('Segoe UI', 24, QFont.Bold)
        self.header_font = QFont('Segoe UI', 14, QFont.Bold)
        self.normal_font = QFont('Segoe UI', 12)
        self.status_font = QFont('Segoe UI', 11)

        # Variables
        self.progress_queue = Queue()
        self.setup_ui()
        
        # Start progress check timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_progress_queue)
        self.timer.start(100)

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(30, 15, 30, 15)

        # Title
        title_label = QLabel("YouTube Video Downloader")
        title_label.setFont(self.title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # YouTube Logo
        try:
            logo_label = QLabel()
            logo_pixmap = QPixmap('youtube.png')
            # Scale the image to a reasonable size (e.g., 150px width)
            scaled_pixmap = logo_pixmap.scaledToWidth(150, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)
            layout.addSpacing(5)
        except Exception as e:
            print(f"Warning: Could not load youtube.png: {e}")

        # URL Section
        url_group = QGroupBox("Video URL")
        url_group.setFont(self.header_font)
        url_layout = QVBoxLayout(url_group)
        url_layout.setSpacing(5)
        url_layout.setContentsMargins(10, 10, 10, 10)

        # Multiple URLs checkbox
        self.multiple_urls_check = QCheckBox("Multiple Links")
        self.multiple_urls_check.setFont(self.normal_font)
        self.multiple_urls_check.toggled.connect(self.toggle_url_input)
        url_layout.addWidget(self.multiple_urls_check)

        # Single URL input
        self.url_input = QLineEdit()
        self.url_input.setFont(self.normal_font)
        self.url_input.setPlaceholderText("Enter YouTube URL")
        self.url_input.setContextMenuPolicy(Qt.CustomContextMenu)
        self.url_input.customContextMenuRequested.connect(self.show_context_menu)
        url_layout.addWidget(self.url_input)

        # Multiple URL input
        self.url_text = QTextEdit()
        self.url_text.setFont(self.normal_font)
        self.url_text.setPlaceholderText("Enter multiple YouTube URLs (one per line)")
        self.url_text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.url_text.customContextMenuRequested.connect(self.show_context_menu)
        self.url_text.setVisible(False)
        url_layout.addWidget(self.url_text)

        # Paste Multiple URLs button
        self.paste_multiple_btn = QPushButton("Paste Multiple URLs")
        self.paste_multiple_btn.setFont(self.normal_font)
        self.paste_multiple_btn.clicked.connect(self.paste_multiple_urls)
        self.paste_multiple_btn.setVisible(False)
        url_layout.addWidget(self.paste_multiple_btn)

        layout.addWidget(url_group)

        # Save Location Section
        save_group = QGroupBox("Save Location")
        save_group.setFont(self.header_font)
        save_layout = QHBoxLayout(save_group)
        save_layout.setContentsMargins(10, 10, 10, 10)

        self.save_path_input = QLineEdit()
        self.save_path_input.setFont(self.normal_font)
        save_layout.addWidget(self.save_path_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.setFont(self.normal_font)
        browse_btn.clicked.connect(self.choose_save_location)
        save_layout.addWidget(browse_btn)

        layout.addWidget(save_group)

        # Options Section
        options_group = QGroupBox("Download Options")
        options_group.setFont(self.header_font)
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(5)
        options_layout.setContentsMargins(10, 10, 10, 10)

        # Quality selection
        quality_frame = QHBoxLayout()
        quality_label = QLabel("Video Quality:")
        quality_label.setFont(self.normal_font)
        quality_frame.addWidget(quality_label)

        self.quality_combo = QComboBox()
        self.quality_combo.setFont(self.normal_font)
        self.quality_combo.addItems([
            "Best Quality",
            "1080p",
            "720p",
            "480p",
            "360p",
            "240p",
            "144p"
        ])
        quality_frame.addWidget(self.quality_combo)
        quality_frame.addStretch()  # Add stretch to keep combobox from expanding
        options_layout.addLayout(quality_frame)

        # Conversion options
        conversion_frame = QHBoxLayout()
        self.convert_mp3_check = QCheckBox("Convert to MP3")
        self.convert_mp3_check.setFont(self.normal_font)
        conversion_frame.addWidget(self.convert_mp3_check)

        self.delete_video_check = QCheckBox("Delete video after MP3 conversion")
        self.delete_video_check.setFont(self.normal_font)
        conversion_frame.addWidget(self.delete_video_check)
        options_layout.addLayout(conversion_frame)

        layout.addWidget(options_group)

        # Download Button
        self.download_btn = QPushButton("Download")
        self.download_btn.setFont(QFont('Segoe UI', 14, QFont.Bold))
        self.download_btn.setMinimumHeight(40)
        self.download_btn.clicked.connect(self.start_download)
        layout.addWidget(self.download_btn)

        # Progress Section
        progress_group = QGroupBox("Progress")
        progress_group.setFont(self.header_font)
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setSpacing(5)
        progress_layout.setContentsMargins(10, 10, 10, 10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFont(self.normal_font)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setFont(self.status_font)
        self.status_label.setWordWrap(True)
        progress_layout.addWidget(self.status_label)

        layout.addWidget(progress_group)

    def choose_save_location(self):
        directory = QFileDialog.getExistingDirectory(self, "Choose Save Location")
        if directory:
            self.save_path_input.setText(directory)

    def toggle_url_input(self):
        """Toggle between single and multiple URL input modes"""
        if self.multiple_urls_check.isChecked():
            # Switch to multiple URLs mode
            self.url_input.setVisible(False)
            self.url_text.setVisible(True)
            self.paste_multiple_btn.setVisible(True)
            # Transfer any existing URL to the text widget
            self.url_text.clear()
            if self.url_input.text():
                self.url_text.append(self.url_input.text())
        else:
            # Switch to single URL mode
            self.url_text.setVisible(False)
            self.paste_multiple_btn.setVisible(False)
            self.url_input.setVisible(True)
            # Transfer first URL (if any) to the entry widget
            self.url_input.setText(self.url_text.toPlainText().strip().split('\n')[0])

    def paste_multiple_urls(self):
        """Paste URLs from clipboard, one per line"""
        try:
            clipboard_text = QApplication.clipboard().text()
            # Split by newlines and filter out empty lines
            urls = [url.strip() for url in clipboard_text.split('\n') if url.strip()]
            # Add URLs to text widget
            current_urls = self.url_text.toPlainText().strip().split('\n')
            current_urls = [url for url in current_urls if url.strip()]
            # Combine existing and new URLs, remove duplicates while preserving order
            all_urls = []
            seen = set()
            for url in current_urls + urls:
                if url not in seen:
                    all_urls.append(url)
                    seen.add(url)
            # Update text widget
            self.url_text.clear()
            self.url_text.append('\n'.join(all_urls))
        except:
            pass

    def start_download(self):
        if self.multiple_urls_check.isChecked():
            urls = [url.strip() for url in self.url_text.toPlainText().split('\n') if url.strip()]
            if not urls:
                QMessageBox.warning(self, "Warning", "Please enter at least one YouTube URL.")
                return
        else:
            urls = [self.url_input.text().strip()]
            if not urls[0]:
                QMessageBox.warning(self, "Warning", "Please enter a YouTube URL.")
            return

        save_path = self.save_path_input.text()
        if not save_path:
            QMessageBox.warning(self, "Warning", "Please choose a save location.")
            return

        # Disable download button during download
        self.download_btn.setEnabled(False)

        # Reset progress and status
        self.status_label.setText("Starting downloads...")
        self.progress_bar.setValue(0)

        # Create and start new download thread
        self.download_thread = DownloadThread(self, urls, save_path)
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished.connect(self.thread_finished)
        self.download_thread.start()

    def thread_finished(self):
        """Handle thread completion"""
        if self.download_thread:
            self.download_thread.disconnect()
            self.download_thread = None
            self.download_btn.setEnabled(True)
            if self.multiple_urls_check.isChecked():
                self.status_label.setText("✅ All downloads completed successfully!")
                QMessageBox.information(self, "Success", "All videos downloaded successfully!")

    def process_download_queue(self, urls, save_path):
        """Process multiple URLs one at a time"""
        total_videos = len(urls)
        for index, url in enumerate(urls, 1):
            try:
                self.status_label.setText(f"Processing video {index} of {total_videos}")
                self.download_video(url, save_path)
                # Wait for the current download to complete
                while not self.progress_queue.empty():
                    msg_type, _ = self.progress_queue.get()
                    if msg_type in ['complete', 'error']:
                        break
            except Exception as e:
                self.progress_queue.put(('error', f"Error downloading {url}: {str(e)}"))

        # Final completion message
        self.progress_queue.put(('complete', f"Completed downloading {total_videos} videos!"))

    def convert_to_mp3_file(self, video_path):
        try:
            output_path = os.path.splitext(video_path)[0] + '.mp3'
            self.status_label.setText("Converting to MP3...")
            
            stream = ffmpeg.input(video_path)
            stream = ffmpeg.output(stream, output_path, acodec='libmp3lame', q=4)
            ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
            
            if self.delete_video_check.isChecked():
                os.remove(video_path)
                
            self.status_label.setText("MP3 conversion completed!")
            return True
        except Exception as e:
            self.status_label.setText(f"MP3 conversion failed: {str(e)}")
            return False

    def download_video(self, url, save_path):
        def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    # Get raw values instead of formatted strings
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                    speed = d.get('speed', 0)
                    eta = d.get('eta', 0)

                    # Calculate percentage
                    if total > 0:
                        percentage = (downloaded / total) * 100
                    else:
                        percentage = 0

                    # Format values in a clean way
                    formatted_data = {
                        'percent': f"{percentage:.1f}%",
                        'size': self.format_size(total),
                        'speed': self.format_speed(speed),
                        'eta': self.format_time(eta)
                    }

                    self.progress_queue.put(('progress', formatted_data))
                except Exception as e:
                    print(f"Error in progress_hook: {e}")

            elif d['status'] == 'finished':
                self.progress_queue.put(('status', 'Finalizing download...'))

        try:
            ydl_opts = {
                'outtmpl': f'{save_path}/%(title)s.%(ext)s',
                'format': self.get_format_string(),  # Use the selected quality
                'merge_output_format': 'mp4',
                'quiet': True,
                'progress_hooks': [progress_hook],
                'noprogress': False,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                }
            }
                
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_path = ydl.prepare_filename(info)
                
                if self.convert_mp3_check.isChecked():
                    if self.convert_to_mp3_file(video_path):
                        self.progress_queue.put(('complete', "Video downloaded and converted to MP3 successfully!"))
                    else:
                        self.progress_queue.put(('error', "MP3 conversion failed"))
                else:
                    self.progress_queue.put(('complete', None))
                    
        except Exception as e:
            self.progress_queue.put(('error', str(e)))

    def format_size(self, bytes_size):
        """Convert bytes to human readable format"""
        if bytes_size == 0:
            return "N/A"
        units = ['B', 'KB', 'MB', 'GB']
        size = float(bytes_size)
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"

    def format_speed(self, bytes_per_second):
        """Convert speed to human readable format"""
        if not bytes_per_second:
            return "N/A"
        return f"{self.format_size(bytes_per_second)}/s"

    def format_time(self, seconds):
        """Convert seconds to human readable time format"""
        if not seconds:
            return "N/A"
        minutes, seconds = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def check_progress_queue(self):
        while not self.progress_queue.empty():
            msg_type, msg_content = self.progress_queue.get()

            if msg_type == 'progress':
                try:
                    # Update progress bar
                    percent = float(msg_content['percent'].strip('%'))
                    self.progress_bar.setValue(percent)

                    # Create clean status message
                    status_msg = (
                        f"Downloaded: {msg_content['percent']} "
                        f"| Total Size: {msg_content['size']} "
                        f"| Speed: {msg_content['speed']} "
                        f"| Time Left: {msg_content['eta']}"
                    )
                    self.status_label.setText(status_msg)
                except ValueError:
                    pass
            elif msg_type == 'status':
                self.status_label.setText(msg_content)
            elif msg_type == 'complete':
                if msg_content:
                    self.status_label.setText(msg_content)  # Use custom completion message
                else:
                    self.status_label.setText("✅ Download completed successfully!")
                self.progress_bar.setValue(100)
                self.download_btn.setEnabled(True)
                QMessageBox.information(self, "Success", "Video downloaded successfully.")
            elif msg_type == 'error':
                self.status_label.setText(f"❌ Error: {msg_content}")
                self.progress_bar.setValue(0)
                self.download_btn.setEnabled(True)
                QMessageBox.warning(self, "Error", msg_content)

    def update_progress(self, progress_data):
        """Handle progress updates from the download thread"""
        msg_type, msg_content = progress_data
        
        if msg_type == 'progress':
            try:
                percent = float(msg_content['percent'].strip('%'))
                self.progress_bar.setValue(int(percent))
                
                status_msg = (
                    f"Downloaded: {msg_content['percent']} "
                    f"| Total Size: {msg_content['size']} "
                    f"| Speed: {msg_content['speed']} "
                    f"| Time Left: {msg_content['eta']}"
                )
                self.status_label.setText(status_msg)
            except (ValueError, KeyError) as e:
                print(f"Error updating progress: {e}")
                
        elif msg_type == 'status':
            self.status_label.setText(msg_content)
            
        elif msg_type == 'complete':
            self.status_label.setText(msg_content or "✅ Download completed successfully!")
            self.progress_bar.setValue(100)
            self.download_btn.setEnabled(True)
            if not self.multiple_urls_check.isChecked():  # Only show message box for single video
                QMessageBox.information(self, "Success", "Download completed successfully!")
            
        elif msg_type == 'error':
            self.handle_error(msg_content)

    def handle_error(self, error_message):
        """Handle download errors"""
        self.status_label.setText(f"❌ Error: {error_message}")
        self.progress_bar.setValue(0)
        self.download_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", str(error_message))

    def show_context_menu(self, pos):
        """Show context menu for URL inputs"""
        menu = QMenu()
        paste_action = menu.addAction("Paste")
        
        # Get the widget that triggered the context menu
        widget = self.sender()
        
        action = menu.exec_(widget.mapToGlobal(pos))
        if action == paste_action:
            clipboard = QApplication.clipboard()
            if isinstance(widget, QLineEdit):
                widget.setText(clipboard.text())
            elif isinstance(widget, QTextEdit):
                widget.insertPlainText(clipboard.text())

    def closeEvent(self, event):
        """Handle application closing"""
        if self.download_thread and self.download_thread.isRunning():
            # Stop the download thread
            self.download_thread.stop()
            
            # Show "Canceling..." message
            self.status_label.setText("Canceling download...")
            QApplication.processEvents()  # Process any pending events
            
            # Wait with timeout
            if not self.download_thread.wait(3000):  # Wait up to 3 seconds
                self.download_thread.terminate()  # Force quit if taking too long
                self.download_thread.wait()
                
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YouTubeDownloaderApp()
    window.show()
    sys.exit(app.exec_())