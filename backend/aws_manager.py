import boto3
import time
import os
import requests
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except ImportError:
    print("⚠️ urllib3.util.retry not found. Installing urllib3 explicitly might be required.")
    Retry = None

class AWSManager:
    def __init__(self):
        """Initialize AWS EC2 client and resource manager."""
        self.ec2 = boto3.client("ec2")
        self.ec2_resource = boto3.resource("ec2")
        self.s3 = boto3.client("s3")
        self.active_vm_id = None
        self.bucket_name = "cloud-ram-scripts"

    def create_key_pair(self):
        """Dynamically creates an EC2 key pair and saves it locally in the same directory as the running script."""
        key_name = "cloud-ram-key"
        key_path = os.path.join(os.path.dirname(__file__), f"{key_name}.pem")

        try:
            existing_keys = self.ec2.describe_key_pairs()["KeyPairs"]
            if any(key["KeyName"] == key_name for key in existing_keys):
                print(f"✅ Key Pair {key_name} already exists in AWS.")
                if not os.path.exists(key_path):
                    print(f"❌ Key Pair {key_name} exists in AWS but the local key file is missing. Please manually create or download the key.")
                    return None, None
                else:
                    print(f"✅ Key Pair Already Exists Locally: {key_path}")
                    return key_name, key_path
            else:
                response = self.ec2.create_key_pair(KeyName=key_name)
                private_key = response["KeyMaterial"]
                print(f"🔑 New Key Pair Created in AWS: {key_name}")

                print(f"📥 Downloading key pair to {key_path}...")
                with open(key_path, "w") as key_file:
                    key_file.write(private_key)
                os.chmod(key_path, 0o400)
                print(f"✅ Key Pair Saved Locally: {key_path}")

                return key_name, key_path
        except Exception as e:
            print(f"❌ Error creating or downloading key pair: {str(e)}")
            return None, None

    def create_security_group(self):
        """Dynamically creates a security group for the VM."""
        sg_name = "cloud-ram-sg"
        try:
            existing_sgs = self.ec2.describe_security_groups()["SecurityGroups"]
            for sg in existing_sgs:
                if sg["GroupName"] == sg_name:
                    print(f"✅ Security Group {sg_name} already exists.")
                    return sg["GroupId"]
            response = self.ec2.create_security_group(GroupName=sg_name, Description="Security group for Cloud RAM SaaS VMs")
            sg_id = response["GroupId"]
            self.ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {"IpProtocol": "tcp", "FromPort": 3389, "ToPort": 3389, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                    {"IpProtocol": "tcp", "FromPort": 5000, "ToPort": 5000, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                    {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                    {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                    {"IpProtocol": "tcp", "FromPort": 8080, "ToPort": 8080, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                    {"IpProtocol": "tcp", "FromPort": 5900, "ToPort": 5900, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                    {"IpProtocol": "tcp", "FromPort": 6080, "ToPort": 6080, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}
                ]
            )
            print(f"🛡 New Security Group Created: {sg_name} ({sg_id})")
            return sg_id
        except Exception as e:
            print(f"❌ Error creating security group: {str(e)}")
            return None

    def get_latest_windows_ami(self):
        """Finds the latest Windows Server AMI dynamically."""
        try:
            response = self.ec2.describe_images(
                Filters=[
                    {"Name": "platform", "Values": ["windows"]},
                    {"Name": "name", "Values": ["Windows_Server-2022-English-Full-Base*"]}
                ],
                Owners=["amazon"]
            )
            if not response["Images"]:
                print("❌ No Windows Server AMI found.")
                return None
            ami_id = sorted(response["Images"], key=lambda x: x["CreationDate"], reverse=True)[0]["ImageId"]
            print(f"📦 Latest Windows AMI Found: {ami_id}")
            return ami_id
        except Exception as e:
            print(f"❌ Error fetching Windows AMI: {str(e)}")
            return None

    def upload_script_to_s3(self):
        script_path = os.path.join("vm_scripts", "vm_server.py")
        script_key = "vm_server.py"

        if not os.path.exists(script_path):
            print(f"❌ Flask Server script not found at {script_path}")
            return None

        try:
            self.s3.upload_file(script_path, self.bucket_name, script_key)
            print(f"📤 Uploaded {script_path} to s3://{self.bucket_name}/{script_key}")
        except Exception as e:
            print(f"❌ Error uploading script to S3: {str(e)}")
            return None

    def create_vm(self, ram_size):
        self.upload_script_to_s3()
        """Dynamically launches an EC2 instance with readiness check and key upload."""
        existing_vm_id, existing_ip = self.get_existing_vm()
        if existing_vm_id:
            print(f"✅ Returning existing VM: {existing_vm_id} (IP: {existing_ip})")
            return existing_vm_id, existing_ip

        key_name, key_path = self.create_key_pair()
        if not key_name or not key_path:
            print("❌ Failed to create or retrieve key pair.")
            return None, None

        instance_type = {1: "t3.micro", 2: "t3.small", 4: "t3.medium"}.get(ram_size, "t3.medium")
        startup_script_path = os.path.join("vm_scripts", "vm_startup_script.ps1")
        if not os.path.exists(startup_script_path):
            print(f"❌ Startup script not found at {startup_script_path}")
            return None, None

        with open(startup_script_path, "r") as script_file:
            startup_script = script_file.read()

        with open(key_path, "r") as key_file:
            key_content = key_file.read()

        user_data = f"{startup_script}\n\n" + \
                    f"$keyContent = @'\n{key_content}\n'@\n" + \
                    "New-Item -ItemType Directory -Path 'C:\\CloudRAM' -Force\n" + \
                    "Set-Content -Path 'C:\\CloudRAM\\cloud-ram-key.pem' -Value $keyContent -Force\n" + \
                    "icacls 'C:\\CloudRAM\\cloud-ram-key.pem' /inheritance:r /grant:r 'Administrators:F'"

        try:
            print(f"🚀 Creating EC2 instance with {ram_size}GB RAM ({instance_type})")
            response = self.ec2.run_instances(
                ImageId=self.get_latest_windows_ami(),
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                KeyName=key_name,
                SecurityGroupIds=[self.create_security_group()],
                UserData=user_data,
                IamInstanceProfile={
                    'Name': 'CloudRAMEC2Role'
                }
            )
            instance = response["Instances"][0]
            self.active_vm_id = instance["InstanceId"]
            print("⏳ Waiting for instance to start...")
            waiter = self.ec2.get_waiter("instance_running")
            waiter.wait(InstanceIds=[self.active_vm_id])

            vm_info = self.ec2.describe_instances(InstanceIds=[self.active_vm_id])
            ip_address = vm_info["Reservations"][0]["Instances"][0].get("PublicIpAddress", "Pending")
            print(f"✅ Instance running at {ip_address}. Waiting for services...")

            session = requests.Session()
            if Retry:
                retry_strategy = Retry(total=10, backoff_factor=5, status_forcelist=[500, 502, 503, 504])
                adapter = HTTPAdapter(max_retries=retry_strategy)
                session.mount("http://", adapter)
            print(f"⏳ Waiting for Flask server at {ip_address}:5000...")
            for attempt in range(180):
                try:
                    response = session.get(f"http://{ip_address}:5000/", timeout=20)
                    if response.status_code == 200:
                        print(f"✅ Flask server ready at {ip_address}:5000 after {attempt + 1} attempts")
                        break
                except requests.RequestException as e:
                    print(f"⏳ Attempt {attempt + 1}/180: Waiting for Flask... ({str(e)})")
                    time.sleep(10)
            else:
                print(f"❌ Flask server not ready after 30 minutes at {ip_address}:5000")
                self.terminate_vm(self.active_vm_id)
                return None, None

            print(f"✅ VM Created: ID={self.active_vm_id}, IP={ip_address}")
            return self.active_vm_id, ip_address
        except Exception as e:
            print(f"❌ Error creating VM: {str(e)}")
            return None, None

    def terminate_vm(self, vm_id):
        """Terminates the EC2 instance."""
        try:
            self.ec2.terminate_instances(InstanceIds=[vm_id])
            print(f"🛑 VM {vm_id} Terminated.")
            self.active_vm_id = None
        except Exception as e:
            print(f"❌ Error terminating VM: {str(e)}")

    def get_vm_status(self, vm_ip):
        """Check VM's running processes and resource usage."""
        try:
            url = f"http://{vm_ip}:5000/ram_usage"
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return {"error": f"Failed to fetch status, status code: {response.status_code}"}
            return response.json()
        except requests.RequestException as e:
            print(f"❌ Error fetching VM status: {str(e)}")
            return {"error": str(e)}

    def get_existing_vm(self):
        """Check if an active VM already exists."""
        try:
            instances = self.ec2.describe_instances(
                Filters=[{"Name": "instance-state-name", "Values": ["pending", "running"]}]
            )
            for reservation in instances["Reservations"]:
                for instance in reservation["Instances"]:
                    if "InstanceId" in instance:
                        vm_id = instance["InstanceId"]
                        ip_address = instance.get("PublicIpAddress", "Pending")
                        print(f"✅ Found Active VM: {vm_id} (IP: {ip_address})")
                        self.active_vm_id = vm_id
                        return vm_id, ip_address
        except Exception as e:
            print(f"❌ Error checking for existing VMs: {str(e)}")
        return None, None

    def install_application_on_vm(self, vm_ip, app_name):
        """Dynamically install an application on the VM if not present."""
        try:
            response = requests.get(f"http://{vm_ip}:5000/list_tasks", timeout=10)
            if response.status_code == 200:
                tasks = response.json().get("tasks", [])
                if any(task["name"].lower() == app_name.lower() for task in tasks):
                    print(f"✅ {app_name} already running on VM {vm_ip}")
                    return True
            session = requests.Session()
            if Retry:
                retry_strategy = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
                adapter = HTTPAdapter(max_retries=retry_strategy)
                session.mount("http://", adapter)
            install_payload = {"app_name": app_name}
            print(f"⏳ Attempting to install {app_name} on VM {vm_ip}")
            response = session.post(f"http://{vm_ip}:5000/install_app", json=install_payload, timeout=120)
            if response.status_code == 200:
                print(f"✅ Successfully installed {app_name} on VM {vm_ip}")
                return True
            else:
                print(f"❌ Failed to install {app_name}: {response.text}")
                return False
        except requests.Timeout as e:
            print(f"❌ Timeout installing {app_name} on VM {vm_ip}: {str(e)}")
            return False
        except requests.RequestException as e:
            print(f"❌ Error installing {app_name} on VM {vm_ip}: {str(e)}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error installing {app_name} on VM {vm_ip}: {str(e)}")
            return False

    def migrate_task_with_ui(self, vm_ip, task_name):
        """Migrate a task and return the VNC URL for UI streaming."""
        try:
            if not self.install_application_on_vm(vm_ip, task_name):
                print(f"❌ Failed to install {task_name} on VM {vm_ip}")
                return None
            
            print(f"⏳ Migrating {task_name} with UI streaming to VM {vm_ip}")
            response = requests.post(
                f"http://{vm_ip}:5000/migrate_task_with_ui",
                json={"task_name": task_name, "task_data": {"state": "auto_migrated"}},
                timeout=60
            )
        
            if response.status_code == 200:
                response_data = response.json()
                stream_url = response_data.get("web_vnc_url", f"http://{vm_ip}:8080/vnc.html")
                vnc_direct = response_data.get("vnc_url", f"vnc://{vm_ip}:5900")
            
                print(f"✅ Task {task_name} migrated with UI streaming")
                print(f"Web VNC: {stream_url}")
                print(f"Direct VNC: {vnc_direct}")
            
                return stream_url
            else:
                print(f"❌ Failed to migrate {task_name}: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Error migrating {task_name} with UI: {str(e)}")
            return None

if __name__ == "__main__":
    manager = AWSManager()
    vm_id, ip = manager.create_vm(2)
    if vm_id:
        print(f"VM ID: {vm_id}, IP: {ip}")