from flask import Flask, request, jsonify
import requests
import json
import re
import uuid
import time
from bs4 import BeautifulSoup
from datetime import datetime

app = Flask(__name__)

def extract_snlm0e_token(html):
    snlm0e_patterns = [
        r'"SNlM0e":"([^"]+)"',
        r"'SNlM0e':'([^']+)'",
        r'SNlM0e["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'"FdrFJe":"([^"]+)"',
        r"'FdrFJe':'([^']+)'",
        r'FdrFJe["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'"cfb2h":"([^"]+)"',
        r"'cfb2h':'([^']+)'",
        r'cfb2h["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'at["\']?\s*[:=]\s*["\']([^"\']{50,})["\']',
        r'"at":"([^"]+)"',
        r'"token":"([^"]+)"',
        r'data-token["\']?\s*=\s*["\']([^"\']+)["\']',
    ]

    for pattern in snlm0e_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            token = match.group(1)
            if len(token) > 20:
                return token
    return None


def extract_from_script_tags(html):
    soup = BeautifulSoup(html, 'html.parser')
    script_tags = soup.find_all('script')

    for script in script_tags:
        if script.string:
            script_content = script.string

            if 'SNlM0e' in script_content or 'FdrFJe' in script_content:
                token = extract_snlm0e_token(script_content)
                if token:
                    return token
    return None


def extract_build_and_session_params(html):
    params = {}

    bl_match = re.search(r'"bl":"([^"]+)"', html)
    if bl_match:
        params['bl'] = bl_match.group(1)
    else:
        params['bl'] = 'boq_assistant-bard-web-server_20251217.07_p5'

    params['fsid'] = str(-1 * int(time.time() * 1000))
    params['reqid'] = int(time.time() * 1000) % 1000000

    return params


def scrape_fresh_session():
    session = requests.Session()
    url = 'https://gemini.google.com/app'

    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'text/html',
        'Accept-Language': 'en-US,en;q=0.9'
    }

    try:
        response = session.get(url, headers=headers, timeout=30)
        html = response.text

        snlm0e = extract_snlm0e_token(html)
        if not snlm0e:
            snlm0e = extract_from_script_tags(html)

        if not snlm0e:
            return None

        params = extract_build_and_session_params(html)

        return {
            'session': session,
            'snlm0e': snlm0e,
            'bl': params['bl'],
            'fsid': params['fsid'],
            'reqid': params['reqid']
        }

    except Exception:
        return None


def build_payload(prompt, snlm0e):
    escaped_prompt = prompt.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    session_id = uuid.uuid4().hex
    request_uuid = str(uuid.uuid4()).upper()

    payload_data = [
        [escaped_prompt, 0, None, None, None, None, 0],
        ["en-US"],
        ["", "", "", None, None, None, None, None, None, ""],
        snlm0e,
        session_id,
        None,
        [0],
        1,
        None,
        None,
        1,
        0,
        None,
        None,
        None,
        None,
        None,
        [[0]],
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        1,
        None,
        None,
        [4],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        [2],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        0,
        None,
        None,
        None,
        None,
        None,
        request_uuid,
        None,
        []
    ]

    payload_str = json.dumps(payload_data, separators=(',', ':'))
    escaped_payload = payload_str.replace('\\', '\\\\').replace('"', '\\"')

    return {
        'f.req': f'[null,"{escaped_payload}"]',
        '': ''
    }


def chat_with_gemini(prompt):
    start_time = time.time()
    scraped = scrape_fresh_session()

    if not scraped:
        return {'success': False, 'error': 'Failed to establish session'}

    session = scraped['session']
    snlm0e = scraped['snlm0e']
    bl = scraped['bl']
    fsid = scraped['fsid']
    reqid = scraped['reqid']

    base_url = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
    url = f"{base_url}?bl={bl}&f.sid={fsid}&hl=en-US&_reqid={reqid}&rt=c"

    payload = build_payload(prompt, snlm0e)

    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'origin': 'https://gemini.google.com',
        'referer': 'https://gemini.google.com/'
    }

    try:
        response = session.post(url, data=payload, headers=headers, timeout=60)

        if response.status_code != 200:
            return {'success': False, 'error': f'HTTP {response.status_code}'}

        end_time = time.time()
        response_time = round(end_time - start_time, 2)

        return {
            'success': True,
            'response': response.text,
            'metadata': {
                'response_time': f'{response_time}s',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        }

    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': str(e)}


@app.route('/')
def home():
    return jsonify({
        'success': True,
        'message': 'Gemini AI API is running!',
        'endpoints': {
            '/api/ask': {
                'method': 'GET',
                'parameters': {
                    'prompt': 'Your question or message (required)'
                }
            }
        }
    })


@app.route('/api/ask', methods=['GET'])
def ask_gemini():
    prompt = request.args.get('prompt')

    if not prompt or len(prompt.strip()) == 0:
        return jsonify({
            'success': False,
            'error': 'Missing or empty prompt'
        }), 400

    result = chat_with_gemini(prompt)
    result['prompt'] = prompt

    return jsonify(result), 200 if result['success'] else 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'available_endpoints': ['/', '/api/ask']
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)