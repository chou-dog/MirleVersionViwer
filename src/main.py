import sys

try:
    from PyQt5.QtWidgets import QApplication
    QT_AVAILABLE = True
except ImportError:
    try:
        from PySide2.QtWidgets import QApplication
        QT_AVAILABLE = True
    except ImportError:
        sys.exit(1)

from ui import SSHConnectionApp


def main():
    try:
        app = QApplication(sys.argv)
        window = SSHConnectionApp()
        window.show()
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        print("Program interrupted by user")
        sys.exit(0)
    except Exception as e:
        print("Error: {}".format(e))
        sys.exit(1)


if __name__ == "__main__":
    main()