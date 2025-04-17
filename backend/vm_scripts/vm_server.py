from flask import Flask, request, jsonify
import os
import psutil
import subprocess
import boto3
import botocore
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import sys
import logging
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("C:\\CloudRAM\\vm_server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# AWS + Local Paths using environment variable credentials
BUCKET_NAME = 'notepadfiles'
SYNCED_DIR = "C:\\Users\\vm_user\\SyncedNotepadFiles"

# Load credentials from environment variables (Machine-level)
session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
)
credentials = session.get_credentials()

if credentials is None:
    logger.error("AWS credentials not found in environment.")
else:
    logger.info("AWS credentials loaded from environment.")

s3 = session.client('s3')

# Notepad++ possible paths
NOTEPAD_PATHS = [
    r"C:\\Program Files\\Notepad++\\notepad++.exe",
    r"C:\\Program Files (x86)\\Notepad++\\notepad++.exe"
]

# In-memory task tracking
running_tasks = {}
# Track open files in Notepad++
open_notepad_files = set()

def get_notepad_exe():
    for path in NOTEPAD_PATHS:
        if os.path.exists(path):
            return path
    return "notepad++.exe"

@app.route("/")
def home():
    logger.info("Accessed home endpoint")
    return jsonify({"message": "Cloud RAM VM API is running!"})

@app.route("/list_tasks", methods=["GET"])
def list_tasks():
    target_tasks = ['notepad++.exe', 'chrome.exe', 'Code.exe']
    task_list = []
    for proc in psutil.process_iter(attrs=['pid', 'name']):
        if proc.info['name'] in target_tasks:
            task_list.append({"pid": proc.info['pid'], "name": proc.info['name']})
    return jsonify({"tasks": task_list})

@app.route("/terminate_task", methods=["POST"])
def terminate_task():
    data = request.get_json()
    pid = data.get("pid")
    if not pid:
        logger.error("PID required but not provided")
        return jsonify({"error": "PID required"}), 400
    try:
        process = psutil.Process(pid)
        process.terminate()
        running_tasks.pop(pid, None)
        logger.info(f"Task with PID {pid} terminated successfully")
        return jsonify({"message": f"Task with PID {pid} terminated successfully"})
    except psutil.NoSuchProcess:
        logger.error(f"Process with PID {pid} not found")
        return jsonify({"error": "Process not found"}), 404

@app.route("/ram_usage", methods=["GET"])
def ram_usage():
    ram_info = psutil.virtual_memory()
    return jsonify({
        "total_ram": ram_info.total,
        "used_ram": ram_info.used,
        "available_ram": ram_info.available,
        "percent_used": ram_info.percent
    })

