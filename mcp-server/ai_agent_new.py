import requests
import subprocess
import time
import json
from datetime import datetime
import os

MCP_URL = "http://127.0.0.1:5000"
OLLAMA_URL = "http://localhost:11434/api/generate"
CHECK_INTERVAL = 15
LOG_FILE = "pod_restart_log.txt"

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
def get_pod_logs(pod_name):
    """Get logs from a pod via MCP server for root cause analysis"""
    try:
        r = requests.get(f"{MCP_URL}/logs/{pod_name}", timeout=10)
        if r.status_code == 200:
            return r.json().get("logs", "No logs available")
        return "Failed to fetch logs"
    except Exception as e:
        return f"Error fetching logs: {e}"


# ---------------------------------------------------
def get_pod_describe(pod_name):
    """Get detailed pod info via MCP server for root cause analysis"""
    try:
        r = requests.get(f"{MCP_URL}/describe/{pod_name}", timeout=10)
        if r.status_code == 200:
            return r.json().get("describe", "No description available")
        return "Failed to fetch description"
    except Exception as e:
        return f"Error fetching description: {e}"


# ---------------------------------------------------
def analyze_root_cause(pod_name):
    """Gather diagnostic information for root cause analysis"""
    print(f"    Analyzing root cause for {pod_name}...")
    
    logs = get_pod_logs(pod_name)
    describe = get_pod_describe(pod_name)
    
    # Extract last 50 lines of logs for analysis
    log_lines = logs.split('\n') if logs else []
    recent_logs = '\n'.join(log_lines[-50:]) if log_lines else "No logs"
    
    return {
        "logs": recent_logs,
        "describe": describe
    }


# ---------------------------------------------------
def log_action(namespace, pod, issue, action, root_cause, ai_diagnosis):
    """Log pod actions with root cause and fix recommendations"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    log_entry = f"""
{'='*80}
Timestamp: {timestamp}
Namespace: {namespace}
Pod: {pod}
Issue Detected: {issue}
Action Taken: {action}

AI ROOT CAUSE DIAGNOSIS:
-----------------------
{json.dumps(ai_diagnosis, indent=2)}

DIAGNOSTIC DATA:
---------------
Describe Info:
{root_cause.get('describe', 'N/A')[:1500]}

Recent Logs (last 50 lines):
{root_cause.get('logs', 'N/A')[:3000]}

RECOMMENDATION:
--------------
Fix Type: {ai_diagnosis.get('fix_type', 'N/A')}
Fix Action: {ai_diagnosis.get('fix_action', 'N/A')}
Severity: {ai_diagnosis.get('severity', 'N/A')}

{'='*80}

"""
    
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        print(f"    ✓ Logged to {LOG_FILE}")
    except Exception as e:
        print(f"    ✗ Failed to write log: {e}")


# ---------------------------------------------------
def ask_ai_for_diagnosis(context):
    """Ask AI to diagnose the root cause and suggest fixes"""
    prompt = f"""
You are a Kubernetes SRE AI expert. Analyze the pod failure below and identify the ROOT CAUSE.

Pod diagnostic data:
{json.dumps(context, indent=2)}

Analyze the logs, describe output, and events to determine:
1. What is the ACTUAL root cause? (not just "CrashLoopBackOff" but WHY)
2. What is the recommended FIX?

CRITICAL RULES:
- If issue is "OOMKilled" → MUST use fix_type="resources" (memory too low)
- If logs show "Out of memory" or "OOM" → fix_type="resources"
- If CPU throttling detected → fix_type="resources"
- If ImagePullBackOff/ErrImagePull → fix_type="image"
- If missing env vars or volumes → fix_type="config"
- If application code errors → fix_type="app_code"

Respond ONLY with this exact JSON format:

