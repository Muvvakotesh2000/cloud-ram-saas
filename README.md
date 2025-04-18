# 🌥️ Cloud RAM SaaS

Welcome to **Cloud RAM SaaS**, an innovative web application that lets you dynamically allocate cloud-based RAM resources on AWS EC2 instances! 🚀 Whether you're running memory-intensive tasks or need a remote environment for your apps, this project makes it easy to spin up virtual machines, migrate tasks, and even sync files like a pro. With a sleek frontend, a robust backend, and seamless AWS integration, Cloud RAM SaaS is your go-to solution for cloud computing needs.

---

## 🎯 Features That Shine

- 🔒 **Secure Authentication**: Log in effortlessly with AWS Cognito using email/password or Google SSO.
- 💾 **Dynamic RAM Allocation**: Choose from 1GB, 2GB, or 4GB RAM to create EC2 instances on demand.
- 🚀 **Task Migration**: Move local tasks (e.g., Notepad++, Chrome, VS Code) to the cloud with a single click.
- 📊 **Interactive Dashboard**: Monitor RAM usage, view running tasks, and access your VM via a browser-based VNC client.
- 📁 **File Sync Magic**: Keep your Notepad++ sessions in sync between local and cloud environments.
- 🧹 **Auto-Cleanup**: Automatically terminates VMs when you close the browser to save resources.

> **Fun Fact**: Did you know that Cloud RAM SaaS can spin up a VM in just 10-15 minutes? That's faster than brewing a perfect cup of coffee! ☕

---

## 🏗️ Project Architecture

Cloud RAM SaaS is built with a modern tech stack to ensure scalability and performance:

- **Frontend**: HTML, JavaScript, and CSS, hosted on **AWS Amplify** for lightning-fast delivery.
- **Backend**: **FastAPI** running on an AWS EC2 Windows instance, handling VM creation and task management.
- **AWS Services**:
  - **EC2**: Powers virtual machines for RAM allocation.
  - **DynamoDB**: Stores user-VM mappings securely.
  - **Cognito**: Manages user authentication with ease.
  - **Amplify**: Hosts the frontend with automatic scaling.

---

## 📁 Project Structure

Here’s how the repository is organized:

```
CLOUDRAMSAAS/
├── backend/
│   ├── vm_scripts/                  # Scripts for VM management
│   ├── aws_manager.py              # AWS EC2 and VM management logic
│   ├── main.py                     # FastAPI backend server
│   ├── notepad_file_paths.txt      # Stores Notepad++ file paths for syncing
│   ├── process_manager.py          # Handles task migration and file syncing
│   └── requirements.txt            # Backend dependencies
├── frontend/
│   ├── static/
│   │   ├── script.js               # Frontend JavaScript logic
│   │   ├── style.css               # Styling for the frontend
│   ├── app.py                      # Flask app for local frontend testing
│   ├── index.html                  # Main page (login, registration, home, allocate)
│   └── status.html                 # VM dashboard page
└── README.md                       # You're reading it!
```

---

## 🚀 Getting Started

Ready to dive in? Follow these steps to set up and run Cloud RAM SaaS locally or in the cloud!

### Prerequisites

- **AWS Account**: Access to EC2, DynamoDB, Cognito, and Amplify.
- **Python 3.8+**: For running the backend.
- **Git**: To clone the repository.
- **Node.js** (optional): For local frontend development.
- **AWS CLI** (optional): For configuring AWS credentials.

### 1️⃣ Backend Setup (EC2 Windows Instance)

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/Muvvakotesh2000/cloud-ram-saas.git
   cd cloud-ram-saas
   ```

2. **Set Up an EC2 Instance**:
   - Launch a Windows EC2 instance (e.g., `t2.medium` with 2 vCPUs, 4GB RAM).
   - Configure the security group to allow:
     - **Port 8000 (HTTP)**: For FastAPI backend.
     - **Port 8080 (VNC)**: For VM GUI access.
   - Connect via RDP.

3. **Install Dependencies**:
   - Install Python 3.8+ on the EC2 instance.
   - Install backend dependencies:
     ```bash
     pip install -r backend/requirements.txt
     ```

4. **Configure AWS Credentials**:
   - Set up AWS credentials for EC2, DynamoDB, and other services.
   - Attach an IAM role to the EC2 instance with permissions for:
     - `ec2:RunInstances`, `ec2:TerminateInstances`, `ec2:DescribeInstances`
     - `dynamodb:PutItem`, `dynamodb:GetItem`, `dynamodb:DeleteItem`

5. **Run the Backend**:
   - Navigate to the backend directory:
     ```bash
     cd backend
     ```
   - Start the FastAPI server:
     ```bash
     python -m uvicorn main:app --host 0.0.0.0 --port 8000
     ```
   - Test the backend:
     ```
     http://<ec2-public-ip>:8000/health
     ```
     Expected response: `{"status": "healthy"}`

6. **Keep It Running**:
   - Use a process manager like `pm2` or Windows Task Scheduler to ensure the backend persists after RDP sessions close.

> **Pro Tip**: Set up HTTPS on your EC2 instance using AWS ALB or Let’s Encrypt to secure API calls! 🔐

### 2️⃣ Frontend Setup (AWS Amplify)

1. **Configure AWS Amplify**:
   - In the [AWS Amplify Console](https://aws.amazon.com/amplify/), create a new app.
   - Connect to your GitHub repository (`https://github.com/Muvvakotesh2000/cloud-ram-saas`) or upload the `frontend` folder manually.

2. **Set Environment Variables**:
   - In the Amplify Console, go to **App Settings > Environment Variables** and add:
     ```
     API_URL=http://<ec2-public-ip>:8000
     ```
     Example: `API_URL=http://18.220.82.87:8000`

