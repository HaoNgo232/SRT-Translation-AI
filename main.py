import os
import re
import time
import json
import pickle
import requests
import concurrent.futures
from typing import List, Dict, Optional

def parse_srt(file_path: str) -> List[Dict]:
    """
    Phân tích file SRT thành danh sách các mục phụ đề.
    
    Mỗi mục là một từ điển với các khóa:
    - index: số thứ tự phụ đề
    - start_time: thời điểm bắt đầu
    - end_time: thời điểm kết thúc
    - text: nội dung phụ đề
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Tách thành các mục phụ đề riêng lẻ
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

def write_srt(subtitles: List[Dict], output_file: str) -> None:
    """Ghi phụ đề vào file SRT."""
    with open(output_file, 'w', encoding='utf-8') as file:
        for subtitle in subtitles:
            file.write(f"{subtitle['index']}\n")
            file.write(f"{subtitle['start_time']} --> {subtitle['end_time']}\n")
            file.write(f"{subtitle['text']}\n\n")

def split_subtitles(subtitles: List[Dict], num_chunks: int) -> List[List[Dict]]:
    """Chia phụ đề thành các phần gần bằng nhau."""
    chunk_size = len(subtitles) // num_chunks
    if chunk_size == 0:
        chunk_size = 1
    
    chunks = []
    for i in range(0, len(subtitles), chunk_size):
        chunk = subtitles[i:i+chunk_size]
        if chunk:  # Đảm bảo không thêm các phần trống
            chunks.append(chunk)
    
    return chunks

def translate_batch(subtitles_batch: List[Dict], api_key: str, thread_id: int, max_retries: int = 10) -> List[Dict]:
    """
    Dịch một lô phụ đề từ tiếng Anh sang tiếng Việt sử dụng API Gemini.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    
    # Định dạng phụ đề dưới dạng danh sách đánh số
    subtitles_text = ""
    for i, subtitle in enumerate(subtitles_batch):
        subtitles_text += f"[{i+1}] {subtitle['text']}\n\n"
    
    # Tạo prompt yêu cầu dịch sang tiếng Việt
    prompt = (
        "Translate the following English subtitles to Vietnamese. Maintain the numbering format exactly as provided.\n"
        "Each subtitle is marked with [number] followed by text. Translate ONLY the text, keeping the [number] format.\n"
        "Return ONLY the translated subtitles with their numbers, no additional text or explanations.\n\n"
        f"{subtitles_text}"
    )
    
    data = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,  # Giảm nhiệt độ để có bản dịch ổn định hơn
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 8192,
            "responseMimeType": "text/plain"
        }
    }
    
    retries = 0
    while retries < max_retries:
        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    
                    # Kiểm tra xem chúng ta có định dạng phản hồi như mong đợi không
                    if ('candidates' in response_data and 
                        len(response_data['candidates']) > 0 and 
                        'content' in response_data['candidates'][0] and
                        'parts' in response_data['candidates'][0]['content'] and
                        len(response_data['candidates'][0]['content']['parts']) > 0 and
                        'text' in response_data['candidates'][0]['content']['parts'][0]):
                        
                        translated_text = response_data['candidates'][0]['content']['parts'][0]['text']
                        
                        # Phân tích phản hồi được dịch
                        translated_parts = re.findall(r'\[(\d+)\](.*?)(?=\n\[|\Z)', translated_text, re.DOTALL)
                        
                        # Nếu không nhận được định dạng như mong đợi, thử một mẫu linh hoạt hơn
                        if not translated_parts:
                            translated_parts = re.findall(r'(?:\[)?(\d+)(?:\])?[:\.\s]+(.*?)(?=\n(?:\[)?\d+(?:\])?[:\.\s]+|\Z)', 
                                                        translated_text, re.DOTALL)
                        
                        # Tạo ánh xạ từ chỉ số dịch đến văn bản đã dịch
                        translations = {}
                        for idx_str, text in translated_parts:
                            try:
                                idx = int(idx_str)
                                translations[idx] = text.strip()
                            except ValueError:
                                print(f"Thread {thread_id}: Cảnh báo - Định dạng chỉ số không hợp lệ trong bản dịch: {idx_str}")
                        
                        # Kiểm tra xem chúng ta đã nhận được bản dịch cho tất cả phụ đề chưa
                        if len(translations) < len(subtitles_batch) / 2:
                            print(f"Thread {thread_id}: Cảnh báo - Chỉ nhận được {len(translations)} bản dịch cho {len(subtitles_batch)} phụ đề")
                            
                            # Nếu chỉ nhận được một phần nhỏ bản dịch, thử lại
                            if retries < max_retries - 1:
                                retries += 1
                                time.sleep(2 ** retries)  # Tăng thời gian chờ theo cấp số nhân
                                continue
                        
                        # Áp dụng bản dịch cho phụ đề gốc
                        translated_subtitles = []
                        for i, subtitle in enumerate(subtitles_batch):
                            translated = subtitle.copy()
                            if i+1 in translations:
                                translated['text'] = translations[i+1]
                            else:
                                print(f"Thread {thread_id}: Cảnh báo - Thiếu bản dịch cho phụ đề {i+1}")
                            translated_subtitles.append(translated)
                        
                        return translated_subtitles
                    
                    else:
                        print(f"Thread {thread_id}: Định dạng phản hồi không như mong đợi (lần thử {retries+1}/{max_retries})")
                
                except json.JSONDecodeError:
                    print(f"Thread {thread_id}: Không thể phân tích phản hồi JSON (lần thử {retries+1}/{max_retries})")
            
            else:
                # Nếu đến đây, có vấn đề với phản hồi API
                print(f"Thread {thread_id}: Lỗi API (lần thử {retries+1}/{max_retries}): {response.status_code}")
            
            # Tăng thời gian chờ theo cấp số nhân
            sleep_time = min(2 ** retries, 60)  # Giới hạn ở 60 giây
            print(f"Thread {thread_id}: Thử lại sau {sleep_time} giây...")
            time.sleep(sleep_time)
            retries += 1
            
        except Exception as e:
            print(f"Thread {thread_id}: Ngoại lệ trong quá trình gọi API (lần thử {retries+1}/{max_retries}): {str(e)}")
            sleep_time = min(2 ** retries, 60)  # Giới hạn ở 60 giây
            time.sleep(sleep_time)
            retries += 1
    
    print(f"Thread {thread_id}: Không thể dịch lô sau {max_retries} lần thử")
    # Trả về phụ đề gốc nếu dịch thất bại
    return subtitles_batch

