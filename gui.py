import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Dict, List, Callable

class SRTTranslatorGUI:
    def __init__(self, api_config: Dict[str, str], update_status: Callable[[str], None], start_translation: Callable):
        """Khởi tạo giao diện người dùng."""
        self.root = tk.Tk()
        self.root.title("Ứng dụng dịch phụ đề từ tiếng Anh sang tiếng Việt")
        self.root.geometry("700x750")
        
        # Các biến giao diện
        self.api_var = tk.StringVar()
        self.api_var.set(api_config['type'])  # Giá trị mặc định
        self.bilingual_var = tk.BooleanVar()
        self.bilingual_var.set(False)  # Mặc định: tắt
        
        # Lưu trữ đối tượng progress_bars
        self.progress_bars = {}
        
        # Frame cho các điều khiển chính
        main_frame = tk.Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Tabbed interface
        self.tabs = ttk.Notebook(main_frame)
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab cài đặt
        settings_tab = ttk.Frame(self.tabs)
        self.tabs.add(settings_tab, text="Cài đặt")
        
        # Tab tiến trình
        progress_tab = ttk.Frame(self.tabs)
        self.tabs.add(progress_tab, text="Tiến trình")
        
        # ========== SETTINGS TAB ==========
        settings_frame = tk.LabelFrame(settings_tab, text="Cấu hình", padx=10, pady=10)
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Dropdown để chọn API
        api_frame = tk.Frame(settings_frame)
        api_frame.pack(fill=tk.X, pady=5)
        
        api_label = tk.Label(api_frame, text="Chọn dịch vụ API:", width=15, anchor='w')
        api_label.pack(side=tk.LEFT)
        
        api_dropdown = ttk.Combobox(api_frame, textvariable=self.api_var, values=["gemini", "novita"], state="readonly", width=30)
        api_dropdown.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # API Key
        key_frame = tk.Frame(settings_frame)
        key_frame.pack(fill=tk.X, pady=5)
        
        key_label = tk.Label(key_frame, text="API Key:", width=15, anchor='w')
        key_label.pack(side=tk.LEFT)
        
        self.api_key_entry = tk.Entry(key_frame, width=50)
        self.api_key_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Novita frames - sẽ hiển thị/ẩn khi cần
        self.novita_frames = []
        
        # Novita API Base URL
        base_url_frame = tk.Frame(settings_frame)
        self.novita_frames.append(base_url_frame)
        
        base_url_label = tk.Label(base_url_frame, text="Novita Base URL:", width=15, anchor='w')
        base_url_label.pack(side=tk.LEFT)
        
        self.base_url_entry = tk.Entry(base_url_frame, width=50)
        self.base_url_entry.insert(0, "https://api.novita.ai/v3/openai")
        self.base_url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Novita Model
        model_frame = tk.Frame(settings_frame)
        self.novita_frames.append(model_frame)
        
        model_label = tk.Label(model_frame, text="Novita Model:", width=15, anchor='w')
        model_label.pack(side=tk.LEFT)
        
        self.model_entry = tk.Entry(model_frame, width=50)
        self.model_entry.insert(0, "meta-llama/llama-3.1-8b-instruct")
        self.model_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # File đầu vào
        input_file_frame = tk.Frame(settings_frame)
        input_file_frame.pack(fill=tk.X, pady=5)
        
        input_file_label = tk.Label(input_file_frame, text="File phụ đề đầu vào:", width=15, anchor='w')
        input_file_label.pack(side=tk.LEFT)
        
        self.input_file_entry = tk.Entry(input_file_frame, width=50)
        self.input_file_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        input_file_button = tk.Button(input_file_frame, text="Duyệt...", command=self.browse_input_file)
        input_file_button.pack(side=tk.LEFT, padx=5)
        
        # File đầu ra
        output_file_frame = tk.Frame(settings_frame)
        output_file_frame.pack(fill=tk.X, pady=5)
        
        output_file_label = tk.Label(output_file_frame, text="File phụ đề đầu ra:", width=15, anchor='w')
        output_file_label.pack(side=tk.LEFT)
        
        self.output_file_entry = tk.Entry(output_file_frame, width=50)
        self.output_file_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        output_file_button = tk.Button(output_file_frame, text="Duyệt...", command=self.browse_output_file)
        output_file_button.pack(side=tk.LEFT, padx=5)
        
        # Frame cho các cài đặt nâng cao
        advanced_frame = tk.LabelFrame(settings_tab, text="Cài đặt nâng cao", padx=10, pady=10)
        advanced_frame.pack(fill=tk.BOTH, padx=5, pady=5)
        
        # Tuỳ chọn song ngữ
        bilingual_frame = tk.Frame(advanced_frame)
        bilingual_frame.pack(fill=tk.X, pady=5)

        bilingual_check = tk.Checkbutton(bilingual_frame, text="Chế độ song ngữ (giữ nguyên phụ đề gốc)", variable=self.bilingual_var)
        bilingual_check.pack(side=tk.LEFT, padx=5)
        
        # Số luồng
        threads_frame = tk.Frame(advanced_frame)
        threads_frame.pack(fill=tk.X, pady=5)
        
        threads_label = tk.Label(threads_frame, text="Số luồng dịch:", width=25, anchor='w')
        threads_label.pack(side=tk.LEFT)
        
        self.threads_entry = tk.Entry(threads_frame, width=10)
        self.threads_entry.insert(0, "5")  # Giá trị mặc định
        self.threads_entry.pack(side=tk.LEFT, padx=5)
        
        # Kích thước lô
        batch_size_frame = tk.Frame(advanced_frame)
        batch_size_frame.pack(fill=tk.X, pady=5)
        
        batch_size_label = tk.Label(batch_size_frame, text="Kích thước lô:", width=25, anchor='w')
        batch_size_label.pack(side=tk.LEFT)
        
        self.batch_size_entry = tk.Entry(batch_size_frame, width=10)
        self.batch_size_entry.insert(0, "10")  # Giá trị mặc định
        self.batch_size_entry.pack(side=tk.LEFT, padx=5)
        
        # Số lần thử lại
        retries_frame = tk.Frame(advanced_frame)
        retries_frame.pack(fill=tk.X, pady=5)
        
        retries_label = tk.Label(retries_frame, text="Số lần thử lại (0 = không giới hạn):", width=25, anchor='w')
        retries_label.pack(side=tk.LEFT)
        
        self.retries_entry = tk.Entry(retries_frame, width=10)
        self.retries_entry.insert(0, "0")  # Giá trị mặc định
        self.retries_entry.pack(side=tk.LEFT, padx=5)
        
        # ========== PROGRESS TAB ==========
        # Khu vực hiển thị tiến trình
        progress_frame = tk.Frame(progress_tab, padx=10, pady=10)
        progress_frame.pack(fill=tk.BOTH, expand=True)
        
        # Frame chứa các thanh tiến trình
        self.progress_bars_frame = tk.Frame(progress_frame)
        self.progress_bars_frame.pack(fill=tk.BOTH, expand=True)
        
        # Khu vực log
        log_frame = tk.Frame(progress_tab, padx=10, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        log_label = tk.Label(log_frame, text="Nhật ký hoạt động:")
        log_label.pack(anchor=tk.W)
        
        self.status_text = tk.Text(log_frame, height=15, width=70, wrap=tk.WORD)
        self.status_text.pack(fill=tk.BOTH, expand=True)
        self.status_text.config(state=tk.DISABLED)
        
        # Thêm thanh cuộn cho status_text
        scrollbar = tk.Scrollbar(self.status_text)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.status_text.yview)
        
        # Lưu status_text để cập nhật từ hàm update_status
        update_status.status_text = self.status_text
        update_status.root = self.root

        # Button Frame
        button_frame = tk.Frame(self.root, padx=10, pady=10)
        button_frame.pack(fill=tk.X)
        
        # Tạo hàm wrapper để truyền các tham số vào start_translation
        def on_start_click():
            start_translation(
                self.api_var, 
                self.api_key_entry, 
                self.base_url_entry, 
                self.model_entry, 
                self.input_file_entry, 
                self.output_file_entry, 
                self.threads_entry, 
                self.batch_size_entry, 
                self.retries_entry, 
                self.bilingual_var
            )
        
        self.start_button = tk.Button(button_frame, text="Bắt đầu dịch", command=on_start_click, width=20, height=2)
        self.start_button.pack()

        # Thiết lập sự kiện khi thay đổi API
        self.api_var.trace("w", self.on_api_change)
        # Gọi on_api_change để thiết lập ban đầu
        self.on_api_change()

    def browse_input_file(self):
        """Mở hộp thoại chọn file đầu vào"""
        filename = filedialog.askopenfilename(
            initialdir=".", 
            title="Chọn file SRT",
            filetypes=(("SRT files", "*.srt"), ("All files", "*.*"))
        )
        if filename:
            self.input_file_entry.delete(0, tk.END)
            self.input_file_entry.insert(0, filename)
            
            # Tự động đề xuất tên file đầu ra
            suggested_output = filename.replace(".srt", "_vi.srt")
            self.output_file_entry.delete(0, tk.END)
            self.output_file_entry.insert(0, suggested_output)

    def browse_output_file(self):
        """Mở hộp thoại chọn file đầu ra"""
        filename = filedialog.asksaveasfilename(
            initialdir=".", 
            title="Lưu file SRT",
            filetypes=(("SRT files", "*.srt"), ("All files", "*.*")),
            defaultextension=".srt"
        )
        if filename:
            self.output_file_entry.delete(0, tk.END)
            self.output_file_entry.insert(0, filename)

    def on_api_change(self, *args):
        """Xử lý khi thay đổi loại API"""
        if self.api_var.get() == "novita":
            for frame in self.novita_frames:
                frame.pack(fill=tk.X, pady=5, after=self.api_key_entry.master)
        else:
            for frame in self.novita_frames:
                frame.pack_forget()

    def run(self):
        """Khởi chạy vòng lặp chính của GUI"""
        self.root.mainloop()
