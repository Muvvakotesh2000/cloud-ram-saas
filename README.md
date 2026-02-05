# CloudRAMSaaS

A cloud-based Software as a Service (SaaS) platform that allows users to dynamically allocate RAM resources on AWS EC2 instances and migrate local applications to cloud VMs. Extend your local machine's available RAM by offloading applications to cloud-hosted Windows VMs with VNC GUI access.

## Features

- **Dynamic Cloud RAM Allocation** - Choose from 1GB, 2GB, or 4GB RAM configurations
- **Application Migration** - Move local applications (Notepad++, Chrome, VS Code) to cloud VMs
- **Supabase Authentication** - Secure login with email/password and Google OAuth
- **Real-time RAM Monitoring** - Track RAM usage on cloud VMs
- **VNC Remote Desktop Access** - Interact with cloud VMs through embedded VNC viewer
- **File Synchronization** - Automatic bidirectional sync of Notepad++ documents via AWS S3
- **Auto-Sync** - Continuous file monitoring with 30-second periodic sync

## Tech Stack

### Frontend
- HTML5 (Single Page Application)
- Vanilla JavaScript
- CSS3 with modern gradients
- Flask (Python) for static file serving
- Supabase JS SDK v2

### Backend
- FastAPI (async Python web framework)
- Uvicorn (ASGI server)
- Python 3.x

### Infrastructure & Cloud
- AWS EC2 (Windows Server 2022 VMs)
- AWS S3 (file storage)
- AWS IAM roles
- Boto3 (AWS SDK for Python)

### Authentication
- Supabase (managed auth backend)
- JWT tokens (HTTP Bearer authentication)

### Process & File Management
- psutil (process monitoring)
- watchdog (file system monitoring)
- win32gui, win32con (Windows GUI interaction)

## Project Structure

```
CloudRAMSaaS/
├── frontend/                    # Frontend SPA (Flask + HTML/JS)
│   ├── app.py                   # Flask app for static file serving
│   ├── templates/               # Jinja templates
│   │   ├── index.html           # Login/Register/Home SPA
│   │   └── status.html          # Cloud RAM dashboard
│   └── static/                  # Static assets
│       ├── script.js            # SPA logic, auth, RAM allocation
│       ├── status_auth.js       # Supabase auth helper
│       └── style.css            # Application styling
│
├── backend/                     # FastAPI backend (core API)
│   ├── main.py                  # FastAPI app with endpoints
│   ├── aws_manager.py           # AWS EC2/S3 management
│   ├── process_manager.py       # Local process/file management
│   ├── requirements.txt         # Python dependencies
│   ├── notepad_file_paths.txt   # Tracked Notepad++ files
│   ├── cloud-ram-key.pem        # EC2 SSH key pair
│   ├── unsaved_files/           # Temporary unsaved file backups
│   └── vm_scripts/              # Scripts deployed to EC2 VMs
│       ├── vm_server.py         # Flask server running on VM
│       ├── vm_startup_script.ps1# PowerShell bootstrap script
│       └── requirements.txt     # VM Python dependencies
│
└── README.md
```

## Installation

### Prerequisites

- Python 3.8+
- AWS Account with EC2 and S3 access
- Supabase account (for authentication)
- Windows OS (for local process management features)

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
```

### Frontend Setup

```bash
cd frontend
pip install flask
```

### AWS Configuration

1. **Create IAM Role**: Create an IAM role named `CloudRAMEC2Role` with EC2 and S3 permissions

2. **Create S3 Buckets**:
   - `cloud-ram-scripts` - For storing VM bootstrap scripts
   - `notepadfiles` - For file synchronization

3. **Configure AWS Credentials**: Ensure AWS credentials are configured locally:
   ```bash
   aws configure
   ```

### Supabase Configuration

1. Create a Supabase project
2. Enable Email/Password and Google OAuth authentication
3. Update the Supabase URL and anon key in:
   - `/frontend/static/script.js`
   - `/frontend/static/status_auth.js`
   - `/backend/main.py`

## Running the Application

### Start Backend Server

```bash
cd backend
python main.py
```
The backend API runs on `http://0.0.0.0:8000`

### Start Frontend Server

```bash
cd frontend
python app.py
```
The frontend runs on `http://localhost:5000`

### Access the Application

1. Open `http://localhost:5000` in your browser
2. Register or login with your credentials
3. Select desired RAM allocation (1GB, 2GB, or 4GB)
4. Wait for VM provisioning to complete
5. Access the dashboard to monitor RAM and migrate tasks

## API Endpoints

### Authentication Required Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/allocate` | Allocate RAM and create EC2 instance |
| POST | `/release_ram` | Terminate VM and release resources |
| GET | `/ram_usage` | Get current VM RAM usage statistics |
| POST | `/move_task` | Move a single task to cloud VM |
| POST | `/migrate_tasks` | Migrate multiple tasks with file sync |
| POST | `/sync_notepad` | Sync Notepad++ files to cloud |

### Public Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check endpoint |
| GET | `/running_tasks` | List locally running tasks |