@app.route("/run_task", methods=["POST"])
def run_task():
    try:
        logger.info("/run_task endpoint called")
        data = request.get_json()
        task = data.get("task")

        if not task:
            return jsonify({"error": "Task name required"}), 400

        if task != "notepad++.exe":
            return jsonify({"error": f"Unsupported task: {task}"}), 400

        # Ensure directories exist
        os.makedirs(SYNCED_DIR, exist_ok=True)
        os.makedirs("C:\\CloudRAM", exist_ok=True)

        # Sync files from S3
        try:
            sync_notepad_files()
        except Exception as sync_error:
            logger.error(f"Sync error: {sync_error}")

        # Gather file paths
        file_paths = [
            os.path.join(SYNCED_DIR, f)
            for f in os.listdir(SYNCED_DIR)
            if os.path.isfile(os.path.join(SYNCED_DIR, f)) and f.endswith(('.txt', '.cpp', '.py', '.html'))
        ]

        if not file_paths:
            logger.info("No files found to open")
            return jsonify({"message": "No files found to open", "file_count": 0})

        # Get Notepad++ executable path
        notepad_exe = get_notepad_exe()
        if not os.path.exists(notepad_exe):
            logger.error(f"Notepad++ executable not found at {notepad_exe}")
            return jsonify({"error": "Notepad++ executable not found"}), 500

        # Log current session info for debugging
        try:
            session_info = subprocess.run(
                ["wmic", "process", "where", f"ProcessID={os.getpid()}", "get", "SessionId"],
                capture_output=True, text=True
            )
            logger.info(f"Flask app running in session: {session_info.stdout}")
        except Exception as e:
            logger.error(f"Failed to get session info: {e}")

        # Get the active session ID (VNC session)
        try:
            session_check = subprocess.run(
                ["qwinsta"], capture_output=True, text=True
            )
            logger.info(f"Active sessions: {session_check.stdout}")
            active_session_id = None
            for line in session_check.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[3] == "Active" and ("console" in line.lower() or "rdp-tcp" in line.lower()):
                    active_session_id = parts[2]  # Session ID is the third column
                    break
            logger.info(f"Detected active session ID: {active_session_id}")
        except Exception as e:
            logger.error(f"Failed to get active session: {e}")
            active_session_id = None

        # Use schtasks to launch Notepad++ in the active session
        task_name = "LaunchNotepad"
        cmd = f'"{notepad_exe}" {" ".join([f"\"{path}\"" for path in file_paths])}'
        logger.info(f"Preparing to launch Notepad++ with schtasks command: {cmd}")

        try:
            # Delete existing task if it exists
            delete_result = subprocess.run(
                ["schtasks", "/delete", "/tn", task_name, "/f"],
                capture_output=True, text=True
            )
            logger.info(f"schtasks delete output: {delete_result.stdout}")
            if delete_result.stderr:
                logger.error(f"schtasks delete error: {delete_result.stderr}")

            # Create a scheduled task to run immediately under the Administrator user
            create_task_cmd = [
                "schtasks", "/create", "/tn", task_name, "/tr", cmd,
                "/sc", "once", "/st", "00:00", "/ru", "Administrator", "/it"
            ]
            create_result = subprocess.run(
                create_task_cmd, capture_output=True, text=True
            )
            logger.info(f"schtasks create output: {create_result.stdout}")
            if create_result.stderr:
                logger.error(f"schtasks create error: {create_result.stderr}")

            # Check if task was created
            query_task = subprocess.run(
                ["schtasks", "/query", "/tn", task_name],
                capture_output=True, text=True
            )
            logger.info(f"schtasks query output: {query_task.stdout}")
            if query_task.stderr:
                logger.error(f"schtasks query error: {query_task.stderr}")

            # Run the task immediately
            run_task_cmd = ["schtasks", "/run", "/tn", task_name]
            run_result = subprocess.run(
                run_task_cmd, capture_output=True, text=True
            )
            logger.info(f"schtasks run output: {run_result.stdout}")
            if run_result.stderr:
                logger.error(f"schtasks run error: {run_result.stderr}")

            # Check if Notepad++ is running
            time.sleep(2)  # Give it a moment to start
            task_check = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq notepad++.exe", "/V"],
                capture_output=True, text=True
            )
            logger.info(f"Tasklist output for Notepad++: {task_check.stdout}")

            # Extract PID if Notepad++ is running
            pid = None
            for line in task_check.stdout.splitlines():
                if "notepad++.exe" in line.lower():
                    parts = line.split()
                    pid = parts[1]  # PID is the second column
                    break

            if not pid:
                logger.warning("Notepad++ not found in tasklist, trying notepad.exe as fallback")
                # Fallback: Create and run a task for notepad.exe
                cmd_fallback = f'"notepad.exe" {" ".join([f"\"{path}\"" for path in file_paths])}'
                create_task_cmd = [
                    "schtasks", "/create", "/tn", task_name, "/tr", cmd_fallback,
                    "/sc", "once", "/st", "00:00", "/ru", "Administrator", "/it"
                ]
                create_result = subprocess.run(
                    create_task_cmd, capture_output=True, text=True
                )
                logger.info(f"schtasks create (fallback) output: {create_result.stdout}")
                if create_result.stderr:
                    logger.error(f"schtasks create (fallback) error: {create_result.stderr}")

                run_result = subprocess.run(
                    ["schtasks", "/run", "/tn", task_name],
                    capture_output=True, text=True
                )
                logger.info(f"schtasks run (fallback) output: {run_result.stdout}")
                if run_result.stderr:
                    logger.error(f"schtasks run (fallback) error: {run_result.stderr}")

                time.sleep(2)
                task_check = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq notepad.exe", "/V"],
                    capture_output=True, text=True
                )
                logger.info(f"Tasklist output for notepad.exe: {task_check.stdout}")

                for line in task_check.stdout.splitlines():
                    if "notepad.exe" in line.lower():
                        parts = line.split()
                        pid = parts[1]
                        break

            opened_files = file_paths
            if pid:
                running_tasks[pid] = {"name": task, "files": file_paths}
                return jsonify({
                    "message": "Launched with files",
                    "file_count": len(opened_files),
                    "files": opened_files,
                    "pid": pid
                })
            else:
                return jsonify({"error": "Failed to launch application"}), 500

        except subprocess.SubprocessError as e:
            logger.error(f"Failed to launch: {e}")
            return jsonify({"error": f"Failed to launch: {str(e)}"}), 500

    except Exception as e:
        error_msg = f"Error in /run_task: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({"error": error_msg}), 500

@app.route("/sync_notepad_files", methods=["POST"])
def sync_notepad_files_endpoint():
    data = request.get_json()
    specific_file = data.get("file")
    
    if specific_file:
        logger.info(f"Syncing specific file: {specific_file}")
        sync_specific_file(specific_file)
        # Refresh open files if needed
        refresh_open_files_in_notepad()
    else:
        logger.info("Syncing all Notepad++ files")
        sync_notepad_files()
        
    return jsonify({"message": "Notepad++ files synced with S3"})