{{
  "root_cause": "specific technical reason for failure",
  "fix_type": "config|resources|image|app_code|restart|manual",
  "fix_action": "specific fix to apply",
  "should_restart": true/false,
  "severity": "critical|high|medium|low"
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
        
        # Remove markdown code blocks
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
def check_if_managed_pod(namespace, pod):
    """Check if pod is managed by a controller (Deployment, StatefulSet, etc.)"""
    try:
        result = subprocess.run(
            ["kubectl", "get", "pod", pod, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            pod_data = json.loads(result.stdout)
            owner_refs = pod_data.get("metadata", {}).get("ownerReferences", [])
            
            if owner_refs:
                owner_kind = owner_refs[0].get("kind", "")
                return True, owner_kind
            return False, "StandalonePod"
    except Exception as e:
        print(f"    ⚠ Error checking pod ownership: {e}")
    
    return False, "Unknown"


# ---------------------------------------------------
def get_pod_owner_deployment(namespace, pod):
    """Get the deployment name for a pod"""
    try:
        result = subprocess.run(
            ["kubectl", "get", "pod", pod, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            pod_data = json.loads(result.stdout)
            owner_refs = pod_data.get("metadata", {}).get("ownerReferences", [])
            
            if owner_refs:
                owner_kind = owner_refs[0].get("kind", "")
                owner_name = owner_refs[0].get("name", "")
                
                # If owned by ReplicaSet, find the parent Deployment
                if owner_kind == "ReplicaSet":
                    rs_result = subprocess.run(
                        ["kubectl", "get", "replicaset", owner_name, "-n", namespace, "-o", "json"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if rs_result.returncode == 0:
                        rs_data = json.loads(rs_result.stdout)
                        rs_owners = rs_data.get("metadata", {}).get("ownerReferences", [])
                        if rs_owners and rs_owners[0].get("kind") == "Deployment":
                            return rs_owners[0].get("name")
                
                return owner_name
    except Exception as e:
        print(f"    ⚠ Error finding deployment: {e}")
    
    return None


# ---------------------------------------------------
def apply_fix(namespace, pod, diagnosis):
    """Apply the recommended fix based on AI diagnosis"""
    fix_type = diagnosis.get("fix_type", "")
    fix_action = diagnosis.get("fix_action", "")
    
    print(f"\n  Fix Type: {fix_type}")
    print(f"  Fix Action: {fix_action}")
    
    # Check if pod is managed by a controller
    is_managed, owner_kind = check_if_managed_pod(namespace, pod)
    
    if fix_type == "resources":
        print(f"  → Attempting to fix resource limits...")
        deployment = get_pod_owner_deployment(namespace, pod)
        
        if deployment:
            print(f"  → Found deployment: {deployment}")
            
            # Get current container specs from the pod
            try:
                pod_result = subprocess.run(
                    ["kubectl", "get", "pod", pod, "-n", namespace, "-o", "json"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if pod_result.returncode == 0:
                    pod_data = json.loads(pod_result.stdout)
                    containers = pod_data.get("spec", {}).get("containers", [])
                    
                    if containers:
                        container_name = containers[0].get("name")
                        current_resources = containers[0].get("resources", {})
                        current_limits = current_resources.get("limits", {})
                        
                        # Calculate new limits (3x current or safe defaults)
                        def parse_memory(mem_str):
                            """Parse memory string like '128Mi' to MB"""
                            if not mem_str:
                                return 256
                            if mem_str.endswith("Mi"):
                                return int(mem_str[:-2])
                            elif mem_str.endswith("Gi"):
                                return int(mem_str[:-2]) * 1024
                            return 256
                        
                        def parse_cpu(cpu_str):
                            """Parse CPU string like '100m' to millicores"""
                            if not cpu_str:
                                return 500
                            if cpu_str.endswith("m"):
                                return int(cpu_str[:-1])
                            return int(float(cpu_str) * 1000)
                        
                        current_mem = parse_memory(current_limits.get("memory"))
                        current_cpu = parse_cpu(current_limits.get("cpu"))
                        
                        # Increase by 3x or set minimums
                        new_mem = max(current_mem * 3, 512)
                        new_cpu = max(current_cpu * 3, 500)
                        
                        print(f"  → Container: {container_name}")
                        print(f"  → Current limits: memory={current_mem}Mi, cpu={current_cpu}m")
                        print(f"  → New limits: memory={new_mem}Mi, cpu={new_cpu}m")
                        print(f"  → Patching deployment...")
                        
                        patch = {
                            "spec": {
                                "template": {
                                    "spec": {
                                        "containers": [{
                                            "name": container_name,
                                            "resources": {
                                                "limits": {
                                                    "memory": f"{new_mem}Mi",
                                                    "cpu": f"{new_cpu}m"
                                                },
                                                "requests": {
                                                    "memory": f"{new_mem // 2}Mi",
                                                    "cpu": f"{new_cpu // 2}m"
                                                }
                                            }
                                        }]
                                    }
                                }
                            }
                        }
                        
                        result = subprocess.run(
                            ["kubectl", "patch", "deployment", deployment, "-n", namespace, 
                             "--type=strategic", "-p", json.dumps(patch)],
                            capture_output=True,
                            text=True
                        )
                        
                        if result.returncode == 0:
                            print(f"  ✓ Resource limits increased successfully!")
                            print(f"  → Deployment will rollout new pods automatically")
                            return "RESOURCES_FIXED"
                        else:
                            print(f"  ✗ Failed to patch: {result.stderr}")
                            return "RESOURCE_FIX_FAILED"
                            
            except Exception as e:
                print(f"  ✗ Error patching resources: {e}")
                return "RESOURCE_FIX_FAILED"
        else:
            print(f"  ⚠ No deployment found, manual intervention needed")
            return "MANUAL_RESOURCE_FIX_NEEDED"
    
    elif fix_type == "config":
        print(f"  → Configuration issue detected")
        print(f"  → Manual ConfigMap/Secret update required: {fix_action}")
        return "CONFIG_FIX_NEEDED"
    
    elif fix_type == "image":
        print(f"  → Image issue detected")
        deployment = get_pod_owner_deployment(namespace, pod)
        
        if deployment:
            print(f"  → Found deployment: {deployment}")
            print(f"  → Manual image update needed: {fix_action}")
            return "IMAGE_FIX_NEEDED"
        else:
            return "MANUAL_IMAGE_FIX_NEEDED"
    
    elif fix_type == "app_code":
        print(f"  → Application code bug detected")
        print(f"  → Developer action required: {fix_action}")
        
        if not is_managed:
            print(f"  ⚠ STANDALONE POD - Will NOT delete (pod won't recreate)")
            return "APP_CODE_FIX_NEEDED_NO_DELETE"
        else:
            print(f"  → Pod is managed by {owner_kind}, restart may help expose more logs")
            if diagnosis.get("should_restart"):
                print(f"  → Restarting pod...")
                result = subprocess.run(
                    ["kubectl", "delete", "pod", pod, "-n", namespace],
                    capture_output=True,
                    text=True
                )
                return "RESTARTED_FOR_LOGS"
            return "APP_CODE_FIX_NEEDED"
    
    elif fix_type == "restart" or diagnosis.get("should_restart"):
        if not is_managed:
            print(f"  ⚠ STANDALONE POD - Will NOT delete (pod won't recreate)")
            print(f"  → Please fix the issue manually and redeploy")
            return "STANDALONE_POD_NO_DELETE"
        
        print(f"  → Pod is managed by {owner_kind}, safe to restart")
        print(f"  → Restarting pod {namespace}/{pod}...")
        result = subprocess.run(
            ["kubectl", "delete", "pod", pod, "-n", namespace],
            capture_output=True,
            text=True
        )
        return "RESTARTED"
    
    elif fix_type == "manual":
        print(f"  → Manual intervention required")
        print(f"  → ACTION NEEDED: {fix_action}")
        return "MANUAL_ACTION_NEEDED"
    
    else:
        print(f"  → Unknown fix type, logging for manual review")
        return "MANUAL_REVIEW_NEEDED"


# ---------------------------------------------------
def diagnose_and_fix_pod(namespace, pod, issue):
    """Diagnose root cause and apply appropriate fix"""
    key = f"{namespace}/{pod}"
    now = time.time()

    last = restart_history.get(key, {"count": 0, "time": 0})

    if last["count"] >= MAX_RESTARTS:
        print(f"  ⚠ Max restarts reached for {key} - needs manual investigation")
        return False

    if now - last["time"] < RESTART_COOLDOWN:
        print(f"  ⏳ Cooldown active for {key}")
        return False

    print(f"\n🔍 Diagnosing {key}...")
    
    # Gather diagnostic information
    root_cause_data = analyze_root_cause(pod)
    
    # Prepare context for AI diagnosis
    diagnostic_context = {
        "namespace": namespace,
        "pod": pod,
        "issue": issue,
        "logs": root_cause_data.get("logs", "No logs")[:2000],
        "describe": root_cause_data.get("describe", "No description")[:1500]
    }
    
    # Get AI diagnosis and fix recommendation
    ai_diagnosis = ask_ai_for_diagnosis(diagnostic_context)
    
    if not ai_diagnosis:
        print("  ⚠ AI diagnosis failed, will restart as fallback")
        ai_diagnosis = {
            "root_cause": "Unknown - AI diagnosis unavailable",
            "fix_type": "restart",
            "fix_action": "Restart pod as fallback",
            "should_restart": True,
            "severity": "medium"
        }
    
    print(f"\n📋 AI Diagnosis:")
    print(f"  Root Cause: {ai_diagnosis.get('root_cause', 'Unknown')}")
    print(f"  Severity: {ai_diagnosis.get('severity', 'unknown').upper()}")
    
    # Apply the recommended fix
    action_taken = apply_fix(namespace, pod, ai_diagnosis)
    
    # Log everything
    log_action(namespace, pod, issue, action_taken, root_cause_data, ai_diagnosis)
    
    # Update restart history only if we actually restarted
    if "RESTART" in action_taken:
        restart_history[key] = {
            "count": last["count"] + 1,
            "time": now
        }
    
    return True


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
            last_state = c.get("lastState", {})

            # Check for CrashLoopBackOff
            if state.get("waiting", {}).get("reason") == "CrashLoopBackOff":
                problems.append({
                    "namespace": namespace,
                    "pod": name,
                    "issue": "CrashLoopBackOff"
                })

            # Check for OOMKilled in last terminated state
            terminated_reason = last_state.get("terminated", {}).get("reason", "")
            if terminated_reason == "OOMKilled":
                problems.append({
                    "namespace": namespace,
                    "pod": name,
                    "issue": "OOMKilled"
                })

            # High restart count
            elif c.get("restartCount", 0) >= 5:
                problems.append({
                    "namespace": namespace,
                    "pod": name,
                    "issue": "HighRestartCount"
                })

        # Detect non-healthy phases (but skip Terminating as it's already being deleted)
        if phase == "Pending":
            # Pod stuck in pending - could be scheduling issues
            problems.append({
                "namespace": namespace,
                "pod": name,
                "issue": "PodPending"
            })
        elif phase == "Failed":
            problems.append({
                "namespace": namespace,
                "pod": name,
                "issue": "PodFailed"
            })
        elif phase == "Unknown":
            problems.append({
                "namespace": namespace,
                "pod": name,
                "issue": "PodUnknown"
            })
        elif phase == "Terminating":
            # Pod is being deleted - just log it, don't take action
            print(f"    Pod {namespace}/{name} is terminating (manual deletion or update)")

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

    print(f"\n🔧 Analyzing {len(problems)} problematic pod(s)...\n")
    
    fixed = 0
    for p in problems:
        print(f"{'='*60}")
        if diagnose_and_fix_pod(p["namespace"], p["pod"], p["issue"]):
            fixed += 1
    
    print(f"\n{'='*60}")
    print(f"✓ Processed {fixed}/{len(problems)} pod(s)")
    print(f"Check {LOG_FILE} for detailed diagnosis")


# ---------------------------------------------------
def monitor():
    print("="*80)
    print(f" Autonomous AI DevOps Agent started")
    print(f" Log file: {LOG_FILE}")
    print(f" Check interval: {CHECK_INTERVAL}s")
    print(f" MCP Server: {MCP_URL}")
    print("="*80)

    while True:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] Checking cluster health...")
            detect_and_fix()
        except Exception as e:
            print(f"Agent error: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(CHECK_INTERVAL)


# ---------------------------------------------------
if __name__ == "__main__":
    monitor()
