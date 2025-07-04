try:
    from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox, QProgressBar, QDateEdit, QSpinBox, QGroupBox, QGridLayout, QCheckBox
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDate
    from PyQt5.QtGui import QFont
    QT_AVAILABLE = True
except ImportError:
    try:
        from PySide2.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox, QProgressBar, QDateEdit, QSpinBox, QGroupBox, QGridLayout, QCheckBox
        from PySide2.QtCore import Qt, QThread, Signal as pyqtSignal, QDate
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
    build_version_found = pyqtSignal(str, str, str)  # 檔案名, 檔案內容, build version
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # 當前進度, 總數
    restart_count = pyqtSignal(int)  # 重啟次數
    
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
            restart_count = 0
            
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
                    # 檢查是否包含build version
                    if "build version" in content.lower():
                        # 提取build version資訊
                        build_version = self.extract_build_version(content)
                        self.build_version_found.emit(filename, content, build_version)
                        restart_count += 1
                else:
                    self.error.emit("Failed to read file {}: {}".format(file_path, content))
                
                self.progress.emit(i + 1, total_files)
            
            # 計算重啟次數並發送信號
            self.restart_count.emit(restart_count)
            self.finished.emit()
            
        except Exception as e:
            self.error.emit("Error during file reading: {}".format(str(e)))
    
    def extract_build_version(self, content):
        """從檔案內容中提取build version資訊"""
        lines = content.split('\n')
        for line in lines:
            if 'build version' in line.lower():
                return line.strip()
        return "build version not found"


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
        
        # 第一行：開始時間
        start_label = QLabel("Start:")
        time_filter_layout.addWidget(start_label, 0, 0)
        
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDate(QDate.currentDate().addDays(-1))
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setCalendarPopup(True)
        time_filter_layout.addWidget(self.start_date_edit, 0, 1)
        
        self.start_hour_spin = QSpinBox()
        self.start_hour_spin.setRange(0, 23)
        self.start_hour_spin.setValue(0)
        self.start_hour_spin.setSuffix("時")
        time_filter_layout.addWidget(self.start_hour_spin, 0, 2)
        
        self.start_minute_spin = QSpinBox()
        self.start_minute_spin.setRange(0, 59)
        self.start_minute_spin.setValue(0)
        self.start_minute_spin.setSuffix("分")
        time_filter_layout.addWidget(self.start_minute_spin, 0, 3)
        
        self.start_second_spin = QSpinBox()
        self.start_second_spin.setRange(0, 59)
        self.start_second_spin.setValue(0)
        self.start_second_spin.setSuffix("秒")
        time_filter_layout.addWidget(self.start_second_spin, 0, 4)
        
        # 第二行：結束時間
        end_label = QLabel("End:")
        time_filter_layout.addWidget(end_label, 1, 0)
        
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setCalendarPopup(True)
        time_filter_layout.addWidget(self.end_date_edit, 1, 1)
        
        self.end_hour_spin = QSpinBox()
        self.end_hour_spin.setRange(0, 23)
        self.end_hour_spin.setValue(23)
        self.end_hour_spin.setSuffix("時")
        time_filter_layout.addWidget(self.end_hour_spin, 1, 2)
        
        self.end_minute_spin = QSpinBox()
        self.end_minute_spin.setRange(0, 59)
        self.end_minute_spin.setValue(59)
        self.end_minute_spin.setSuffix("分")
        time_filter_layout.addWidget(self.end_minute_spin, 1, 3)
        
        self.end_second_spin = QSpinBox()
        self.end_second_spin.setRange(0, 59)
        self.end_second_spin.setValue(59)
        self.end_second_spin.setSuffix("秒")
        time_filter_layout.addWidget(self.end_second_spin, 1, 4)
        
        # 第三行：啟用時間過濾和快速設置按鈕
        self.enable_time_filter = QCheckBox("Enable Time Filter")
        self.enable_time_filter.setChecked(True)
        self.enable_time_filter.toggled.connect(self.on_time_filter_toggled)
        time_filter_layout.addWidget(self.enable_time_filter, 2, 0, 1, 2)
        
        self.last_hour_btn = QPushButton("Last Hour")
        self.last_hour_btn.clicked.connect(self.set_last_hour)
        time_filter_layout.addWidget(self.last_hour_btn, 2, 2)
        
        self.last_day_btn = QPushButton("Last 24 Hours")
        self.last_day_btn.clicked.connect(self.set_last_day)
        time_filter_layout.addWidget(self.last_day_btn, 2, 3)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.reset_time_filter)
        time_filter_layout.addWidget(self.reset_btn, 2, 4)
        
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
        
        # 重啟次數顯示
        self.restart_count_label = QLabel("")
        self.restart_count_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")
        self.restart_count_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.restart_count_label)
        
        # Build version log 顯示
        self.content_display = QTextEdit()
        self.content_display.setReadOnly(True)
        self.content_display.setFont(QFont("Courier", 10))
        main_layout.addWidget(self.content_display)
        
        # 狀態標籤
        self.status_label = QLabel("Ready to scan log files")
        self.status_label.setStyleSheet("color: blue;")
        main_layout.addWidget(self.status_label)
        
        # 儲存build version日誌
        self.build_version_logs = []
        
        # 初始化時間過濾狀態
        self.on_time_filter_toggled()
    
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
        self.content_display.clear()
        self.build_version_logs.clear()
        self.restart_count_label.setText("")
        if self.enable_time_filter.isChecked():
            start_str = "{} {:02d}:{:02d}:{:02d}".format(
                self.start_date_edit.date().toString("yyyy-MM-dd"),
                self.start_hour_spin.value(),
                self.start_minute_spin.value(),
                self.start_second_spin.value()
            )
            end_str = "{} {:02d}:{:02d}:{:02d}".format(
                self.end_date_edit.date().toString("yyyy-MM-dd"),
                self.end_hour_spin.value(),
                self.end_minute_spin.value(),
                self.end_second_spin.value()
            )
            self.status_label.setText("Scanning build version logs from {} to {}...".format(start_str, end_str))
        else:
            self.status_label.setText("Scanning build version logs...")
        self.status_label.setStyleSheet("color: orange;")
        
        # 獲取時間過濾參數
        start_time = None
        end_time = None
        
        if self.enable_time_filter.isChecked():
            # 合併日期和時間
            start_date = self.start_date_edit.date()
            end_date = self.end_date_edit.date()
            
            start_time = datetime(start_date.year(), start_date.month(), start_date.day(),
                                self.start_hour_spin.value(), self.start_minute_spin.value(), self.start_second_spin.value())
            end_time = datetime(end_date.year(), end_date.month(), end_date.day(),
                              self.end_hour_spin.value(), self.end_minute_spin.value(), self.end_second_spin.value())
            
            # 驗證時間範圍
            if start_time > end_time:
                QMessageBox.warning(self, "Warning", "Start time must be earlier than end time")
                self.scan_button.setEnabled(True)
                self.progress_bar.setVisible(False)
                return
        
        # 啟動檔案讀取工作執行緒
        self.file_worker = FileReadWorker(self.ssh_client, "/run/media/mmcblk1p1/log/agvapp/", start_time, end_time)
        self.file_worker.build_version_found.connect(self.on_build_version_found)
        self.file_worker.progress.connect(self.on_progress_update)
        self.file_worker.error.connect(self.on_error)
        self.file_worker.restart_count.connect(self.on_restart_count)
        self.file_worker.finished.connect(self.on_scan_finished)
        self.file_worker.start()
    
    def on_build_version_found(self, filename, content, build_version):
        """當找到包含build version的檔案時的回調"""
        # 解析檔案時間
        file_datetime = parse_filename_datetime(filename)
        time_str = file_datetime.strftime("%Y-%m-%d %H:%M:%S") if file_datetime else "Unknown time"
        
        # 格式化日誌條目
        log_entry = "=== {} ({}) ===\n{}\n\n".format(filename, time_str, build_version)
        
        # 添加到日誌列表
        self.build_version_logs.append(log_entry)
        
        # 更新顯示
        self.update_display()
    
    def on_restart_count(self, count):
        """更新重啟次數顯示"""
        if self.enable_time_filter.isChecked():
            start_str = "{} {:02d}:{:02d}:{:02d}".format(
                self.start_date_edit.date().toString("yyyy-MM-dd"),
                self.start_hour_spin.value(),
                self.start_minute_spin.value(),
                self.start_second_spin.value()
            )
            end_str = "{} {:02d}:{:02d}:{:02d}".format(
                self.end_date_edit.date().toString("yyyy-MM-dd"),
                self.end_hour_spin.value(),
                self.end_minute_spin.value(),
                self.end_second_spin.value()
            )
            self.restart_count_label.setText("在 {} 到 {} 總共重開 {} 次".format(start_str, end_str, count))
        else:
            self.restart_count_label.setText("總共重開 {} 次".format(count))
    
    def update_display(self):
        """更新顯示內容"""
        # 按時間排序日誌
        self.build_version_logs.sort()
        
        # 顯示所有build version日誌
        all_logs = "".join(self.build_version_logs)
        self.content_display.setText(all_logs)
    
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
        
        log_count = len(self.build_version_logs)
        if log_count > 0:
            self.status_label.setText("Found {} build version logs".format(log_count))
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("No build version logs found")
            self.status_label.setStyleSheet("color: orange;")
    
    
    def on_time_filter_toggled(self):
        """時間過濾開關狀態改變時的處理"""
        enabled = self.enable_time_filter.isChecked()
        self.start_date_edit.setEnabled(enabled)
        self.start_hour_spin.setEnabled(enabled)
        self.start_minute_spin.setEnabled(enabled)
        self.start_second_spin.setEnabled(enabled)
        self.end_date_edit.setEnabled(enabled)
        self.end_hour_spin.setEnabled(enabled)
        self.end_minute_spin.setEnabled(enabled)
        self.end_second_spin.setEnabled(enabled)
        self.last_hour_btn.setEnabled(enabled)
        self.last_day_btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)
    
    def set_last_hour(self):
        """設置為最近一小時"""
        from datetime import datetime, timedelta
        
        current_time = datetime.now()
        start_time = current_time - timedelta(hours=1)
        
        # 設置開始時間
        self.start_date_edit.setDate(QDate(start_time.year, start_time.month, start_time.day))
        self.start_hour_spin.setValue(start_time.hour)
        self.start_minute_spin.setValue(start_time.minute)
        self.start_second_spin.setValue(start_time.second)
        
        # 設置結束時間
        self.end_date_edit.setDate(QDate(current_time.year, current_time.month, current_time.day))
        self.end_hour_spin.setValue(current_time.hour)
        self.end_minute_spin.setValue(current_time.minute)
        self.end_second_spin.setValue(current_time.second)
    
    def set_last_day(self):
        """設置為最近24小時"""
        from datetime import datetime, timedelta
        
        current_time = datetime.now()
        start_time = current_time - timedelta(days=1)
        
        # 設置開始時間
        self.start_date_edit.setDate(QDate(start_time.year, start_time.month, start_time.day))
        self.start_hour_spin.setValue(start_time.hour)
        self.start_minute_spin.setValue(start_time.minute)
        self.start_second_spin.setValue(start_time.second)
        
        # 設置結束時間
        self.end_date_edit.setDate(QDate(current_time.year, current_time.month, current_time.day))
        self.end_hour_spin.setValue(current_time.hour)
        self.end_minute_spin.setValue(current_time.minute)
        self.end_second_spin.setValue(current_time.second)
    
    def reset_time_filter(self):
        """重置時間過濾為預設值"""
        self.start_date_edit.setDate(QDate.currentDate().addDays(-1))
        self.start_hour_spin.setValue(0)
        self.start_minute_spin.setValue(0)
        self.start_second_spin.setValue(0)
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_hour_spin.setValue(23)
        self.end_minute_spin.setValue(59)
        self.end_second_spin.setValue(59)
    
    def back_to_login(self):
        """返回登入頁面"""
        from .login import SSHConnectionApp
        
        self.login_window = SSHConnectionApp()
        self.login_window.show()
        self.close()