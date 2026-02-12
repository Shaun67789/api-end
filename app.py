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
    
    for i, pattern in enumerate(snlm0e_patterns):
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
            
            json_patterns = [
                r'\{[^}]*"[^"]*token[^"]*"[^}]*\}',
                r'\{[^}]*SNlM0e[^}]*\}',
                r'\{[^}]*FdrFJe[^}]*\}'
            ]
            
            for pattern in json_patterns:
                matches = re.finditer(pattern, script_content, re.IGNORECASE)
                for match in matches:
                    try:
                        json_str = match.group(0)
                        json_obj = json.loads(json_str)
                        
                        for key, value in json_obj.items():
                            if isinstance(value, str) and len(value) > 50:
                                return value
                    except:
                        continue
    
    return None

def extract_build_and_session_params(html):
    params = {}
    
    bl_patterns = [
        r'bl["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'"bl":"([^"]+)"',
        r'buildLabel["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'boq[_-]assistant[^"\']*_(\d+\.\d+[^"\']*)',
        r'/_/BardChatUi.*?bl=([^&"\']+)',
    ]
    
    for pattern in bl_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            params['bl'] = match.group(1)
            break
    
    fsid_patterns = [
        r'f\.sid["\']?\s*[:=]\s*["\']?([^"\'&\s]+)',
        r'"fsid":"([^"]+)"',
        r'f\.sid=([^&"\']+)',
        r'sessionId["\']?\s*[:=]\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in fsid_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            params['fsid'] = match.group(1)
            break
    
    reqid_match = re.search(r'_reqid["\']?\s*[:=]\s*["\']?(\d+)', html)
    if reqid_match:
        params['reqid'] = int(reqid_match.group(1))
    
    if not params.get('bl'):
        params['bl'] = 'boq_assistant-bard-web-server_20251217.07_p5'
    
    if not params.get('fsid'):
        params['fsid'] = str(-1 * int(time.time() * 1000))
    
    if not params.get('reqid'):
        params['reqid'] = int(time.time() * 1000) % 1000000
    
    return params

def scrape_fresh_session():
    session = requests.Session()
    
    url = 'https://gemini.google.com/app'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-site': 'none',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-dest': 'document',
        'upgrade-insecure-requests': '1',
        'cache-control': 'no-cache',
        'pragma': 'no-cache'
    }
    
    try:
        response = session.get(url, headers=headers, timeout=30)
        html = response.text
        
        cookies = {}
        for cookie in session.cookies:
            cookies[cookie.name] = cookie.value
        
        snlm0e = extract_snlm0e_token(html)
        
        if not snlm0e:
            snlm0e = extract_from_script_tags(html)
        
        if not snlm0e:
            return None
        
        params = extract_build_and_session_params(html)
        
        scraped_data = {
            'session': session,
            'cookies': cookies,
            'snlm0e': snlm0e,
            'bl': params['bl'],
            'fsid': params['fsid'],
            'reqid': params['reqid'],
            'html': html
        }
        
        return scraped_data
        
    except Exception as e:
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

def parse_streaming_response(response_text):
    lines = response_text.strip().split('\n')
    full_text = ""
    
    for line in lines:
        if not line or line.startswith(')]}'):
            continue
            
        try:
            if line.isdigit():
                continue
                
            data = json.loads(line)
            
            if isinstance(data, list) and len(data) > 0:
                if data[0][0] == "wrb.fr" and len(data[0]) > 2:
                    inner_json = data[0][2]
                    
                    if inner_json:
                        parsed = json.loads(inner_json)
                        
                        if isinstance(parsed, list) and len(parsed) > 4:
                            content_array = parsed[4]
                            
                            if isinstance(content_array, list) and len(content_array) > 0:
                                first_item = content_array[0]
                                
                                if isinstance(first_item, list) and len(first_item) > 0:
                                    response_id = first_item[0]
                                    
                                    if isinstance(response_id, str) and response_id.startswith('rc_'):
                                        if len(first_item) > 1 and isinstance(first_item[1], list):
                                            text_array = first_item[1]
                                            
                                            if len(text_array) > 0:
                                                text_content = text_array[0]
                                                
                                                if isinstance(text_content, str) and len(text_content) > len(full_text):
                                                    full_text = text_content
        except Exception as e:
            continue
    
    if full_text:
        full_text = full_text.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    
    return full_text if full_text else None

