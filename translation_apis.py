import re
import time
import json
import requests
from openai import OpenAI
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable

import re
import time
import json
import requests
from openai import OpenAI
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable, Tuple

# Định nghĩa các model có sẵn cho mỗi API với đánh dấu model miễn phí
# Mỗi tuple có format (model_id, description, is_free)

GEMINI_MODELS = [
    ("gemini-1.0-pro", "Gemini 1.0 Pro", False),
    ("gemini-1.5-pro", "Gemini 1.5 Pro", True),  # Miễn phí 120 req/phút
    ("gemini-1.5-flash", "Gemini 1.5 Flash", True),  # Miễn phí 120 req/phút
    ("gemini-2.0-pro", "Gemini 2.0 Pro", False),
    ("gemini-2.0-flash", "Gemini 2.0 Flash", True),  # Miễn phí 10 req/phút
    ("gemini-2.0-flash-exp", "Gemini 2.0 Flash Experimental", True),  # Miễn phí
]

NOVITA_MODELS = [
    ("meta-llama/llama-3.1-8b-instruct", "Llama 3.1 8B Instruct", False),
    ("meta-llama/llama-3.1-70b-instruct", "Llama 3.1 70B Instruct", False),
    ("anthropic/claude-3-opus-20240229", "Claude 3 Opus", False),
    ("anthropic/claude-3-sonnet-20240229", "Claude 3 Sonnet", False),
    ("anthropic/claude-3-haiku-20240307", "Claude 3 Haiku", False),
    ("mistralai/mistral-7b-instruct-v0.2", "Mistral 7B Instruct", False),
    ("mistralai/mixtral-8x7b-instruct-v0.1", "Mixtral 8x7B Instruct", False),
]

# Thêm danh sách model miễn phí của OpenRouter
# Dựa trên thông tin từ https://openrouter.ai/models?max_price=0
OPENROUTER_MODELS = [
    ("openai/gpt-4o", "GPT-4o", False),
    ("openai/gpt-4-turbo", "GPT-4 Turbo", False),
    ("openai/gpt-3.5-turbo", "GPT-3.5 Turbo", False),
    ("anthropic/claude-3-opus", "Claude 3 Opus", False),
    ("anthropic/claude-3-sonnet", "Claude 3 Sonnet", False),
    ("anthropic/claude-3-haiku", "Claude 3 Haiku", False),
    ("meta-llama/llama-3-70b-instruct", "Llama 3 70B Instruct", True),  # Miễn phí
    ("meta-llama/llama-3-8b-instruct", "Llama 3 8B Instruct", True),  # Miễn phí
    ("google/gemini-1.5-pro", "Gemini 1.5 Pro", True),  # Miễn phí qua OpenRouter
    ("google/gemini-1.5-flash", "Gemini 1.5 Flash", True),  # Miễn phí qua OpenRouter
    ("01-ai/yi-1.5-34b", "Yi 1.5 34B", True),  # Miễn phí
    ("mistral/mistral-small", "Mistral Small", True),  # Miễn phí
    ("mistral/mistral-tiny", "Mistral Tiny", True),  # Miễn phí
    ("groq/llama-3-8b-8192", "Llama 3 8B via Groq", True),  # Miễn phí
    ("cohere/command-r-plus", "Cohere Command R+", True),  # Miễn phí hạn chế
]


