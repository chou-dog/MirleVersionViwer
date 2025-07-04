try:
    from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QListWidget, QSplitter, QMessageBox, QProgressBar, QListWidgetItem, QDateTimeEdit, QGroupBox, QGridLayout, QCheckBox
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDateTime
    from PyQt5.QtGui import QFont
    QT_AVAILABLE = True
except ImportError:
    try:
        from PySide2.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QListWidget, QSplitter, QMessageBox, QProgressBar, QListWidgetItem, QDateTimeEdit, QGroupBox, QGridLayout,QCheckBox
        from PySide2.QtCore import Qt, QThread, Signal as pyqtSignal, QDateTime
        from PySide2.QtGui import QFont
        QT_AVAILABLE = True
    except ImportError:
        print("Error: PyQt5 or PySide2 is required to run this application.")
        raise ImportError("Qt library not found")

import sys
import os
import re
from datetime import datetime
# 添加父目錄到Python路徑，以便導入其他模組
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ssh import SSHClient


def parse_filename_datetime(filename):
    """從檔案名稱中解析時間
    支援格式: agvapp_25_07_04_09_55_31.tmp 或 agvapp_YY_MM_DD_HH_MM_SS.*
    """
    # 匹配檔案名稱中的時間格式
    pattern = r'agvapp_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})'
    match = re.search(pattern, filename)
    
    if match:
        year, month, day, hour, minute, second = match.groups()
        # 假設年份為20XX
        year = int("20" + year)
        month = int(month)
        day = int(day)
        hour = int(hour)
        minute = int(minute)
        second = int(second)
        
        try:
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            # 如果日期無效，返回None
            return None
    
    return None


class FileReadWorker(QThread):
    """檔案讀取工作執行緒"""
    finished = pyqtSignal()
    file_found = pyqtSignal(str, str)  # 檔案名, 檔案內容
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # 當前進度, 總數
    
    def __init__(self, ssh_client, log_directory="/run/media/mmcblk1p1/log/agvapp/", start_time=None, end_time=None):
        super().__init__()
        self.ssh_client = ssh_client
        self.log_directory = log_directory
        self.start_time = start_time
        self.end_time = end_time
        
    def run(self):
        try:
            # 列出目錄中的所有.tmp檔案和agvapp日誌檔案
            success, result = self.ssh_client.execute_command("find {} \( -name '*.tmp' -o -name 'agvapp_*' \) -type f 2>/dev/null".format(self.log_directory))
            
            if not success:
                self.error.emit("Failed to list files in directory: {}".format(result))
                return
            
            files = result.strip().split('\n') if result.strip() else []
            files = [f for f in files if f.strip()]  # 移除空行
            
            if not files:
                self.error.emit("No .tmp or agvapp log files found in directory: {}".format(self.log_directory))
                return
            
            total_files = len(files)
            
            for i, file_path in enumerate(files):
                filename = os.path.basename(file_path)
                
                # 如果啟用了時間過濾，檢查檔案時間
                if self.start_time or self.end_time:
                    file_datetime = parse_filename_datetime(filename)
                    if file_datetime:
                        # 檢查是否在時間範圍內
                        if self.start_time and file_datetime < self.start_time:
                            self.progress.emit(i + 1, total_files)
                            continue
                        if self.end_time and file_datetime > self.end_time:
                            self.progress.emit(i + 1, total_files)
                            continue
                    else:
                        # 無法解析時間的檔案，如果啟用時間過濾則跳過
                        self.progress.emit(i + 1, total_files)
                        continue
                
                # 讀取檔案內容
                success, content = self.ssh_client.execute_command("cat '{}'".format(file_path))
                
                if success:
                    self.file_found.emit(filename, content)
                else:
                    self.error.emit("Failed to read file {}: {}".format(file_path, content))
                
                self.progress.emit(i + 1, total_files)
            
            self.finished.emit()
            
        except Exception as e:
            self.error.emit("Error during file reading: {}".format(str(e)))


