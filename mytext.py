import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import vision, translate_v3 as translate
from openai import OpenAI

# 로깅 설정 (debug 레벨 이상 모두 출력)
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app)

# 환경변수 출력 (디버깅)
logging.debug(f"GCP_SERVICE_ACCOUNT_EMAIL: {os.getenv('GCP_SERVICE_ACCOUNT_EMAIL')}")
logging.debug(f"GCP_PROJECT_ID: {os.getenv('GCP_PROJECT_ID')}")
logging.debug(f"OPENAI_API_KEY set: {'YES' if os.getenv('OPENAI_API_KEY') else 'NO'}")

# Google Cloud Vision 및 Translate 클라이언트 초기화
try:
    vision_client = vision.ImageAnnotatorClient(
        credentials={
            "client_email": os.getenv("GCP_SERVICE_ACCOUNT_EMAIL"),
            "private_key": os.getenv("GCP_PRIVATE_KEY").replace("\\n", "\n"),
            "project_id": os.getenv("GCP_PROJECT_ID"),
        }
    )
    translate_client = translate.TranslationServiceClient(
        credentials={
            "client_email": os.getenv("GCP_SERVICE_ACCOUNT_EMAIL"),
            "private_key": os.getenv("GCP_PRIVATE_KEY").replace("\\n", "\n"),
            "project_id": os.getenv("GCP_PROJECT_ID"),
        }
    )
    logging.debug("Google Cloud clients initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing Google Cloud clients: {str(e)}")

# OpenAI 클라이언트 초기화
try:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_client = OpenAI(api_key=openai_api_key)
    logging.debug("OpenAI client initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing OpenAI client: {str(e)}")

@app.route("/api/process-image", methods=["POST"])
def process_image():
    logging.debug("Received request for /api/process-image")

    if "image" not in request.files:
        logging.error("No image file in request")
        return jsonify({"error": "No image file"}), 400

    try:
        image_file = request.files["image"]
        content = image_file.read()
        logging.debug(f"Image file read successfully, size: {len(content)} bytes")

        image = vision.Image(content=content)
        response = vision_client.text_detection(image=image)
        texts = response.text_annotations

        if texts:
            chinese_text = texts[0].description
            logging.debug(f"Extracted text from image: {chinese_text[:100]}...")  # 앞 100자만 로깅
        else:
            chinese_text = ""
            logging.warning("No text detected in image")

        # 번역 요청 (예시 한국어로 번역)
        project_id = os.getenv("GCP_PROJECT_ID")
        location = "global"
        parent = f"projects/{project_id}/locations/{location}"

        translate_request = {
            "parent": parent,
            "contents": [chinese_text],
            "mime_type": "text/plain",
            "source_language_code": "zh",
            "target_language_code": "ko",
        }
        translate_response = translate_client.translate_text(request=translate_request)
        translated_text = translate_response.translations[0].translated_text
        logging.debug(f"Translated text: {translated_text[:100]}...") # 앞 100자만 로깅

        # OpenAI 스타일링 호출
        formatted_text = style_text_with_openai(translated_text)
        logging.debug("Processed text with OpenAI successfully.")

        return jsonify({"result": formatted_text})

    except Exception as e:
        logging.error(f"Error processing image: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def style_text_with_openai(text: str) -> str:
    prompt = f"Text: {text}\nPlease style the above text to be more natural."
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error calling OpenAI API: {str(e)}", exc_info=True)
        return text


if __name__ == "__main__":
    logging.debug("Starting Flask app")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