# Định nghĩa lớp trừu tượng cho tất cả các API dịch
# Định nghĩa lớp trừu tượng cho tất cả các API dịch
class TranslationAPI(ABC):
    @abstractmethod
    def translate_batch(
        self,
        subtitles_batch: List[Dict],
        thread_id: int,
        update_status: Callable[[str], None],
        max_retries: int = float("inf"),
    ) -> List[Dict]:
        """
        Dịch một lô phụ đề.
        """
        pass

    @staticmethod
    def create_api(api_type: str, api_config: Dict) -> "TranslationAPI":
        """
        Factory method để tạo đối tượng API tương ứng.
        """
        if api_type == "gemini":
            model = api_config.get(
                "model", GEMINI_MODELS[5][0]
            )  # Mặc định: gemini-2.0-flash-exp
            return GeminiAPI(api_config["key"], model)
        elif api_type == "novita":
            model = api_config.get(
                "model", NOVITA_MODELS[0][0]
            )  # Mặc định: llama-3.1-8b-instruct
            return NovitaAPI(api_config["key"], api_config["base_url"], model)
        elif api_type == "openrouter":
            model = api_config.get("model", OPENROUTER_MODELS[0][0])  # Mặc định: gpt-4o
            site_url = api_config.get("site_url")
            site_name = api_config.get("site_name")
            return OpenRouterAPI(api_config["key"], model, site_url, site_name)
        else:
            raise ValueError(f"Loại API không được hỗ trợ: {api_type}")

    @staticmethod
    def get_supported_apis():
        """
        Trả về danh sách các API được hỗ trợ
        """
        return ["gemini", "novita", "openrouter"]

    @staticmethod
    def get_models_for_api(api_type: str) -> List[Tuple[str, str, bool]]:
        """
        Trả về danh sách các model được hỗ trợ cho một API cụ thể
        Format: [(model_id, display_name, is_free), ...]
        """
        if api_type == "gemini":
            return GEMINI_MODELS
        elif api_type == "novita":
            return NOVITA_MODELS
        elif api_type == "openrouter":
            return OPENROUTER_MODELS
        else:
            return []


# Cài đặt API Gemini
class GeminiAPI(TranslationAPI):
    def __init__(self, api_key: str, model: str = GEMINI_MODELS[5][0]):
        self.api_key = api_key
        self.model = model

    def translate_batch(
        self,
        subtitles_batch: List[Dict],
        thread_id: int,
        update_status: Callable[[str], None],
        max_retries: int = float("inf"),
    ) -> List[Dict]:
        """
        Dịch một lô phụ đề từ tiếng Anh sang tiếng Việt sử dụng API Gemini.
        """
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        subtitles_text = ""
        for i, subtitle in enumerate(subtitles_batch):
            subtitles_text += f"[{i+1}] {subtitle['text']}\n\n"

        prompt = (
            "Translate the following English subtitles to Vietnamese. Maintain the numbering format exactly as provided.\n"
            "Each subtitle is marked with [number] followed by text. Translate ONLY the text, keeping the [number] format.\n"
            "Return ONLY the translated subtitles with their numbers, no additional text or explanations.\n\n"
            f"{subtitles_text}"
        )

        data = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 8192,
                "responseMimeType": "text/plain",
            },
        }

        retries = 0
        while retries < max_retries:
            try:
                response = requests.post(url, headers=headers, json=data, timeout=60)

                if response.status_code == 200:
                    try:
                        response_data = response.json()

                        if (
                            "candidates" in response_data
                            and len(response_data["candidates"]) > 0
                            and "content" in response_data["candidates"][0]
                            and "parts" in response_data["candidates"][0]["content"]
                            and len(response_data["candidates"][0]["content"]["parts"])
                            > 0
                            and "text"
                            in response_data["candidates"][0]["content"]["parts"][0]
                        ):

                            translated_text = response_data["candidates"][0]["content"][
                                "parts"
                            ][0]["text"]

                            translated_parts = re.findall(
                                r"\[(\d+)\](.*?)(?=\n\[|\Z)", translated_text, re.DOTALL
                            )

                            if not translated_parts:
                                translated_parts = re.findall(
                                    r"(?:\[)?(\d+)(?:\])?[:\.\s]+(.*?)(?=\n(?:\[)?\d+(?:\])?[:\.\s]+|\Z)",
                                    translated_text,
                                    re.DOTALL,
                                )

                            translations = {}
                            for idx_str, text in translated_parts:
                                try:
                                    idx = int(idx_str)
                                    translations[idx] = text.strip()
                                except ValueError:
                                    update_status(
                                        f"Thread {thread_id}: Cảnh báo - Định dạng chỉ số không hợp lệ: {idx_str}"
                                    )

                            if len(translations) < len(subtitles_batch) / 2:
                                update_status(
                                    f"Thread {thread_id}: Cảnh báo - Chỉ nhận được {len(translations)}/{len(subtitles_batch)} bản dịch"
                                )

                                if retries < max_retries - 1:
                                    retries += 1
                                    sleep_time = min(2**retries, 60)
                                    update_status(
                                        f"Thread {thread_id}: Thử lại sau {sleep_time} giây..."
                                    )
                                    time.sleep(sleep_time)
                                    continue

                            translated_subtitles = []
                            for i, subtitle in enumerate(subtitles_batch):
                                translated = subtitle.copy()
                                # Lưu phụ đề gốc
                                translated["original_text"] = subtitle["text"]
                                if i + 1 in translations:
                                    translated["text"] = translations[i + 1]
                                else:
                                    update_status(
                                        f"Thread {thread_id}: Thiếu bản dịch cho phụ đề {i+1}"
                                    )
                                translated_subtitles.append(translated)

                            return translated_subtitles

                        else:
                            update_status(
                                f"Thread {thread_id}: Định dạng phản hồi không như mong đợi (lần thử {retries+1})"
                            )

                    except json.JSONDecodeError:
                        update_status(
                            f"Thread {thread_id}: Không thể phân tích phản hồi JSON (lần thử {retries+1})"
                        )

                else:
                    update_status(
                        f"Thread {thread_id}: Lỗi API (lần thử {retries+1}): {response.status_code}"
                    )

                sleep_time = min(2**retries, 60)
                update_status(f"Thread {thread_id}: Thử lại sau {sleep_time} giây...")
                time.sleep(sleep_time)
                retries += 1

            except Exception as e:
                update_status(
                    f"Thread {thread_id}: Ngoại lệ trong quá trình gọi API (lần thử {retries+1}): {str(e)}"
                )
                sleep_time = min(2**retries, 60)
                time.sleep(sleep_time)
                retries += 1

        update_status(
            f"Thread {thread_id}: Không thể dịch lô sau {max_retries} lần thử"
        )
        return subtitles_batch


