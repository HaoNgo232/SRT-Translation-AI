# gui.py
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Dict, List, Callable

# Import các danh sách model
from translation_apis import (
    TranslationAPI,
    GEMINI_MODELS,
    NOVITA_MODELS,
    OPENROUTER_MODELS,
)


class SRTTranslatorGUI:
    def __init__(
        self,
        api_config: Dict[str, str],
        update_status: Callable[[str], None],
        start_translation: Callable,
    ):
        """Khởi tạo giao diện người dùng."""
        self.root = tk.Tk()

        self.root.title("Ứng dụng dịch phụ đề từ tiếng Anh sang tiếng Việt")
        self.root.geometry("700x750")

        # Các biến giao diện
        self.api_var = tk.StringVar()
        self.api_var.set(api_config["type"])  # Giá trị mặc định
        self.bilingual_var = tk.BooleanVar()
        self.bilingual_var.set(False)  # Mặc định: tắt

        # Thêm biến để lưu chế độ dịch (file đơn lẻ hoặc thư mục)
        self.mode_var = tk.StringVar()
        self.mode_var.set("file")  # Mặc định: dịch file đơn lẻ
        self.file_suffix_var = tk.StringVar()
        self.file_suffix_var.set("_vi")  # Mặc định: _vi
        self.model_var = tk.StringVar()
        self.custom_model_var = tk.BooleanVar()
        self.custom_model_var.set(False)

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
        api_label = tk.Label(api_frame, text="Chọn dịch vụ API:", width=15, anchor="w")
        api_label.pack(side=tk.LEFT)
        api_dropdown = ttk.Combobox(
            api_frame,
            textvariable=self.api_var,
            values=["gemini", "novita", "openrouter"],
            state="readonly",
            width=30,
        )
        api_dropdown.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # API Key
        key_frame = tk.Frame(settings_frame)
        key_frame.pack(fill=tk.X, pady=5)
        key_label = tk.Label(key_frame, text="API Key:", width=15, anchor="w")
        key_label.pack(side=tk.LEFT)
        self.api_key_entry = tk.Entry(key_frame, width=50)
        self.api_key_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Novita frames - sẽ hiển thị/ẩn khi cần
        self.novita_frames = []

        # Novita API Base URL
        base_url_frame = tk.Frame(settings_frame)
        self.novita_frames.append(base_url_frame)
        base_url_label = tk.Label(
            base_url_frame, text="Novita Base URL:", width=15, anchor="w"
        )
        base_url_label.pack(side=tk.LEFT)
        self.base_url_entry = tk.Entry(base_url_frame, width=50)
        self.base_url_entry.insert(0, "https://api.novita.ai/v3/openai")
        self.base_url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Thêm frame cho model selection
        model_frame = tk.Frame(settings_frame)
        model_frame.pack(fill=tk.X, pady=5)
        model_label = tk.Label(model_frame, text="Chọn model:", width=15, anchor="w")
        model_label.pack(side=tk.LEFT)

        # Listbox để chọn model với thông tin miễn phí
        self.model_listbox = tk.Listbox(
            model_frame, height=6, width=50, exportselection=0
        )
        self.model_listbox.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        model_scrollbar = tk.Scrollbar(model_frame, orient=tk.VERTICAL)
        model_scrollbar.config(command=self.model_listbox.yview)
        model_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.model_listbox.config(yscrollcommand=model_scrollbar.set)

        # Đặt sự kiện cho listbox - SỬA: thêm << và >>
        self.model_listbox.bind("<<ListboxSelect>>", self.on_model_select)

        # Checkbox cho phép nhập model tùy chỉnh
        custom_model_check = tk.Checkbutton(
            settings_frame,
            text="Model tùy chỉnh",
            variable=self.custom_model_var,
            command=self.toggle_custom_model,
        )
        custom_model_check.pack(anchor=tk.W, padx=15, pady=5)

        # Frame để nhập model tùy chỉnh (mặc định ẩn)
        self.custom_model_frame = tk.Frame(settings_frame)
        custom_model_label = tk.Label(
            self.custom_model_frame, text="Model tùy chỉnh:", width=15, anchor="w"
        )
        custom_model_label.pack(side=tk.LEFT)
        self.custom_model_entry = tk.Entry(self.custom_model_frame, width=50)
        self.custom_model_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Thiết lập sự kiện khi thay đổi API
        self.api_var.trace_add("write", self.on_api_change)

        # Gọi on_api_change để thiết lập ban đầu
        self.on_api_change()

        # Thêm frame chọn chế độ dịch
        mode_frame = tk.Frame(settings_frame)
        mode_frame.pack(fill=tk.X, pady=5)

        mode_label = tk.Label(mode_frame, text="Chế độ dịch:", width=15, anchor="w")
        mode_label.pack(side=tk.LEFT)

        # Radio button cho chế độ dịch file đơn lẻ
        file_radio = tk.Radiobutton(
            mode_frame,
            text="Dịch file đơn lẻ",
            variable=self.mode_var,
            value="file",
            command=self.update_mode_ui,
        )
        file_radio.pack(side=tk.LEFT, padx=5)

        # Radio button cho chế độ dịch thư mục
        dir_radio = tk.Radiobutton(
            mode_frame,
            text="Dịch thư mục",
            variable=self.mode_var,
            value="directory",
            command=self.update_mode_ui,
        )
        dir_radio.pack(side=tk.LEFT, padx=5)

        # Thêm frame cho đường dẫn thư mục
        self.directory_frame = tk.Frame(settings_frame)

        directory_label = tk.Label(
            self.directory_frame, text="Thư mục chứa SRT:", width=15, anchor="w"
        )
        directory_label.pack(side=tk.LEFT)

        self.directory_entry = tk.Entry(self.directory_frame, width=50)
        self.directory_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        directory_button = tk.Button(
            self.directory_frame, text="Duyệt...", command=self.browse_directory
        )
        directory_button.pack(side=tk.LEFT, padx=5)

        # Frame cho hậu tố file
        suffix_frame = tk.Frame(settings_frame)
        suffix_frame.pack(fill=tk.X, pady=5)

        suffix_label = tk.Label(
            suffix_frame, text="Hậu tố file đầu ra:", width=15, anchor="w"
        )
        suffix_label.pack(side=tk.LEFT)

        self.suffix_entry = tk.Entry(
            suffix_frame, width=10, textvariable=self.file_suffix_var
        )
        self.suffix_entry.pack(side=tk.LEFT, padx=5)

        suffix_help = tk.Label(suffix_frame, text="(Ví dụ: video.srt → video_vi.srt)")
        suffix_help.pack(side=tk.LEFT, padx=5)

        # File đầu vào
        input_file_frame = tk.Frame(settings_frame)
        input_file_frame.pack(fill=tk.X, pady=5)

        input_file_label = tk.Label(
            input_file_frame, text="File phụ đề đầu vào:", width=15, anchor="w"
        )
        input_file_label.pack(side=tk.LEFT)

        self.input_file_entry = tk.Entry(input_file_frame, width=50)
        self.input_file_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        input_file_button = tk.Button(
            input_file_frame, text="Duyệt...", command=self.browse_input_file
        )
        input_file_button.pack(side=tk.LEFT, padx=5)

        # File đầu ra
        output_file_frame = tk.Frame(settings_frame)
        output_file_frame.pack(fill=tk.X, pady=5)

        output_file_label = tk.Label(
            output_file_frame, text="File phụ đề đầu ra:", width=15, anchor="w"
        )
        output_file_label.pack(side=tk.LEFT)

        self.output_file_entry = tk.Entry(output_file_frame, width=50)
        self.output_file_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        output_file_button = tk.Button(
            output_file_frame, text="Duyệt...", command=self.browse_output_file
        )
        output_file_button.pack(side=tk.LEFT, padx=5)

        # Frame cho các cài đặt nâng cao
        advanced_frame = tk.LabelFrame(
            settings_tab, text="Cài đặt nâng cao", padx=10, pady=10
        )
        advanced_frame.pack(fill=tk.BOTH, padx=5, pady=5)

        # Tuỳ chọn song ngữ
        bilingual_frame = tk.Frame(advanced_frame)
        bilingual_frame.pack(fill=tk.X, pady=5)

        bilingual_check = tk.Checkbutton(
            bilingual_frame,
            text="Chế độ song ngữ (giữ nguyên phụ đề gốc)",
            variable=self.bilingual_var,
        )
        bilingual_check.pack(side=tk.LEFT, padx=5)

        # Số luồng
        threads_frame = tk.Frame(advanced_frame)
        threads_frame.pack(fill=tk.X, pady=5)

        threads_label = tk.Label(
            threads_frame, text="Số luồng dịch:", width=25, anchor="w"
        )
        threads_label.pack(side=tk.LEFT)

        self.threads_entry = tk.Entry(threads_frame, width=10)
        self.threads_entry.insert(0, "5")  # Giá trị mặc định
        self.threads_entry.pack(side=tk.LEFT, padx=5)

        # Kích thước lô
        batch_size_frame = tk.Frame(advanced_frame)
        batch_size_frame.pack(fill=tk.X, pady=5)

        batch_size_label = tk.Label(
            batch_size_frame, text="Kích thước lô:", width=25, anchor="w"
        )
        batch_size_label.pack(side=tk.LEFT)

        self.batch_size_entry = tk.Entry(batch_size_frame, width=10)
        self.batch_size_entry.insert(0, "10")  # Giá trị mặc định
        self.batch_size_entry.pack(side=tk.LEFT, padx=5)

        # Số lần thử lại
        retries_frame = tk.Frame(advanced_frame)
        retries_frame.pack(fill=tk.X, pady=5)

        retries_label = tk.Label(
            retries_frame,
            text="Số lần thử lại khi api phản hồi (0 = không giới hạn):",
            width=25,
            anchor="w",
        )
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
            # Xác định model được sử dụng
            if self.custom_model_var.get():
                model = self.custom_model_entry.get().strip()
            else:
                model = self.model_var.get()
            start_translation(
                self.api_var,
                self.api_key_entry,
                self.base_url_entry,
                model,
                self.input_file_entry,
                self.output_file_entry,
                self.threads_entry,
                self.batch_size_entry,
                self.retries_entry,
                self.bilingual_var,
                self.mode_var,  # Thêm chế độ dịch
                self.directory_entry,  # Thêm entry chứa đường dẫn thư mục
                self.file_suffix_var,  # Thêm hậu tố file
            )

        self.start_button = tk.Button(
            button_frame,
            text="Bắt đầu dịch",
            command=on_start_click,
            width=20,
            height=2,
        )
        self.start_button.pack()

        # Thiết lập sự kiện khi thay đổi API
        self.api_var.trace_add("write", self.on_api_change)
        # Gọi on_api_change để thiết lập ban đầu
        self.on_api_change()

        # Gọi update_mode_ui để cài đặt ban đầu
        self.update_mode_ui()

    def update_mode_ui(self):
        """Cập nhật giao diện dựa trên chế độ dịch được chọn"""
        mode = self.mode_var.get()

        if mode == "file":
            # Ẩn frame thư mục
            self.directory_frame.pack_forget()

            # Hiển thị frame file đầu vào và đầu ra
            self.input_file_entry.master.pack(fill=tk.X, pady=5)
            self.output_file_entry.master.pack(fill=tk.X, pady=5)
        else:
            # Hiển thị frame thư mục
            self.directory_frame.pack(
                fill=tk.X, pady=5, after=self.api_key_entry.master
            )

            # Ẩn frame file đầu vào và đầu ra
            self.input_file_entry.master.pack_forget()
            self.output_file_entry.master.pack_forget()

    def browse_directory(self):
        """Mở hộp thoại chọn thư mục"""
        directory = filedialog.askdirectory(
            initialdir=".", title="Chọn thư mục chứa file SRT"
        )
        if directory:
            self.directory_entry.delete(0, tk.END)
            self.directory_entry.insert(0, directory)

    def browse_input_file(self):
        """Mở hộp thoại chọn file đầu vào"""
        filename = filedialog.askopenfilename(
            initialdir=".",
            title="Chọn file SRT",
            filetypes=(("SRT files", "*.srt"), ("All files", "*.*")),
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
            defaultextension=".srt",
        )
        if filename:
            self.output_file_entry.delete(0, tk.END)
            self.output_file_entry.insert(0, filename)

    def on_api_change(self, *args):
        """Xử lý khi thay đổi loại API"""
        api_type = self.api_var.get()

        # Cập nhật danh sách model dựa trên API được chọn
        self.model_listbox.delete(0, tk.END)
        models = TranslationAPI.get_models_for_api(api_type)

        for i, (model_id, description, is_free) in enumerate(models):
            display_text = f"{model_id} - {description}"
            if is_free:
                display_text += " (FREE)"
            self.model_listbox.insert(tk.END, display_text)
            if is_free:
                self.model_listbox.itemconfig(
                    i, {"bg": "#e6ffe6"}
                )  # Nền xanh nhạt cho model miễn phí

        # Chọn model mặc định là model đầu tiên
        if models:
            self.model_listbox.selection_set(0)
            self.model_var.set(models[0][0])

        # Hiển thị/ẩn các frame Novita
        if api_type == "novita":
            for frame in self.novita_frames:
                frame.pack(fill=tk.X, pady=5, after=self.api_key_entry.master)
        else:
            for frame in self.novita_frames:
                frame.pack_forget()

        # Ẩn custom model nếu đang được hiển thị
        if self.custom_model_var.get():
            self.custom_model_var.set(False)
            self.toggle_custom_model()

    def on_model_select(self, event):
        """Lưu model được chọn từ listbox"""
        if self.model_listbox.curselection():
            index = self.model_listbox.curselection()[0]
            value = self.model_listbox.get(index)
            # Lấy model_id từ giá trị hiển thị (cắt phần "(FREE)" nếu có)
            model_id = value.split(" (FREE)")[0].split(" - ")[0].strip()
            self.model_var.set(model_id)

    def toggle_custom_model(self):
        """Hiển thị/ẩn trường nhập model tùy chỉnh"""
        if self.custom_model_var.get():
            self.custom_model_frame.pack(
                fill=tk.X, pady=5, after=self.model_listbox.master
            )
            self.model_listbox.config(state=tk.DISABLED)
        else:
            self.custom_model_frame.pack_forget()
            self.model_listbox.config(state=tk.NORMAL)

    def run(self):
        """Khởi chạy vòng lặp chính của GUI"""
        self.root.mainloop()
