import os
import re
import time
import pickle
import concurrent.futures
import tkinter as tk
from tkinter import ttk
from typing import List, Dict, Optional
import threading

# Import lớp API từ module khác
from translation_apis import TranslationAPI
from gui import SRTTranslatorGUI

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
        gui.progress_bars[thread_id]['bar']['value'] = progress
        gui.progress_bars[thread_id]['label'].config(text=f"Thread {thread_id}: {current}/{total} ({progress:.1f}%)")
        gui.root.update()

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

def start_translation(api_var, api_key_entry, base_url_entry, model_entry, input_file_entry, output_file_entry, threads_entry, batch_size_entry, retries_entry, bilingual_var):
    global gui
    
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
    gui.start_button.config(state=tk.DISABLED)
    
    # Thiết lập file tiến trình
    progress_file = f"{output_file}.progress"
    
    # Tạo bản sao lưu của file đầu vào nếu chưa tồn tại
    backup_file = input_file + ".backup"
    if not os.path.exists(backup_file):
        import shutil
        shutil.copy2(input_file, backup_file)
        update_status(f"Đã tạo bản sao lưu tại: {backup_file}")
    
    # Xóa các thanh tiến trình cũ nếu có
    for widget in gui.progress_bars_frame.winfo_children():
        widget.destroy()
    
    gui.progress_bars.clear()
    
    # Chuyển sang tab tiến trình
    gui.tabs.select(1)
    
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
                thread_frame = tk.Frame(gui.progress_bars_frame)
                thread_frame.pack(fill=tk.X, pady=2)
                
                label = tk.Label(thread_frame, text=f"Thread {i}: 0/0 (0%)", width=20, anchor='w')
                label.pack(side=tk.LEFT, padx=5)
                
                progress_bar = ttk.Progressbar(thread_frame, length=400, mode='determinate')
                progress_bar.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
                
                gui.progress_bars[i] = {'bar': progress_bar, 'label': label}
            
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
            gui.root.after(0, lambda: gui.start_button.config(state=tk.NORMAL))
    
    # Bắt đầu luồng dịch
    thread = threading.Thread(target=translation_thread)
    thread.daemon = True  # Cho phép chương trình thoát nếu luồng này vẫn chạy
    thread.start()

if __name__ == "__main__":
    # Khởi tạo giao diện
    api_config = {
        'type': 'gemini',  # Giá trị mặc định
        'key': '',
        'base_url': '',
        'model': ''
    }
    
    gui = SRTTranslatorGUI(api_config, update_status, start_translation)
    gui.run()