def chat_with_gemini(prompt):
    start_time = time.time()
    
    scraped = scrape_fresh_session()
    
    if not scraped:
        return {
            'success': False,
            'error': 'Failed to establish session with Gemini'
        }
    
    session = scraped['session']
    cookies = scraped['cookies']
    snlm0e = scraped['snlm0e']
    bl = scraped['bl']
    fsid = scraped['fsid']
    reqid = scraped['reqid']
    
    base_url = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
    url = f"{base_url}?bl={bl}&f.sid={fsid}&hl=en-US&_reqid={reqid}&rt=c"
    
    payload = build_payload(prompt, snlm0e)
    
    cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'x-same-domain': '1',
        'origin': 'https://gemini.google.com',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'referer': 'https://gemini.google.com/',
        'Cookie': cookie_str
    }
    
    try:
        response = session.post(url, data=payload, headers=headers, timeout=60)
        
        if response.status_code != 200:
            return {
                'success': False,
                'error': f'HTTP {response.status_code}'
            }
        
        result = parse_streaming_response(response.text)
        
        end_time = time.time()
        response_time = round(end_time - start_time, 2)
        
        if result:
            return {
                'success': True,
                'response': result,
                'metadata': {
                    'response_time': f'{response_time}s',
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'model': 'gemini',
                    'character_count': len(result),
                    'word_count': len(result.split())
                }
            }
        else:
            return {
                'success': False,
                'error': 'No response received from Gemini'
            }
        
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': str(e)
        }

@app.route('/')
def home():
    return jsonify({
        'success': True,
        'message': 'Gemini AI API is running!',
        'api_dev': '@ShawonXnone',
        'endpoints': {
            '/api/ask': {
                'method': 'GET',
                'parameters': {
                    'prompt': 'Your question or message (required)'
                },
                'example': '/api/ask?prompt=Hello, how are you?'
            }
        },
        'documentation': {
            'description': 'Flask API wrapper for Google Gemini AI',
            'version': '1.0.0',
            
        }
    })

@app.route('/api/ask', methods=['GET'])
def ask_gemini():
    prompt = request.args.get('prompt')
    
    if not prompt:
        return jsonify({
            'success': False,
            'error': 'Missing required parameter: prompt',
            'api_dev': '@ShawonXnone',
            'usage': {
                'endpoint': '/api/ask',
                'method': 'GET',
                'parameters': {
                    'prompt': 'Your question or message (required)'
                },
                'example': '/api/ask?prompt=Hello, how are you?'
            }
        }), 400
    
    if len(prompt.strip()) == 0:
        return jsonify({
            'success': False,
            'error': 'Prompt cannot be empty',
            'api_dev': '@ShawonXnone'
        }), 400
    
    result = chat_with_gemini(prompt)
    
    result['api_dev'] = '@ShawonXnone'
    result['prompt'] = prompt
    
    if result['success']:
        return jsonify(result), 200
    else:
        return jsonify(result), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'api_dev': '@ShawonXnone',
        'available_endpoints': ['/', '/api/ask']
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'api_dev': '@ShawonXnone'
    }), 500

if __name__ == '__main__':
    print('=' * 60)
    print('Gemini AI Flask API')
    print('Developer: @ShawonXnone')
    print('=' * 60)
    print('  http://localhost:5000/api/ask?prompt=Hello, how are you?')
    print('=' * 60)
    print('\nStarting server...\n')
    
    app.run(debug=True, host='0.0.0.0', port=5000)
