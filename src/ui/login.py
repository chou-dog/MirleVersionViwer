try:
    from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QFrame, QCheckBox, QComboBox
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QFont
    QT_AVAILABLE = True
except ImportError:
    try:
        from PySide2.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QFrame, QCheckBox, QComboBox
        from PySide2.QtCore import Qt, QThread, Signal as pyqtSignal
        from PySide2.QtGui import QFont
        QT_AVAILABLE = True
    except ImportError:
        print("Error: PyQt5 or PySide2 is required to run this application.")
        print("Please install one of them using:")
        print("  pip install PyQt5")
        print("  or")
        print("  pip install PySide2")
        raise ImportError("Qt library not found")

import sys
import os
# 添加父目錄到Python路徑，以便導入其他模組
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ssh import SSHWorker
from config import config_manager


class SSHConnectionApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SSH Connection Manager")
        self.setGeometry(100, 100, 400, 350)
        
        self.create_widgets()
        self.load_last_config()
        
    def closeEvent(self, event):
        """處理窗口關閉事件"""
        # 如果有正在運行的SSH工作執行緒，先停止它
        if hasattr(self, 'ssh_worker') and self.ssh_worker.isRunning():
            self.ssh_worker.terminate()
            self.ssh_worker.wait(3000)  # 等待最多3秒
        
        event.accept()  # 接受關閉事件
        
    def create_widgets(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)
        
        title_label = QLabel("Agv 版本查詢工具")
        title_font = QFont("Arial", 16, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 添加下拉式選單
        profile_layout = QHBoxLayout()
        profile_label = QLabel("快速選取:")
        profile_layout.addWidget(profile_label)
        
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("-- Select a saved connection --")
        self.profile_combo.currentTextChanged.connect(self.on_profile_selected)
        profile_layout.addWidget(self.profile_combo)
        
        self.delete_profile_button = QPushButton("刪除")
        self.delete_profile_button.clicked.connect(self.delete_selected_profile)
        self.delete_profile_button.setEnabled(False)
        profile_layout.addWidget(self.delete_profile_button)
        
        main_layout.addLayout(profile_layout)
        
        form_layout = QGridLayout()
        
        ip_label = QLabel("IP Address:")
        form_layout.addWidget(ip_label, 0, 0)
        self.ip_entry = QLineEdit()
        form_layout.addWidget(self.ip_entry, 0, 1)
        
        port_label = QLabel("Port:")
        form_layout.addWidget(port_label, 1, 0)
        self.port_entry = QLineEdit()
        self.port_entry.setText("22")
        form_layout.addWidget(self.port_entry, 1, 1)
        
        username_label = QLabel("Username:")
        form_layout.addWidget(username_label, 2, 0)
        self.username_entry = QLineEdit()
        self.username_entry.setText("root")
        form_layout.addWidget(self.username_entry, 2, 1)
        
        password_label = QLabel("Password:")
        form_layout.addWidget(password_label, 3, 0)
        self.password_entry = QLineEdit()
        self.password_entry.setEchoMode(QLineEdit.Password)
        form_layout.addWidget(self.password_entry, 3, 1)
        
        self.allow_no_password = QCheckBox("不須設定密碼進行登入")
        self.allow_no_password.stateChanged.connect(self.on_allow_no_password_changed)
        form_layout.addWidget(self.allow_no_password, 4, 0, 1, 2)
        
        main_layout.addLayout(form_layout)
        
        button_layout = QHBoxLayout()
        
        self.connect_button = QPushButton("連線")
        self.connect_button.clicked.connect(self.connect_ssh)
        button_layout.addWidget(self.connect_button)
        
        self.save_button = QPushButton("儲存至快速選取")
        self.save_button.clicked.connect(self.save_config)
        button_layout.addWidget(self.save_button)
        
        main_layout.addLayout(button_layout)
        
        self.status_label = QLabel("Ready to connect")
        self.status_label.setStyleSheet("color: blue;")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        main_layout.addStretch()
        
    def on_allow_no_password_changed(self, state):
        if state == Qt.Checked:
            self.password_entry.setEnabled(False)
            self.password_entry.setPlaceholderText("Password disabled - will use SSH key")
        else:
            self.password_entry.setEnabled(True)
            self.password_entry.setPlaceholderText("")
    
    def connect_ssh(self):
        ip = self.ip_entry.text().strip()
        port = self.port_entry.text().strip()
        username = self.username_entry.text().strip()
        password = self.password_entry.text()
        
        if not ip or not port or not username:
            QMessageBox.critical(self, "Error", "Please fill in IP address, port, and username")
            return
        
        # 檢查是否需要密碼
        if not self.allow_no_password.isChecked() and not password:
            QMessageBox.critical(self, "Error", "Please provide a password or check 'Allow connection without password'")
            return
        
        # 如果勾選了允許無密碼，則清空密碼
        if self.allow_no_password.isChecked():
            password = ""
            
        try:
            port = int(port)
        except ValueError:
            QMessageBox.critical(self, "Error", "Port must be a valid number")
            return
            
        self.connect_button.setEnabled(False)
        self.status_label.setText("連線中...")
        self.status_label.setStyleSheet("color: orange;")
        
        self.ssh_worker = SSHWorker(ip, port, username, password)
        self.ssh_worker.success.connect(self.connection_success)
        self.ssh_worker.error.connect(self.connection_failed)
        self.ssh_worker.start()
        
    def connection_success(self):
        self.connect_button.setEnabled(True)
        self.status_label.setText("連線成功!")
        self.status_label.setStyleSheet("color: green;")
        
        # 自動保存成功連線的配置
        self.save_config_automatically()
        
        # 跳轉到搜尋頁面
        self.open_search_window()
        
    def connection_failed(self, error_message):
        self.connect_button.setEnabled(True)
        self.status_label.setText("連線失敗")
        self.status_label.setStyleSheet("color: red;")
        QMessageBox.critical(self, "Connection Failed", "Failed to connect via SSH.\n\nError: {}".format(error_message))
    
    def save_config(self):
        """手動保存配置"""
        ip = self.ip_entry.text().strip()
        port = self.port_entry.text().strip()
        username = self.username_entry.text().strip()
        password = self.password_entry.text()
        allow_no_password = self.allow_no_password.isChecked()
        
        if not ip or not port or not username:
            QMessageBox.warning(self, "Warning", "Please fill in IP address, port, and username before saving")
            return
        
        try:
            port_int = int(port)
            if config_manager.save_config(ip, port_int, username, password, allow_no_password):
                QMessageBox.information(self, "Success", "Configuration saved successfully!")
                self.status_label.setText("配置已儲存")
                self.status_label.setStyleSheet("color: green;")
                
                # 刷新下拉式選單並選擇新保存的項目
                self.refresh_profile_combo()
                profile_name = "{}@{}:{}".format(username, ip, port_int)
                index = self.profile_combo.findText(profile_name)
                if index >= 0:
                    self.profile_combo.setCurrentIndex(index)
            else:
                QMessageBox.critical(self, "Error", "Failed to save configuration")
        except ValueError:
            QMessageBox.critical(self, "Error", "Port must be a valid number")
    
    def load_last_config(self):
        """啟動時自動載入上次的配置"""
        # 首先載入所有連線到下拉式選單
        self.refresh_profile_combo()
        
        # 然後載入最後使用的配置
        config = config_manager.load_config()
        if config:
            self.ip_entry.setText(config.get("ip", ""))
            self.port_entry.setText(str(config.get("port", 22)))
            self.username_entry.setText(config.get("username", ""))
            self.password_entry.setText(config.get("password", ""))
            self.allow_no_password.setChecked(config.get("allow_no_password", False))
            
            # 觸發checkbox狀態變化
            self.on_allow_no_password_changed(Qt.Checked if config.get("allow_no_password", False) else Qt.Unchecked)
            
            # 在下拉式選單中選擇對應的profile
            profile_name = config.get("profile_name")
            if profile_name:
                index = self.profile_combo.findText(profile_name)
                if index >= 0:
                    self.profile_combo.setCurrentIndex(index)
            
            self.status_label.setText("載入上次連線配置")
            self.status_label.setStyleSheet("color: blue;")
    
    def save_config_automatically(self):
        """連線成功後自動保存配置"""
        ip = self.ip_entry.text().strip()
        port = self.port_entry.text().strip()
        username = self.username_entry.text().strip()
        password = self.password_entry.text()
        allow_no_password = self.allow_no_password.isChecked()
        
        try:
            port_int = int(port)
            config_manager.save_config(ip, port_int, username, password, allow_no_password)
            # 刷新下拉式選單
            self.refresh_profile_combo()
        except:
            pass  # 靜默失敗，不影響連線成功的顯示
    
    def refresh_profile_combo(self):
        """刷新下拉式選單內容"""
        current_text = self.profile_combo.currentText()
        self.profile_combo.clear()
        self.profile_combo.addItem("-- Select a saved connection --")
        
        connections = config_manager.get_all_connections()
        for profile_name in sorted(connections.keys()):
            self.profile_combo.addItem(profile_name)
        
        # 恢復之前的選擇
        if current_text and current_text != "-- Select a saved connection --":
            index = self.profile_combo.findText(current_text)
            if index >= 0:
                self.profile_combo.setCurrentIndex(index)
    
    def on_profile_selected(self, profile_name):
        """當選擇下拉式選單項目時觸發"""
        if profile_name == "-- Select a saved connection --" or not profile_name:
            self.delete_profile_button.setEnabled(False)
            return
        
        # 啟用刪除按鈕
        self.delete_profile_button.setEnabled(True)
        
        # 載入選擇的配置
        config = config_manager.load_connection_by_name(profile_name)
        if config:
            self.ip_entry.setText(config.get("ip", ""))
            self.port_entry.setText(str(config.get("port", 22)))
            self.username_entry.setText(config.get("username", ""))
            self.password_entry.setText(config.get("password", ""))
            self.allow_no_password.setChecked(config.get("allow_no_password", False))
            
            # 觸發checkbox狀態變化
            self.on_allow_no_password_changed(Qt.Checked if config.get("allow_no_password", False) else Qt.Unchecked)
            
            self.status_label.setText("載入 '{}' ".format(profile_name))
            self.status_label.setStyleSheet("color: blue;")
    
    def delete_selected_profile(self):
        """刪除選擇的profile"""
        current_profile = self.profile_combo.currentText()
        if current_profile == "-- Select a saved connection --" or not current_profile:
            return
        
        reply = QMessageBox.question(self, "Confirm Delete", 
                                   "Are you sure you want to delete the connection profile '{}'?".format(current_profile),
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if config_manager.delete_connection(current_profile):
                QMessageBox.information(self, "Success", "Profile '{}' deleted successfully!".format(current_profile))
                self.refresh_profile_combo()
                
                # 清空表單
                self.ip_entry.setText("")
                self.port_entry.setText("22")
                self.username_entry.setText("root")
                self.password_entry.setText("")
                self.allow_no_password.setChecked(False)
                self.on_allow_no_password_changed(Qt.Unchecked)
                
                self.status_label.setText("配置刪除")
                self.status_label.setStyleSheet("color: orange;")
            else:
                QMessageBox.critical(self, "Error", "Failed to delete profile")
    
    def open_search_window(self):
        """開啟搜尋視窗"""
        from .search import SearchWindow
        
        # 準備連線資訊
        connection_info = {
            'ip': self.ip_entry.text().strip(),
            'port': int(self.port_entry.text().strip()),
            'username': self.username_entry.text().strip(),
            'password': self.password_entry.text() if not self.allow_no_password.isChecked() else ""
        }
        
        # 開啟搜尋視窗
        self.search_window = SearchWindow(connection_info)
        self.search_window.show()
        
        # 隱藏登入視窗
        self.hide()