3. **Update Frontend Code**:
   - Ensure `frontend/static/script.js` and `frontend/status.html` reference the backend URL via `window.env.API_URL` or directly:
     ```javascript
     const API_URL = window.env?.API_URL || "http://<ec2-public-ip>:8000";
     ```
   - Add environment variable support in `frontend/index.html`:
     ```html
     <script>
         window.env = { API_URL: "http://<ec2-public-ip>:8000" };
     </script>
     ```

4. **Deploy the Frontend**:
   - Push changes to your GitHub repository:
     ```bash
     git add .
     git commit -m "Update frontend with backend URL"
     git push origin main
     ```
   - Amplify will auto-deploy. Get the URL (e.g., `https://main.d2xxxxx.amplifyapp.com`).

5. **Test the Frontend**:
   - Open the Amplify URL in a browser.
   - Log in, allocate RAM, and check the status page.

### 3️⃣ AWS Cognito Setup

1. **Create a User Pool**:
   - In [AWS Cognito](https://aws.amazon.com/cognito/), create a user pool.
   - Enable email/password and Google SSO.

2. **Create an App Client**:
   - Add an app client with OAuth scopes: `email`, `openid`, `profile`.
   - Set redirect URLs:
     - Sign-in: `https://<amplify-url>/callback`
     - Sign-out: `https://<amplify-url>/login`

3. **Update Frontend Config**:
   - In `frontend/static/script.js`, configure Amplify Auth with your Cognito details:
     ```javascript
     window.Amplify.Auth.configure({
         Auth: {
             region: 'us-east-2',
             userPoolId: '<your-user-pool-id>',
             userPoolWebClientId: '<your-app-client-id>',
             oauth: {
                 domain: '<your-cognito-domain>.auth.us-east-2.amazoncognito.com',
                 scope: ['email', 'openid', 'profile'],
                 redirectSignIn: window.location.origin + '/callback',
                 redirectSignOut: window.location.origin + '/login',
                 responseType: 'code'
             }
         }
     });
     ```
   - Replace `<your-user-pool-id>`, `<your-app-client-id>`, and `<your-cognito-domain>` with your Cognito settings.

> **Note**: Keep sensitive credentials like user pool IDs secure. Use environment variables or AWS Secrets Manager in production! 🔒

---

## 🎮 How to Use It

1. **Access the App**:
   - Visit the Amplify URL (e.g., `https://main.d2xxxxx.amplifyapp.com`).
   - Log in or register using Cognito.

2. **Allocate RAM**:
   - Go to the “Allocate RAM” page.
   - Select 1GB, 2GB, or 4GB and click “Allocate.”
   - Wait 10-15 minutes for the VM to spin up.

3. **Monitor Your VM**:
   - Navigate to `/status` to view:
     - RAM usage (total, used, available).
     - Running tasks.
     - VM GUI via VNC (port 8080).

4. **Migrate Tasks**:
   - Select tasks like Notepad++ or Chrome from the dashboard.
   - Click “Migrate” to move them to the cloud VM.

5. **Sync Notepad++ Files**:
   - Use the “Sync Notepad++” feature to keep your open files in sync.

6. **Clean Up**:
   - Close the browser tab to automatically terminate the VM and free resources.

---

## 🛠️ Troubleshooting

Got issues? Here’s how to fix common problems:

- **Backend Not Responding**:
  - Verify the backend is running: `curl http://<ec2-public-ip>:8000/health`.
  - Check EC2 security group: Allow TCP 8000 and 8080.
  - Ensure Windows Firewall isn’t blocking ports.

- **CORS Errors**:
  - Update `backend/main.py` to allow the Amplify domain:
    ```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://<amplify-url>"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    ```

- **Mixed Content Errors**:
  - If using HTTP backend with HTTPS frontend, configure HTTPS on EC2 (e.g., via AWS ALB).
  - Update frontend to use HTTPS backend URL.

- **Cognito Login Fails**:
  - Double-check user pool and app client settings in Cognito.
  - Ensure redirect URLs match the Amplify domain.

For more help, open an issue on [GitHub](https://github.com/Muvvakotesh2000/cloud-ram-saas/issues)!

---

## 🌟 Contributing

We’d love your contributions to make Cloud RAM SaaS even better! Here’s how to get started:

1. Fork the repository.
2. Create a feature branch:
   ```bash
   git checkout -b feature/your-cool-feature
   ```
3. Commit your changes:
   ```bash
   git commit -m "Add your cool feature"
   ```
4. Push to GitHub:
   ```bash
   git push origin feature/your-cool-feature
   ```
5. Open a pull request on [GitHub](https://github.com/Muvvakotesh2000/cloud-ram-saas/pulls).

---

## 📚 References & Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/) – Learn more about building APIs.
- [AWS Amplify](https://aws.amazon.com/amplify/) – Host your frontend with ease.
- [AWS Cognito](https://aws.amazon.com/cognito/) – Secure user authentication.
- [AWS EC2](https://aws.amazon.com/ec2/) – Run your VMs in the cloud.
- [Boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) – AWS SDK for Python.
- [VNC Viewer](https://www.realvnc.com/en/connect/) – For remote VM access.

---

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 📬 Get in Touch

Have questions or ideas? Reach out!

- **GitHub Issues**: [https://github.com/Muvvakotesh2000/cloud-ram-saas/issues](https://github.com/Muvvakotesh2000/cloud-ram-saas/issues)
- **Email**: [muvvakotesh2000@example.com](mailto:muvvakoteshyadav@gmail.com) <!-- Replace with your email -->

Let’s build the future of cloud computing together! 🌍
