from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google.cloud import vision
from google.cloud import translate
from openai import OpenAI
import os

app = Flask(__name__, static_folder='build')
CORS(app)

# 인증 키는 환경변수를 통해 설정되므로 코드내 직접 경로 불필요
vision_client = vision.ImageAnnotatorClient()
translate_client = translate.TranslationServiceClient()

openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key)

vision_client = vision.ImageAnnotatorClient()
translate_client = translate.TranslationServiceClient()

PROJECT_ID = "keen-precinct-475110-a5"  # 실제 프로젝트 ID로 변경
LOCATION = "global"

def style_text_with_openai(text: str) -> str:
    prompt = (
        "다음 한글 문장을 상세페이지에 어울리는 감성적이고 자연스러운 문구로 바꿔줘:\n\n"
        f"{text}\n\n"
        "고객의 관심을 끌 수 있게 부드럽고 매력적으로 작성해줘."
    )
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI API 오류: {e}")
        return text

@app.route('/')
def serve():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

@app.route('/process-image', methods=['POST'])
def process_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image file"}), 400

    file = request.files['image']
    content = file.read()

    # OCR - 중국어 추출
    image = vision.Image(content=content)
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations
    
    chinese_text = texts[0].description if texts else ""

    # 번역 - 중국어 -> 한국어
    translated_text = "이미지에서 텍스트를 찾을 수 없습니다."
    if chinese_text:
        parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
        response = translate_client.translate_text(
            request={
                "parent": parent,
                "contents": [chinese_text],
                "mime_type": "text/plain",
                "target_language_code": "ko",
            }
        )
        translated_text = response.translations[0].translated_text

    # 감성 스타일링 (OpenAI GPT-3.5 Turbo)
    styled_text = style_text_with_openai(translated_text)

    return jsonify({"translated_text": styled_text})

if __name__ == '__main__':
    app.run(port=5000, debug=True)
