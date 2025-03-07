# main.py
import os
import threading
import tkinter as tk
from tkinter import ttk

# Import lớp SRTTranslator
from srt_translator import SRTTranslator
from translation_apis import TranslationAPI
from gui import SRTTranslatorGUI

# Biến toàn cục để lưu trữ giao diện
gui = None


def update_status(message: str):
    """Cập nhật thông báo trạng thái."""
    if hasattr(update_status, "status_text") and update_status.status_text:
        # Nếu sử dụng GUI
        current_text = update_status.status_text.get("1.0", tk.END)
        lines = current_text.split("\n")
        # Giữ tối đa 15 dòng gần nhất
        if len(lines) > 15:
            lines = lines[-15:]
        lines.append(message)
        update_status.status_text.config(state=tk.NORMAL)
        update_status.status_text.delete("1.0", tk.END)
        update_status.status_text.insert(tk.END, "\n".join(lines) + "\n")
        update_status.status_text.see(tk.END)  # Cuộn đến cuối
        update_status.status_text.config(state=tk.DISABLED)
        # Cập nhật giao diện người dùng
        update_status.root.update()
    else:
        # Nếu sử dụng Terminal
        print(message)


def update_progress_bar(thread_id, current, total):
    """Cập nhật thanh tiến trình cho một luồng cụ thể"""
    global gui
    if gui and thread_id in gui.progress_bars and gui.progress_bars[thread_id]:
        progress = (current / total) * 100
        gui.progress_bars[thread_id]["bar"]["value"] = progress
        gui.progress_bars[thread_id]["label"].config(
            text=f"Thread {thread_id}: {current}/{total} ({progress:.1f}%)"
        )
        gui.root.update()


def start_translation(
    api_var,
    api_key_entry,
    base_url_entry,
    model_entry,
    input_file_entry,
    output_file_entry,
    threads_entry,
    batch_size_entry,
    retries_entry,
    bilingual_var,
    mode_var=None,
    directory_entry=None,
    file_suffix_var=None,
):
    global gui

    # Lấy chế độ dịch
    mode = mode_var.get() if mode_var else "file"

    bilingual = bilingual_var.get()
    # Lấy cấu hình từ giao diện
    api_type = api_var.get()
    api_key = api_key_entry.get().strip()

    try:
        num_threads = int(threads_entry.get().strip())
        batch_size = int(batch_size_entry.get().strip())
        max_retries_str = retries_entry.get().strip()
        max_retries = float("inf") if max_retries_str == "0" else int(max_retries_str)
    except ValueError:
        update_status(
            "Lỗi: Vui lòng nhập số hợp lệ cho số luồng, kích thước lô và số lần thử lại"
        )
        return

    # Kiểm tra đầu vào hợp lệ
    if not api_key:
        update_status("Lỗi: Vui lòng nhập API key")
        return

    # Kiểm tra đầu vào dựa trên chế độ
    if mode == "file":
        input_file = input_file_entry.get().strip()
        output_file = output_file_entry.get().strip()

        if not input_file or not os.path.exists(input_file):
            update_status(f"Lỗi: File đầu vào '{input_file}' không tồn tại")
            return

        if not output_file:
            update_status("Lỗi: Vui lòng nhập file đầu ra")
            return
    else:  # mode == "directory"
        directory = directory_entry.get().strip()

        if not directory or not os.path.isdir(directory):
            update_status(f"Lỗi: Thư mục '{directory}' không tồn tại")
            return

        file_suffix = file_suffix_var.get().strip() if file_suffix_var else "_vi"

    # Cấu hình API
    api_config = {"type": api_type, "key": api_key}
    if api_type == "novita":
        base_url = base_url_entry.get().strip()
        model = model_entry.get().strip()
        if not base_url or not model:
            update_status("Lỗi: Vui lòng nhập Base URL và Model cho Novita AI")
            return
        api_config["base_url"] = base_url
        api_config["model"] = model

    # Vô hiệu hóa nút bắt đầu trong quá trình dịch
    gui.start_button.config(state=tk.DISABLED)

    # Xóa các thanh tiến trình cũ nếu có
    for widget in gui.progress_bars_frame.winfo_children():
        widget.destroy()

    gui.progress_bars.clear()

    # Tạo thanh tiến trình mới
    for i in range(1, num_threads + 1):
        thread_frame = tk.Frame(gui.progress_bars_frame)
        thread_frame.pack(fill=tk.X, pady=2)

        label = tk.Label(
            thread_frame, text=f"Thread {i}: 0/0 (0%)", width=20, anchor="w"
        )
        label.pack(side=tk.LEFT, padx=5)

        progress_bar = ttk.Progressbar(thread_frame, length=400, mode="determinate")
        progress_bar.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        gui.progress_bars[i] = {"bar": progress_bar, "label": label}

    # Chuyển sang tab tiến trình
    gui.tabs.select(1)

    # Khởi tạo SRTTranslator với các hàm callback
    translator = SRTTranslator(update_status, update_progress_bar)

    # Khởi chạy dịch trong một luồng riêng biệt để không chặn GUI
    def translation_thread():
        try:
            if mode == "file":
                # Dịch file đơn lẻ
                success = translator.translate_file(
                    input_file,
                    output_file,
                    api_config,
                    num_threads,
                    batch_size,
                    max_retries,
                    bilingual,
                )

                if not success:
                    update_status(
                        "Dịch thất bại. Vui lòng kiểm tra thông báo lỗi ở trên."
                    )
            else:  # mode == "directory"
                # Dịch toàn bộ thư mục
                update_status(
                    f"Bắt đầu dịch tất cả file SRT trong thư mục: {directory}"
                )
                results = translator.translate_directory(
                    directory,
                    api_config,
                    num_threads,
                    batch_size,
                    max_retries,
                    bilingual,
                    file_suffix,
                )

                # Hiển thị tổng kết chi tiết
                update_status("\n===== KẾT QUẢ CHI TIẾT =====")
                for file_path, success in results.items():
                    status = "Thành công" if success else "Thất bại"
                    update_status(f"{os.path.basename(file_path)}: {status}")

        finally:
            # Kích hoạt lại nút bắt đầu sau khi hoàn thành hoặc gặp lỗi
            gui.root.after(0, lambda: gui.start_button.config(state=tk.NORMAL))

    # Bắt đầu luồng dịch
    thread = threading.Thread(target=translation_thread)
    thread.daemon = True  # Cho phép chương trình thoát nếu luồng này vẫn chạy
    thread.start()


if __name__ == "__main__":
    # Khởi tạo giao diện
    api_config = {
        "type": "gemini",  # Giá trị mặc định
        "key": "",
        "base_url": "",
        "model": "",
    }

    gui = SRTTranslatorGUI(api_config, update_status, start_translation)
    gui.run()
