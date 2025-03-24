import sys
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QFileDialog, QSlider, QLabel, QSpinBox, 
                            QDoubleSpinBox, QComboBox, QCheckBox, QFrame, QMessageBox,
                            QProgressBar, QGroupBox, QGridLayout, QTabWidget)
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QTimer, QRect, pyqtSignal
import imageio.v2 as imageio
from PIL import Image, ImageSequence
import tempfile

class VideoPlayerWidget(QWidget):
    frameChanged = pyqtSignal(int)
    cropAreaChanged = pyqtSignal(QRect)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 480)
        self.video_frame = None
        self.current_frame_index = 0
        self.total_frames = 0
        self.fps = 30
        self.playing = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
        
        self.is_cropping = False
        self.crop_start = None
        self.crop_end = None
        self.crop_rect = QRect()
        
        self.dragging = False
        self.drag_start = None
        self.drag_rect = None
        
        self.resizing = False
        self.resize_edge = None
        self.edge_tolerance = 10  
        
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.frames = []
        self.is_gif = False
    
    def load_video(self, video_path):
        
        if video_path.lower().endswith('.gif'):
            return self.load_gif(video_path)
        
        self.is_gif = False
        self.frames = []
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            return False
        
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.video_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.current_frame_index = 0
        self.seek_to_frame(0)
        return True
    
    def load_gif(self, gif_path):
        try:
            self.is_gif = True
            self.frames = []
            
            gif = Image.open(gif_path)
            self.fps = 1000 / (gif.info.get('duration', 100))  
            self.video_width, self.video_height = gif.size
            
            for frame_index, frame in enumerate(ImageSequence.Iterator(gif)):
               
                frame_array = np.array(frame.convert('RGB'))
                self.frames.append(frame_array)
            
            self.total_frames = len(self.frames)
            self.current_frame_index = 0
            
            if self.total_frames > 0:
                self.display_frame(self.frames[0])
                self.frameChanged.emit(0)
                return True
            return False
        except Exception as e:
            print(f"Error loading GIF: {str(e)}")
            return False
    
    def seek_to_frame(self, frame_index):
        if frame_index < 0:
            frame_index = 0
        if frame_index >= self.total_frames:
            frame_index = self.total_frames - 1
        
        if self.is_gif:
            if 0 <= frame_index < len(self.frames):
                self.current_frame_index = frame_index
                self.display_frame(self.frames[frame_index])
                self.frameChanged.emit(frame_index)
        else:
            if not hasattr(self, 'cap') or not self.cap.isOpened():
                return
            
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = self.cap.read()
            if ret:
                self.current_frame_index = frame_index
                self.display_frame(frame)
                self.frameChanged.emit(frame_index)
    
    def display_frame(self, frame):
        if frame is None:
            return
        
        if not self.is_gif:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        else:
            frame_rgb = frame
            
        self.current_frame = frame_rgb
        
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        self.video_frame = QPixmap.fromImage(q_img)
        self.update()
    
    def next_frame(self):
        if self.is_gif:
            if self.current_frame_index < self.total_frames - 1:
                self.current_frame_index += 1
                self.display_frame(self.frames[self.current_frame_index])
                self.frameChanged.emit(self.current_frame_index)
            else:
                
                self.current_frame_index = 0
                self.display_frame(self.frames[self.current_frame_index])
                self.frameChanged.emit(self.current_frame_index)
        else:
            if not hasattr(self, 'cap') or not self.cap.isOpened():
                return
            
            if self.current_frame_index < self.total_frames - 1:
                ret, frame = self.cap.read()
                if ret:
                    self.current_frame_index += 1
                    self.display_frame(frame)
                    self.frameChanged.emit(self.current_frame_index)
            else:
                self.stop()
    
    def play(self):
        if (self.is_gif and not self.frames) or (not self.is_gif and (not hasattr(self, 'cap') or not self.cap.isOpened())):
            return
        
        self.playing = True
        interval = int(1000 / self.fps)
        self.timer.start(interval)
    
    def pause(self):
        self.playing = False
        self.timer.stop()
    
    def stop(self):
        self.pause()
        self.seek_to_frame(0)
    
    def toggle_play_pause(self):
        if self.playing:
            self.pause()
        else:
            self.play()
    
    def get_edge_at_position(self, pos, scaled_rect, tolerance):
        
        if not scaled_rect.isValid():
            return None
            
        near_left = abs(pos.x() - scaled_rect.left()) < tolerance
        near_right = abs(pos.x() - scaled_rect.right()) < tolerance
        near_top = abs(pos.y() - scaled_rect.top()) < tolerance
        near_bottom = abs(pos.y() - scaled_rect.bottom()) < tolerance
        
        if near_left and near_top:
            return "top-left"
        if near_right and near_top:
            return "top-right"
        if near_left and near_bottom:
            return "bottom-left"
        if near_right and near_bottom:
            return "bottom-right"
        
        if near_left:
            return "left"
        if near_right:
            return "right"
        if near_top:
            return "top"
        if near_bottom:
            return "bottom"
            
        return None
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        
        if self.video_frame:
          
            scaled_pixmap = self.video_frame.scaled(
                self.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            x = (self.width() - scaled_pixmap.width()) // 2
            y = (self.height() - scaled_pixmap.height()) // 2
            
            painter.drawPixmap(x, y, scaled_pixmap)
            
            if hasattr(self, 'video_width') and hasattr(self, 'video_height'):
                scale_x = scaled_pixmap.width() / self.video_width
                scale_y = scaled_pixmap.height() / self.video_height
                
                if not self.crop_rect.isNull():
                    painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.SolidLine))
                    scaled_rect = QRect(
                        int(x + self.crop_rect.x() * scale_x),
                        int(y + self.crop_rect.y() * scale_y),
                        int(self.crop_rect.width() * scale_x),
                        int(self.crop_rect.height() * scale_y)
                    )
                    painter.drawRect(scaled_rect)
                    
                    handle_size = 8
                    painter.setBrush(QColor(255, 0, 0))
                    
                    painter.drawRect(scaled_rect.left() - handle_size//2, scaled_rect.top() - handle_size//2, handle_size, handle_size)
                    painter.drawRect(scaled_rect.right() - handle_size//2, scaled_rect.top() - handle_size//2, handle_size, handle_size)
                    painter.drawRect(scaled_rect.left() - handle_size//2, scaled_rect.bottom() - handle_size//2, handle_size, handle_size)
                    painter.drawRect(scaled_rect.right() - handle_size//2, scaled_rect.bottom() - handle_size//2, handle_size, handle_size)
                    
                    painter.drawRect(scaled_rect.left() + scaled_rect.width()//2 - handle_size//2, scaled_rect.top() - handle_size//2, handle_size, handle_size)
                    painter.drawRect(scaled_rect.left() + scaled_rect.width()//2 - handle_size//2, scaled_rect.bottom() - handle_size//2, handle_size, handle_size)
                    painter.drawRect(scaled_rect.left() - handle_size//2, scaled_rect.top() + scaled_rect.height()//2 - handle_size//2, handle_size, handle_size)
                    painter.drawRect(scaled_rect.right() - handle_size//2, scaled_rect.top() + scaled_rect.height()//2 - handle_size//2, handle_size, handle_size)
    
    def mousePressEvent(self, event):
        if not self.video_frame or not hasattr(self, 'video_width'):
            return
        
        scaled_pixmap = self.video_frame.scaled(
            self.size(), 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        x_offset = (self.width() - scaled_pixmap.width()) // 2
        y_offset = (self.height() - scaled_pixmap.height()) // 2
        
        video_rect = QRect(x_offset, y_offset, scaled_pixmap.width(), scaled_pixmap.height())
        if not video_rect.contains(event.pos()):
            return
        
        scale_x = self.video_width / scaled_pixmap.width()
        scale_y = self.video_height / scaled_pixmap.height()
        
        video_x = int((event.x() - x_offset) * scale_x)
        video_y = int((event.y() - y_offset) * scale_y)
        
        if event.button() == Qt.LeftButton:
            
            if not self.crop_rect.isNull():
                scaled_rect = QRect(
                    int(x_offset + self.crop_rect.x() * scale_x),
                    int(y_offset + self.crop_rect.y() * scale_y),
                    int(self.crop_rect.width() * scale_x),
                    int(self.crop_rect.height() * scale_y)
                )
                
                edge = self.get_edge_at_position(event.pos(), scaled_rect, self.edge_tolerance)
                if edge:
                    self.resizing = True
                    self.resize_edge = edge
                    self.drag_start = event.pos()
                    self.drag_rect = self.crop_rect.translated(0, 0)  
                    return
                
       
                if scaled_rect.contains(event.pos()):
                    self.dragging = True
                    self.drag_start = event.pos()
                    self.drag_rect = self.crop_rect.translated(0, 0) 
                    return
            
            self.is_cropping = True
            self.crop_start = (video_x, video_y)
            self.crop_end = self.crop_start
            self.crop_rect = QRect(
                min(self.crop_start[0], self.crop_end[0]),
                min(self.crop_start[1], self.crop_end[1]),
                abs(self.crop_end[0] - self.crop_start[0]),
                abs(self.crop_end[1] - self.crop_start[1])
            )
            self.update()
    
    def mouseMoveEvent(self, event):
        if not self.video_frame or not hasattr(self, 'video_width'):
            return
        
        scaled_pixmap = self.video_frame.scaled(
            self.size(), 
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        x_offset = (self.width() - scaled_pixmap.width()) // 2
        y_offset = (self.height() - scaled_pixmap.height()) // 2
        
        scale_x = self.video_width / scaled_pixmap.width()
        scale_y = self.video_height / scaled_pixmap.height()
        
        video_x = max(0, min(self.video_width, int((event.x() - x_offset) * scale_x)))
        video_y = max(0, min(self.video_height, int((event.y() - y_offset) * scale_y)))
        
        if self.is_cropping:
            self.crop_end = (video_x, video_y)
            self.crop_rect = QRect(
                min(self.crop_start[0], self.crop_end[0]),
                min(self.crop_start[1], self.crop_end[1]),
                abs(self.crop_end[0] - self.crop_start[0]),
                abs(self.crop_end[1] - self.crop_start[1])
            )
            self.update()
        elif self.dragging and self.drag_start:
            
            delta_x = int((event.x() - self.drag_start.x()) * scale_x)
            delta_y = int((event.y() - self.drag_start.y()) * scale_y)
            
            new_x = max(0, min(self.video_width - self.drag_rect.width(), self.drag_rect.x() + delta_x))
            new_y = max(0, min(self.video_height - self.drag_rect.height(), self.drag_rect.y() + delta_y))
            
            self.crop_rect = QRect(new_x, new_y, self.drag_rect.width(), self.drag_rect.height())
            self.drag_start = event.pos()
            self.drag_rect = self.crop_rect.translated(0, 0) 
            self.update()
        elif self.resizing and self.drag_start and self.resize_edge:
          
            delta_x = int((event.x() - self.drag_start.x()) * scale_x)
            delta_y = int((event.y() - self.drag_start.y()) * scale_y)
            
            new_rect = QRect(self.drag_rect)
            
            if self.resize_edge == "left" or self.resize_edge == "top-left" or self.resize_edge == "bottom-left":
                new_left = max(0, self.drag_rect.left() + delta_x)
                if new_left < self.drag_rect.right():
                    new_rect.setLeft(new_left)
            
            if self.resize_edge == "right" or self.resize_edge == "top-right" or self.resize_edge == "bottom-right":
                new_right = min(self.video_width, self.drag_rect.right() + delta_x)
                if new_right > new_rect.left():
                    new_rect.setRight(new_right)
            
            if self.resize_edge == "top" or self.resize_edge == "top-left" or self.resize_edge == "top-right":
                new_top = max(0, self.drag_rect.top() + delta_y)
                if new_top < self.drag_rect.bottom():
                    new_rect.setTop(new_top)
            
            if self.resize_edge == "bottom" or self.resize_edge == "bottom-left" or self.resize_edge == "bottom-right":
                new_bottom = min(self.video_height, self.drag_rect.bottom() + delta_y)
                if new_bottom > new_rect.top():
                    new_rect.setBottom(new_bottom)
            
            self.crop_rect = new_rect
            self.drag_start = event.pos()
            self.drag_rect = self.crop_rect.translated(0, 0)  
            self.update()
        
        if not self.is_cropping and not self.dragging and not self.resizing and not self.crop_rect.isNull():
            scaled_rect = QRect(
                int(x_offset + self.crop_rect.x() * scale_x),
                int(y_offset + self.crop_rect.y() * scale_y),
                int(self.crop_rect.width() * scale_x),
                int(self.crop_rect.height() * scale_y)
            )
            
            edge = self.get_edge_at_position(event.pos(), scaled_rect, self.edge_tolerance)
            if edge:
                if edge == "left" or edge == "right":
                    self.setCursor(Qt.SizeHorCursor)
                elif edge == "top" or edge == "bottom":
                    self.setCursor(Qt.SizeVerCursor)
                elif edge == "top-left" or edge == "bottom-right":
                    self.setCursor(Qt.SizeFDiagCursor)
                elif edge == "top-right" or edge == "bottom-left":
                    self.setCursor(Qt.SizeBDiagCursor)
            elif scaled_rect.contains(event.pos()):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_cropping:
                self.is_cropping = False
               
                self.cropAreaChanged.emit(self.crop_rect)
            elif self.dragging:
                self.dragging = False
                self.drag_start = None
               
                self.cropAreaChanged.emit(self.crop_rect)
            elif self.resizing:
                self.resizing = False
                self.resize_edge = None
                self.drag_start = None
                
                self.cropAreaChanged.emit(self.crop_rect)
            
            self.setCursor(Qt.ArrowCursor)
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.toggle_play_pause()
        elif event.key() == Qt.Key_Left:
            self.seek_to_frame(self.current_frame_index - 1)
        elif event.key() == Qt.Key_Right:
            self.seek_to_frame(self.current_frame_index + 1)
        elif event.key() == Qt.Key_Home:
            self.seek_to_frame(0)
        elif event.key() == Qt.Key_End:
            self.seek_to_frame(self.total_frames - 1)
        else:
            super().keyPressEvent(event)
    
    def reset_crop(self):
        self.crop_rect = QRect()
        self.update()
        self.cropAreaChanged.emit(self.crop_rect)

class CropControlsWidget(QWidget):
    cropChanged = pyqtSignal(int, int, int, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QGridLayout(self)
        
        self.layout.addWidget(QLabel("Top:"), 0, 0)
        self.top_spin = QSpinBox()
        self.top_spin.setMinimum(0)
        self.top_spin.setMaximum(9999)
        self.top_spin.valueChanged.connect(self.emit_crop_changed)
        self.layout.addWidget(self.top_spin, 0, 1)
        
        self.layout.addWidget(QLabel("Bottom:"), 1, 0)
        self.bottom_spin = QSpinBox()
        self.bottom_spin.setMinimum(0)
        self.bottom_spin.setMaximum(9999)
        self.bottom_spin.valueChanged.connect(self.emit_crop_changed)
        self.layout.addWidget(self.bottom_spin, 1, 1)
        
        self.layout.addWidget(QLabel("Left:"), 0, 2)
        self.left_spin = QSpinBox()
        self.left_spin.setMinimum(0)
        self.left_spin.setMaximum(9999)
        self.left_spin.valueChanged.connect(self.emit_crop_changed)
        self.layout.addWidget(self.left_spin, 0, 3)
        
        self.layout.addWidget(QLabel("Right:"), 1, 2)
        self.right_spin = QSpinBox()
        self.right_spin.setMinimum(0)
        self.right_spin.setMaximum(9999)
        self.right_spin.valueChanged.connect(self.emit_crop_changed)
        self.layout.addWidget(self.right_spin, 1, 3)
        
        self.reset_btn = QPushButton("Reset Crop Values")
        self.reset_btn.clicked.connect(self.reset_values)
        self.layout.addWidget(self.reset_btn, 2, 0, 1, 4)
    
    def set_max_values(self, width, height):
        self.top_spin.setMaximum(height - 1)
        self.bottom_spin.setMaximum(height - 1)
        self.left_spin.setMaximum(width - 1)
        self.right_spin.setMaximum(width - 1)
    
    def update_from_rect(self, rect, video_width, video_height):
        self.blockSignals(True)
        self.set_max_values(video_width, video_height)
        
        if rect.isNull():
            self.reset_values()
        else:
            self.top_spin.setValue(rect.top())
            self.left_spin.setValue(rect.left())
            self.right_spin.setValue(video_width - rect.right() - 1)
            self.bottom_spin.setValue(video_height - rect.bottom() - 1)
        
        self.blockSignals(False)
    
    def get_crop_rect(self, video_width, video_height):
        left = self.left_spin.value()
        top = self.top_spin.value()
        right = video_width - self.right_spin.value() - 1
        bottom = video_height - self.bottom_spin.value() - 1
        
        if left >= right or top >= bottom:
            return QRect()
        
        return QRect(left, top, right - left + 1, bottom - top + 1)
    
    def reset_values(self):
        self.blockSignals(True)
        self.top_spin.setValue(0)
        self.bottom_spin.setValue(0)
        self.left_spin.setValue(0)
        self.right_spin.setValue(0)
        self.blockSignals(False)
        self.emit_crop_changed()
    
    def emit_crop_changed(self):
        self.cropChanged.emit(
            self.top_spin.value(),
            self.bottom_spin.value(),
            self.left_spin.value(),
            self.right_spin.value()
        )

class GifCutterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gif Cutter made by TheZ")
        self.setMinimumSize(900, 700)
        
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        self.video_player = VideoPlayerWidget()
        self.video_player.frameChanged.connect(self.update_frame_info)
        self.video_player.cropAreaChanged.connect(self.update_crop_info)
        self.main_layout.addWidget(self.video_player, 3)  
        
        self.controls_layout = QHBoxLayout()
        
        self.video_controls = QGroupBox("Video Controls")
        self.video_controls_layout = QVBoxLayout(self.video_controls)
        
        self.playback_layout = QHBoxLayout()
        self.play_pause_btn = QPushButton("Play/Pause")
        self.play_pause_btn.clicked.connect(self.video_player.toggle_play_pause)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.video_player.stop)
        self.playback_layout.addWidget(self.play_pause_btn)
        self.playback_layout.addWidget(self.stop_btn)
        self.video_controls_layout.addLayout(self.playback_layout)
        
        self.slider_layout = QHBoxLayout()
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(100)
        self.frame_slider.valueChanged.connect(self.slider_value_changed)
        self.frame_info_label = QLabel("Frame: 0 / 0")
        self.slider_layout.addWidget(self.frame_slider)
        self.slider_layout.addWidget(self.frame_info_label)
        self.video_controls_layout.addLayout(self.slider_layout)
        
        self.time_selection_layout = QGridLayout()
        self.time_selection_layout.addWidget(QLabel("Start Frame:"), 0, 0)
        self.start_frame_spin = QSpinBox()
        self.start_frame_spin.setMinimum(0)
        self.start_frame_spin.setMaximum(0)  
        self.time_selection_layout.addWidget(self.start_frame_spin, 0, 1)
        
        self.time_selection_layout.addWidget(QLabel("End Frame:"), 1, 0)
        self.end_frame_spin = QSpinBox()
        self.end_frame_spin.setMinimum(0)
        self.end_frame_spin.setMaximum(0)  
        self.time_selection_layout.addWidget(self.end_frame_spin, 1, 1)
        
        self.video_controls_layout.addLayout(self.time_selection_layout)
        
        self.controls_layout.addWidget(self.video_controls)
        
        self.crop_group = QGroupBox("Crop Controls")
        self.crop_layout = QVBoxLayout(self.crop_group)
        
        self.crop_info_label = QLabel("No crop selected")
        self.crop_layout.addWidget(self.crop_info_label)
        
        self.crop_controls = CropControlsWidget()
        self.crop_controls.cropChanged.connect(self.manual_crop_changed)
        self.crop_layout.addWidget(self.crop_controls)
        
        self.reset_crop_btn = QPushButton("Reset Crop")
        self.reset_crop_btn.clicked.connect(self.video_player.reset_crop)
        self.crop_layout.addWidget(self.reset_crop_btn)
        
        self.controls_layout.addWidget(self.crop_group)
        
        self.gif_settings = QGroupBox("GIF Settings")
        self.gif_settings_layout = QVBoxLayout(self.gif_settings)
        
        self.fps_layout = QHBoxLayout()
        self.fps_layout.addWidget(QLabel("FPS:"))
        self.fps_spin = QSpinBox()
        self.fps_spin.setMinimum(1)
        self.fps_spin.setMaximum(60)
        self.fps_spin.setValue(10)
        self.fps_layout.addWidget(self.fps_spin)
        self.gif_settings_layout.addLayout(self.fps_layout)
        
        self.quality_layout = QHBoxLayout()
        self.quality_layout.addWidget(QLabel("Quality:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["High", "Medium", "Low"])
        self.quality_layout.addWidget(self.quality_combo)
        self.gif_settings_layout.addLayout(self.quality_layout)
        
        self.loop_layout = QHBoxLayout()
        self.loop_check = QCheckBox("Loop GIF")
        self.loop_check.setChecked(True)
        self.loop_layout.addWidget(self.loop_check)
        self.gif_settings_layout.addLayout(self.loop_layout)
        
        self.controls_layout.addWidget(self.gif_settings)
        
        self.file_ops = QGroupBox("File Operations")
        self.file_ops_layout = QVBoxLayout(self.file_ops)
        
        self.load_video_btn = QPushButton("Load Video")
        self.load_video_btn.clicked.connect(self.load_video)
        self.file_ops_layout.addWidget(self.load_video_btn)
        
        self.load_gif_btn = QPushButton("Load GIF")
        self.load_gif_btn.clicked.connect(self.load_gif)
        self.file_ops_layout.addWidget(self.load_gif_btn)
        
        self.create_gif_btn = QPushButton("Create GIF")
        self.create_gif_btn.clicked.connect(self.create_gif)
        self.file_ops_layout.addWidget(self.create_gif_btn)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.file_ops_layout.addWidget(self.progress_bar)
        
        self.controls_layout.addWidget(self.file_ops)
        
        self.main_layout.addLayout(self.controls_layout, 1)
        
        self.video_path = None
    
    def load_video(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self, "Open Video File", "", 
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv);;All Files (*)"
        )
        
        if file_path:
            self.load_media_file(file_path)
    
    def load_gif(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self, "Open GIF File", "", 
            "GIF Files (*.gif);;All Files (*)"
        )
        
        if file_path:
            self.load_media_file(file_path)
    
    def load_media_file(self, file_path):
        self.video_path = file_path
        if self.video_player.load_video(file_path):
            
            self.frame_slider.setMaximum(self.video_player.total_frames - 1)
            self.start_frame_spin.setMaximum(self.video_player.total_frames - 1)
            self.end_frame_spin.setMaximum(self.video_player.total_frames - 1)
            self.end_frame_spin.setValue(self.video_player.total_frames - 1)
            self.fps_spin.setValue(min(int(self.video_player.fps), 30))
            self.update_frame_info(0)
            
            self.video_player.reset_crop()
            self.crop_controls.set_max_values(self.video_player.video_width, self.video_player.video_height)
        else:
            QMessageBox.critical(self, "Error", "Failed to load media file.")
    
    def slider_value_changed(self, value):
        self.video_player.seek_to_frame(value)
    
    def update_frame_info(self, frame_index):
        self.frame_info_label.setText(f"Frame: {frame_index} / {self.video_player.total_frames - 1}")
       
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(frame_index)
        self.frame_slider.blockSignals(False)
    
    def update_crop_info(self, rect):
        if rect.isNull():
            self.crop_info_label.setText("No crop selected")
        else:
            self.crop_info_label.setText(
                f"Crop: ({rect.x()}, {rect.y()}) - {rect.width()}x{rect.height()}"
            )
        
        if hasattr(self.video_player, 'video_width') and hasattr(self.video_player, 'video_height'):
            self.crop_controls.update_from_rect(rect, self.video_player.video_width, self.video_player.video_height)
    
    def manual_crop_changed(self, top, bottom, left, right):
        if hasattr(self.video_player, 'video_width') and hasattr(self.video_player, 'video_height'):
            rect = self.crop_controls.get_crop_rect(self.video_player.video_width, self.video_player.video_height)
            
            self.video_player.crop_rect = rect
            self.video_player.update()
            
            if rect.isNull():
                self.crop_info_label.setText("No crop selected")
            else:
                self.crop_info_label.setText(
                    f"Crop: ({rect.x()}, {rect.y()}) - {rect.width()}x{rect.height()}"
                )
    
    def create_gif(self):
        if not self.video_path or (not self.video_player.is_gif and not hasattr(self.video_player, 'cap')):
            QMessageBox.warning(self, "Warning", "Please load a video or GIF first.")
            return
        
        start_frame = self.start_frame_spin.value()
        end_frame = self.end_frame_spin.value()
        
        if start_frame >= end_frame:
            QMessageBox.warning(self, "Warning", "Start frame must be less than end frame.")
            return
        
        file_dialog = QFileDialog()
        output_path, _ = file_dialog.getSaveFileName(
            self, "Save GIF", "", "GIF Files (*.gif);;All Files (*)"
        )
        
        if not output_path:
            return
        
        if not output_path.lower().endswith('.gif'):
            output_path += '.gif'
        
        fps = self.fps_spin.value()
        quality = self.quality_combo.currentText().lower()
        loop = self.loop_check.isChecked()
        crop_rect = self.video_player.crop_rect
        
        if quality == "high":
            optimize = True
            colors = 256
        elif quality == "medium":
            optimize = True
            colors = 128
        else:  
            optimize = False
            colors = 64
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        try:
            
            with tempfile.TemporaryDirectory() as temp_dir:
                frames = []
                frame_count = end_frame - start_frame + 1
                
                if self.video_player.is_gif:
                
                    for i in range(frame_count):
                        frame_index = start_frame + i
                        if frame_index >= len(self.video_player.frames):
                            break
                        
                        frame = self.video_player.frames[frame_index].copy()
                        
                        if not crop_rect.isNull():
                            x, y, w, h = crop_rect.x(), crop_rect.y(), crop_rect.width(), crop_rect.height()
                            frame = frame[y:y+h, x:x+w]
                        
                        frame_path = os.path.join(temp_dir, f"frame_{i:04d}.png")
                        imageio.imwrite(frame_path, frame)
                        frames.append(frame_path)
                        
                        progress = int((i + 1) / frame_count * 100)
                        self.progress_bar.setValue(progress)
                        QApplication.processEvents()  
                else:
                 
                    cap = cv2.VideoCapture(self.video_path)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                    
                    for i in range(frame_count):
                        ret, frame = cap.read()
                        if not ret:
                            break
                        
                        if not crop_rect.isNull():
                            x, y, w, h = crop_rect.x(), crop_rect.y(), crop_rect.width(), crop_rect.height()
                            frame = frame[y:y+h, x:x+w]
                        
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        
                        frame_path = os.path.join(temp_dir, f"frame_{i:04d}.png")
                        imageio.imwrite(frame_path, frame_rgb)
                        frames.append(frame_path)
                        
                        progress = int((i + 1) / frame_count * 100)
                        self.progress_bar.setValue(progress)
                        QApplication.processEvents()  
                    
                    cap.release()
                
                with imageio.get_writer(output_path, mode='I', fps=fps, loop=0 if loop else 1) as writer:
                    for frame_path in frames:
                        image = imageio.imread(frame_path)
                        writer.append_data(image)
                
                if optimize:
                
                    img = Image.open(output_path)
                    frames_pil = []
                    
                    for frame in ImageSequence.Iterator(img):
                        frames_pil.append(frame.copy())
                    
                    frames_pil[0].save(
                        output_path,
                        save_all=True,
                        append_images=frames_pil[1:],
                        optimize=optimize,
                        duration=int(1000/fps),
                        loop=0 if loop else 1,
                        quality=100,
                        quantize=colors
                    )
            
            QMessageBox.information(self, "Success", f"GIF saved to {output_path}")
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create GIF: {str(e)}")
        
        finally:
            self.progress_bar.setVisible(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GifCutterApp()
    window.show()
    sys.exit(app.exec_())

