# import requests
# import subprocess
# import time
# import json

# # MCP server URL
# MCP_URL = "http://127.0.0.1:5000"

# # Ollama local AI URL
# OLLAMA_URL = "http://localhost:11434/api/generate"

# # Monitoring interval (seconds)
# CHECK_INTERVAL = 10


# # ---------------------------------------------------
# # Get pods from MCP server
# # ---------------------------------------------------
# def get_pods():

#     try:
#         response = requests.get(f"{MCP_URL}/pods")

#         if response.status_code != 200:
#             print("Failed to fetch pods from MCP")
#             return []

#         return response.json().get("items", [])

#     except Exception as e:
#         print("Error connecting to MCP server:", e)
#         return []


# # ---------------------------------------------------
# # Get metrics from MCP server
# # ---------------------------------------------------
# def get_metrics():

#     try:
#         response = requests.get(f"{MCP_URL}/metrics")

#         if response.status_code != 200:
#             return "No metrics available"

#         return response.json().get("metrics", "")

#     except Exception as e:
#         print("Error fetching metrics:", e)
#         return ""


# # ---------------------------------------------------
# # Ask AI for diagnosis using Ollama
# # ---------------------------------------------------
# def ask_ai(context):

#     prompt = f"""
# You are an expert Kubernetes DevOps AI agent.

# Analyze the cluster state below and identify problems.

# Cluster data:
# {json.dumps(context, indent=2)}

# Respond ONLY in JSON format like this:

# {{
#   "problem": "CrashLoopBackOff",
#   "affected_pods": ["pod-name"],
#   "recommendation": "Restart pod"
# }}
# """

#     try:

#         response = requests.post(
#             OLLAMA_URL,
#             json={
#                 "model": "llama3",
#                 "prompt": prompt,
#                 "stream": False
#             }
#         )

#         return response.json().get("response", "")

#     except Exception as e:

#         print("Error communicating with AI:", e)
#         return ""


# # ---------------------------------------------------
# # Restart unhealthy pod
# # ---------------------------------------------------
# def restart_pod(pod_name):

#     print(f"Restarting pod: {pod_name}")

#     try:

#         result = subprocess.run(
#             ["kubectl", "delete", "pod", pod_name],
#             capture_output=True,
#             text=True
#         )

#         print(result.stdout)

#     except Exception as e:

#         print("Failed to restart pod:", e)


# # ---------------------------------------------------
# # Detect unhealthy pods properly
# # ---------------------------------------------------
# def detect_unhealthy_pods(pods):

#     unhealthy = []

#     for pod in pods:

#         name = pod["metadata"]["name"]

#         status = pod["status"]

#         phase = status.get("phase")

#         container_statuses = status.get("containerStatuses", [])

#         # Check pod phase
#         if phase != "Running":

#             print(f"{name} phase is {phase}")
#             unhealthy.append(name)
#             continue


#         # Check container states
#         for container in container_statuses:

#             restart_count = container.get("restartCount", 0)

#             state = container.get("state", {})

#             waiting = state.get("waiting")

#             terminated = state.get("terminated")


#             if waiting:

#                 reason = waiting.get("reason", "")
#                 print(f"{name} waiting state: {reason}")
#                 unhealthy.append(name)


#             elif terminated:

#                 reason = terminated.get("reason", "")
#                 print(f"{name} terminated: {reason}")
#                 unhealthy.append(name)


#             elif restart_count > 0:

#                 print(f"{name} restart count: {restart_count}")
#                 unhealthy.append(name)


#     return list(set(unhealthy))


# # ---------------------------------------------------
# # Main detection and auto-healing logic
# # ---------------------------------------------------
# def detect_and_fix():

#     pods = get_pods()

#     if not pods:

#         print("No pods found or MCP not working")
#         return


#     unhealthy = detect_unhealthy_pods(pods)


#     if not unhealthy:

#         print("All pods healthy")
#         return


#     print("\nUnhealthy pods detected:", unhealthy)


#     context = {

#         "unhealthy_pods": unhealthy,
#         "metrics": get_metrics()
#     }


#     ai_response = ask_ai(context)


#     print("\nAI Diagnosis:")
#     print(ai_response)


#     # Auto restart unhealthy pods
#     for pod in unhealthy:

#         restart_pod(pod)


# # ---------------------------------------------------
# # Continuous monitoring loop
# # ---------------------------------------------------
# def monitor():

#     print("Starting Autonomous AI DevOps Agent...")

#     while True:

#         print("\nChecking cluster health...")

#         detect_and_fix()

#         time.sleep(CHECK_INTERVAL)


# # ---------------------------------------------------
# # Start agent
# # ---------------------------------------------------
# if __name__ == "__main__":

#     monitor()

import requests
import subprocess
import time
import json

MCP_URL = "http://127.0.0.1:5000"
OLLAMA_URL = "http://localhost:11434/api/generate"
CHECK_INTERVAL = 15

