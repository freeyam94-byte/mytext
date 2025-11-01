import os
import logging
import json
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google.cloud import vision, translate_v3 as translate
from google.oauth2 import service_account
from openai import OpenAI
from PIL import Image, ImageDraw
import io
import cv2
import numpy as np

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__, static_folder='build')
CORS(app)

# Set Google Cloud credentials
service_account_file = os.path.join(os.path.dirname(__file__), 'mytext-475212-729c4ebb7588.json')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = service_account_file

# Extract project_id from service account file
with open(service_account_file, 'r') as f:
    service_account_info = json.load(f)
    project_id = service_account_info['project_id']

vision_client = None
translate_client = None
openai_client = None

logging.debug(f"GCP_PROJECT_ID: {project_id}")
logging.debug(f"OPENAI_API_KEY set: {'YES' if os.getenv('OPENAI_API_KEY') else 'NO'}")

try:
    vision_client = vision.ImageAnnotatorClient()
    translate_client = translate.TranslationServiceClient()
    logging.debug("Google Cloud clients initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing Google Cloud clients: {str(e)}")

try:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_client = OpenAI(api_key=openai_api_key)
    logging.debug("OpenAI client initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing OpenAI client: {str(e)}")

@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route("/api/process-image", methods=["POST"])
def process_image():
    logging.debug("Received request for /api/process-image")

    if "image" not in request.files:
        logging.error("No image file in request")
        return jsonify({"error": "No image file"}), 400

    if vision_client is None:
        logging.error("Google Cloud Vision client not initialized.")
        return jsonify({"error": "Server configuration error: Vision client not available."}), 500

    try:
        image_file = request.files["image"]
        content = image_file.read()
        logging.debug(f"Image file read successfully, size: {len(content)} bytes")

        image = vision.Image(content=content)
        response = vision_client.text_detection(image=image)
        texts = response.text_annotations

        if texts:
            chinese_text = texts[0].description
            logging.debug(f"Extracted text from image: {chinese_text[:100]}...")
        else:
            chinese_text = ""
            logging.warning("No text detected in image")

        if translate_client is None:
            logging.error("Google Cloud Translate client not initialized.")
            return jsonify({"error": "Server configuration error: Translate client not available."}), 500

        location = "global"
        parent = f"projects/{project_id}/locations/{location}"

        translate_request = {
            "parent": parent,
            "contents": [chinese_text],
            "mime_type": "text/plain",
            "target_language_code": "ko",
        }
        translate_response = translate_client.translate_text(request=translate_request)
        translated_text = translate_response.translations[0].translated_text
        logging.debug(f"Translated text: {translated_text[:100]}...")

        formatted_text = style_text_with_openai(translated_text)
        logging.debug("Processed text with OpenAI successfully.")

        return jsonify({"result": formatted_text})

    except Exception as e:
        logging.error(f"Error processing image: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/remove-text", methods=["POST"])
def remove_text():
    logging.debug("Received request for /api/remove-text")

    if "image" not in request.files:
        logging.error("No image file in request")
        return jsonify({"error": "No image file"}), 400

    if vision_client is None or translate_client is None or openai_client is None:
        logging.error("A required client is not initialized.")
        return jsonify({"error": "Server configuration error: clients not available."}), 500

    try:
        image_file = request.files["image"]
        content = image_file.read()
        logging.debug(f"Image file read successfully, size: {len(content)} bytes")

        image_for_vision = vision.Image(content=content)
        response = vision_client.text_detection(image=image_for_vision)
        texts = response.text_annotations

        if not texts:
            logging.info("No text detected, returning original image.")
            return content, 200, {'Content-Type': 'image/png'}

        # Create a mask for Chinese text
        img_pil = Image.open(io.BytesIO(content)).convert("RGBA")
        mask_pil = Image.new("RGBA", img_pil.size, (255, 255, 255, 255))
        draw = ImageDraw.Draw(mask_pil)

        for text in texts[1:]:
            try:
                parent = f"projects/{project_id}/locations/global"
                detect_language_response = translate_client.detect_language(
                    parent=parent,
                    content=text.description,
                    mime_type="text/plain",
                )
                detected_language = detect_language_response.languages[0].language_code
                if detected_language.lower().startswith('zh'):
                    vertices = [(vertex.x, vertex.y) for vertex in text.bounding_poly.vertices]
                    draw.polygon(vertices, fill=(0, 0, 0, 0))
            except Exception as e:
                logging.error(f"Error detecting language or drawing mask: {str(e)}")

        # Dilate the mask to include surrounding areas
        mask_np = np.array(mask_pil)
        kernel = np.ones((10, 10), np.uint8)
        dilated_mask_np = cv2.dilate(mask_np, kernel, iterations=1)
        mask_pil = Image.fromarray(dilated_mask_np)

        # Convert PIL images to byte arrays for OpenAI API
        image_byte_arr = io.BytesIO()
        img_pil.save(image_byte_arr, format='PNG')
        image_byte_arr = image_byte_arr.getvalue()

        mask_byte_arr = io.BytesIO()
        mask_pil.save(mask_byte_arr, format='PNG')
        mask_byte_arr = mask_byte_arr.getvalue()

        # Call OpenAI Images API for inpainting
        response = openai_client.images.edit(
            image=("image.png", image_byte_arr, "image/png"),
            mask=("mask.png", mask_byte_arr, "image/png"),
            prompt="Remove the text and restore the background.",
            n=1,
            size="1024x1024"
        )

        inpainted_image_url = response.data[0].url
        
        # Download the inpainted image
        inpainted_image_response = requests.get(inpainted_image_url)
        inpainted_image_bytes = inpainted_image_response.content

        return inpainted_image_bytes, 200, {'Content-Type': 'image/png'}

    except Exception as e:
        logging.error(f"Error removing text from image: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

def style_text_with_openai(text: str) -> str:
    if openai_client is None:
        logging.error("OpenAI client not initialized.")
        return text

    prompt = f"다음 텍스트를 자연스러운 한국어로 번역하고 다듬어 주세요. 만약 이미 한국어라면, 더욱 자연스럽고 매력적으로 다듬어 주세요: {text}"
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
