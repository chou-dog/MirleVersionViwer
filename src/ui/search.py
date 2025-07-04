try:
    from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox, QProgressBar, QDateEdit, QComboBox, QGroupBox, QGridLayout, QCheckBox
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDate
    from PyQt5.QtGui import QFont
    QT_AVAILABLE = True
except ImportError:
    try:
        from PySide2.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox, QProgressBar, QDateEdit, QComboBox, QGroupBox, QGridLayout, QCheckBox
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
    build_version_found = pyqtSignal(str, str, dict)  # 檔案名, 檔案內容, build version info
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
                # 提取開機時間、版本號和版本時間
                import re
                
                # 匹配時間格式 HH:MM:SS.mmm
                time_match = re.search(r'(\d{2}:\d{2}:\d{2}\.\d{3})', line)
                time_str = time_match.group(1) if time_match else "Unknown"
                
                # 匹配版本號格式 X.X.X
                version_match = re.search(r'build version :(\d+\.\d+\.\d+)', line)
                version_str = version_match.group(1) if version_match else "Unknown"
                
                # 匹配版本時間格式 YYYYMMDDHHMMSS
                version_time_match = re.search(r'(\d{12})', line)
                version_time_str = version_time_match.group(1) if version_time_match else "Unknown"
                
                return {
                    'time': time_str,
                    'version': version_str,
                    'version_time': version_time_str,
                    'full_line': line.strip()
                }
        return {
            'time': "Unknown",
            'version': "Unknown", 
            'version_time': "Unknown",
            'full_line': "build version not found"
        }