def translate_subtitle_chunk(chunk: List[Dict], api_key: str, thread_id: int, 
                            progress_file: str, max_retries: int = 10, 
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
                print(f"Thread {thread_id}: Đã tải {len(chunk_progress)} phụ đề đã dịch từ tiến trình đã lưu")
        except Exception as e:
            print(f"Thread {thread_id}: Lỗi khi tải file tiến trình: {str(e)}")
    
    # Tìm vị trí để tiếp tục
    completed_indices = {sub['index'] for sub in chunk_progress}
    remaining_chunk = [sub for sub in chunk if sub['index'] not in completed_indices]
    
    if not remaining_chunk:
        print(f"Thread {thread_id}: Tất cả phụ đề trong phần này đã được dịch")
        return chunk_progress
    
    # Thêm phụ đề đã dịch vào kết quả
    translated_chunk = chunk_progress.copy()
    
    print(f"Thread {thread_id}: Phụ đề còn lại cần dịch: {len(remaining_chunk)}/{len(chunk)}")
    
    for batch_idx in range(0, len(remaining_chunk), batch_size):
        # Lấy một lô phụ đề
        batch = remaining_chunk[batch_idx:batch_idx + batch_size]
        current_batch = batch_idx // batch_size + 1
        remaining_batches = (len(remaining_chunk) + batch_size - 1) // batch_size
        
        print(f"Thread {thread_id}: Đang dịch lô {current_batch}/{remaining_batches} ({len(batch)} phụ đề)")
        
        # Dịch lô
        translated_batch = translate_batch(batch, api_key, thread_id, max_retries)
        translated_chunk.extend(translated_batch)
        
        # Lưu tiến trình sau mỗi lô
        try:
            with open(chunk_progress_file, 'wb') as f:
                pickle.dump(translated_chunk, f)
            print(f"Thread {thread_id}: Đã lưu tiến trình ({len(translated_chunk)}/{len(chunk)} phụ đề)")
        except Exception as e:
            print(f"Thread {thread_id}: Lỗi khi lưu tiến trình: {str(e)}")
        
        # Nghỉ một chút để tránh giới hạn tốc độ
        time.sleep(2)
    
    # Dọn dẹp file tiến trình khi phần này hoàn thành
    if os.path.exists(chunk_progress_file):
        try:
            os.remove(chunk_progress_file)
            print(f"Thread {thread_id}: Đã xóa file tiến trình (phần đã hoàn thành)")
        except Exception as e:
            print(f"Thread {thread_id}: Lỗi khi xóa file tiến trình: {str(e)}")
    
    return translated_chunk

def save_global_progress(all_translated: List[Dict], progress_file: str) -> None:
    """Lưu tiến trình dịch toàn cục hiện tại."""
    try:
        with open(progress_file, 'wb') as f:
            pickle.dump(all_translated, f)
        print(f"Đã lưu tiến trình toàn cục ({len(all_translated)} phụ đề)")
    except Exception as e:
        print(f"Lỗi khi lưu tiến trình toàn cục: {str(e)}")

def load_global_progress(progress_file: str) -> List[Dict]:
    """Tải tiến trình dịch toàn cục."""
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'rb') as f:
                progress = pickle.load(f)
            print(f"Đã tải tiến trình toàn cục ({len(progress)} phụ đề)")
            return progress
        except Exception as e:
            print(f"Lỗi khi tải file tiến trình toàn cục: {str(e)}")
    return []