# Cài đặt API Novita
class NovitaAPI(TranslationAPI):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def translate_batch(
        self,
        subtitles_batch: List[Dict],
        thread_id: int,
        update_status: Callable[[str], None],
        max_retries: int = float("inf"),
    ) -> List[Dict]:
        """
        Dịch một lô phụ đề từ tiếng Anh sang tiếng Việt sử dụng API Novita AI.
        """
        try:
            client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            )

            subtitles_text = ""
            for i, subtitle in enumerate(subtitles_batch):
                subtitles_text += f"[{i+1}] {subtitle['text']}\n\n"

            prompt = (
                "Translate the following English subtitles to Vietnamese. Maintain the numbering format exactly as provided.\n"
                "Each subtitle is marked with [number] followed by text. Translate ONLY the text, keeping the [number] format.\n"
                "Return ONLY the translated subtitles with their numbers, no additional text or explanations.\n\n"
                f"{subtitles_text}"
            )

            retries = 0
            while retries < max_retries:
                try:
                    chat_completion_res = client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a professional translator specialized in translating English to Vietnamese. Return only the translated text with the same formatting as the input.",
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        stream=False,
                        max_tokens=8192,
                        temperature=0.1,
                    )

                    if (
                        chat_completion_res
                        and hasattr(chat_completion_res, "choices")
                        and len(chat_completion_res.choices) > 0
                    ):
                        translated_text = chat_completion_res.choices[0].message.content

                        translated_parts = re.findall(
                            r"\[(\d+)\](.*?)(?=\n\[|\Z)", translated_text, re.DOTALL
                        )

                        if not translated_parts:
                            translated_parts = re.findall(
                                r"(?:\[)?(\d+)(?:\])?[:\.\s]+(.*?)(?=\n(?:\[)?\d+(?:\])?[:\.\s]+|\Z)",
                                translated_text,
                                re.DOTALL,
                            )

                        translations = {}
                        for idx_str, text in translated_parts:
                            try:
                                idx = int(idx_str)
                                translations[idx] = text.strip()
                            except ValueError:
                                update_status(
                                    f"Thread {thread_id}: Cảnh báo - Định dạng chỉ số không hợp lệ: {idx_str}"
                                )

                        if len(translations) < len(subtitles_batch) / 2:
                            update_status(
                                f"Thread {thread_id}: Cảnh báo - Chỉ nhận được {len(translations)}/{len(subtitles_batch)} bản dịch"
                            )

                            if retries < max_retries - 1:
                                retries += 1
                                sleep_time = min(2**retries, 60)
                                update_status(
                                    f"Thread {thread_id}: Thử lại sau {sleep_time} giây..."
                                )
                                time.sleep(sleep_time)
                                continue

                        translated_subtitles = []
                        for i, subtitle in enumerate(subtitles_batch):
                            translated = subtitle.copy()
                            # Lưu phụ đề gốc
                            translated["original_text"] = subtitle["text"]
                            if i + 1 in translations:
                                translated["text"] = translations[i + 1]
                            else:
                                update_status(
                                    f"Thread {thread_id}: Thiếu bản dịch cho phụ đề {i+1}"
                                )
                            translated_subtitles.append(translated)

                        return translated_subtitles

                    else:
                        update_status(
                            f"Thread {thread_id}: Phản hồi Novita AI không như mong đợi (lần thử {retries+1})"
                        )

                        sleep_time = min(2**retries, 60)
                        update_status(
                            f"Thread {thread_id}: Thử lại sau {sleep_time} giây..."
                        )
                        time.sleep(sleep_time)
                        retries += 1

                except Exception as e:
                    update_status(
                        f"Thread {thread_id}: Lỗi khi gọi Novita AI API (lần thử {retries+1}): {str(e)}"
                    )
                    sleep_time = min(2**retries, 60)
                    time.sleep(sleep_time)
                    retries += 1

            update_status(
                f"Thread {thread_id}: Không thể dịch lô sau {max_retries} lần thử"
            )

        except Exception as e:
            update_status(
                f"Thread {thread_id}: Lỗi nghiêm trọng khi sử dụng Novita AI: {str(e)}"
            )

        return subtitles_batch


