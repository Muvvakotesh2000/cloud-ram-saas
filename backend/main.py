from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from aws_manager import AWSManager
from process_manager import ProcessManager
import uvicorn
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
import requests
from jose import jwt, JWTError
import boto3
from botocore.exceptions import ClientError
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI()
aws_manager = AWSManager()
process_manager = ProcessManager()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'static'))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Cognito Configuration
COGNITO_REGION = 'us-east-1'
COGNITO_USER_POOL_ID = 'us-east-2_4Fo9tOcji'  # Replace with your User Pool ID
COGNITO_JWKS_URL = f'https://cognito-idp.us-east-2.amazonaws.com/us-east-2_4Fo9tOcji/.well-known/jwks.json'

# Fetch JWKS for JWT verification
jwks = requests.get(COGNITO_JWKS_URL).json()

# DynamoDB for storing user-VM mappings
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('CloudRAMUserVMs')

# Security scheme for JWT
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Verify JWT
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
        if rsa_key:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience='18bacrpgl7tnfj5sgi7h1iq2oq',  # Replace with your App Client ID
                issuer=f'https://cognito-idp.us-east-2.amazonaws.com/us-east-2_4Fo9tOcji'
            )
            return payload
        raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")

class RamRequest(BaseModel):
    ram_size: int

class TaskRequest(BaseModel):
    task_name: str
    vm_ip: str

class MigrateTasksRequest(BaseModel):
    task_names: list[str]
    vm_ip: str

class TerminateRequest(BaseModel):
    vm_id: str

class FileSyncRequest(BaseModel):
    file: str

@app.post("/allocate/")
async def allocate_ram(request: RamRequest, user: dict = Depends(verify_token)):
    user_id = user['sub']
    print(f"📌 User {user_id} requested to allocate {request.ram_size} GB RAM")
    
    # Check if user already has a VM
    try:
        response = table.get_item(Key={'user_id': user_id})
        if 'Item' in response:
            vm_id = response['Item']['vm_id']
            vm_ip = response['Item']['vm_ip']
            return {"vm_id": vm_id, "ip": vm_ip}
    except ClientError as e:
        print(f"Error checking user VM: {e}")
    
    # Create new VM
    vm_id, ip_address = aws_manager.create_vm(request.ram_size)
    if vm_id is None or ip_address is None:
        raise HTTPException(status_code=500, detail="Failed to allocate RAM.")

    # Store user-VM mapping in DynamoDB
    try:
        table.put_item(Item={
            'user_id': user_id,
            'vm_id': vm_id,
            'vm_ip': ip_address,
            'created_at': int(time.time())
        })
    except ClientError as e:
        print(f"Error storing user VM mapping: {e}")
        aws_manager.terminate_vm(vm_id)
        raise HTTPException(status_code=500, detail="Failed to store VM mapping.")

    return {"vm_id": vm_id, "ip": ip_address}

@app.get("/running_tasks/")
async def running_tasks():
    tasks = process_manager.get_local_tasks()
    print(f"Returning tasks: {tasks}")
    return tasks

@app.post("/move_task/")
async def move_task(request: TaskRequest, user: dict = Depends(verify_token)):
    success = process_manager.move_task_to_cloud(request.task_name, request.vm_ip)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to move task.")
    return {"message": f"Task {request.task_name} moved to Cloud RAM at {request.vm_ip}"}

@app.post("/migrate_tasks/")
async def migrate_tasks(request: MigrateTasksRequest, user: dict = Depends(verify_token)):
    results = []
    for task_name in request.task_names:
        success = process_manager.move_task_to_cloud(task_name, request.vm_ip, sync_state=(task_name == "notepad++.exe"))
        results.append({"task": task_name, "success": success})
    return {"results": results}

@app.get("/ram_usage/")
async def ram_usage(vm_ip: str, user: dict = Depends(verify_token)):
    if not vm_ip:
        raise HTTPException(status_code=400, detail="VM IP is required")
    ram_info = aws_manager.get_vm_status(vm_ip)
    if "error" in ram_info:
        raise HTTPException(status_code=500, detail=ram_info["error"])
    return {
        "total_ram": ram_info.get("total_ram", 0),
        "used_ram": ram_info.get("used_ram", 0),
        "available_ram": ram_info.get("available_ram", 0),
        "percent_used": ram_info.get("percent_used", 0)
    }

@app.post("/release_ram/")
async def release_ram(request: TerminateRequest, user: dict = Depends(verify_token)):
    user_id = user['sub']
    aws_manager.terminate_vm(request.vm_id)
    # Remove user-VM mapping
    try:
        table.delete_item(Key={'user_id': user_id})
    except ClientError as e:
        print(f"Error deleting user VM mapping: {e}")
    return {"message": f"VM {request.vm_id} terminated, RAM released."}

@app.post("/sync_notepad/")
async def sync_notepad(request: TaskRequest, user: dict = Depends(verify_token)):
    print("Tracking files — pulling from session.xml...")
    process_manager.tracked_files = process_manager.get_current_open_files()
    process_manager.sync_notepad_files(request.vm_ip)
    return {"message": "Synced Notepad++ files"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)