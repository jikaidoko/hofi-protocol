import re

path = r'C:\dev\hofi-protocol\packages\tenzo-agent\tenzo_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

if 'import time' not in content:
    content = content.replace('import json', 'import json\nimport time', 1)

old = 'def llamar_gemini(prompt: str) -> dict:\n    if not API_KEY:\n        raise ValueError("GEMINI_API_KEY no configurada")\n    url = (\n        f"https://generativelanguage.googleapis.com/v1beta/models/"\n        f"{MODEL_NAME}:generateContent"\n    )\n    resp = requests.post(\n        url,\n        json={\n            "contents": [{"parts": [{"text": prompt}]}],\n            "generationConfig": {\n                "responseMimeType": "application/json",\n                "temperature": 0.2,\n            },\n        },\n        headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY},\n        timeout=30,\n    )\n    resp.raise_for_status()'

new = 'def llamar_gemini(prompt: str, _reintentos: int = 3) -> dict:\n    import time as _time\n    if not API_KEY:\n        raise ValueError("GEMINI_API_KEY no configurada")\n    url = (\n        f"https://generativelanguage.googleapis.com/v1beta/models/"\n        f"{MODEL_NAME}:generateContent"\n    )\n    resp = None\n    for intento in range(_reintentos):\n        resp = requests.post(\n            url,\n            json={\n                "contents": [{"parts": [{"text": prompt}]}],\n                "generationConfig": {\n                    "responseMimeType": "application/json",\n                    "temperature": 0.2,\n                },\n            },\n            headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY},\n            timeout=30,\n        )\n        if resp.status_code == 429 and intento < _reintentos - 1:\n            espera = 10 * (2 ** intento)\n            logger.warning("Gemini 429 reintentando en %ds (%d/%d)", espera, intento+1, _reintentos)\n            _time.sleep(espera)\n            continue\n        resp.raise_for_status()\n        break'

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK - retry agregado')
else:
    print('ERROR - texto no encontrado')
    idx = content.find('def llamar_gemini')
    if idx >= 0:
        print('Funcion encontrada en pos', idx)
        print(repr(content[idx:idx+200]))