# Cài đặt API OpenRouter
class OpenRouterAPI(TranslationAPI):
    def __init__(
        self, api_key: str, model: str, site_url: str = None, site_name: str = None
    ):
        self.api_key = api_key
        self.model = model
        self.site_url = site_url
        self.site_name = site_name

    def translate_batch(
        self,
        subtitles_batch: List[Dict],
        thread_id: int,
        update_status: Callable[[str], None],
        max_retries: int = float("inf"),
    ) -> List[Dict]:
        """
        Dịch một lô phụ đề từ tiếng Anh sang tiếng Việt sử dụng API OpenRouter.
        """
        try:
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.api_key,
            )

            subtitles_text = ""
            for i, subtitle in enumerate(subtitles_batch):
                subtitles_text += f"[{i+1}] {subtitle['text']}\n\n"

            prompt = (
                "Translate the following English subtitles to Vietnamese. Maintain the numbering format exactly as provided.\n"
                "Each subtitle is marked with [number] followed by text. Translate ONLY the text, keeping the [number] format.\n"
                "Return ONLY the translated subtitles with their numbers, no additional text or explanations.\n\n"
                f"{subtitles_text}"
            )

            retries = 0
            while retries < max_retries:
                try:
                    extra_headers = {}
                    if self.site_url:
                        extra_headers["HTTP-Referer"] = self.site_url
                    if self.site_name:
                        extra_headers["X-Title"] = self.site_name

                    completion = client.chat.completions.create(
                        extra_headers=extra_headers,
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                    )

                    if (
                        completion
                        and hasattr(completion, "choices")
                        and len(completion.choices) > 0
                    ):
                        translated_text = completion.choices[0].message.content

                        # Xử lý phần còn lại giống như các API khác...
                        translated_parts = re.findall(
                            r"\[(\d+)\](.*?)(?=\n\[|\Z)", translated_text, re.DOTALL
                        )
                        if not translated_parts:
                            translated_parts = re.findall(
                                r"(?:\[)?(\d+)(?:\])?[:\.\s]+(.*?)(?=\n(?:\[)?\d+(?:\])?[:\.\s]+|\Z)",
                                translated_text,
                                re.DOTALL,
                            )

                        translations = {}
                        for idx_str, text in translated_parts:
                            try:
                                idx = int(idx_str)
                                translations[idx] = text.strip()
                            except ValueError:
                                update_status(
                                    f"Thread {thread_id}: Cảnh báo - Định dạng chỉ số không hợp lệ: {idx_str}"
                                )

                        if len(translations) < len(subtitles_batch) / 2:
                            update_status(
                                f"Thread {thread_id}: Cảnh báo - Chỉ nhận được {len(translations)}/{len(subtitles_batch)} bản dịch"
                            )
                            if retries < max_retries - 1:
                                retries += 1
                                sleep_time = min(2**retries, 60)
                                update_status(
                                    f"Thread {thread_id}: Thử lại sau {sleep_time} giây..."
                                )
                                time.sleep(sleep_time)
                                continue

                        translated_subtitles = []
                        for i, subtitle in enumerate(subtitles_batch):
                            translated = subtitle.copy()
                            translated["original_text"] = subtitle["text"]

                            if i + 1 in translations:
                                translated["text"] = translations[i + 1]
                            else:
                                update_status(
                                    f"Thread {thread_id}: Thiếu bản dịch cho phụ đề {i+1}"
                                )

                            translated_subtitles.append(translated)

                        return translated_subtitles
                    else:
                        update_status(
                            f"Thread {thread_id}: Định dạng phản hồi không như mong đợi (lần thử {retries+1})"
                        )

                except Exception as e:
                    update_status(
                        f"Thread {thread_id}: Lỗi khi gọi OpenRouter API (lần thử {retries+1}): {str(e)}"
                    )

                sleep_time = min(2**retries, 60)
                update_status(f"Thread {thread_id}: Thử lại sau {sleep_time} giây...")
                time.sleep(sleep_time)
                retries += 1

            update_status(
                f"Thread {thread_id}: Không thể dịch lô sau {max_retries} lần thử"
            )

        except Exception as e:
            update_status(
                f"Thread {thread_id}: Lỗi nghiêm trọng khi sử dụng OpenRouter API: {str(e)}"
            )

        return subtitles_batch


# Để thêm một API mới, tạo một lớp mới như sau:
"""
class NewAPI(TranslationAPI):
    def __init__(self, api_key: str, other_params):
        self.api_key = api_key
        self.other_params = other_params
    
    def translate_batch(self, subtitles_batch: List[Dict], thread_id: int, update_status: Callable[[str], None], max_retries: int = float('inf')) -> List[Dict]:
        # Triển khai code dịch ở đây
        pass

# Và cập nhật phương thức create_api:
@staticmethod
def create_api(api_type: str, api_config: Dict) -> 'TranslationAPI':
    if api_type == 'gemini':
        return GeminiAPI(api_config['key'])
    elif api_type == 'novita':
        return NovitaAPI(api_config['key'], api_config['base_url'], api_config['model'])
    elif api_type == 'new_api':
        return NewAPI(api_config['key'], api_config['other_param'])
    else:
        raise ValueError(f"Loại API không được hỗ trợ: {api_type}")

# Cũng cập nhật danh sách API hỗ trợ:
@staticmethod
def get_supported_apis():
    return ["gemini", "novita", "new_api"]
"""