def process_chunk_batch(api_key: str, chunks: List[List[Dict]], 
                        max_workers: int, progress_file: str,
                        batch_size: int = 10, max_retries: int = 10) -> List[Dict]:
    """Xử lý nhiều phần đồng thời sử dụng ThreadPoolExecutor."""
    all_translated = load_global_progress(progress_file)
    
    # Nếu có tiến trình hoàn chỉnh, chỉ cần trả về nó
    if all_translated:
        total_subtitles = sum(len(chunk) for chunk in chunks)
        if len(all_translated) >= total_subtitles:
            print("Tất cả phụ đề đã được dịch")
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
    
    print(f"Phần đã hoàn thành: {len(completed_chunks)}/{len(chunks)}")
    print(f"Phần còn lại: {len(remaining_chunks)}/{len(chunks)}")
    
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
                api_key, 
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
                print(f"Phần {chunk_idx + 1} đã hoàn thành ({completed_futures}/{total_futures})")
                
                # Cập nhật all_translated với kết quả mới
                for sub in result:
                    # Xóa bất kỳ phụ đề hiện có nào có cùng chỉ số
                    all_translated = [s for s in all_translated if s['index'] != sub['index']]
                    # Thêm phụ đề mới
                    all_translated.append(sub)
                
                # Lưu tiến trình toàn cục sau khi mỗi phần hoàn thành
                save_global_progress(all_translated, progress_file)
                
            except Exception as e:
                print(f"Phần {chunk_idx + 1} gặp ngoại lệ: {e}")
                print(f"Chi tiết lỗi: {str(e)}")
                # Trong trường hợp ngoại lệ không xử lý, vẫn thêm phụ đề gốc
                # để tránh mất nội dung
                if chunk_idx < len(chunks):
                    for sub in chunks[chunk_idx]:
                        if not any(s['index'] == sub['index'] for s in all_translated):
                            all_translated.append(sub)
    
    # Sắp xếp theo chỉ số để đảm bảo thứ tự chính xác
    all_translated.sort(key=lambda x: x['index'])
    save_global_progress(all_translated, progress_file)
    return all_translated

def main():
    # Cấu hình
    print("=== Trình dịch phụ đề SRT (Tiếng Anh sang Tiếng Việt) ===")
    API_KEY = input("Nhập API key Gemini của bạn: ")
    input_file = input("Nhập đường dẫn đến file SRT: ")
    output_file = input("Nhập đường dẫn cho file SRT đã dịch: ")
    
    num_threads = input("Nhập số luồng dịch (mặc định 5): ")
    num_threads = int(num_threads) if num_threads.strip() else 5
    
    batch_size = input("Nhập kích thước lô (mặc định 10): ")
    batch_size = int(batch_size) if batch_size.strip() else 10
    
    max_retries = input("Nhập số lần thử lại tối đa (mặc định 10): ")
    max_retries = int(max_retries) if max_retries.strip() else 10
    
    if not os.path.exists(input_file):
        print(f"Lỗi: Không tìm thấy file đầu vào '{input_file}'")
        return
    
    # Thiết lập file tiến trình
    progress_file = f"{output_file}.progress"
    
    # Tạo bản sao lưu của file đầu vào nếu chưa tồn tại
    backup_file = input_file + ".backup"
    if not os.path.exists(backup_file):
        import shutil
        shutil.copy2(input_file, backup_file)
        print(f"Đã tạo bản sao lưu tại: {backup_file}")
    
    # Phân tích file SRT
    print("Đang phân tích file SRT...")
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
            API_KEY, chunks, num_threads, progress_file, batch_size, max_retries
        )
        
        # Ghi file SRT đã dịch
        write_srt(translated_subtitles, output_file)
        
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
    try:
        main()
    except KeyboardInterrupt:
        print("\nQuá trình bị người dùng gián đoạn. Đang thoát...")
        print("Tiến trình của bạn đã được lưu. Chạy lại script để tiếp tục.")
    except Exception as e:
        print(f"\nLỗi không mong đợi: {str(e)}")
        print("Tiến trình của bạn đã được lưu. Chạy lại script để tiếp tục.")
