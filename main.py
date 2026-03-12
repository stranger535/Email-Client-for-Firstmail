import sys
import re
import logging
import traceback
import requests
from bs4 import BeautifulSoup
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSize
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLineEdit, QMessageBox,
    QListWidget, QListWidgetItem, QHBoxLayout, QFileDialog, QProgressBar,
    QStyle, QLabel, QSplitter, QTextBrowser
)
from PyQt6.QtGui import QClipboard

API_KEY = ""

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] [%(module)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler("app.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

setup_logging()

def get_all_messages(email: str, password: str, api_key: str):
    try:
        url = f"https://api.firstmail.ltd/v1/get/messages?username={email}&password={password}"
        headers = {"accept": "application/json", "X-API-KEY": api_key}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error("Ошибка в get_all_messages", exc_info=True)
        return {"error": str(e)}

def log_exception(extra_message=""):
    logging.error(f"{extra_message}\n{traceback.format_exc()}")

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return "Сообщение отсутствует"
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator="\n")
    text = re.sub(r'\n+', '\n', text).strip()
    return text.replace("\n", "<br>")

def highlight_links(text: str) -> str:
    pattern = re.compile(r'(https?://[^\s<]+)')
    replacement = r'<a href="link:\1" style="cursor:pointer; color: #00aaff; text-decoration: none;"><b>\1</b></a>'
    return pattern.sub(replacement, text)

def highlight_codes(text: str) -> str:
    parts = re.split(r'(<a .*?>.*?</a>)', text, flags=re.IGNORECASE | re.DOTALL)
    code_pattern = re.compile(r'\b(\d{6})\b')
    new_parts = []
    for part in parts:
        if part.lower().startswith('<a'):
            new_parts.append(part)
        else:
            new_parts.append(
                code_pattern.sub(
                    lambda m: f'<a href="copy:{m.group(1)}" style="cursor:pointer; color: #00ff00; text-decoration: none;"><b>{m.group(1)}</b></a>',
                    part
                )
            )
    return "".join(new_parts)

def highlight_emails(text: str) -> str:
    email_pattern = re.compile(r'([\w\.-]+@[\w\.-]+\.\w+)')
    return email_pattern.sub(lambda m: f"<span style='color: #A084CA;'><b>{m.group(1)}</b></span>", text)

def format_messages(messages) -> str:
    formatted_text = ""
    for msg in messages:
        sender = msg.get("from", "Неизвестный отправитель")
        subject = msg.get("subject", "Без темы")
        date = msg.get("date", "Без даты")
        body = msg.get("body", None) or msg.get("text", None) or msg.get("content", None) or "Сообщение отсутствует"
        content = clean_html(body)
        content = highlight_links(content)
        content = highlight_codes(content)
        content = highlight_emails(content)
        formatted_text += (
            f"<div style='border: 2px solid #444; padding: 30px; margin: 10px; border-radius: 10px; background-color: #222;'>"
            f"<p><b> Дата:</b> <span style='color: #1ABC9C;'>{date}</span></p>"
            f"<p><b> Отправитель:</b> <span style='color: #1ABC9C;'>{sender}</span></p>"
            f"<p><b>✉ Тема:</b> <span style='color: #1ABC9C;'><b>{subject}</b></span></p>"
            f"<p><span style='font-weight: normal;'>{content}</span></p>"
            f"<hr style='border: 1px solid #555;'>"
            f"</div>"
        )
    return formatted_text if formatted_text else "Нет сообщений на почте."

class FetchMessagesThread(QThread):
    result_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)
    def __init__(self, email: str, password: str, api_key: str):
        super().__init__()
        self.email = email
        self.password = password
        self.api_key = api_key
    def run(self):
        try:
            messages = get_all_messages(self.email, self.password, self.api_key)
            self.result_signal.emit(messages)
        except Exception as e:
            self.error_signal.emit(str(e))
            logging.error("Ошибка в FetchMessagesThread\n%s", e, exc_info=True)

class CustomTextBrowser(QTextBrowser):
    def mouseReleaseEvent(self, event):
        anchor = self.anchorAt(event.pos())
        if anchor:
            if anchor.startswith("copy:"):
                code = anchor.replace("copy:", "")
                QApplication.clipboard().setText(code)
                return
            elif anchor.startswith("link:"):
                link = anchor.replace("link:", "")
                QApplication.clipboard().setText(link)
                return
        super().mouseReleaseEvent(event)

