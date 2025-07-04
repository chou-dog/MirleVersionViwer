import sys
import paramiko
import socket

try:
    from PyQt5.QtCore import QThread, pyqtSignal
    QT_AVAILABLE = True
except ImportError:
    try:
        from PySide2.QtCore import QThread, Signal as pyqtSignal
        QT_AVAILABLE = True
    except ImportError:
        import threading
        QT_AVAILABLE = False

if QT_AVAILABLE:
    class SSHWorker(QThread):
        """SSH連線工作執行緒，用於Qt介面"""
        success = pyqtSignal()
        error = pyqtSignal(str)
        
        def __init__(self, ip, port, username, password=""):
            super().__init__()
            self.ip = ip
            self.port = port
            self.username = username
            self.password = password
            
        def run(self):
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                if self.password:
                    ssh.connect(
                        hostname=self.ip,
                        port=self.port,
                        username=self.username,
                        password=self.password,
                        timeout=10
                    )
                else:
                    # 嘗試多種認證方式
                    connection_successful = False
                    last_error = None
                    
                    # 方式1: 嘗試SSH金鑰認證
                    try:
                        ssh.connect(
                            hostname=self.ip,
                            port=self.port,
                            username=self.username,
                            timeout=10,
                            look_for_keys=True,
                            allow_agent=True
                        )
                        connection_successful = True
                    except paramiko.AuthenticationException as e:
                        last_error = e
                        # 方式2: 嘗試空密碼
                        try:
                            ssh.connect(
                                hostname=self.ip,
                                port=self.port,
                                username=self.username,
                                password="",
                                timeout=10,
                                look_for_keys=False,
                                allow_agent=False
                            )
                            connection_successful = True
                        except paramiko.AuthenticationException:
                            pass
                    
                    if not connection_successful:
                        raise last_error if last_error else paramiko.AuthenticationException("All authentication methods failed")
                
                stdin, stdout, stderr = ssh.exec_command('echo "SSH connection successful"')
                result = stdout.read().decode()
                
                ssh.close()
                
                self.success.emit()
                
            except paramiko.AuthenticationException:
                if self.password:
                    self.error.emit("Authentication failed. Please check username and password.")
                else:
                    self.error.emit("Authentication failed. Tried multiple methods:\n• SSH key authentication\n• Empty password\n\nPlease:\n1. Provide a password, or\n2. Set up SSH key authentication, or\n3. Check if the server allows passwordless login\n4. Verify the username is correct")
            except paramiko.SSHException as e:
                self.error.emit("SSH connection error: {}".format(str(e)))
            except socket.timeout:
                self.error.emit("Connection timeout. Please check IP address and port.")
            except socket.gaierror:
                self.error.emit("Invalid hostname or IP address.")
            except Exception as e:
                self.error.emit("Connection failed: {}".format(str(e)))
else:
    class SSHWorker:
        """空的SSHWorker類，用於沒有Qt的環境"""
        def __init__(self, *args, **kwargs):
            raise ImportError("SSHWorker requires PyQt5 or PySide2")


class SSHClient:
    """SSH客戶端類，提供SSH連線功能"""
    
    def __init__(self):
        self.ssh = None
        
    def connect(self, ip, port, username, password=""):
        """連線到SSH伺服器"""
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if password:
                self.ssh.connect(
                    hostname=ip,
                    port=port,
                    username=username,
                    password=password,
                    timeout=10
                )
            else:
                # 嘗試多種認證方式
                connection_successful = False
                last_error = None
                
                # 方式1: 嘗試SSH金鑰認證
                try:
                    self.ssh.connect(
                        hostname=ip,
                        port=port,
                        username=username,
                        timeout=10,
                        look_for_keys=True,
                        allow_agent=True
                    )
                    connection_successful = True
                except paramiko.AuthenticationException as e:
                    last_error = e
                    # 方式2: 嘗試空密碼
                    try:
                        self.ssh.connect(
                            hostname=ip,
                            port=port,
                            username=username,
                            password="",
                            timeout=10,
                            look_for_keys=False,
                            allow_agent=False
                        )
                        connection_successful = True
                    except paramiko.AuthenticationException:
                        pass
                
                if not connection_successful:
                    raise last_error if last_error else paramiko.AuthenticationException("All authentication methods failed")
            
            return True, "Connection successful"
            
        except paramiko.AuthenticationException:
            if password:
                return False, "Authentication failed. Please check username and password."
            else:
                return False, "Authentication failed. Tried multiple methods:\n• SSH key authentication\n• Empty password\n\nPlease:\n1. Provide a password, or\n2. Set up SSH key authentication, or\n3. Check if the server allows passwordless login\n4. Verify the username is correct"
        except paramiko.SSHException as e:
            return False, "SSH connection error: {}".format(str(e))
        except socket.timeout:
            return False, "Connection timeout. Please check IP address and port."
        except socket.gaierror:
            return False, "Invalid hostname or IP address."
        except Exception as e:
            return False, "Connection failed: {}".format(str(e))
    
    def execute_command(self, command):
        """執行SSH命令"""
        if not self.ssh:
            return False, "Not connected to SSH server"
        
        try:
            stdin, stdout, stderr = self.ssh.exec_command(command)
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            if error:
                return False, error
            else:
                return True, output
                
        except Exception as e:
            return False, "Command execution failed: {}".format(str(e))
    
    def close(self):
        """關閉SSH連線"""
        if self.ssh:
            self.ssh.close()
            self.ssh = None
    
    def __del__(self):
        """析構函數，確保連線被關閉"""
        self.close()


def test_ssh_connection(ip, port, username, password=""):
    """測試SSH連線的便利函數"""
    client = SSHClient()
    success, message = client.connect(ip, port, username, password)
    client.close()
    return success, message


