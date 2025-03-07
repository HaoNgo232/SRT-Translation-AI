import os
import re
import time
import pickle
import concurrent.futures
import tkinter as tk
from tkinter import filedialog, ttk
from typing import List, Dict, Optional
import sys

# Import lớp API từ module khác
from translation_apis import TranslationAPI

def parse_srt(file_path: str) -> List[Dict]:
    """
    Phân tích file SRT thành danh sách các mục phụ đề.
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    subtitle_pattern = r'(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\s+([\s\S]*?)(?=\n\s*\n|\Z)'
    matches = re.findall(subtitle_pattern, content, re.MULTILINE)
    
    subtitles = []
    for match in matches:
        index, start_time, end_time, text = match
        subtitles.append({
            'index': int(index),
            'start_time': start_time,
            'end_time': end_time,
            'text': text.strip()
        })
    
    return subtitles

def write_srt(subtitles: List[Dict], output_file: str, bilingual: bool = False) -> None:
    """Ghi phụ đề vào file SRT."""
    with open(output_file, 'w', encoding='utf-8') as file:
        for subtitle in subtitles:
            file.write(f"{subtitle['index']}\n")
            file.write(f"{subtitle['start_time']} --> {subtitle['end_time']}\n")
            
            if bilingual and 'original_text' in subtitle:
                # Ghi cả phụ đề gốc và phụ đề đã dịch
                file.write(f"{subtitle['original_text']}\n{subtitle['text']}\n\n")
            else:
                # Chỉ ghi phụ đề đã dịch
                file.write(f"{subtitle['text']}\n\n")


def split_subtitles(subtitles: List[Dict], num_chunks: int) -> List[List[Dict]]:
    """Chia phụ đề thành các phần gần bằng nhau."""
    chunk_size = len(subtitles) // num_chunks
    if chunk_size == 0:
        chunk_size = 1
    
    chunks = []
    for i in range(0, len(subtitles), chunk_size):
        chunk = subtitles[i:i+chunk_size]
        if chunk:
            chunks.append(chunk)
    
    return chunks

def translate_subtitle_chunk(chunk: List[Dict], api_config: Dict, thread_id: int, 
                           progress_file: str, max_retries: int = float('inf'), 
                           batch_size: int = 10) -> List[Dict]:
    """Dịch một phần phụ đề, xử lý thành các lô nhỏ hơn."""
    total_batches = (len(chunk) + batch_size - 1) // batch_size
    translated_chunk = []
    
    # Kiểm tra tiến trình đã lưu
    chunk_progress = []
    chunk_progress_file = f"{progress_file}.chunk{thread_id}"
    if os.path.exists(chunk_progress_file):
        try:
            with open(chunk_progress_file, 'rb') as f:
                chunk_progress = pickle.load(f)
                update_status(f"Thread {thread_id}: Đã tải {len(chunk_progress)} phụ đề đã dịch từ tiến trình đã lưu")
        except Exception as e:
            update_status(f"Thread {thread_id}: Lỗi khi tải file tiến trình: {str(e)}")
    
    # Tìm vị trí để tiếp tục
    completed_indices = {sub['index'] for sub in chunk_progress}
    remaining_chunk = [sub for sub in chunk if sub['index'] not in completed_indices]
    
    if not remaining_chunk:
        update_status(f"Thread {thread_id}: Tất cả phụ đề trong phần này đã được dịch")
        return chunk_progress
    
    # Thêm phụ đề đã dịch vào kết quả
    translated_chunk = chunk_progress.copy()
    
    update_status(f"Thread {thread_id}: Phụ đề còn lại cần dịch: {len(remaining_chunk)}/{len(chunk)}")
    
    # Tạo đối tượng API từ cấu hình
    translation_api = TranslationAPI.create_api(api_config['type'], api_config)
    
    for batch_idx in range(0, len(remaining_chunk), batch_size):
        # Lấy một lô phụ đề
        batch = remaining_chunk[batch_idx:batch_idx + batch_size]
        current_batch = batch_idx // batch_size + 1
        remaining_batches = (len(remaining_chunk) + batch_size - 1) // batch_size
        
        update_status(f"Thread {thread_id}: Đang dịch lô {current_batch}/{remaining_batches} ({len(batch)} phụ đề)")
        update_progress_bar(thread_id, current_batch, remaining_batches)
        
        # Sử dụng API để dịch lô
        translated_batch = translation_api.translate_batch(batch, thread_id, update_status, max_retries)
        translated_chunk.extend(translated_batch)
        
        # Lưu tiến trình sau mỗi lô
        try:
            with open(chunk_progress_file, 'wb') as f:
                pickle.dump(translated_chunk, f)
            update_status(f"Thread {thread_id}: Đã lưu tiến trình ({len(translated_chunk)}/{len(chunk)} phụ đề)")
        except Exception as e:
            update_status(f"Thread {thread_id}: Lỗi khi lưu tiến trình: {str(e)}")
        
        # Nghỉ một chút để tránh giới hạn tốc độ
        time.sleep(1)
    
    # Dọn dẹp file tiến trình khi phần này hoàn thành
    if os.path.exists(chunk_progress_file):
        try:
            os.remove(chunk_progress_file)
            update_status(f"Thread {thread_id}: Đã xóa file tiến trình (phần đã hoàn thành)")
        except Exception as e:
            update_status(f"Thread {thread_id}: Lỗi khi xóa file tiến trình: {str(e)}")
    
    return translated_chunk

def save_global_progress(all_translated: List[Dict], progress_file: str) -> None:
    """Lưu tiến trình dịch toàn cục hiện tại."""
    try:
        with open(progress_file, 'wb') as f:
            pickle.dump(all_translated, f)
        update_status(f"Đã lưu tiến trình toàn cục ({len(all_translated)} phụ đề)")
    except Exception as e:
        update_status(f"Lỗi khi lưu tiến trình toàn cục: {str(e)}")

def load_global_progress(progress_file: str) -> List[Dict]:
    """Tải tiến trình dịch toàn cục."""
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'rb') as f:
                progress = pickle.load(f)
            update_status(f"Đã tải tiến trình toàn cục ({len(progress)} phụ đề)")
            return progress
        except Exception as e:
            update_status(f"Lỗi khi tải file tiến trình toàn cục: {str(e)}")
    return []

# Biến toàn cục để lưu trữ các thanh tiến trình
progress_bars = {}

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
    if thread_id in progress_bars and progress_bars[thread_id]:
        progress = (current / total) * 100
        progress_bars[thread_id]['bar']['value'] = progress
        progress_bars[thread_id]['label'].config(text=f"Thread {thread_id}: {current}/{total} ({progress:.1f}%)")
        update_status.root.update()

def process_chunk_batch(api_config: Dict, chunks: List[List[Dict]], 
                        max_workers: int, progress_file: str,
                        batch_size: int = 10, max_retries: int = float('inf')) -> List[Dict]:
    """Xử lý nhiều phần đồng thời sử dụng ThreadPoolExecutor."""
    all_translated = load_global_progress(progress_file)
    
    # Nếu có tiến trình hoàn chỉnh, chỉ cần trả về nó
    if all_translated:
        total_subtitles = sum(len(chunk) for chunk in chunks)
        if len(all_translated) >= total_subtitles:
            update_status("Tất cả phụ đề đã được dịch")
            return all_translated
    
    # Theo dõi phần nào đã hoàn thành
    completed_indices = {sub['index'] for sub in all_translated}
    completed_chunks = []
    remaining_chunks = []
    
    for i, chunk in enumerate(chunks):
        # Kiểm tra xem tất cả phụ đề trong phần này đã được dịch chưa
        if all(sub['index'] in completed_indices for sub in chunk):
            completed_chunks.append(i)
        else:
            remaining_chunks.append((i, chunk))
    
    update_status(f"Phần đã hoàn thành: {len(completed_chunks)}/{len(chunks)}")
    update_status(f"Phần còn lại: {len(remaining_chunks)}/{len(chunks)}")
    
    if not remaining_chunks:
        return all_translated
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Tạo danh sách để giữ kết quả tương lai
        future_to_chunk_idx = {}
        
        # Gửi công việc dịch cho các phần còn lại
        for i, chunk in remaining_chunks:
            future = executor.submit(
                translate_subtitle_chunk, 
                chunk, 
                api_config, 
                i + 1,  # Thread ID (bắt đầu từ 1)
                progress_file,
                max_retries,
                batch_size
            )
            future_to_chunk_idx[future] = i
        
        # Theo dõi tiến trình tổng thể
        completed_futures = 0
        total_futures = len(future_to_chunk_idx)
        
        # Xử lý kết quả khi hoàn thành
        for future in concurrent.futures.as_completed(future_to_chunk_idx):
            chunk_idx = future_to_chunk_idx[future]
            completed_futures += 1
            
            try:
                result = future.result()
                update_status(f"Phần {chunk_idx + 1} đã hoàn thành ({completed_futures}/{total_futures})")
                
                # Cập nhật all_translated với kết quả mới
                for sub in result:
                    # Xóa bất kỳ phụ đề hiện có nào có cùng chỉ số
                    all_translated = [s for s in all_translated if s['index'] != sub['index']]
                    # Thêm phụ đề mới
                    all_translated.append(sub)
                
                # Lưu tiến trình toàn cục sau khi mỗi phần hoàn thành
                save_global_progress(all_translated, progress_file)
                
            except Exception as e:
                update_status(f"Phần {chunk_idx + 1} gặp ngoại lệ: {e}")
                update_status(f"Chi tiết lỗi: {str(e)}")
                # Trong trường hợp ngoại lệ không xử lý, vẫn thêm phụ đề gốc
                if chunk_idx < len(chunks):
                    for sub in chunks[chunk_idx]:
                        if not any(s['index'] == sub['index'] for s in all_translated):
                            all_translated.append(sub)
    
    # Sắp xếp theo chỉ số để đảm bảo thứ tự chính xác
    all_translated.sort(key=lambda x: x['index'])
    save_global_progress(all_translated, progress_file)
    return all_translated

def gui_main():
    """Tạo giao diện người dùng sử dụng tkinter."""
    root = tk.Tk()
    root.title("Ứng dụng dịch phụ đề từ tiếng Anh sang tiếng Việt")
    root.geometry("700x750")
    
    # Frame cho các điều khiển chính
    main_frame = tk.Frame(root, padx=10, pady=10)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Tabbed interface
    tabs = ttk.Notebook(main_frame)
    tabs.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    # Tab cài đặt
    settings_tab = ttk.Frame(tabs)
    tabs.add(settings_tab, text="Cài đặt")
    
    # Tab tiến trình
    progress_tab = ttk.Frame(tabs)
    tabs.add(progress_tab, text="Tiến trình")
    
    # ========== SETTINGS TAB ==========
    settings_frame = tk.LabelFrame(settings_tab, text="Cấu hình", padx=10, pady=10)
    settings_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    # Dropdown để chọn API
    api_frame = tk.Frame(settings_frame)
    api_frame.pack(fill=tk.X, pady=5)
    
    api_label = tk.Label(api_frame, text="Chọn dịch vụ API:", width=15, anchor='w')
    api_label.pack(side=tk.LEFT)
    
    api_var = tk.StringVar()
    api_var.set("gemini")  # Giá trị mặc định
    api_dropdown = ttk.Combobox(api_frame, textvariable=api_var, values=TranslationAPI.get_supported_apis(), state="readonly", width=30)
    api_dropdown.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    # API Key
    key_frame = tk.Frame(settings_frame)
    key_frame.pack(fill=tk.X, pady=5)
    
    key_label = tk.Label(key_frame, text="API Key:", width=15, anchor='w')
    key_label.pack(side=tk.LEFT)
    
    api_key_entry = tk.Entry(key_frame, width=50)
    api_key_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    # Novita frames - sẽ hiển thị/ẩn khi cần
    novita_frames = []
    
    # Novita API Base URL
    base_url_frame = tk.Frame(settings_frame)
    novita_frames.append(base_url_frame)
    
    base_url_label = tk.Label(base_url_frame, text="Novita Base URL:", width=15, anchor='w')
    base_url_label.pack(side=tk.LEFT)
    
    base_url_entry = tk.Entry(base_url_frame, width=50)
    base_url_entry.insert(0, "https://api.novita.ai/v3/openai")
    base_url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    # Novita Model
    model_frame = tk.Frame(settings_frame)
    novita_frames.append(model_frame)
    
    model_label = tk.Label(model_frame, text="Novita Model:", width=15, anchor='w')
    model_label.pack(side=tk.LEFT)
    
    model_entry = tk.Entry(model_frame, width=50)
    model_entry.insert(0, "meta-llama/llama-3.1-8b-instruct")
    model_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    # File đầu vào
    input_file_frame = tk.Frame(settings_frame)
    input_file_frame.pack(fill=tk.X, pady=5)
    
    input_file_label = tk.Label(input_file_frame, text="File phụ đề đầu vào:", width=15, anchor='w')
    input_file_label.pack(side=tk.LEFT)
    
    input_file_entry = tk.Entry(input_file_frame, width=50)
    input_file_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    def browse_input_file():
        filename = filedialog.askopenfilename(
            initialdir=".", 
            title="Chọn file SRT",
            filetypes=(("SRT files", "*.srt"), ("All files", "*.*"))
        )
        if filename:
            input_file_entry.delete(0, tk.END)
            input_file_entry.insert(0, filename)
            
            # Tự động đề xuất tên file đầu ra
            suggested_output = filename.replace(".srt", "_vi.srt")
            output_file_entry.delete(0, tk.END)
            output_file_entry.insert(0, suggested_output)
    
    input_file_button = tk.Button(input_file_frame, text="Duyệt...", command=browse_input_file)
    input_file_button.pack(side=tk.LEFT, padx=5)
    
    # File đầu ra
    output_file_frame = tk.Frame(settings_frame)
    output_file_frame.pack(fill=tk.X, pady=5)
    
    output_file_label = tk.Label(output_file_frame, text="File phụ đề đầu ra:", width=15, anchor='w')
    output_file_label.pack(side=tk.LEFT)
    
    output_file_entry = tk.Entry(output_file_frame, width=50)
    output_file_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    def browse_output_file():
        filename = filedialog.asksaveasfilename(
            initialdir=".", 
            title="Lưu file SRT",
            filetypes=(("SRT files", "*.srt"), ("All files", "*.*")),
            defaultextension=".srt"
        )
        if filename:
            output_file_entry.delete(0, tk.END)
            output_file_entry.insert(0, filename)
    
    output_file_button = tk.Button(output_file_frame, text="Duyệt...", command=browse_output_file)
    output_file_button.pack(side=tk.LEFT, padx=5)
    
    # Frame cho các cài đặt nâng cao
    advanced_frame = tk.LabelFrame(settings_tab, text="Cài đặt nâng cao", padx=10, pady=10)
    advanced_frame.pack(fill=tk.BOTH, padx=5, pady=5)
    
    # Tuỳ chọn song ngữ
    bilingual_frame = tk.Frame(advanced_frame)
    bilingual_frame.pack(fill=tk.X, pady=5)

    bilingual_var = tk.BooleanVar()
    bilingual_var.set(False)  # Mặc định: tắt
    bilingual_check = tk.Checkbutton(bilingual_frame, text="Chế độ song ngữ (giữ nguyên phụ đề gốc)", variable=bilingual_var)
    bilingual_check.pack(side=tk.LEFT, padx=5)
    
    # Số luồng
    threads_frame = tk.Frame(advanced_frame)
    threads_frame.pack(fill=tk.X, pady=5)
    
    threads_label = tk.Label(threads_frame, text="Số luồng dịch:", width=25, anchor='w')
    threads_label.pack(side=tk.LEFT)
    
    threads_entry = tk.Entry(threads_frame, width=10)
    threads_entry.insert(0, "5")  # Giá trị mặc định
    threads_entry.pack(side=tk.LEFT, padx=5)
    
    # Kích thước lô
    batch_size_frame = tk.Frame(advanced_frame)
    batch_size_frame.pack(fill=tk.X, pady=5)
    
    batch_size_label = tk.Label(batch_size_frame, text="Kích thước lô:", width=25, anchor='w')
    batch_size_label.pack(side=tk.LEFT)
    
    batch_size_entry = tk.Entry(batch_size_frame, width=10)
    batch_size_entry.insert(0, "10")  # Giá trị mặc định
    batch_size_entry.pack(side=tk.LEFT, padx=5)
    
    # Số lần thử lại
    retries_frame = tk.Frame(advanced_frame)
    retries_frame.pack(fill=tk.X, pady=5)
    
    retries_label = tk.Label(retries_frame, text="Số lần thử lại (0 = không giới hạn):", width=25, anchor='w')
    retries_label.pack(side=tk.LEFT)
    
    retries_entry = tk.Entry(retries_frame, width=10)
    retries_entry.insert(0, "0")  # Giá trị mặc định
    retries_entry.pack(side=tk.LEFT, padx=5)
    
    # ========== PROGRESS TAB ==========
    # Khu vực hiển thị tiến trình
    progress_frame = tk.Frame(progress_tab, padx=10, pady=10)
    progress_frame.pack(fill=tk.BOTH, expand=True)
    
    # Frame chứa các thanh tiến trình
    progress_bars_frame = tk.Frame(progress_frame)
    progress_bars_frame.pack(fill=tk.BOTH, expand=True)
    
    # Khu vực log
    log_frame = tk.Frame(progress_tab, padx=10, pady=10)
    log_frame.pack(fill=tk.BOTH, expand=True)
    
    log_label = tk.Label(log_frame, text="Nhật ký hoạt động:")
    log_label.pack(anchor=tk.W)
    
    status_text = tk.Text(log_frame, height=15, width=70, wrap=tk.WORD)
    status_text.pack(fill=tk.BOTH, expand=True)
    status_text.config(state=tk.DISABLED)
    
    # Thêm thanh cuộn cho status_text
    scrollbar = tk.Scrollbar(status_text)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    status_text.config(yscrollcommand=scrollbar.set)
    scrollbar.config(command=status_text.yview)
    
    # Lưu status_text để cập nhật từ hàm update_status
    update_status.status_text = status_text
    update_status.root = root
    
    # Xử lý hiển thị/ẩn các trường Novita khi thay đổi API
    def on_api_change(*args):
        if api_var.get() == "novita":
            for frame in novita_frames:
                frame.pack(fill=tk.X, pady=5, after=key_frame)
        else:
            for frame in novita_frames:
                frame.pack_forget()
    
    api_var.trace("w", on_api_change)
    
    # Button Frame
    button_frame = tk.Frame(root, padx=10, pady=10)
    button_frame.pack(fill=tk.X)
    
    # Nút bắt đầu
    def start_translation():
        bilingual = bilingual_var.get()
        # Lấy cấu hình từ giao diện
        api_type = api_var.get()
        api_key = api_key_entry.get().strip()
        input_file = input_file_entry.get().strip()
        output_file = output_file_entry.get().strip()
        
        try:
            num_threads = int(threads_entry.get().strip())
            batch_size = int(batch_size_entry.get().strip())
            max_retries_str = retries_entry.get().strip()
            max_retries = float('inf') if max_retries_str == '0' else int(max_retries_str)
        except ValueError:
            update_status("Lỗi: Vui lòng nhập số hợp lệ cho số luồng, kích thước lô và số lần thử lại")
            return
        
        # Kiểm tra đầu vào hợp lệ
        if not api_key:
            update_status("Lỗi: Vui lòng nhập API key")
            return
        
        if not input_file or not os.path.exists(input_file):
            update_status(f"Lỗi: File đầu vào '{input_file}' không tồn tại")
            return
        
        if not output_file:
            update_status("Lỗi: Vui lòng nhập file đầu ra")
            return
        
        # Cấu hình API
        api_config = {'type': api_type, 'key': api_key}
        if api_type == 'novita':
            base_url = base_url_entry.get().strip()
            model = model_entry.get().strip()
            if not base_url or not model:
                update_status("Lỗi: Vui lòng nhập Base URL và Model cho Novita AI")
                return
            api_config['base_url'] = base_url
            api_config['model'] = model
        
        # Vô hiệu hóa nút bắt đầu trong quá trình dịch
        start_button.config(state=tk.DISABLED)
        
        # Thiết lập file tiến trình
        progress_file = f"{output_file}.progress"
        
        # Tạo bản sao lưu của file đầu vào nếu chưa tồn tại
        backup_file = input_file + ".backup"
        if not os.path.exists(backup_file):
            import shutil
            shutil.copy2(input_file, backup_file)
            update_status(f"Đã tạo bản sao lưu tại: {backup_file}")
        
        # Xóa các thanh tiến trình cũ nếu có
        for widget in progress_bars_frame.winfo_children():
            widget.destroy()
        
        global progress_bars
        progress_bars.clear()
        
        # Chuyển sang tab tiến trình
        tabs.select(1)
        
        # Khởi chạy dịch trong một luồng riêng biệt để không chặn GUI
        def translation_thread():
            try:
                # Phân tích file SRT
                update_status("Đang phân tích file SRT...")
                subtitles = parse_srt(input_file)
                update_status(f"Tìm thấy {len(subtitles)} mục phụ đề")
                
                # Chia thành các phần
                chunks = split_subtitles(subtitles, num_threads)
                update_status(f"Đã chia thành {len(chunks)} phần")
                
                # Tạo các thanh tiến trình
                for i in range(1, len(chunks) + 1):
                    thread_frame = tk.Frame(progress_bars_frame)
                    thread_frame.pack(fill=tk.X, pady=2)
                    
                    label = tk.Label(thread_frame, text=f"Thread {i}: 0/0 (0%)", width=20, anchor='w')
                    label.pack(side=tk.LEFT, padx=5)
                    
                    progress_bar = ttk.Progressbar(thread_frame, length=400, mode='determinate')
                    progress_bar.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
                    
                    progress_bars[i] = {'bar': progress_bar, 'label': label}
                
                # Dịch
                update_status("\nBắt đầu dịch...")
                start_time = time.time()
                
                translated_subtitles = process_chunk_batch(
                    api_config, chunks, num_threads, progress_file, batch_size, max_retries
                )
                
                # Ghi file SRT đã dịch
                write_srt(translated_subtitles, output_file, bilingual)
                
                end_time = time.time()
                update_status(f"\nDịch hoàn thành trong {end_time - start_time:.2f} giây")
                update_status(f"File đã dịch được lưu tại: {output_file}")
                
                # Dọn dẹp file tiến trình khi hoàn thành thành công
                if os.path.exists(progress_file):
                    try:
                        os.remove(progress_file)
                        update_status("Đã xóa file tiến trình (dịch hoàn thành thành công)")
                    except Exception as e:
                        update_status(f"Lỗi khi xóa file tiến trình: {str(e)}")
                
            except Exception as e:
                update_status(f"\nLỗi trong quá trình dịch: {str(e)}")
                update_status("Dịch thất bại. Vui lòng kiểm tra thông báo lỗi ở trên.")
                update_status("Tiến trình đã được lưu. Bạn có thể thử lại để tiếp tục dịch.")
            
            finally:
                # Kích hoạt lại nút bắt đầu sau khi hoàn thành hoặc gặp lỗi
                root.after(0, lambda: start_button.config(state=tk.NORMAL))
        
        # Bắt đầu luồng dịch
        import threading
        translation_thread = threading.Thread(target=translation_thread)
        translation_thread.daemon = True  # Cho phép chương trình thoát nếu luồng này vẫn chạy
        translation_thread.start()
    
    start_button = tk.Button(button_frame, text="Bắt đầu dịch", command=start_translation, width=20, height=2)
    start_button.pack()
    
    # Gọi on_api_change để thiết lập ban đầu
    on_api_change()
    
    # Khởi chạy vòng lặp chính của GUI
    root.mainloop()

def console_main():
    """Phiên bản giao diện dòng lệnh."""
    print("=== Trình dịch phụ đề SRT (Tiếng Anh sang Tiếng Việt) ===")
    
    # Lấy danh sách API được hỗ trợ
    supported_apis = TranslationAPI.get_supported_apis()
    
    # Chọn API
    print("\nChọn API để sử dụng:")
    for i, api in enumerate(supported_apis, 1):
        print(f"{i}. {api.capitalize()} API")
    
    api_choice = input(f"Lựa chọn của bạn (1-{len(supported_apis)}): ").strip()
    
    try:
        idx = int(api_choice) - 1
        if 0 <= idx < len(supported_apis):
            api_type = supported_apis[idx]
        else:
            api_type = supported_apis[0]  # Default to first API
    except ValueError:
        api_type = supported_apis[0]  # Default to first API
    
    # Tuỳ chọn ché độ song ngữ
    bilingual_option = input("\nBật chế độ song ngữ (giữ nguyên phụ đề gốc)? (y/n) [n]: ").strip().lower()
    bilingual = bilingual_option in ('y', 'yes')
    
    # Cấu hình API
    api_config = {'type': api_type}
    
    if api_type == "gemini":
        api_config['key'] = input("Nhập Gemini API key: ").strip()
    elif api_type == "novita":
        api_config['key'] = input("Nhập Novita AI API key: ").strip()
        api_config['base_url'] = input("Nhập Novita AI base URL [https://api.novita.ai/v3/openai]: ").strip()
        if not api_config['base_url']:
            api_config['base_url'] = "https://api.novita.ai/v3/openai"
        
        api_config['model'] = input("Nhập model [meta-llama/llama-3.1-8b-instruct]: ").strip()
        if not api_config['model']:
            api_config['model'] = "meta-llama/llama-3.1-8b-instruct"
    # Có thể thêm các API khác ở đây
    
    # Đường dẫn file
    input_file = input("\nNhập đường dẫn đến file SRT: ").strip()
    if not os.path.exists(input_file):
        print(f"Lỗi: File '{input_file}' không tồn tại")
        return
    
    output_file = input("Nhập đường dẫn cho file SRT đã dịch: ").strip()
    if not output_file:
        # Tạo tên file đầu ra mặc định
        output_file = input_file.replace(".srt", "_vi.srt")
        if output_file == input_file:
            output_file = input_file + "_vi.srt"
        print(f"Sử dụng file đầu ra mặc định: {output_file}")
    
    # Cấu hình nâng cao
    num_threads = input("\nNhập số luồng dịch [5]: ").strip()
    num_threads = int(num_threads) if num_threads else 5
    
    batch_size = input("Nhập kích thước lô [10]: ").strip()
    batch_size = int(batch_size) if batch_size else 10
    
    max_retries_str = input("Nhập số lần thử lại tối đa (0 = không giới hạn) [0]: ").strip()
    max_retries = float('inf') if not max_retries_str or max_retries_str == '0' else int(max_retries_str)
    
    # Thiết lập file tiến trình
    progress_file = f"{output_file}.progress"
    
    # Tạo bản sao lưu của file đầu vào nếu chưa tồn tại
    backup_file = input_file + ".backup"
    if not os.path.exists(backup_file):
        import shutil
        shutil.copy2(input_file, backup_file)
        print(f"Đã tạo bản sao lưu tại: {backup_file}")
    
    # Phân tích file SRT
    print("\nĐang phân tích file SRT...")
    subtitles = parse_srt(input_file)
    print(f"Tìm thấy {len(subtitles)} mục phụ đề")
    
    # Chia thành các phần
    chunks = split_subtitles(subtitles, num_threads)
    print(f"Đã chia thành {len(chunks)} phần")
    
    # Dịch
    print("\nBắt đầu dịch...")
    start_time = time.time()
    
    try:
        translated_subtitles = process_chunk_batch(
            api_config, chunks, num_threads, progress_file, batch_size, max_retries
        )
        
        # Ghi file SRT đã dịch
        write_srt(translated_subtitles, output_file, bilingual)
        
        end_time = time.time()
        print(f"\nDịch hoàn thành trong {end_time - start_time:.2f} giây")
        print(f"File đã dịch được lưu tại: {output_file}")
        
        # Dọn dẹp file tiến trình khi hoàn thành thành công
        if os.path.exists(progress_file):
            try:
                os.remove(progress_file)
                print("Đã xóa file tiến trình (dịch hoàn thành thành công)")
            except Exception as e:
                print(f"Lỗi khi xóa file tiến trình: {str(e)}")
        
    except KeyboardInterrupt:
        print("\nQuá trình bị người dùng gián đoạn.")
        print("Tiến trình đã được lưu. Chạy lại script để tiếp tục dịch.")
        
    except Exception as e:
        print(f"\nLỗi trong quá trình dịch: {str(e)}")
        print("Dịch thất bại. Vui lòng kiểm tra thông báo lỗi ở trên.")
        print("Tiến trình đã được lưu. Chạy lại script để tiếp tục dịch.")

if __name__ == "__main__":
    # Kiểm tra xem có thể sử dụng tkinter không
    try:
        import tkinter
        # Kiểm tra xem chúng ta có chạy trong môi trường hỗ trợ GUI không
        if 'DISPLAY' in os.environ or os.name == 'nt':  # Linux với DISPLAY hoặc Windows
            gui_main()
        else:
            console_main()
    except ImportError:
        # Không có tkinter, sử dụng giao diện dòng lệnh
        console_main()
    except Exception as e:
        # Có lỗi khi khởi tạo tkinter, sử dụng giao diện dòng lệnh
        print(f"Lỗi khi khởi tạo giao diện đồ họa: {str(e)}")
        print("Chuyển sang giao diện dòng lệnh...")
        console_main()