# ===== Safety controls =====
RESTART_COOLDOWN = 300  # seconds
MAX_RESTARTS = 2

PROTECTED_NAMESPACES = {
    "kube-system",
    "monitoring",
    "prometheus",
    "grafana"
}

restart_history = {}


# ---------------------------------------------------
def get_pods():
    try:
        r = requests.get(f"{MCP_URL}/pods", timeout=5)
        return r.json().get("items", [])
    except Exception as e:
        print("MCP error:", e)
        return []


# ---------------------------------------------------
def get_metrics():
    try:
        r = requests.get(f"{MCP_URL}/metrics", timeout=5)
        return r.json().get("metrics", "")
    except:
        return ""


# ---------------------------------------------------
def ask_ai(context):
    prompt = f"""
You are a Kubernetes SRE AI.

Analyze the cluster issues below and decide if pods should be restarted.

Cluster data:
{json.dumps(context, indent=2)}

Rules:
- CrashLoopBackOff pods should usually be restarted
- HighRestartCount pods (>5 restarts) need investigation but can be restarted
- Respond with valid action: "restart" or "ignore"

Respond ONLY with this exact JSON format:

{{
  "problem": "brief description",
  "action": "restart",
  "reason": "why this action"
}}
"""
    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": "phi3",
                "prompt": prompt,
                "stream": False
            },
            timeout=60
        )
        
        resp_data = r.json()
        response_text = resp_data.get("response", "")
        
        if not response_text:
            print("AI error: Empty response from Ollama")
            return None
        
        # Remove markdown code blocks (```json ... ``` or ``` ... ```)
        import re
        response_text = re.sub(r'^```(?:json)?\s*\n', '', response_text)
        response_text = re.sub(r'\n```\s*$', '', response_text)
        response_text = response_text.strip()
        
        # Try direct JSON parsing
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try finding JSON object in text
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass
            
            print(f"AI error: Could not parse JSON from: {response_text[:200]}")
            return None
    
    except Exception as e:
        print(f"AI error: {type(e).__name__}: {str(e)[:200]}")
        return None


# ---------------------------------------------------
def restart_pod(namespace, pod):
    key = f"{namespace}/{pod}"
    now = time.time()

    last = restart_history.get(key, {"count": 0, "time": 0})

    if last["count"] >= MAX_RESTARTS:
        print(f" Max restarts reached for {key}")
        return

    if now - last["time"] < RESTART_COOLDOWN:
        print(f" Cooldown active for {key}")
        return

    print(f" Restarting pod {key}")
    subprocess.run(
        ["kubectl", "delete", "pod", pod, "-n", namespace],
        capture_output=True,
        text=True
    )

    restart_history[key] = {
        "count": last["count"] + 1,
        "time": now
    }


# ---------------------------------------------------
def detect_unhealthy_pods(pods):
    problems = []

    for pod in pods:
        name = pod["metadata"]["name"]
        namespace = pod["metadata"]["namespace"]

        if namespace in PROTECTED_NAMESPACES:
            continue

        status = pod.get("status", {})
        phase = status.get("phase")

        containers = status.get("containerStatuses", [])

        for c in containers:
            state = c.get("state", {})

            if state.get("waiting", {}).get("reason") == "CrashLoopBackOff":
                problems.append({
                    "namespace": namespace,
                    "pod": name,
                    "issue": "CrashLoopBackOff"
                })

            elif c.get("restartCount", 0) >= 5:
                problems.append({
                    "namespace": namespace,
                    "pod": name,
                    "issue": "HighRestartCount"
                })

        if phase not in ("Running", "Succeeded"):
            problems.append({
                "namespace": namespace,
                "pod": name,
                "issue": f"Phase:{phase}"
            })

    return problems


# ---------------------------------------------------
def detect_and_fix():
    pods = get_pods()

    if not pods:
        print("No pods found")
        return

    problems = detect_unhealthy_pods(pods)

    if not problems:
        print("Cluster healthy")
        return

    print(" Problems detected:", problems)

    context = {
        "problems": problems,
        "metrics": get_metrics()
    }

    ai = ask_ai(context)

    if not ai:
        print("AI unavailable — skipping auto-fix")
        return

    print(" AI decision:", ai)

    action = ai.get("action", "").lower()
    if action == "restart" or "restart" in action:
        print(f" Restarting {len(problems)} problematic pods...")
        for p in problems:
            restart_pod(p["namespace"], p["pod"])
    else:
        print(f" AI chose action '{action}' - skipping restart")


# ---------------------------------------------------
def monitor():
    print(" Autonomous AI DevOps Agent started")

    while True:
        try:
            detect_and_fix()
        except Exception as e:
            print("Agent error:", e)

        time.sleep(CHECK_INTERVAL)


# ---------------------------------------------------
if __name__ == "__main__":
    monitor()