def sync_specific_file(filename):
    """Sync a specific file from S3"""
    os.makedirs(SYNCED_DIR, exist_ok=True)
    local_path = os.path.join(SYNCED_DIR, filename)
    
    try:
        logger.info(f"Downloading {filename} to {local_path}")
        s3.download_file(BUCKET_NAME, filename, local_path)
        logger.info(f"Downloaded {filename}")
        
        # If this file is open in Notepad++, refresh it
        if local_path in open_notepad_files:
            logger.info(f"File {filename} is open in Notepad++")
    except Exception as e:
        logger.error(f"Error downloading {filename}: {e}")

def sync_notepad_files():
    os.makedirs(SYNCED_DIR, exist_ok=True)
    logger.info(f"Syncing from S3 bucket: {BUCKET_NAME}")

    try:
        response = s3.list_objects_v2(Bucket=BUCKET_NAME)
        objects = response.get('Contents', [])

        if not objects:
            logger.info("No files found in S3 bucket")
            return

        for obj in objects:
            s3_key = obj['Key']
            filename = os.path.basename(s3_key)
            local_path = os.path.join(SYNCED_DIR, filename)

            try:
                logger.info(f"Downloading {s3_key} to {local_path}")
                s3.download_file(BUCKET_NAME, s3_key, local_path)
                logger.info(f"Downloaded {filename}")
            except Exception as e:
                logger.error(f"Error downloading {s3_key}: {e}")

    except botocore.exceptions.ClientError as ce:
        logger.error(f"S3 ClientError: {ce}")
    except Exception as e:
        logger.error(f"General sync error: {e}")

def upload_to_s3(file_path):
    """Upload modified file to S3 bucket and notify local system"""
    if not os.path.isfile(file_path):
        logger.error(f"Cannot upload non-existent file: {file_path}")
        return
        
    try:
        filename = os.path.basename(file_path)
        logger.info(f"Uploading {filename} to S3")
        s3.upload_file(file_path, BUCKET_NAME, filename)
        logger.info(f"Uploaded {filename} to S3")

    except Exception as e:
        logger.error(f"Error uploading {file_path} to S3: {e}")

@app.route("/upload_modified_file", methods=["POST"])
def upload_modified_file():
    data = request.get_json()
    file_path = data.get("file_path")
    
    if not file_path:
        logger.error("No file path provided")
        return jsonify({"error": "File path required"}), 400
        
    if not os.path.isfile(file_path):
        logger.error(f"File not found: {file_path}")
        return jsonify({"error": "File not found"}), 404
        
    try:
        upload_to_s3(file_path)
        return jsonify({"message": f"File {file_path} uploaded to S3"})
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return jsonify({"error": str(e)}), 500

def check_for_open_notepad_files():
    """Check if any notepad processes have the synced files open"""
    if not os.path.exists(SYNCED_DIR):
        return []
        
    synced_files = [
        os.path.join(SYNCED_DIR, f)
        for f in os.listdir(SYNCED_DIR)
        if f.endswith(('.txt', '.cpp', '.py', '.html'))
    ]
    
    if not synced_files:
        return []
        
    open_files = []
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] == 'notepad++.exe':
            try:
                p = psutil.Process(proc.info['pid'])
                for file in p.open_files():
                    if file.path in synced_files:
                        open_files.append(file.path)
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
    
    return open_files

def refresh_open_files_in_notepad():
    """Alert Notepad++ to reload files that may have changed"""
    open_files = check_for_open_notepad_files()
    if not open_files:
        logger.info("No open files to refresh")
        return
        
    logger.info(f"Files open in Notepad++: {open_files}")
    # Since Notepad++ auto-detects file changes, we just need to ensure
    # the files are properly synchronized

class NotepadSyncHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(('.txt', '.cpp', '.py', '.html')):
            logger.info(f"Detected change on VM: {event.src_path}")
            # Upload to S3 when file changes
            upload_to_s3(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(('.txt', '.cpp', '.py', '.html')):
            logger.info(f"New file created on VM: {event.src_path}")
            # Upload new file to S3
            upload_to_s3(event.src_path)

def start_vm_file_watcher():
    event_handler = NotepadSyncHandler()
    observer = Observer()
    observer.schedule(event_handler, SYNCED_DIR, recursive=True)
    observer.start()
    logger.info(f"Watching for changes in VM files at: {SYNCED_DIR}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    logger.info("Starting VM server...")
    watcher_thread = threading.Thread(target=start_vm_file_watcher, daemon=True)
    watcher_thread.start()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)