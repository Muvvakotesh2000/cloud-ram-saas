import psutil
import requests
import os
import shutil
import boto3
import botocore.exceptions
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import time
import xml.etree.ElementTree as ET
import subprocess
import logging
import win32gui
import win32con

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("process_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProcessManager:
    def __init__(self):
        self.s3 = boto3.client('s3')
        self.BUCKET_NAME = 'notepadfiles'
        self.sync_running = False
        self.notepad_dir = r"C:\\Users\\muvva\\AppData\\Roaming\\Notepad++"
        self.backup_dir = os.path.join(self.notepad_dir, "backup")
        self.unsaved_temp_dir = os.path.join(os.getcwd(), "unsaved_files")
        os.makedirs(self.unsaved_temp_dir, exist_ok=True)
        self.tracked_files = set()
        self.file_record_path = "notepad_file_paths.txt"
        self.vm_ip = None
        self.load_tracked_files()

    def load_tracked_files(self):
        """Load previously tracked files from the record"""
        if os.path.exists(self.file_record_path):
            with open(self.file_record_path, 'r') as f:
                self.tracked_files = set(line.strip() for line in f)
                logger.info(f"Loaded {len(self.tracked_files)} tracked files from record")

    def force_notepad_session_save(self):
        """
        Force Notepad++ to save its session by sending a WM_CLOSE message to its window,
        then immediately cancel the close to keep it running.
        """
        try:
            # Find the Notepad++ window
            hwnd = None
            def enum_windows_callback(hwnd, results):
                if "notepad++" in win32gui.GetWindowText(hwnd).lower():
                    results.append(hwnd)
            windows = []
            win32gui.EnumWindows(enum_windows_callback, windows)
            if not windows:
                logger.warning("No Notepad++ window found to force session save")
                return False

            hwnd = windows[0]
            logger.info(f"Found Notepad++ window handle: {hwnd}")

            # Send WM_CLOSE to trigger session save
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            time.sleep(1)  # Give it a moment to save the session

            # Check if Notepad++ is still running; if not, restart it
            notepad_running = any(proc.info['name'].lower() == 'notepad++.exe' 
                                 for proc in psutil.process_iter(['pid', 'name']))
            if not notepad_running:
                logger.info("Notepad++ closed after WM_CLOSE, restarting...")
                notepad_exe = r"C:\\Program Files\\Notepad++\\notepad++.exe"
                if not os.path.exists(notepad_exe):
                    notepad_exe = r"C:\\Program Files (x86)\\Notepad++\\notepad++.exe"
                subprocess.Popen([notepad_exe])
                time.sleep(3)

            logger.info("Forced Notepad++ session save")
            return True
        except Exception as e:
            logger.error(f"Failed to force Notepad++ session save: {e}")
            return False

    def get_current_open_files(self):
        """
        Get the currently open files in Notepad++ by inspecting the process's open file handles.
        Fallback to session.xml if necessary.
        """
        open_files = []
        
        # Step 1: Find the Notepad++ process and inspect its open files
        notepad_proc = None
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'].lower() == 'notepad++.exe':
                notepad_proc = proc
                break
        
        if notepad_proc:
            try:
                # Get all file handles opened by the Notepad++ process
                all_files = notepad_proc.open_files()
                logger.info(f"All open files in Notepad++ via psutil: {[f.path for f in all_files]}")
                for file in all_files:
                    file_path = file.path
                    # Filter for typical Notepad++ file extensions and exclude internal files
                    if (file_path.lower().endswith(('.txt', '.cpp', '.py', '.html')) and 
                        'notepad++' not in file_path.lower() and 
                        os.path.isfile(file_path)):
                        open_files.append(file_path)
                        logger.info(f"Found open file via psutil: {file_path}")
            except psutil.AccessDenied:
                logger.warning("Access denied while trying to get open files from Notepad++ process")
            except Exception as e:
                logger.error(f"Error getting open files via psutil: {e}")

        # Step 2: Fallback to session.xml if no files were found via psutil
        if not open_files:
            logger.info("No files found via psutil, falling back to session.xml")
            session_path = os.path.expanduser("C:\\Users\\muvva\\AppData\\Roaming\\Notepad++\\session.xml")
            if not os.path.exists(session_path):
                logger.error("session.xml not found.")
                return open_files

            try:
                with open(session_path, 'r', encoding='utf-8') as f:
                    session_content = f.read()
                    logger.info(f"session.xml content: {session_content}")
                tree = ET.parse(session_path)
                root = tree.getroot()
                for file_node in root.iter('File'):
                    file_path = file_node.get('filename')
                    if file_path and os.path.isfile(file_path):
                        open_files.append(file_path)
                        logger.info(f"Found open file in session.xml: {file_path}")
            except Exception as e:
                logger.error(f"Failed to parse session.xml: {e}")

        # Remove duplicates while preserving order
        open_files = list(dict.fromkeys(open_files))
        logger.info(f"Final list of open files: {open_files}")
        return open_files

    def get_unsaved_backup_files(self):
        """
        Get unsaved backup files from Notepad++'s backup directory.
        Wait briefly to ensure backups are created.
        """
        # Wait to allow Notepad++ to create backup files
        time.sleep(2)  # Adjust delay if needed
        backups = []
        if os.path.exists(self.backup_dir):
            backup_files = os.listdir(self.backup_dir)
            logger.info(f"Backup files found in {self.backup_dir}: {backup_files}")
            for file in backup_files:
                full_path = os.path.join(self.backup_dir, file)
                if os.path.isfile(full_path):
                    dest = os.path.join(self.unsaved_temp_dir, file)
                    shutil.copy2(full_path, dest)
                    backups.append(dest)
                    logger.info(f"Backed up unsaved file: {file}")
        else:
            logger.warning(f"Backup directory {self.backup_dir} does not exist")
        return backups

    def _refresh_notepad_session(self, files_to_open, unsaved_files):
        try:
            logger.info("Terminating Notepad++ to refresh state...")
            subprocess.call(["taskkill", "/F", "/IM", "notepad++.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)

            notepad_exe = r"C:\\Program Files\\Notepad++\\notepad++.exe"
            if not os.path.exists(notepad_exe):
                notepad_exe = r"C:\\Program Files (x86)\\Notepad++\\notepad++.exe"
            if not os.path.exists(notepad_exe):
                raise FileNotFoundError("Notepad++ executable not found.")

            # Combine files_to_open and unsaved_files, removing duplicates
            all_files = list(dict.fromkeys(files_to_open + unsaved_files))
            command = [notepad_exe] + all_files  # Remove -nosession to allow Notepad++ to load its session state
            logger.info(f"Restarting Notepad++ with updated files: {all_files}")
            subprocess.Popen(command)
            time.sleep(3)

            logger.info("Restart complete.")
            return True

        except Exception as e:
            logger.error(f"Error refreshing Notepad++ session: {e}")
            return False

    def move_task_to_cloud(self, task_name, vm_ip, sync_state=False):
        logger.info(f"move_task_to_cloud called for {task_name} to VM {vm_ip}")
        self.vm_ip = vm_ip

        # Find the process before we do anything
        task = next((p for p in psutil.process_iter(["pid", "name"]) if p.info["name"].lower() == task_name.lower()), None)
        if not task:
            logger.error(f"Task {task_name} not found locally")
            return False

        pid = task.info["pid"]  # Store PID early

        if task_name.lower() == "notepad++.exe" and sync_state:
            logger.info("Extracting Notepad++ session info...")
            # Force Notepad++ to save its session
            self.force_notepad_session_save()

            # Get currently open files
            files_to_track = self.get_current_open_files()
            logger.info(f"Files to track after get_current_open_files: {files_to_track}")

            # Get unsaved files
            unsaved_files = self.get_unsaved_backup_files()
            logger.info(f"Unsaved files detected: {unsaved_files}")

            logger.info("Refreshing Notepad++ session...")
            self._refresh_notepad_session(files_to_track, unsaved_files)

            # Update tracked files
            self.tracked_files = set(files_to_track)
            # Include unsaved files in tracked files if they correspond to actual files
            for unsaved_file in unsaved_files:
                # If the unsaved file has a corresponding real file, track it
                base_name = os.path.basename(unsaved_file)
                # Try to match with open files or assume it's a new file
                corresponding_file = None
                for tracked in files_to_track:
                    if base_name in tracked:
                        corresponding_file = tracked
                        break
                if corresponding_file:
                    self.tracked_files.add(corresponding_file)
                else:
                    # If it's a new unsaved file, we need to give it a proper path
                    new_file_path = os.path.join(os.path.expanduser("~/Documents/NotepadSync"), base_name)
                    if not os.path.exists(os.path.dirname(new_file_path)):
                        os.makedirs(os.path.dirname(new_file_path))
                    shutil.copy2(unsaved_file, new_file_path)
                    self.tracked_files.add(new_file_path)
                    logger.info(f"Added new unsaved file to tracked files: {new_file_path}")

            self._update_tracked_file_list(self.tracked_files)
            logger.info(f"Tracked files after update: {self.tracked_files}")

            logger.info("Uploading tracked files to S3...")
            self._upload_tracked_files_to_s3()

            self.start_notepad_auto_sync(vm_ip)
            self.start_periodic_sync(interval_seconds=30)

            # Force kill again just to be sure
            logger.info("Force killing Notepad++ after refresh...")
            subprocess.call(["taskkill", "/F", "/IM", "notepad++.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.info["name"].lower() == "notepad++.exe":
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except Exception as e:
                        logger.warning(f"Could not terminate lingering Notepad++: {e}")

        else:
            try:
                logger.info(f"Terminating {task_name} (PID: {pid})...")
                proc = psutil.Process(pid)
                proc.terminate()
                proc.wait(timeout=5)
            except psutil.NoSuchProcess:
                logger.warning(f"{task_name} already terminated.")
            except Exception as e:
                logger.error(f"Error terminating {task_name}: {e}")
                return False

        # Start on VM
        try:
            logger.info(f"Sending POST to VM: http://{vm_ip}:5000/run_task with task={task_name}")
            response = requests.post(f"http://{vm_ip}:5000/run_task", json={"task": task_name})
            logger.info(f"Response: {response.status_code} - {response.text}")
            if response.status_code == 200:
                logger.info(f"{task_name} started on VM")
                return True
            else:
                logger.error(f"Failed to start {task_name} on VM")
                return False
        except Exception as e:
            logger.error(f"Could not contact VM: {e}")
            return False

    def get_local_tasks(self):
        try:
            target_tasks = ['notepad++.exe', 'chrome.exe', 'Code.exe']
            tasks = [{"pid": p.info["pid"], "name": p.info["name"]}
                     for p in psutil.process_iter(["pid", "name"]) if p.info["name"] in target_tasks]
            return {"tasks": tasks}
        except Exception as e:
            logger.error(f"Error fetching local tasks: {str(e)}")
            return {"tasks": []}

    def _update_tracked_file_list(self, current_files):
        previous_files = set()
        if os.path.exists(self.file_record_path):
            with open(self.file_record_path, 'r') as f:
                previous_files = set(line.strip() for line in f)

        updated_files = previous_files.union(current_files)
        with open(self.file_record_path, 'w') as f:
            for file in sorted(updated_files):
                f.write(file + '\n')

        logger.info(f"Updated tracked files list with {len(updated_files)} files")

    def _upload_tracked_files_to_s3(self):
        for file_path in self.tracked_files:
            if os.path.exists(file_path):
                s3_key = os.path.basename(file_path)
                try:
                    self._upload_file_to_s3(file_path, s3_key)
                except Exception as e:
                    logger.error(f"Upload error: {e}")
            else:
                logger.warning(f"Tracked file not found, can't upload: {file_path}")

    def _upload_file_to_s3(self, file_path, s3_key):
        logger.info(f"Uploading {file_path} -> s3://{self.BUCKET_NAME}/{s3_key}...")
        self.s3.upload_file(file_path, self.BUCKET_NAME, s3_key)
        logger.info(f"Upload complete: {s3_key}")
        
        # Notify VM to sync this file if we have a VM IP
        if self.vm_ip:
            try:
                response = requests.post(
                    f"http://{self.vm_ip}:5000/sync_notepad_files", 
                    json={"file": s3_key}
                )
                logger.info(f"VM notification response: {response.status_code}")
            except Exception as e:
                logger.error(f"Failed to notify VM of file change: {e}")

    def start_notepad_auto_sync(self, vm_ip):
        if self.sync_running:
            logger.info("Auto-sync already running.")
            return

        self.vm_ip = vm_ip  # Store VM IP for later use

        class NotepadFileEventHandler(FileSystemEventHandler):
            def __init__(self, manager):
                self.manager = manager
                self.last_modified = {}  # Track last modification times to debounce

            def on_modified(self, event):
                if event.is_directory:
                    return
                    
                # Check if this is a tracked file or within tracked directories
                is_tracked = False
                file_path = event.src_path
                
                # Direct match with tracked files
                if file_path in self.manager.tracked_files:
                    is_tracked = True
                
                # Check if file basename matches a tracked file
                for tracked in self.manager.tracked_files:
                    if os.path.basename(file_path) == os.path.basename(tracked):
                        is_tracked = True
                        file_path = tracked  # Use the tracked path for sync
                        
                if is_tracked:
                    # Debounce rapidly occurring events (files sometimes trigger multiple events)
                    current_time = time.time()
                    if file_path in self.last_modified and current_time - self.last_modified[file_path] < 2:
                        return
                        
                    self.last_modified[file_path] = current_time
                    logger.info(f"Detected file save: {file_path}")
                    self.manager.sync_specific_file(file_path)

        def run_watcher():
            event_handler = NotepadFileEventHandler(self)
            observer = Observer()
            
            # Set up watchers for both Notepad++ directories and tracked file directories
            watched_dirs = set([self.notepad_dir])
            
            # Add parent directories of tracked files
            for file_path in self.tracked_files:
                parent_dir = os.path.dirname(file_path)
                if os.path.exists(parent_dir):
                    watched_dirs.add(parent_dir)
            
            # Schedule watchers for all directories
            for directory in watched_dirs:
                logger.info(f"Watching for changes in: {directory}")
                observer.schedule(event_handler, directory, recursive=True)
            
            observer.start()
            self.sync_running = True
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
            observer.join()

        thread = threading.Thread(target=run_watcher, daemon=True)
        thread.start()
        logger.info("File watcher thread started")

    def sync_specific_file(self, file_path):
        """Sync a specific file to S3 and notify VM"""
        if not os.path.exists(file_path):
            logger.warning(f"Can't sync non-existent file: {file_path}")
            return
            
        s3_key = os.path.basename(file_path)
        try:
            self._upload_file_to_s3(file_path, s3_key)
            logger.info(f"Synced file: {s3_key}")
        except Exception as e:
            logger.error(f"Error syncing file {file_path}: {e}")

    def sync_notepad_files(self, vm_ip=None, upload=True, specific_file=None):
        """Sync all tracked files or a specific file"""
        logger.info(f"sync_notepad_files called with vm_ip={vm_ip}, upload={upload}, specific_file={specific_file}")
        
        if vm_ip:
            self.vm_ip = vm_ip
            
        if specific_file:
            files_to_sync = [specific_file]
        elif not self.tracked_files:
            logger.warning("No tracked Notepad++ files. Nothing to sync.")
            return
        else:
            files_to_sync = self.tracked_files

        for file_path in files_to_sync:
            if not os.path.exists(file_path):
                logger.warning(f"Tracked file not found: {file_path}")
                continue
                
            s3_key = os.path.basename(file_path)
            try:
                if upload:
                    try:
                        # Check if file exists in S3 and is older
                        s3_head = self.s3.head_object(Bucket=self.BUCKET_NAME, Key=s3_key)
                        s3_mtime = s3_head['LastModified'].timestamp()
                        local_mtime = os.path.getmtime(file_path)
                        
                        if local_mtime > s3_mtime:
                            logger.info(f"Local file {s3_key} is newer than S3 version, uploading...")
                            self._upload_file_to_s3(file_path, s3_key)
                        else:
                            logger.info(f"S3 version of {s3_key} is newer or same as local, skipping upload")
                    except botocore.exceptions.ClientError:
                        # File doesn't exist in S3, upload it
                        logger.info(f"File {s3_key} not found in S3, uploading...")
                        self._upload_file_to_s3(file_path, s3_key)
            except Exception as e:
                logger.error(f"Sync error for {file_path}: {e}")

        logger.info(f"Sync completed at {time.strftime('%Y-%m-%d %H:%M:%S')}")

    def add_tracked_file(self, file_path):
        """Add a new file to tracked files list"""
        if os.path.exists(file_path):
            self.tracked_files.add(file_path)
            self._update_tracked_file_list(self.tracked_files)
            logger.info(f"Added {file_path} to tracked files")
            return True
        else:
            logger.error(f"Cannot track non-existent file: {file_path}")
            return False

    def remove_tracked_file(self, file_path):
        """Remove a file from tracked files list"""
        if file_path in self.tracked_files:
            self.tracked_files.remove(file_path)
            self._update_tracked_file_list(self.tracked_files)
            logger.info(f"Removed {file_path} from tracked files")
            return True
        else:
            logger.warning(f"File not in tracked files: {file_path}")
            return False

    def download_from_s3(self, s3_key, local_path):
        """Download a specific file from S3"""
        try:
            logger.info(f"Downloading {s3_key} to {local_path}")
            self.s3.download_file(self.BUCKET_NAME, s3_key, local_path)
            logger.info(f"Downloaded {s3_key}")
            return True
        except Exception as e:
            logger.error(f"Download error for {s3_key}: {e}")
            return False

    def get_all_s3_files(self):
        """List all files in the S3 bucket"""
        try:
            response = self.s3.list_objects_v2(Bucket=self.BUCKET_NAME)
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    files.append(obj['Key'])
            logger.info(f"Found {len(files)} files in S3 bucket {self.BUCKET_NAME}")
            return files
        except Exception as e:
            logger.error(f"Error listing S3 files: {e}")
            return []

    def sync_from_s3(self, vm_ip=None):
        """Download and sync all files from S3"""
        if vm_ip:
            self.vm_ip = vm_ip
            
        s3_files = self.get_all_s3_files()
        if not s3_files:
            logger.warning("No files found in S3 bucket.")
            return False
            
        download_count = 0
        for s3_key in s3_files:
            # Find matching tracked file or create new path
            matching_file = None
            for tracked in self.tracked_files:
                if os.path.basename(tracked) == s3_key:
                    matching_file = tracked
                    break
                    
            if not matching_file:
                # Create new path in user's documents folder
                docs_dir = os.path.expanduser("~/Documents/NotepadSync")
                os.makedirs(docs_dir, exist_ok=True)
                matching_file = os.path.join(docs_dir, s3_key)
                
            try:
                # Compare modification times if local file exists
                if os.path.exists(matching_file):
                    local_mtime = os.path.getmtime(matching_file)
                    s3_head = self.s3.head_object(Bucket=self.BUCKET_NAME, Key=s3_key)
                    s3_mtime = s3_head['LastModified'].timestamp()
                    
                    if s3_mtime > local_mtime:
                        logger.info(f"S3 version of {s3_key} is newer than local, downloading...")
                        self.download_from_s3(s3_key, matching_file)
                        download_count += 1
                    else:
                        logger.info(f"Local version of {s3_key} is newer or same as S3, skipping download")
                else:
                    # Local file doesn't exist, download it
                    logger.info(f"Local file {matching_file} not found, downloading from S3...")
                    self.download_from_s3(s3_key, matching_file)
                    download_count += 1
                    
                # Add to tracked files if not already tracked
                if matching_file not in self.tracked_files:
                    self.tracked_files.add(matching_file)
            except Exception as e:
                logger.error(f"Error syncing {s3_key} from S3: {e}")
                
        # Update tracked files list
        self._update_tracked_file_list(self.tracked_files)
        logger.info(f"Downloaded {download_count} files from S3")
        return True

    def restart_notepad_with_files(self, files=None):
        """Restart Notepad++ with specified files or all tracked files"""
        try:
            # Kill any running Notepad++ instances
            subprocess.call(["taskkill", "/IM", "notepad++.exe"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
            
            # Find Notepad++ executable
            notepad_exe = r"C:\\Program Files\\Notepad++\\notepad++.exe"
            if not os.path.exists(notepad_exe):
                notepad_exe = r"C:\\Program Files (x86)\\Notepad++\\notepad++.exe"
            if not os.path.exists(notepad_exe):
                raise FileNotFoundError("Notepad++ executable not found.")
                
            files_to_open = []
            if files:
                files_to_open = [f for f in files if os.path.exists(f)]
            else:
                files_to_open = [f for f in self.tracked_files if os.path.exists(f)]
                
            if not files_to_open:
                logger.warning("No files to open in Notepad++")
                subprocess.Popen([notepad_exe])
                return False
                
            logger.info(f"Restarting Notepad++ with {len(files_to_open)} files...")
            command = [notepad_exe] + files_to_open
            subprocess.Popen(command)
            logger.info("Notepad++ restarted with tracked files")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart Notepad++: {e}")
            return False
            
    def get_vm_status(self, vm_ip):
        """Check if VM is responding"""
        if not vm_ip:
            if self.vm_ip:
                vm_ip = self.vm_ip
            else:
                logger.error("No VM IP provided for status check")
                return False
                
        try:
            response = requests.get(f"http://{vm_ip}:5000/status", timeout=5)
            if response.status_code == 200:
                logger.info(f"VM at {vm_ip} is responding")
                return True
            else:
                logger.error(f"VM at {vm_ip} returned status code {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to VM at {vm_ip}: {e}")
            return False
            
    def cleanup_temp_files(self):
        """Clean up temporary unsaved files"""
        if os.path.exists(self.unsaved_temp_dir):
            try:
                for file in os.listdir(self.unsaved_temp_dir):
                    file_path = os.path.join(self.unsaved_temp_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                logger.info(f"Cleaned up temporary files in {self.unsaved_temp_dir}")
                return True
            except Exception as e:
                logger.error(f"Error cleaning up temp files: {e}")
                return False
        return True

    def start_periodic_sync(self, interval_seconds=30):
        if hasattr(self, "_periodic_sync_thread") and self._periodic_sync_thread.is_alive():
            logger.info("Periodic sync is already running.")
            return

        def periodic_task():
            logger.info(f"Starting periodic sync every {interval_seconds} seconds...")
            while True:
                try:
                    self.sync_from_s3()
                except Exception as e:
                    logger.error(f"Periodic sync failed: {e}")
                time.sleep(interval_seconds)

        self._periodic_sync_thread = threading.Thread(target=periodic_task, daemon=True)
        self._periodic_sync_thread.start()