### Request/Response Examples

**Allocate RAM**
```json
// POST /allocate
// Request
{ "ram_size": 2 }

// Response
{ "vm_id": "i-0abc123def456", "ip": "52.23.145.67" }
```

**Get RAM Usage**
```json
// GET /ram_usage?vm_ip=52.23.145.67
// Response
{
  "total_ram": 2147483648,
  "used_ram": 536870912,
  "available_ram": 1610612736,
  "percent_used": 25.0
}
```

**Migrate Tasks**
```json
// POST /migrate_tasks
// Request
{
  "task_names": ["notepad++.exe"],
  "vm_ip": "52.23.145.67"
}

// Response
{
  "results": [
    { "task": "notepad++.exe", "success": true }
  ]
}
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Browser       │────▶│  Frontend       │────▶│  Backend API    │
│   (User)        │     │  (Flask:5000)   │     │  (FastAPI:8000) │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┼────────────────────────────────┐
                        │                                ▼                                │
                        │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
                        │  │   AWS EC2       │    │    AWS S3       │    │  Supabase   │ │
                        │  │  (Windows VM)   │    │ (File Storage)  │    │   (Auth)    │ │
                        │  │                 │    │                 │    │             │ │
                        │  │ ┌─────────────┐ │    │ - vm scripts    │    │ - JWT       │ │
                        │  │ │ Flask Server│ │◀───│ - notepad files │    │ - OAuth     │ │
                        │  │ │ (Port 5000) │ │    │                 │    │             │ │
                        │  │ └─────────────┘ │    └─────────────────┘    └─────────────┘ │
                        │  │ ┌─────────────┐ │                                           │
                        │  │ │  UltraVNC   │ │◀── VNC Access (Port 5900)                 │
                        │  │ └─────────────┘ │                                           │
                        │  └─────────────────┘                                           │
                        │                         AWS Cloud                              │
                        └────────────────────────────────────────────────────────────────┘
```

## Instance Type Mapping

| RAM Selection | EC2 Instance Type | Actual RAM |
|---------------|-------------------|------------|
| 1 GB          | t3.micro          | 1 GB       |
| 2 GB          | t3.small          | 2 GB       |
| 4 GB          | t3.medium         | 4 GB       |

## File Synchronization

The application provides automatic file synchronization for Notepad++ documents:

1. **Initial Sync**: When migrating Notepad++ to cloud, all open files are uploaded to S3
2. **File Watcher**: Local file changes are detected using the `watchdog` library
3. **Auto-Upload**: Modified files are automatically uploaded to S3
4. **Periodic Sync**: Every 30 seconds, files are synced bidirectionally
5. **Conflict Resolution**: Files are compared by modification time; newer version wins

### S3 Bucket Structure

```
notepadfiles/
├── document1.txt
├── document2.py
└── notes.md

cloud-ram-scripts/
└── vm_server.py
```

## Security Considerations

### Current Implementation
- JWT-based authentication via Supabase
- Bearer token required for protected API endpoints
- CORS configured for localhost development

### Recommendations for Production
- Move Supabase keys to environment variables
- Implement rate limiting on API endpoints
- Use persistent storage (RDS/DynamoDB) instead of in-memory state
- Implement request signing for VM-to-backend communication
- Use HTTPS for all communications
- Rotate EC2 key pairs regularly
- Enable VPC security groups with minimal required ports

## Ports Used

| Service | Port | Purpose |
|---------|------|---------|
| Frontend (Flask) | 5000 | Web application UI |
| Backend (FastAPI) | 8000 | REST API |
| VM Flask Server | 5000 | VM management API |
| VNC | 5900 | Remote desktop access |
| RDP | 3389 | Windows Remote Desktop |
| HTTP | 80 | General HTTP |
| HTTPS | 443 | Secure HTTP |

## Logging

- **Backend**: Standard Python logging to console
- **Process Manager**: Logs to `/backend/process_manager.log`
- **VM Server**: Logs to `C:\CloudRAM\vm_server.log`

## Known Limitations

1. **Windows Only**: Process migration features work only on Windows
2. **In-Memory State**: VM mappings are lost if backend restarts
3. **Hardcoded Paths**: Some Windows paths are hardcoded for specific user profiles
4. **Single VM per User**: Currently supports one VM per authenticated user
5. **Limited Applications**: Only Notepad++, Chrome, and VS Code migration supported

## Troubleshooting

### VM Creation Timeout
If VM creation times out (default: 30 minutes), check:
- AWS credentials are valid
- IAM role has necessary permissions
- EC2 service limits in your region

### File Sync Issues
If files aren't syncing:
- Verify S3 bucket permissions
- Check `process_manager.log` for errors
- Ensure Notepad++ is properly configured

### Authentication Failures
If login fails:
- Verify Supabase project is active
- Check anon key is correctly configured
- Ensure email verification is complete (if enabled)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- AWS for cloud infrastructure
- Supabase for authentication services
- UltraVNC for remote desktop capabilities
- The open-source Python community