class SearchWindow(QMainWindow):
    def __init__(self, ssh_connection_info):
        super().__init__()
        self.ssh_connection_info = ssh_connection_info
        self.ssh_client = None
        self.file_worker = None
        
        self.setWindowTitle("AGV 版本查詢工具")
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
        
        # 檢查是否有login_window，如果有則不退出應用程式
        if hasattr(self, 'login_window') and self.login_window:
            # 如果是通過back_to_login創建的，保持login_window運行
            event.accept()
        else:
            # 如果是直接關閉（點擊X），則退出整個應用程式
            import sys
            event.accept()
            sys.exit(0)
    
    def create_widgets(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # 標題
        title_label = QLabel("AGV版本查詢工具")
        title_font = QFont("Arial", 16, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 連線資訊
        connection_info = "ssh已連線到: {}@{}:{}".format(
            self.ssh_connection_info.get('username', ''),
            self.ssh_connection_info.get('ip', ''),
            self.ssh_connection_info.get('port', '')
        )
        info_label = QLabel(connection_info)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("color: green; font-weight: bold;")
        main_layout.addWidget(info_label)
        
        # 簡潔的時間過濾區域
        time_filter_group = QGroupBox("時間過濾")
        time_filter_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: none;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 20px;
                padding: 0 8px 0 8px;
                color: #2c3e50;
            }
        """)
        time_filter_layout = QGridLayout()
        time_filter_layout.setHorizontalSpacing(5)  # 減少水平間距
        time_filter_layout.setVerticalSpacing(10)   # 設置垂直間距
        time_filter_group.setLayout(time_filter_layout)
        
        # 第一行：開始時間
        start_label = QLabel("Start:")
        time_filter_layout.addWidget(start_label, 0, 0)
        
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDate(QDate.currentDate().addDays(-1))
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setCalendarPopup(True)
        time_filter_layout.addWidget(self.start_date_edit, 0, 1)
        
        # 時間控制元件容器
        time_controls_layout = QHBoxLayout()
        time_controls_layout.setSpacing(10)  # 設置緊密間距
        
        self.start_hour_combo = QComboBox()
        self.start_hour_combo.setEditable(True)
        self.start_hour_combo.addItems([str(i).zfill(2) for i in range(24)])
        self.start_hour_combo.setCurrentText("00")
        self.start_hour_combo.setFixedWidth(50)
        time_controls_layout.addWidget(self.start_hour_combo)
        
        hour_label = QLabel("小時")
        hour_label.setFixedWidth(35)
        time_controls_layout.addWidget(hour_label)
        
        self.start_minute_combo = QComboBox()
        self.start_minute_combo.setEditable(True)
        self.start_minute_combo.addItems([str(i).zfill(2) for i in range(60)])
        self.start_minute_combo.setCurrentText("00")
        self.start_minute_combo.setFixedWidth(50)
        time_controls_layout.addWidget(self.start_minute_combo)
        
        minute_label = QLabel("分鐘")
        minute_label.setFixedWidth(35)
        time_controls_layout.addWidget(minute_label)
        
        self.start_second_combo = QComboBox()
        self.start_second_combo.setEditable(True)
        self.start_second_combo.addItems([str(i).zfill(2) for i in range(60)])
        self.start_second_combo.setCurrentText("00")
        self.start_second_combo.setFixedWidth(50)
        time_controls_layout.addWidget(self.start_second_combo)
        
        second_label = QLabel("秒鐘")
        second_label.setFixedWidth(35)
        time_controls_layout.addWidget(second_label)
        
        time_controls_layout.addStretch()  # 添加彈性空間
        
        time_controls_widget = QWidget()
        time_controls_widget.setLayout(time_controls_layout)
        time_filter_layout.addWidget(time_controls_widget, 0, 2, 1, 6)
        
        # 第二行：結束時間
        end_label = QLabel("End:")
        time_filter_layout.addWidget(end_label, 1, 0)
        
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setCalendarPopup(True)
        time_filter_layout.addWidget(self.end_date_edit, 1, 1)
        
        # 結束時間控制元件容器
        end_time_controls_layout = QHBoxLayout()
        end_time_controls_layout.setSpacing(10)  # 設置緊密間距
        
        self.end_hour_combo = QComboBox()
        self.end_hour_combo.setEditable(True)
        self.end_hour_combo.addItems([str(i).zfill(2) for i in range(24)])
        self.end_hour_combo.setCurrentText("23")
        self.end_hour_combo.setFixedWidth(50)
        end_time_controls_layout.addWidget(self.end_hour_combo)
        
        hour_label2 = QLabel("小時")
        hour_label2.setFixedWidth(35)
        end_time_controls_layout.addWidget(hour_label2)
        
        self.end_minute_combo = QComboBox()
        self.end_minute_combo.setEditable(True)
        self.end_minute_combo.addItems([str(i).zfill(2) for i in range(60)])
        self.end_minute_combo.setCurrentText("59")
        self.end_minute_combo.setFixedWidth(50)
        end_time_controls_layout.addWidget(self.end_minute_combo)
        
        minute_label2 = QLabel("分鐘")
        minute_label2.setFixedWidth(35)
        end_time_controls_layout.addWidget(minute_label2)
        
        self.end_second_combo = QComboBox()
        self.end_second_combo.setEditable(True)
        self.end_second_combo.addItems([str(i).zfill(2) for i in range(60)])
        self.end_second_combo.setCurrentText("59")
        self.end_second_combo.setFixedWidth(50)
        end_time_controls_layout.addWidget(self.end_second_combo)
        
        second_label2 = QLabel("秒鐘")
        second_label2.setFixedWidth(35)
        end_time_controls_layout.addWidget(second_label2)
        
        end_time_controls_layout.addStretch()  # 添加彈性空間
        
        end_time_controls_widget = QWidget()
        end_time_controls_widget.setLayout(end_time_controls_layout)
        time_filter_layout.addWidget(end_time_controls_widget, 1, 2, 1, 6)
        
        # 第三行：啟用時間過濾和快速設置按鈕
        self.enable_time_filter = QCheckBox("使用時間過濾進行篩選(未勾選為全部搜尋)")
        self.enable_time_filter.setChecked(True)
        self.enable_time_filter.toggled.connect(self.on_time_filter_toggled)
        time_filter_layout.addWidget(self.enable_time_filter, 2, 0, 1, 2)
        
        # 快捷按鈕布局
        button_container = QHBoxLayout()
        
        self.last_hour_btn = QPushButton("1小時前")
        self.last_hour_btn.clicked.connect(self.set_last_hour)
        self.last_hour_btn.setFixedSize(100, 30)
        button_container.addWidget(self.last_hour_btn)
        
        self.last_day_btn = QPushButton("24小時前")
        self.last_day_btn.clicked.connect(self.set_last_day)
        self.last_day_btn.setFixedSize(100, 30)
        button_container.addWidget(self.last_day_btn)
        
        button_container.addStretch()
        
        button_widget = QWidget()
        button_widget.setLayout(button_container)
        time_filter_layout.addWidget(button_widget, 2, 2, 1, 6)
        
        main_layout.addWidget(time_filter_group)
        
        # 美化的控制按鈕
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        self.scan_button = QPushButton("開始搜尋")
        self.scan_button.clicked.connect(self.scan_log_files)
        self.scan_button.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa;
                border: 1px solid #ddd;
                color: #495057;
                padding: 10px 20px;
                font-size: 13px;
                border-radius: 4px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
                border-color: #bbb;
            }
            QPushButton:pressed {
                background-color: #dee2e6;
            }
            QPushButton:disabled {
                background-color: #f8f9fa;
                color: #adb5bd;
                border-color: #e9ecef;
            }
        """)
        button_layout.addWidget(self.scan_button)
        
        self.back_button = QPushButton("回到ssh登入頁面")
        self.back_button.clicked.connect(self.back_to_login)
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa;
                border: 1px solid #ddd;
                color: #495057;
                padding: 10px 20px;
                font-size: 13px;
                border-radius: 4px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
                border-color: #bbb;
            }
            QPushButton:pressed {
                background-color: #dee2e6;
            }
        """)
        button_layout.addWidget(self.back_button)
        
        main_layout.addLayout(button_layout)
        
        # 簡潔的進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                text-align: center;
                background-color: #f8f9fa;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #6c757d;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self.progress_bar)
        
        # 簡潔的重啟次數顯示
        self.restart_count_label = QLabel("")
        self.restart_count_label.setStyleSheet("""
            QLabel {
                color: #dc3545;
                font-weight: bold;
                font-size: 14px;
                padding: 8px;
                background-color: #ffffff;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin: 5px;
            }
        """)
        self.restart_count_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.restart_count_label)
        
        # 簡潔的顯示區域
        main_display_group = QGroupBox("Agv版本訊息")
        main_display_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: none;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px 0 10px;
                color: #2c3e50;
            }
        """)
        main_display_layout = QVBoxLayout()
        
        # 簡潔的內容顯示區域
        self.content_display = QTextEdit()
        self.content_display.setReadOnly(True)
        self.content_display.setFont(QFont("Consolas", 11))
        self.content_display.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #ffffff;
                padding: 15px;
                line-height: 1.4;
            }
        """)
        
        main_display_layout.addWidget(self.content_display)
        main_display_layout.setContentsMargins(15, 15, 15, 15)
        main_display_group.setLayout(main_display_layout)
        
        main_layout.addWidget(main_display_group)
        
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
            start_str = "{} {}:{}:{}".format(
                self.start_date_edit.date().toString("yyyy-MM-dd"),
                self.start_hour_combo.currentText(),
                self.start_minute_combo.currentText(),
                self.start_second_combo.currentText()
            )
            end_str = "{} {}:{}:{}".format(
                self.end_date_edit.date().toString("yyyy-MM-dd"),
                self.end_hour_combo.currentText(),
                self.end_minute_combo.currentText(),
                self.end_second_combo.currentText()
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
                                int(self.start_hour_combo.currentText()), int(self.start_minute_combo.currentText()), int(self.start_second_combo.currentText()))
            end_time = datetime(end_date.year(), end_date.month(), end_date.day(),
                              int(self.end_hour_combo.currentText()), int(self.end_minute_combo.currentText()), int(self.end_second_combo.currentText()))
            
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
    
    def on_build_version_found(self, filename, content, build_version_info):
        """當找到包含build version的檔案時的回調"""
        # 解析檔案時間
        file_datetime = parse_filename_datetime(filename)
        file_time_str = file_datetime.strftime("%Y-%m-%d %H:%M:%S") if file_datetime else "Unknown time"
        
        # 格式化日誌條目
        log_entry = {
            'filename': filename,
            'file_time': file_time_str,
            'boot_time': build_version_info['time'],
            'version': build_version_info['version'],
            'version_time': build_version_info['version_time'],
            'full_line': build_version_info['full_line']
        }
        
        # 添加到日誌列表
        self.build_version_logs.append(log_entry)
        
        # 更新顯示
        self.update_display()
    
    def on_restart_count(self, count):
        """更新重啟次數顯示"""
        if self.enable_time_filter.isChecked():
            start_str = "{} {}:{}:{}".format(
                self.start_date_edit.date().toString("yyyy-MM-dd"),
                self.start_hour_combo.currentText(),
                self.start_minute_combo.currentText(),
                self.start_second_combo.currentText()
            )
            end_str = "{} {}:{}:{}".format(
                self.end_date_edit.date().toString("yyyy-MM-dd"),
                self.end_hour_combo.currentText(),
                self.end_minute_combo.currentText(),
                self.end_second_combo.currentText()
            )
            self.restart_count_label.setText("在 {} 到 {} 總共重開 {} 次".format(start_str, end_str, count))
        else:
            self.restart_count_label.setText("總共重開 {} 次".format(count))
    
    def update_display(self):
        """更新顯示內容"""
        # 按檔案時間排序日誌
        self.build_version_logs.sort(key=lambda x: x['file_time'])
        
        # 準備顯示內容 - 添加標題行和數據
        display_lines = []
        
        # 添加表頭
        header = "{:<20} {:<15} {:<15}".format("開機時間", "版本號", "版本時間")
        display_lines.append(header)
        display_lines.append("=" * 60)  # 分隔線
        
        # 添加數據行
        for log in self.build_version_logs:
            line = "{:<20} {:<15} {:<15}".format(
                log['boot_time'][:20],  # 限制長度避免格式錯亂
                log['version'][:15],
                log['version_time'][:15]
            )
            display_lines.append(line)
        
        # 更新單一顯示區域
        self.content_display.setText("\n".join(display_lines))
    
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
        self.start_hour_combo.setEnabled(enabled)
        self.start_minute_combo.setEnabled(enabled)
        self.start_second_combo.setEnabled(enabled)
        self.end_date_edit.setEnabled(enabled)
        self.end_hour_combo.setEnabled(enabled)
        self.end_minute_combo.setEnabled(enabled)
        self.end_second_combo.setEnabled(enabled)
        self.last_hour_btn.setEnabled(enabled)
        self.last_day_btn.setEnabled(enabled)
    
    def set_last_hour(self):
        """設置為最近一小時"""
        from datetime import datetime, timedelta
        
        current_time = datetime.now()
        start_time = current_time - timedelta(hours=1)
        
        # 設置開始時間
        self.start_date_edit.setDate(QDate(start_time.year, start_time.month, start_time.day))
        self.start_hour_combo.setCurrentText(str(start_time.hour).zfill(2))
        self.start_minute_combo.setCurrentText(str(start_time.minute).zfill(2))
        self.start_second_combo.setCurrentText(str(start_time.second).zfill(2))
        
        # 設置結束時間
        self.end_date_edit.setDate(QDate(current_time.year, current_time.month, current_time.day))
        self.end_hour_combo.setCurrentText(str(current_time.hour).zfill(2))
        self.end_minute_combo.setCurrentText(str(current_time.minute).zfill(2))
        self.end_second_combo.setCurrentText(str(current_time.second).zfill(2))
    
    def set_last_day(self):
        """設置為最近24小時"""
        from datetime import datetime, timedelta
        
        current_time = datetime.now()
        start_time = current_time - timedelta(days=1)
        
        # 設置開始時間
        self.start_date_edit.setDate(QDate(start_time.year, start_time.month, start_time.day))
        self.start_hour_combo.setCurrentText(str(start_time.hour).zfill(2))
        self.start_minute_combo.setCurrentText(str(start_time.minute).zfill(2))
        self.start_second_combo.setCurrentText(str(start_time.second).zfill(2))
        
        # 設置結束時間
        self.end_date_edit.setDate(QDate(current_time.year, current_time.month, current_time.day))
        self.end_hour_combo.setCurrentText(str(current_time.hour).zfill(2))
        self.end_minute_combo.setCurrentText(str(current_time.minute).zfill(2))
        self.end_second_combo.setCurrentText(str(current_time.second).zfill(2))
    
    
    def back_to_login(self):
        """返回登入頁面"""
        # 清理資源
        if self.file_worker and self.file_worker.isRunning():
            self.file_worker.terminate()
            self.file_worker.wait(3000)
        
        if self.ssh_client:
            self.ssh_client.close()
        
        # 重新打開登入頁面
        from .login import SSHConnectionApp
        self.login_window = SSHConnectionApp()
        self.login_window.show()
        
        # 關閉當前窗口
        self.close()