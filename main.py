import sys
import os
import requests
import time
import hashlib
import json
import vlc
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QTabWidget, QMessageBox, QProgressBar, QDialog,
                             QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
                             QScrollArea, QFrame, QSlider, QInputDialog)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtCore import QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QSizePolicy

class DownloadWorker(QThread):
    progress = pyqtSignal(int, str, str)  # progress, speed, time remaining
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url, save_path):
        super().__init__()
        self.url = url
        self.save_path = save_path

    def run(self):
        try:
            session = requests.Session()
            session.verify = False
            session.trust_env = False

            response = session.get(self.url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            os.makedirs(os.path.dirname(self.save_path), exist_ok=True)

            block_size = 1024
            downloaded = 0
            start_time = time.time()

            with open(self.save_path, 'wb') as f:
                for data in response.iter_content(block_size):
                    if not data:
                        continue
                        
                    downloaded += len(data)
                    f.write(data)
                    
                    # Calculate progress
                    if total_size > 0:
                        progress = int((downloaded / total_size) * 100)
                    else:
                        progress = int((downloaded / (1024 * 1024)) % 100)
                    
                    # Calculate speed
                    elapsed_time = time.time() - start_time
                    if elapsed_time > 0:
                        speed = downloaded / (1024 * elapsed_time)  # KB/s
                        if speed > 1024:
                            speed_text = f"{speed/1024:.1f} MB/s"
                        else:
                            speed_text = f"{speed:.1f} KB/s"
                            
                        # Calculate time remaining
                        if total_size > 0:
                            bytes_remaining = total_size - downloaded
                            time_remaining = bytes_remaining / (downloaded / elapsed_time)
                            
                            if time_remaining > 60:
                                time_text = f"{time_remaining/60:.1f} minutes remaining"
                            else:
                                time_text = f"{time_remaining:.1f} seconds remaining"
                        else:
                            time_text = "Calculating..."
                    else:
                        speed_text = "Calculating..."
                        time_text = "Calculating..."
                    
                    self.progress.emit(progress, speed_text, time_text)

            self.finished.emit(self.save_path)

        except Exception as e:
            self.error.emit(str(e))

class PlaylistSelector(QDialog):
    def __init__(self, playlists_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Playlist")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.parent = parent
        self.playlists_info = playlists_info
        
        layout = QVBoxLayout()
        
        # Create list widget
        self.list_widget = QListWidget()
        
        # Add only existing playlists to the list
        self.existing_playlists = {}
        for filename, info in playlists_info.items():
            file_path = info.get('path', '')
            if os.path.exists(file_path):
                self.existing_playlists[filename] = info
                item = QListWidgetItem()
                url = info.get('url', 'Unknown URL')
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', 
                                      time.localtime(info.get('timestamp', 0)))
                item.setText(f"{filename}\nURL: {url}\nDownloaded: {timestamp}")
                item.setData(Qt.UserRole, file_path)
                self.list_widget.addItem(item)
        
        # Update parent's playlist_info if any playlists were removed
        if len(self.existing_playlists) < len(playlists_info):
            self.parent.playlist_info = self.existing_playlists
            self.parent.save_playlist_info()
            removed_count = len(playlists_info) - len(self.existing_playlists)
            QMessageBox.information(self, "Playlist Cleanup", 
                                f"Removed {removed_count} missing playlist(s) from the list.")
        
        if self.list_widget.count() == 0:
            QMessageBox.warning(self, "No Playlists", 
                            "No downloaded playlists available.")
            self.reject()
            return
            
        layout.addWidget(self.list_widget)
        
        # Management buttons layout
        management_layout = QHBoxLayout()
        
        # Add rename button
        rename_button = QPushButton("Rename Selected")
        rename_button.clicked.connect(self.rename_playlist)
        management_layout.addWidget(rename_button)
        
        # Add delete button
        delete_button = QPushButton("Delete Selected")
        delete_button.clicked.connect(self.delete_playlist)
        delete_button.setStyleSheet("background-color: #ff4444; color: white;")
        management_layout.addWidget(delete_button)
        
        layout.addLayout(management_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        load_button = QPushButton("Load")
        load_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(load_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def delete_playlist(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a playlist to delete.")
            return
        
        # Find the current filename
        current_filename = None
        for filename, info in self.existing_playlists.items():
            if info['path'] == current_item.data(Qt.UserRole):
                current_filename = filename
                break
        
        if not current_filename:
            QMessageBox.warning(self, "Error", "Could not find playlist information.")
            return
        
        # Confirm deletion
        reply = QMessageBox.question(self, "Confirm Delete",
                                   f"Are you sure you want to delete the playlist '{current_filename}'?\n"
                                   "This will permanently delete the playlist file.",
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                # Get the file path
                file_path = self.existing_playlists[current_filename]['path']
                
                # Delete the file
                os.remove(file_path)
                
                # Remove from playlists info
                del self.existing_playlists[current_filename]
                
                # Update parent's playlist info
                self.parent.playlist_info = self.existing_playlists
                self.parent.save_playlist_info()
                
                # Remove from list widget
                row = self.list_widget.row(current_item)
                self.list_widget.takeItem(row)
                
                # Check if we have any playlists left
                if self.list_widget.count() == 0:
                    QMessageBox.information(self, "No Playlists", 
                                        "All playlists have been deleted.")
                    self.reject()
                else:
                    QMessageBox.information(self, "Success", 
                                        f"Playlist '{current_filename}' has been deleted.")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", 
                                   f"Failed to delete playlist: {str(e)}")
    
    def rename_playlist(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a playlist to rename.")
            return
        
        # Find the current filename
        current_filename = None
        for filename, info in self.existing_playlists.items():
            if info['path'] == current_item.data(Qt.UserRole):
                current_filename = filename
                break
        
        if not current_filename:
            QMessageBox.warning(self, "Error", "Could not find playlist information.")
            return
        
        # Show rename dialog
        new_name, ok = QInputDialog.getText(self, "Rename Playlist", 
                                          "Enter new name:", 
                                          QLineEdit.Normal,
                                          current_filename)
        
        if ok and new_name:
            if new_name == current_filename:
                return  # No change needed
                
            if new_name in self.existing_playlists:
                QMessageBox.warning(self, "Name Exists", 
                                  "A playlist with this name already exists.")
                return
            
            try:
                # Get the old file info
                old_info = self.existing_playlists[current_filename]
                old_path = old_info['path']
                
                # Create new file path
                new_path = os.path.join(os.path.dirname(old_path), f"{new_name}.m3u")
                
                # Rename the file
                os.rename(old_path, new_path)
                
                # Update playlist info
                self.existing_playlists[new_name] = old_info.copy()
                self.existing_playlists[new_name]['path'] = new_path
                del self.existing_playlists[current_filename]
                
                # Update parent's playlist info
                self.parent.playlist_info = self.existing_playlists
                self.parent.save_playlist_info()
                
                # Update list item
                url = old_info.get('url', 'Unknown URL')
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', 
                                      time.localtime(old_info.get('timestamp', 0)))
                current_item.setText(f"{new_name}\nURL: {url}\nDownloaded: {timestamp}")
                current_item.setData(Qt.UserRole, new_path)
                
                QMessageBox.information(self, "Success", 
                                      f"Playlist renamed to '{new_name}'")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", 
                                   f"Failed to rename playlist: {str(e)}")
    
    def get_selected_playlist(self):
        current_item = self.list_widget.currentItem()
        if current_item:
            return current_item.data(Qt.UserRole)
        return None

class MediaItem:
    def __init__(self, name, logo_url, group, stream_url):
        self.name = name
        self.logo_url = logo_url
        self.group = group
        self.stream_url = stream_url

class PlaylistParserWorker(QThread):
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(dict, dict, dict)  # channels, movies, series
    error = pyqtSignal(str)

    def __init__(self, playlist_path):
        super().__init__()
        self.playlist_path = playlist_path
        
    def run(self):
        try:
            channels = {}
            movies = {}
            series = {}
            
            with open(self.playlist_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            i = 0
            
            while i < total_lines:
                line = lines[i].strip()
                if line.startswith('#EXTINF:'):
                    info_line = line
                    url_line = lines[i + 1].strip() if i + 1 < total_lines else None
                    
                    if url_line:
                        # Extract information using regex
                        name_match = re.search(r'tvg-name="([^"]*)"', info_line)
                        logo_match = re.search(r'tvg-logo="([^"]*)"', info_line)
                        group_match = re.search(r'group-title="([^"]*)"', info_line)
                        
                        name = name_match.group(1) if name_match else ""
                        logo_url = logo_match.group(1) if logo_match else ""
                        group = group_match.group(1) if group_match else "Ungrouped"
                        
                        # Create MediaItem
                        media_item = MediaItem(name, logo_url, group, url_line)
                        
                        # Add to appropriate dictionary
                        if "/movie/" in url_line:
                            if group not in movies:
                                movies[group] = []
                            movies[group].append(media_item)
                        elif "/series/" in url_line:
                            if group not in series:
                                series[group] = []
                            series[group].append(media_item)
                        else:
                            if group not in channels:
                                channels[group] = []
                            channels[group].append(media_item)
                    
                    i += 2
                else:
                    i += 1
                
                # Emit progress every 100 items
                if i % 100 == 0:
                    self.progress.emit(i, total_lines)
            
            self.progress.emit(total_lines, total_lines)
            self.finished.emit(channels, movies, series)
            
        except Exception as e:
            self.error.emit(str(e))

class MediaTreeWidget(QTreeWidget):
    loading_progress = pyqtSignal(int, int)  # current, total
    loading_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setAnimated(True)
        self.batch_size = 50  # Number of items to load per batch
        self.original_items = {}  # Store original items for search
        self.itemDoubleClicked.connect(self.on_item_double_clicked)
        
    def populate_tree(self, media_dict):
        self.clear()
        self.media_dict = media_dict
        self.original_items = media_dict.copy()  # Store original items
        self.groups = list(media_dict.keys())
        self.current_group = 0
        self.current_item = 0
        
        # Calculate total items
        self.total_items = sum(len(items) for items in media_dict.values())
        self.loaded_items = 0
        
        # Start loading the first batch
        QTimer.singleShot(0, self.load_next_batch)
        
    def search(self, query):
        if not query:  # If search is empty, restore original items
            self.media_dict = self.original_items.copy()
            self.populate_tree(self.media_dict)
            return
            
        # Convert query to lowercase for case-insensitive search
        query = query.lower()
        
        # Create new dictionary with matching items
        filtered_dict = {}
        for group, items in self.original_items.items():
            matching_items = []
            for item in items:
                if query in item.name.lower():
                    matching_items.append(item)
            if matching_items:  # Only add groups that have matching items
                filtered_dict[group] = matching_items
        
        # Update tree with filtered items
        self.media_dict = filtered_dict
        self.populate_tree(filtered_dict)

    def load_next_batch(self):
        batch_count = 0
        
        while self.current_group < len(self.groups) and batch_count < self.batch_size:
            group = self.groups[self.current_group]
            items = self.media_dict[group]
            
            # Create group item if it's the first item in the group
            if self.current_item == 0:
                group_item = QTreeWidgetItem(self)
                group_item.setText(0, group)
                group_item.setExpanded(False)
            else:
                group_item = self.topLevelItem(self.current_group)
            
            # Add items for this batch
            while self.current_item < len(items) and batch_count < self.batch_size:
                media = items[self.current_item]
                item = QTreeWidgetItem(group_item)
                item.setText(0, media.name)
                item.setData(0, Qt.UserRole, media)
                
                self.current_item += 1
                batch_count += 1
                self.loaded_items += 1
                
                # Emit progress
                self.loading_progress.emit(self.loaded_items, self.total_items)
            
            # Move to next group if we've finished the current one
            if self.current_item >= len(items):
                self.current_group += 1
                self.current_item = 0
        
        # Schedule next batch if there are more items to load
        if self.current_group < len(self.groups):
            QTimer.singleShot(10, self.load_next_batch)
        else:
            self.loading_finished.emit()

    def on_item_double_clicked(self, item, column):
        # Check if this is a media item (not a group)
        if item.parent() is not None:  # This means it's a child item (media item)
            media_item = item.data(0, Qt.UserRole)
            if media_item and hasattr(media_item, 'stream_url'):
                # Create and show the media player window
                player = MediaPlayer(media_item.stream_url, media_item.name, self)
                player.show()
                player.media_player.play()  # Start playing immediately

class MediaPlayer(QMainWindow):
    def __init__(self, stream_url, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        
        # Set initial size to 800x800
        screen = QApplication.primaryScreen().geometry()
        # Center the window on screen
        x = (screen.width() - 800) // 2
        y = (screen.height() - 800) // 2
        self.setGeometry(x, y, 800, 800)
        
        # Allow window to be maximized
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        # Create VLC instance and media player
        self.instance = vlc.Instance()
        self.media_player = self.instance.media_player_new()
        
        # Create a widget to hold the video
        self.video_widget = QFrame()
        self.video_widget.setStyleSheet("background-color: black;")
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # Make video expand to fill space
        
        if sys.platform.startswith('win'):
            self.media_player.set_hwnd(self.video_widget.winId())
        elif sys.platform.startswith('linux'):
            self.media_player.set_xwindow(self.video_widget.winId())
        elif sys.platform.startswith('darwin'):
            self.media_player.set_nsobject(int(self.video_widget.winId()))
        
        # Set up the main layout
        main_widget = QWidget()
        main_layout = QHBoxLayout()  # Changed to horizontal layout
        main_layout.setSpacing(0)  # Remove spacing between layouts
        main_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        
        # Video and controls container
        video_container = QVBoxLayout()
        video_container.setSpacing(5)  # Minimal spacing between video and controls
        video_container.setContentsMargins(0, 0, 0, 5)  # Add small bottom margin
        video_container.addWidget(self.video_widget, stretch=1)  # Video takes all available space
        
        # Controls layout
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(2)  # Minimal spacing between controls
        controls_layout.setContentsMargins(5, 0, 5, 0)  # Add horizontal margins
        
        # Time label and slider (for movies and series only)
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setEnabled(False)
        self.time_slider.sliderMoved.connect(self.set_position)
        self.time_slider.setFixedHeight(20)  # Set fixed height for slider
        
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.time_label.setStyleSheet("color: black; font-size: 10pt; background: transparent;")
        self.time_label.setAlignment(Qt.AlignLeft)
        self.time_label.setFixedHeight(15)  # Set fixed height for label
        
        # Only show time slider for movies and series
        is_movie_or_series = "/movie/" in stream_url or "/series/" in stream_url
        self.time_slider.setVisible(is_movie_or_series)
        self.time_label.setVisible(is_movie_or_series)
        
        # Add time controls to layout
        if is_movie_or_series:
            controls_layout.addWidget(self.time_label)
            controls_layout.addWidget(self.time_slider)
        
        # Button controls layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(5)  # Space between buttons
        
        # Play/Pause button
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.play_pause)
        self.play_button.setFixedHeight(30)  # Set fixed height for buttons
        button_layout.addWidget(self.play_button)
        
        # Stop button
        stop_button = QPushButton("Stop")
        stop_button.clicked.connect(self.stop)
        stop_button.setFixedHeight(30)
        button_layout.addWidget(stop_button)
        
        # Maximize button
        maximize_button = QPushButton("Maximize")
        maximize_button.clicked.connect(self.toggle_maximize)
        maximize_button.setFixedHeight(30)
        button_layout.addWidget(maximize_button)
        
        controls_layout.addLayout(button_layout)
        video_container.addLayout(controls_layout)
        
        # Add video container to main layout with full stretch
        main_layout.addLayout(video_container, stretch=1)
        
        # Volume control container
        volume_container = QVBoxLayout()
        volume_container.setContentsMargins(10, 10, 10, 10)  # Add some padding
        
        # Volume label at top
        volume_label = QLabel("Volume")
        volume_label.setAlignment(Qt.AlignCenter)
        volume_container.addWidget(volume_label)
        
        # Vertical volume slider
        self.volume_slider = QSlider(Qt.Vertical)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(50)  # Start at 50%
        self.volume_slider.setTickPosition(QSlider.TicksBothSides)
        self.volume_slider.setTickInterval(10)
        self.volume_slider.valueChanged.connect(self.set_volume)
        volume_container.addWidget(self.volume_slider, stretch=1)
        
        # Volume percentage label at bottom
        self.volume_percent = QLabel("50%")
        self.volume_percent.setAlignment(Qt.AlignCenter)
        volume_container.addWidget(self.volume_percent)
        
        # Add volume container to main layout
        main_layout.addLayout(volume_container)
        
        # Set the main layout
        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # Set up the media
        self.media = self.instance.media_new(stream_url)
        self.media_player.set_media(self.media)
        
        # Set initial volume
        self.media_player.audio_set_volume(100)
        
        # Start playing
        self.media_player.play()
        self.play_button.setText("Pause")
        
        # Setup timer for updating UI
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()
    
    def play_pause(self):
        if self.media_player.is_playing():
            self.media_player.pause()
            self.play_button.setText("Play")
        else:
            self.media_player.play()
            self.play_button.setText("Pause")
    
    def stop(self):
        self.media_player.stop()
        self.play_button.setText("Play")
    
    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
    
    def set_volume(self, volume):
        self.media_player.audio_set_volume(volume)
        self.volume_percent.setText(f"{volume}%")
    
    def update_ui(self):
        # Update play/pause button
        if not self.media_player.is_playing():
            self.play_button.setText("Play")
        else:
            self.play_button.setText("Pause")
            
        # Update time slider and label for movies and series
        if self.time_slider.isVisible():
            media_pos = self.media_player.get_position()
            media_length = self.media_player.get_length() / 1000  # Convert to seconds
            
            # Update slider
            if not self.time_slider.isSliderDown():
                self.time_slider.setValue(int(media_pos * 1000))
            
            if media_length > 0:
                current_time = int(media_length * media_pos)
                total_time = int(media_length)
                
                # Format time as HH:MM:SS
                current_str = time.strftime('%H:%M:%S', time.gmtime(current_time))
                total_str = time.strftime('%H:%M:%S', time.gmtime(total_time))
                
                self.time_label.setText(f"{current_str} / {total_str}")
                
                # Enable slider once media length is known
                if not self.time_slider.isEnabled():
                    self.time_slider.setEnabled(True)
                    self.time_slider.setRange(0, 1000)
            
        # Check for media errors
        state = self.media_player.get_state()
        if state == vlc.State.Error:
            self.handle_error()
            
    def set_position(self, position):
        """Set the media position according to the slider value"""
        self.media_player.set_position(position / 1000.0)
    
    def handle_error(self):
        self.play_button.setEnabled(False)
        QMessageBox.warning(self, "Media Player Error", 
                          "Error playing media. Please check the stream URL.")
    
    def closeEvent(self, event):
        self.timer.stop()
        self.media_player.stop()
        # Reset window state before closing
        self.showNormal()
        event.accept()

    def showEvent(self, event):
        # Ensure window size is 800x800 every time it's shown
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - 800) // 2
        y = (screen.height() - 800) // 2
        self.setGeometry(x, y, 800, 800)
        super().showEvent(event)

class IPTVPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IPTV Player")
        self.setGeometry(100, 100, 1024, 768)
        
        # Set up directories
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.playlists_dir = os.path.join(self.app_dir, 'playlists')
        self.cache_dir = os.path.join(self.app_dir, 'cache')
        self.playlist_info_file = os.path.join(self.app_dir, 'playlist_info.json')
        
        # Create directories if they don't exist
        os.makedirs(self.playlists_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Load playlist information
        self.playlist_info = self.load_playlist_info()
        
        # Main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # Status label
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        
        # Download speed label
        self.speed_label = QLabel()
        self.speed_label.setAlignment(Qt.AlignCenter)
        
        # Playlist Download Section
        download_layout = QHBoxLayout()
        self.playlist_input = QLineEdit()
        self.playlist_input.setPlaceholderText("Enter M3U Playlist URL")
        
        # Set last used URL if available
        last_url = self.get_last_used_url()
        if last_url:
            self.playlist_input.setText(last_url)
            
        # Search Section
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search in current tab...")
        self.search_input.returnPressed.connect(self.perform_search)  # Enter key
        
        search_button = QPushButton("Search")
        search_button.clicked.connect(self.perform_search)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_button)
        
        # Add existing buttons
        download_button = QPushButton("Download Playlist")
        download_button.clicked.connect(self.download_playlist)
        
        load_button = QPushButton("Load Playlist")
        load_button.clicked.connect(self.show_playlist_selector)
        
        update_button = QPushButton("Update Playlist")
        update_button.clicked.connect(self.update_current_playlist)
        
        clear_cache_btn = QPushButton("Clear Cache")
        clear_cache_btn.clicked.connect(self.clear_cache)
        
        download_layout.addWidget(self.playlist_input)
        download_layout.addWidget(download_button)
        download_layout.addWidget(load_button)
        download_layout.addWidget(update_button)
        download_layout.addWidget(clear_cache_btn)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        # Main layout assembly
        main_layout.addLayout(download_layout)
        main_layout.addLayout(search_layout)  # Add search section
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.speed_label)
        
        # Tabs
        self.tabs = QTabWidget()
        live_tv_tab = QWidget()
        movies_tab = QWidget()
        series_tab = QWidget()
        
        self.tabs.addTab(live_tv_tab, "Live TV")
        self.tabs.addTab(movies_tab, "Movies")
        self.tabs.addTab(series_tab, "Series")
        
        # Main layout assembly
        main_layout.addWidget(self.tabs)
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        requests.packages.urllib3.disable_warnings()

    def load_playlist_info(self):
        if os.path.exists(self.playlist_info_file):
            try:
                with open(self.playlist_info_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_playlist_info(self):
        try:
            with open(self.playlist_info_file, 'w') as f:
                json.dump(self.playlist_info, f, indent=4)
        except Exception as e:
            print(f"Error saving playlist info: {e}")

    def get_last_used_url(self):
        if self.playlist_info:
            # Get the most recently added playlist
            latest_playlist = max(self.playlist_info.items(), key=lambda x: x[1].get('timestamp', 0))
            return latest_playlist[1].get('url', '')
        return ''

    def update_progress(self, progress, speed, time_remaining):
        self.progress_bar.setValue(progress)
        status_text = f"Updating playlist... {progress}%"
        self.status_label.setText(status_text)
        self.speed_label.setText(f"{speed} | {time_remaining}")
        
    def update_current_playlist(self):
        url = self.playlist_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "No playlist URL available to update from.")
            return
            
        # Generate filename from URL
        filename = hashlib.md5(url.encode()).hexdigest() + '.m3u'
        save_path = os.path.join(self.playlists_dir, filename)
        
        # Show progress bar and reset status
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Updating playlist...")
        self.speed_label.setText("")
        
        # Create and start download worker
        self.download_worker = DownloadWorker(url, save_path)
        self.download_worker.progress.connect(self.update_progress)
        self.download_worker.finished.connect(self.download_finished)
        self.download_worker.error.connect(self.download_error)
        self.download_worker.start()
        
    def update_finished(self, save_path):
        self.progress_bar.setVisible(False)
        self.speed_label.setText("")
        self.status_label.setText("Playlist updated successfully!")
        
        # Update playlist info
        url = self.playlist_input.text().strip()
        self.update_playlist_info(url, save_path)

    def update_playlist_info(self, url, save_path):
        filename = os.path.basename(save_path)
        self.playlist_info[filename] = {
            'url': url,
            'timestamp': time.time(),
            'path': save_path
        }
        self.save_playlist_info()

    def download_finished(self, file_path):
        self.progress_bar.setVisible(False)
        self.playlist_input.setEnabled(True)
        self.status_label.setText("Download completed!")
        self.speed_label.setText("")
        
        # Update playlist information
        url = self.playlist_input.text().strip()
        filename = os.path.basename(file_path)
        self.playlist_info[filename] = {
            'url': url,
            'timestamp': time.time(),
            'path': file_path
        }
        self.save_playlist_info()
        
        # Parse and load the playlist content
        self.load_playlist(file_path)

        QMessageBox.information(self, "Success", f"Playlist downloaded to: {file_path}")

    def download_error(self, error_msg):
        self.progress_bar.setVisible(False)
        self.status_label.setText("Download failed!")
        self.speed_label.setText("")
        self.playlist_input.setEnabled(True)
        QMessageBox.critical(self, "Download Error", error_msg)
    
    def clear_cache(self):
        try:
            for filename in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, filename)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            QMessageBox.information(self, "Success", "Cache cleared successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear cache: {str(e)}")
    
    def download_playlist(self):
        url = self.playlist_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a playlist URL")
            return
        
        try:
            # Use MD5 hash for consistent filename generation
            filename = hashlib.md5(url.encode()).hexdigest() + '.m3u'
            save_path = os.path.join(self.playlists_dir, filename)
            
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.playlist_input.setEnabled(False)
            self.status_label.setText("Starting download...")
            self.speed_label.setText("Connecting...")
            
            # Update playlist info before starting download
            self.playlist_info[filename] = {
                'url': url,
                'timestamp': time.time(),
                'path': save_path
            }
            self.save_playlist_info()

            self.download_worker = DownloadWorker(url, save_path)
            self.download_worker.progress.connect(self.update_progress)
            self.download_worker.finished.connect(self.download_finished)
            self.download_worker.error.connect(self.download_error)
            self.download_worker.start()
        
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.playlist_input.setEnabled(True)
            self.progress_bar.setVisible(False)

    def verify_playlists(self):
        """Verify playlists exist and clean up JSON if needed"""
        playlists_to_remove = []
        for filename, info in self.playlist_info.items():
            file_path = info.get('path', '')
            if not os.path.exists(file_path):
                playlists_to_remove.append(filename)
        
        # Remove non-existent playlists from info
        for filename in playlists_to_remove:
            del self.playlist_info[filename]
        
        # Save cleaned up playlist info
        if playlists_to_remove:
            self.save_playlist_info()
            
        return len(playlists_to_remove)

    def show_playlist_selector(self):
        # Verify playlists before showing selector
        removed_count = self.verify_playlists()
        if removed_count > 0:
            QMessageBox.information(self, "Playlist Cleanup", 
                                  f"Removed {removed_count} missing playlist(s) from the list.")
        
        if not self.playlist_info:
            QMessageBox.warning(self, "No Playlists", 
                              "No downloaded playlists available.")
            return
            
        dialog = PlaylistSelector(self.playlist_info, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_path = dialog.get_selected_playlist()
            if selected_path:
                # Find the URL for the selected playlist
                for info in self.playlist_info.values():
                    if info.get('path') == selected_path:
                        self.playlist_input.setText(info.get('url', ''))
                        self.status_label.setText(f"Loaded playlist: {os.path.basename(selected_path)}")
                        # Parse and load the playlist content
                        self.load_playlist(selected_path)
                        break

    def load_playlist(self, playlist_path):
        try:
            # Create tree widgets if they don't exist
            if not hasattr(self, 'live_tv_tree'):
                self.live_tv_tree = MediaTreeWidget()
                self.movies_tree = MediaTreeWidget()
                self.series_tree = MediaTreeWidget()
                
                # Connect loading progress signals
                self.live_tv_tree.loading_progress.connect(lambda c, t: self.update_loading_progress("Live TV", c, t))
                self.movies_tree.loading_progress.connect(lambda c, t: self.update_loading_progress("Movies", c, t))
                self.series_tree.loading_progress.connect(lambda c, t: self.update_loading_progress("Series", c, t))
                
                self.live_tv_tree.loading_finished.connect(lambda: self.loading_finished("Live TV"))
                self.movies_tree.loading_finished.connect(lambda: self.loading_finished("Movies"))
                self.series_tree.loading_finished.connect(lambda: self.loading_finished("Series"))
                
                # Add trees to their respective tabs
                live_tv_layout = QVBoxLayout()
                live_tv_layout.addWidget(self.live_tv_tree)
                self.tabs.widget(0).setLayout(live_tv_layout)
                
                movies_layout = QVBoxLayout()
                movies_layout.addWidget(self.movies_tree)
                self.tabs.widget(1).setLayout(movies_layout)
                
                series_layout = QVBoxLayout()
                series_layout.addWidget(self.series_tree)
                self.tabs.widget(2).setLayout(series_layout)
            
            # Show loading progress
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.status_label.setText("Parsing playlist...")
            
            # Create and start parser worker
            self.parser_worker = PlaylistParserWorker(playlist_path)
            self.parser_worker.progress.connect(self.update_parse_progress)
            self.parser_worker.finished.connect(self.parser_finished)
            self.parser_worker.error.connect(self.parser_error)
            self.parser_worker.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load playlist: {str(e)}")
            
    def update_parse_progress(self, current, total):
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"Parsing playlist... {progress}%")
        
    def update_loading_progress(self, section, current, total):
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"Loading {section}... {progress}%")
        
    def loading_finished(self, section):
        self.status_label.setText(f"Finished loading {section}")
        if section == "Series":  # Last section to load
            self.progress_bar.setVisible(False)
            self.status_label.setText("Playlist loaded successfully!")
        
    def parser_finished(self, channels, movies, series):
        self.status_label.setText("Organizing content...")
        
        # Store content for reuse
        self.channels = channels
        self.movies = movies
        self.series = series
        
        # Start populating trees with batch loading
        self.live_tv_tree.populate_tree(channels)
        self.movies_tree.populate_tree(movies)
        self.series_tree.populate_tree(series)
        
    def parser_error(self, error_msg):
        self.progress_bar.setVisible(False)
        self.status_label.setText("Failed to parse playlist!")
        QMessageBox.critical(self, "Error", f"Failed to parse playlist: {error_msg}")
        
    def perform_search(self):
        query = self.search_input.text().strip()
        current_tab = self.tabs.currentWidget()
        
        # Get the tree widget for the current tab
        tree_widget = None
        if current_tab == self.tabs.widget(0):  # Live TV
            tree_widget = self.live_tv_tree
            content_type = "Live TV"
        elif current_tab == self.tabs.widget(1):  # Movies
            tree_widget = self.movies_tree
            content_type = "Movies"
        elif current_tab == self.tabs.widget(2):  # Series
            tree_widget = self.series_tree
            content_type = "Series"
            
        if tree_widget:
            if query:
                tree_widget.search(query)
                self.status_label.setText(f"Showing search results for: {query}")
            else:
                # When search is cleared, reload the content for current tab
                self.status_label.setText(f"Reloading {content_type}...")
                if content_type == "Live TV":
                    tree_widget.populate_tree(self.channels)
                elif content_type == "Movies":
                    tree_widget.populate_tree(self.movies)
                elif content_type == "Series":
                    tree_widget.populate_tree(self.series)
                self.status_label.setText(f"Showing all {content_type}")
                
    def closeEvent(self, event):
        self.save_playlist_info()
        event.accept()

def main():
    os.environ['PYTHONHTTPSVERIFY'] = '0'
    
    app = QApplication(sys.argv)
    player = IPTVPlayer()
    player.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    import re
    main()
