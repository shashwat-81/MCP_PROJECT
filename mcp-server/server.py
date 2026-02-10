# from flask import Flask, jsonify
# import subprocess
# import json

# app = Flask(__name__)

# def run_command(cmd):
#     result = subprocess.run(cmd, capture_output=True, text=True)
#     return result.stdout

# @app.route("/")
# def home():
#     return jsonify({
#         "status": "MCP Server Running",
#         "endpoints": [
#             "/pods",
#             "/metrics",
#             "/logs/<pod>",
#             "/describe/<pod>"
#         ]
#     })

# @app.route("/pods")
# def pods():
#     data = run_command(["kubectl", "get", "pods", "-o", "json"])
#     return jsonify(json.loads(data))

# @app.route("/metrics")
# def metrics():
#     data = run_command(["kubectl", "top", "pods"])
#     return jsonify({"metrics": data})

# @app.route("/logs/<pod>")
# def logs(pod):
#     data = run_command(["kubectl", "logs", pod])
#     return jsonify({"logs": data})

# @app.route("/describe/<pod>")
# def describe(pod):
#     data = run_command(["kubectl", "describe", "pod", pod])
#     return jsonify({"describe": data})

# app.run(port=5000)
from flask import Flask, jsonify
import subprocess
import json

app = Flask(__name__)

def run_command(cmd, timeout=5):
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return "COMMAND_TIMEOUT"


@app.route("/")
def home():
    return jsonify({
        "status": "MCP Server Running",
        "endpoints": [
            "/pods",
            "/metrics",
            "/logs/<namespace>/<pod>",
            "/describe/<namespace>/<pod>"
        ]
    })


@app.route("/pods")
def pods():
    data = run_command(["kubectl", "get", "pods", "-A", "-o", "json"])
    return jsonify(json.loads(data))


@app.route("/metrics")
def metrics():
    data = run_command(["kubectl", "top", "pods", "-A"], timeout=5)
    return jsonify({"metrics": data})


@app.route("/logs/<namespace>/<pod>")
def logs(namespace, pod):
    data = run_command(["kubectl", "logs", "-n", namespace, pod, "--tail=100"])
    return jsonify({"logs": data})


@app.route("/describe/<namespace>/<pod>")
def describe(namespace, pod):
    data = run_command(["kubectl", "describe", "pod", "-n", namespace, pod])
    return jsonify({"describe": data})


if __name__ == "__main__":
    app.run(port=5000)