class EmailChecker(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
    def initUI(self):
        self.setWindowTitle("Почтовый Клиент FIRSTMAIL")
        self.setGeometry(100, 100, 950, 700)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        self.email_list = QListWidget()
        self.email_list.itemClicked.connect(self.select_email)
        left_layout.addWidget(self.email_list)
        btn_layout = QHBoxLayout()
        self.load_button = QPushButton("Добавить почты")
        self.load_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.load_button.clicked.connect(self.load_email_file)
        btn_layout.addWidget(self.load_button)
        self.paste_bulk_button = QPushButton("Вставить список")
        self.paste_bulk_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.paste_bulk_button.clicked.connect(self.paste_bulk_from_clipboard)
        btn_layout.addWidget(self.paste_bulk_button)
        self.clear_button = QPushButton("Удалить почты")
        self.clear_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.clear_button.clicked.connect(self.clear_email_list)
        btn_layout.addWidget(self.clear_button)
        left_layout.addLayout(btn_layout)
        left_widget.setLayout(left_layout)
        main_splitter.addWidget(left_widget)
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        input_layout = QHBoxLayout()
        email_icon = QLabel()
        email_icon.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon).pixmap(QSize(24, 24)))
        input_layout.addWidget(email_icon)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Введите email:password")
        input_layout.addWidget(self.entry)
        self.copy_email_button = QPushButton("Скопировать почту")
        self.copy_email_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.copy_email_button.clicked.connect(self.copy_email)
        input_layout.addWidget(self.copy_email_button)
        right_layout.addLayout(input_layout)
        btn_layout2 = QHBoxLayout()
        self.paste_button = QPushButton("Вставить")
        self.paste_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.paste_button.clicked.connect(self.paste_from_clipboard)
        btn_layout2.addWidget(self.paste_button)
        self.login_button = QPushButton("Войти")
        self.login_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogYesButton))
        self.login_button.clicked.connect(self.fetch_and_display)
        btn_layout2.addWidget(self.login_button)
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_button.clicked.connect(self.fetch_and_display)
        btn_layout2.addWidget(self.refresh_button)
        right_layout.addLayout(btn_layout2)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        right_layout.addWidget(self.progress)
        self.result_text = CustomTextBrowser()
        self.result_text.setOpenExternalLinks(False)
        self.result_text.setStyleSheet("padding: 5px;")
        right_layout.addWidget(self.result_text)
        right_widget.setLayout(right_layout)
        main_splitter.addWidget(right_widget)
        main_splitter.setStretchFactor(1, 4)
        main_splitter.setStretchFactor(0, 1)
        overall_layout = QHBoxLayout()
        overall_layout.addWidget(main_splitter)
        self.setLayout(overall_layout)
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                font-family: Arial;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton {
                background-color: #444;
                border: 1px solid #555;
                border-radius: 10px;
                padding: 6px 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QLineEdit {
                background-color: #333;
                border: 1px solid #555;
                border-radius: 10px;
                padding: 6px;
            }
            QListWidget {
                background-color: #333;
                border: 1px solid #555;
                border-radius: 10px;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #007acc;
                color: white;
            }
            QTextBrowser {
                background-color: #333;
                border: 1px solid #555;
                border-radius: 10px;
                padding: 10px;
            }
            QProgressBar {
                background-color: #444;
                border: 1px solid #555;
                border-radius: 10px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #00aa00;
                border-radius: 10px;
            }
        """)
    def copy_email(self):
        text = self.entry.text().strip()
        email_only = text.split(":", 1)[0] if ":" in text else text
        QApplication.clipboard().setText(email_only)
        logging.info(f"Скопирована почта: {email_only}")
    def select_email(self, item: QListWidgetItem):
        self.entry.setText(item.text())
    def paste_from_clipboard(self):
        self.entry.setText(QApplication.clipboard().text().strip())
    def load_email_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите файл с почтами", "", "Текстовые файлы (*.txt)")
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    for line in file:
                        email = line.strip()
                        if email:
                            self.add_email_item(email)
                logging.info("Почты успешно загружены из файла.")
            except Exception as e:
                log_exception("Ошибка загрузки файла")
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл: {str(e)}")
    def paste_bulk_from_clipboard(self):
        clipboard_text = QApplication.clipboard().text()
        for line in clipboard_text.split("\n"):
            email = line.strip()
            if email:
                self.add_email_item(email)
        logging.info("Почты успешно вставлены из буфера обмена.")
    def add_email_item(self, email: str):
        item = QListWidgetItem(email)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.email_list.addItem(item)
    def clear_email_list(self):
        self.email_list.clear()
    def fetch_and_display(self):
        email_password = self.entry.text().strip()
        if not email_password:
            QMessageBox.warning(self, "Ошибка", "Введите email и пароль")
            return
        if ":" not in email_password:
            QMessageBox.warning(self, "Ошибка", "Неверный формат. Используй формат email:password")
            return
        email, password = email_password.split(":", 1)
        if not email or not password:
            QMessageBox.warning(self, "Ошибка", "Email или пароль не могут быть пустыми")
            return
        self.progress.show()
        self.result_text.clear()
        self.thread = FetchMessagesThread(email, password, API_KEY)
        self.thread.result_signal.connect(self.display_messages)
        self.thread.error_signal.connect(self.display_error)
        self.thread.finished.connect(lambda: self.progress.hide())
        self.thread.start()
    def display_messages(self, messages):
        if isinstance(messages, dict) and "error" in messages:
            self.result_text.setHtml(f"<p style='color: red;'>Ошибка: {messages['error']}</p>")
        elif isinstance(messages, list):
            self.result_text.setHtml(format_messages(messages))
        else:
            self.result_text.setHtml("<p style='color: #bbb;'>Нет сообщений на почте.</p>")
    def display_error(self, error_msg):
        self.result_text.setHtml(f"<p style='color: red;'>Ошибка: {error_msg}</p>")

def main():
    app = QApplication(sys.argv)
    window = EmailChecker()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()