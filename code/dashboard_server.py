from http.server import BaseHTTPRequestHandler, HTTPServer
import json


latest_data = {}


class DashboardHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        global latest_data

        if self.path == "/update":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                latest_data = json.loads(body.decode("utf-8"))
                print("[DASHBOARD] Received:", latest_data)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')

            except Exception as error:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(error).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/":
            html = f"""
            <html>
            <head>
                <title>Scanner Dashboard</title>
                <meta http-equiv="refresh" content="1">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        margin: 40px;
                    }}
                    pre {{
                        background: #eeeeee;
                        padding: 20px;
                        border-radius: 8px;
                    }}
                </style>
            </head>
            <body>
                <h1>Autonomous Grocery Store Scanner Dashboard</h1>
                <h2>Latest scanned product</h2>
                <pre>{json.dumps(latest_data, indent=2)}</pre>
            </body>
            </html>
            """

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8000), DashboardHandler)
    print("[DASHBOARD] Running at http://127.0.0.1:8000")
    server.serve_forever()