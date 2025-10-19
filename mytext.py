import os
from flask import Flask
from flask_cors import CORS
from google.cloud import vision, translate
from openai import OpenAI

# GOOGLE_APPLICATION_CREDENTIALS 환경변수는 integration이 자동 설정함

# Flask 앱 및 CORS 설정
app = Flask(__name__, static_folder='build')
CORS(app)

# 환경변수에서 Google Cloud 인증 정보 바로 사용
vision_client = vision.ImageAnnotatorClient(
    credentials={
        "client_email": os.getenv("GCP_SERVICE_ACCOUNT_EMAIL"),
        "private_key": os.getenv("GCP_PRIVATE_KEY").replace("\\n", "\n"),
    },
    project=os.getenv("GCP_PROJECT_ID")
)

translate_client = translate.TranslationServiceClient(
    credentials={
        "client_email": os.getenv("GCP_SERVICE_ACCOUNT_EMAIL"),
        "private_key": os.getenv("GCP_PRIVATE_KEY").replace("\\n", "\n"),
    },
    project=os.getenv("GCP_PROJECT_ID")
)

# OpenAI API 키 환경변수에서 읽기
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key)

# 프로젝트 및 위치 정보도 환경변수로 관리
PROJECT_ID = os.getenv("PROJECT_ID", "mytext-475212")
LOCATION = os.getenv("LOCATION", "global")

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
