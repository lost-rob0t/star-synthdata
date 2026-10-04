"""Exercise the installed CLI against a local Ollama protocol fixture."""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from starintel_canonical import validate_document

response = {"content": "hello", "platform": "test", "isReply": False,
            "user": "unresolved-user", "unknown": {"flag": False, "nil": None}}

class Ollama(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.path == "/api/generate"
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert request["stream"] is False and request["format"] == "json"
        payload = json.dumps({"response": json.dumps(response)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    command = [sys.argv[1], "message", "-n", "1", "-u", f"http://127.0.0.1:{server.server_port}"]
    result = subprocess.run(command, text=True, capture_output=True, timeout=30, check=True)
    document = json.loads(result.stdout)
    validate_document(document)
    assert document["message"] == "hello" and document["isReply"] is False
    retained = document["extensions"]["starintel.synthdata"]["input"]
    assert json.loads(retained["ollamaResponse"]) == response
    assert "user" not in document
    response = {"content": False}
    result = subprocess.run(command, text=True, capture_output=True, timeout=30)
    assert result.returncode == 1 and not result.stdout
    assert "Error generating document:" in result.stderr
    print("installed CLI: canonical output, lossless input, invalid-output rejection PASS")
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