class SearchWindow(QMainWindow):
    def __init__(self, ssh_connection_info):
        super().__init__()
        self.ssh_connection_info = ssh_connection_info
        self.ssh_client = None
        self.file_worker = None
        
        self.setWindowTitle("AGV Log File Viewer")
        self.setGeometry(200, 200, 1000, 700)
        
        self.create_widgets()
        self.connect_ssh()
        
    def closeEvent(self, event):
        """處理窗口關閉事件"""
        if self.file_worker and self.file_worker.isRunning():
            self.file_worker.terminate()
            self.file_worker.wait(3000)
        
        if self.ssh_client:
            self.ssh_client.close()
        
        event.accept()
    
    def create_widgets(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # 標題
        title_label = QLabel("AGV Log File Viewer")
        title_font = QFont("Arial", 16, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 連線資訊
        connection_info = "Connected to: {}@{}:{}".format(
            self.ssh_connection_info.get('username', ''),
            self.ssh_connection_info.get('ip', ''),
            self.ssh_connection_info.get('port', '')
        )
        info_label = QLabel(connection_info)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("color: green; font-weight: bold;")
        main_layout.addWidget(info_label)
        
        # 時間過濾區域
        time_filter_group = QGroupBox("Time Filter")
        time_filter_layout = QGridLayout()
        time_filter_group.setLayout(time_filter_layout)
        
        # 開始時間
        start_time_label = QLabel("Start Time:")
        time_filter_layout.addWidget(start_time_label, 0, 0)
        
        self.start_time_edit = QDateTimeEdit()
        self.start_time_edit.setDateTime(QDateTime.currentDateTime().addDays(-1))  # 預設為昨天
        self.start_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        time_filter_layout.addWidget(self.start_time_edit, 0, 1)
        
        # 結束時間
        end_time_label = QLabel("End Time:")
        time_filter_layout.addWidget(end_time_label, 1, 0)
        
        self.end_time_edit = QDateTimeEdit()
        self.end_time_edit.setDateTime(QDateTime.currentDateTime())  # 預設為現在
        self.end_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        time_filter_layout.addWidget(self.end_time_edit, 1, 1)
        
        # 啟用/停用時間過濾
        self.enable_time_filter = QCheckBox("Enable Time Filter")
        self.enable_time_filter.setChecked(True)
        time_filter_layout.addWidget(self.enable_time_filter, 2, 0, 1, 2)
        
        main_layout.addWidget(time_filter_group)
        
        # 控制按鈕
        button_layout = QHBoxLayout()
        
        self.scan_button = QPushButton("Scan Log Files")
        self.scan_button.clicked.connect(self.scan_log_files)
        button_layout.addWidget(self.scan_button)
        
        self.back_button = QPushButton("Back to Login")
        self.back_button.clicked.connect(self.back_to_login)
        button_layout.addWidget(self.back_button)
        
        main_layout.addLayout(button_layout)
        
        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # 分割器：檔案列表 + 檔案內容
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 檔案列表
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self.on_file_selected)
        splitter.addWidget(self.file_list)
        
        # 檔案內容顯示
        self.content_display = QTextEdit()
        self.content_display.setReadOnly(True)
        self.content_display.setFont(QFont("Courier", 10))
        splitter.addWidget(self.content_display)
        
        # 設定分割器比例
        splitter.setSizes([300, 700])
        
        # 狀態標籤
        self.status_label = QLabel("Ready to scan log files")
        self.status_label.setStyleSheet("color: blue;")
        main_layout.addWidget(self.status_label)
        
        # 儲存檔案內容的字典
        self.file_contents = {}
    
    def connect_ssh(self):
        """建立SSH連線"""
        try:
            self.ssh_client = SSHClient()
            success, message = self.ssh_client.connect(
                self.ssh_connection_info['ip'],
                self.ssh_connection_info['port'],
                self.ssh_connection_info['username'],
                self.ssh_connection_info.get('password', '')
            )
            
            if not success:
                QMessageBox.critical(self, "SSH Connection Failed", 
                                   "Failed to establish SSH connection:\n{}".format(message))
                self.close()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", "Error connecting to SSH: {}".format(str(e)))
            self.close()
    
    def scan_log_files(self):
        """掃描日誌檔案"""
        if not self.ssh_client:
            QMessageBox.warning(self, "Warning", "No SSH connection available")
            return
        
        self.scan_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.file_list.clear()
        self.content_display.clear()
        self.file_contents.clear()
        self.status_label.setText("Scanning log files...")
        self.status_label.setStyleSheet("color: orange;")
        
        # 獲取時間過濾參數
        start_time = None
        end_time = None
        
        if self.enable_time_filter.isChecked():
            start_time = self.start_time_edit.dateTime().toPython()
            end_time = self.end_time_edit.dateTime().toPython()
            
            # 驗證時間範圍
            if start_time > end_time:
                QMessageBox.warning(self, "Warning", "Start time must be earlier than end time")
                self.scan_button.setEnabled(True)
                self.progress_bar.setVisible(False)
                return
        
        # 啟動檔案讀取工作執行緒
        self.file_worker = FileReadWorker(self.ssh_client, "/run/media/mmcblk1p1/log/agvapp/", start_time, end_time)
        self.file_worker.file_found.connect(self.on_file_found)
        self.file_worker.progress.connect(self.on_progress_update)
        self.file_worker.error.connect(self.on_error)
        self.file_worker.finished.connect(self.on_scan_finished)
        self.file_worker.start()
    
    def on_file_found(self, filename, content):
        """當找到檔案時的回調"""
        # 添加檔案到列表
        item = QListWidgetItem(filename)
        self.file_list.addItem(item)
        
        # 儲存檔案內容
        self.file_contents[filename] = content
    
    def on_progress_update(self, current, total):
        """更新進度條"""
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)
            self.status_label.setText("Processing files: {}/{}".format(current, total))
    
    def on_error(self, error_message):
        """處理錯誤"""
        QMessageBox.critical(self, "Error", error_message)
        self.status_label.setText("Error: {}".format(error_message))
        self.status_label.setStyleSheet("color: red;")
    
    def on_scan_finished(self):
        """掃描完成"""
        self.scan_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        file_count = self.file_list.count()
        if file_count > 0:
            self.status_label.setText("Found {} log files".format(file_count))
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("No log files found")
            self.status_label.setStyleSheet("color: orange;")
    
    def on_file_selected(self, item):
        """當選擇檔案時顯示內容"""
        filename = item.text()
        if filename in self.file_contents:
            content = self.file_contents[filename]
            self.content_display.setText(content)
            self.status_label.setText("Displaying: {}".format(filename))
            self.status_label.setStyleSheet("color: blue;")
    
    def back_to_login(self):
        """返回登入頁面"""
        from .login import SSHConnectionApp
        
        self.login_window = SSHConnectionApp()
        self.login_window.show()
        self.close()