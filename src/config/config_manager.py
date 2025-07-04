import json
import os
import base64
from typing import Dict, Any, Optional


class ConfigManager:
    """配置管理器，用於保存和讀取SSH連線設定"""
    
    def __init__(self, config_file: str = "ssh_config.json"):
        self.config_file = config_file
        self.config_path = os.path.join(os.path.dirname(__file__), "..", self.config_file)
        
    def _encode_password(self, password: str) -> str:
        """簡單編碼密碼（僅用於基本混淆，不是真正的加密）"""
        if not password:
            return ""
        return base64.b64encode(password.encode()).decode()
    
    def _decode_password(self, encoded_password: str) -> str:
        """解碼密碼"""
        if not encoded_password:
            return ""
        try:
            return base64.b64decode(encoded_password.encode()).decode()
        except:
            return ""
    
    def save_config(self, ip: str, port: int, username: str, password: str = "", allow_no_password: bool = False, profile_name: str = None) -> bool:
        """保存SSH連線配置"""
        try:
            # 載入現有配置
            existing_config = self._load_raw_config()
            if not existing_config:
                existing_config = {"connections": {}, "last_connection": ""}
            
            # 確保connections字典存在
            if "connections" not in existing_config:
                existing_config["connections"] = {}
            
            # 生成profile名稱
            if not profile_name:
                profile_name = "{}@{}:{}".format(username, ip, port)
            
            # 保存連線設定
            connection_data = {
                "ip": ip,
                "port": port,
                "username": username,
                "password": self._encode_password(password) if password else "",
                "allow_no_password": allow_no_password,
                "timestamp": self._get_timestamp()
            }
            
            existing_config["connections"][profile_name] = connection_data
            existing_config["last_connection"] = profile_name
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(existing_config, f, indent=4, ensure_ascii=False)
            
            return True
        except Exception as e:
            print("Error saving config: {}".format(e))
            return False
    
    def _load_raw_config(self) -> Optional[Dict[str, Any]]:
        """載入原始配置檔案"""
        try:
            if not os.path.exists(self.config_path):
                return None
                
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception as e:
            print("Error loading raw config: {}".format(e))
            return None
    
    def load_config(self) -> Optional[Dict[str, Any]]:
        """載入最後使用的SSH連線配置"""
        try:
            config = self._load_raw_config()
            if not config:
                return None
            
            # 新格式：從connections中載入
            if "connections" in config and "last_connection" in config:
                last_profile = config["last_connection"]
                if last_profile and last_profile in config["connections"]:
                    last_conn = config["connections"][last_profile]
                    return {
                        "ip": last_conn.get("ip", ""),
                        "port": last_conn.get("port", 22),
                        "username": last_conn.get("username", ""),
                        "password": self._decode_password(last_conn.get("password", "")),
                        "allow_no_password": last_conn.get("allow_no_password", False),
                        "timestamp": last_conn.get("timestamp", ""),
                        "profile_name": last_profile
                    }
            
            # 舊格式兼容性
            if "last_connection" in config and isinstance(config["last_connection"], dict):
                last_conn = config["last_connection"]
                return {
                    "ip": last_conn.get("ip", ""),
                    "port": last_conn.get("port", 22),
                    "username": last_conn.get("username", ""),
                    "password": self._decode_password(last_conn.get("password", "")),
                    "allow_no_password": last_conn.get("allow_no_password", False),
                    "timestamp": last_conn.get("timestamp", ""),
                    "profile_name": None
                }
            
            return None
        except Exception as e:
            print("Error loading config: {}".format(e))
            return None
    
    def get_all_connections(self) -> Dict[str, Dict[str, Any]]:
        """獲取所有保存的連線設定"""
        try:
            config = self._load_raw_config()
            if not config or "connections" not in config:
                return {}
            
            # 解碼所有密碼
            connections = {}
            for profile_name, conn_data in config["connections"].items():
                connections[profile_name] = {
                    "ip": conn_data.get("ip", ""),
                    "port": conn_data.get("port", 22),
                    "username": conn_data.get("username", ""),
                    "password": self._decode_password(conn_data.get("password", "")),
                    "allow_no_password": conn_data.get("allow_no_password", False),
                    "timestamp": conn_data.get("timestamp", "")
                }
            
            return connections
        except Exception as e:
            print("Error getting all connections: {}".format(e))
            return {}
    
    def load_connection_by_name(self, profile_name: str) -> Optional[Dict[str, Any]]:
        """根據profile名稱載入特定連線設定"""
        try:
            connections = self.get_all_connections()
            if profile_name in connections:
                conn_data = connections[profile_name]
                conn_data["profile_name"] = profile_name
                return conn_data
            return None
        except Exception as e:
            print("Error loading connection by name: {}".format(e))
            return None
    
    def delete_connection(self, profile_name: str) -> bool:
        """刪除特定的連線設定"""
        try:
            config = self._load_raw_config()
            if not config or "connections" not in config:
                return False
            
            if profile_name in config["connections"]:
                del config["connections"][profile_name]
                
                # 如果刪除的是最後使用的連線，清空last_connection
                if config.get("last_connection") == profile_name:
                    config["last_connection"] = ""
                
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                
                return True
            return False
        except Exception as e:
            print("Error deleting connection: {}".format(e))
            return False
    
    def clear_config(self) -> bool:
        """清除配置文件"""
        try:
            if os.path.exists(self.config_path):
                os.remove(self.config_path)
            return True
        except Exception as e:
            print("Error clearing config: {}".format(e))
            return False
    
    def _get_timestamp(self) -> str:
        """獲取當前時間戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def get_config_info(self) -> Dict[str, Any]:
        """獲取配置文件資訊"""
        if not os.path.exists(self.config_path):
            return {"exists": False, "size": 0, "modified": ""}
        
        try:
            stat = os.stat(self.config_path)
            from datetime import datetime
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            return {
                "exists": True,
                "size": stat.st_size,
                "modified": modified,
                "path": self.config_path
            }
        except:
            return {"exists": False, "size": 0, "modified": ""}


# 創建全域實例
config_manager = ConfigManager()