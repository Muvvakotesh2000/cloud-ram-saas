document.addEventListener("DOMContentLoaded", function () {
    // Ensure Amplify is loaded
    
    if (!window.Amplify || !window.Amplify.Auth) {
        console.error("Amplify library not loaded. Please check the script tag in index.html.");
        return;
    }    


    // Configure AWS Amplify
    window.Amplify.Auth.configure({
        Auth: {
            region: 'us-east-2',
            userPoolId: 'us-east-2_4Fo9tOcji',
            userPoolWebClientId: '18bacrpgl7tnfj5sgi7h1iq2oq',
            oauth: {
                domain: 'CloudRAMSAAS.auth.us-east-2.amazoncognito.com',
                scope: ['email', 'openid', 'profile'],
                redirectSignIn: window.location.origin + '/callback',
                redirectSignOut: window.location.origin + '/login',
                responseType: 'code'
            }
        }
    });

    // Check if user is authenticated
    checkAuthState();

    // Add event listeners
    const allocateBtn = document.getElementById("allocate-btn");
    if (allocateBtn) {
        allocateBtn.addEventListener("click", allocateRAM);
    }
});

function navigate(page) {
    const pages = ['login-page', 'register-page', 'home-page', 'allocate-page'];
    pages.forEach(p => document.getElementById(p).style.display = 'none');
    document.getElementById(`${page}-page`).style.display = 'block';
    document.getElementById('nav').style.display = (page === 'login' || page === 'register') ? 'none' : 'block';
}

async function checkAuthState() {
    try {
        const user = await Amplify.Auth.currentAuthenticatedUser();
        if (user) {
            navigate('home');
        } else {
            navigate('login');
        }
    } catch (err) {
        console.error("Error checking auth state:", err);
        navigate('login');
    }
}

async function login() {
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    try {
        await Amplify.Auth.signIn(email, password);
        navigate('home');
    } catch (err) {
        errorEl.textContent = err.message || 'Login failed. Please try again.';
    }
}

async function loginWithGoogle() {
    try {
        await Amplify.Auth.federatedSignIn({ provider: 'Google' });
    } catch (err) {
        document.getElementById('login-error').textContent = err.message || 'Google login failed. Please try again.';
    }
}

async function register() {
    const firstName = document.getElementById('register-firstname').value;
    const lastName = document.getElementById('register-lastname').value;
    const phone = document.getElementById('register-phone').value;
    const email = document.getElementById('register-email').value;
    const password = document.getElementById('register-password').value;
    const errorEl = document.getElementById('register-error');

    try {
        const { user } = await Amplify.Auth.signUp({
            username: email,
            password,
            attributes: {
                email,
                'custom:firstName': firstName,
                'custom:lastName': lastName,
                'custom:phoneNumber': phone
            }
        });
        alert('Registration successful! Please check your email to verify your account.');
        navigate('login');
    } catch (err) {
        errorEl.textContent = err.message || 'Registration failed. Please try again.';
    }
}

async function allocateRAM(event) {
    event.preventDefault();
    const ramSize = document.getElementById("ram").value;
    const allocateBtn = document.getElementById("allocate-btn");
    const loadingText = document.getElementById("loading-text");
    const countdownElement = document.getElementById("countdown");

    allocateBtn.disabled = true;
    loadingText.style.display = "block";
    loadingText.textContent = "Processing... This may take 10-15 minutes.";
    countdownElement.style.display = "none";

    try {
        const user = await Amplify.Auth.currentAuthenticatedUser();
        const token = user.signInUserSession.idToken.jwtToken;

        const response = await fetch("/allocate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ ram_size: parseInt(ramSize) })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const data = await response.json();
        if (data.error) {
            throw new Error(data.error);
        }

        document.getElementById("status-message").textContent = "RAM allocated successfully!";
        localStorage.setItem("vm_ip", data.ip);
        localStorage.setItem("vm_id", data.vm_id);

        window.location.href = "/status";
    } catch (error) {
        loadingText.textContent = `Error: ${error.message}`;
        loadingText.style.color = "red";
        allocateBtn.disabled = false;
    } finally {
        setTimeout(() => {
            loadingText.style.display = "none";
        }, 2000);
    }
}

window.addEventListener('beforeunload', async () => {
    const vmId = localStorage.getItem("vm_id");
    if (vmId) {
        try {
            const user = await Amplify.Auth.currentAuthenticatedUser();
            const token = user.signInUserSession.idToken.jwtToken;
            await fetch("/release_ram/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({ vm_id: vmId })
            });
            localStorage.removeItem("vm_id");
            localStorage.removeItem("vm_ip");
        } catch (err) {
            console.error("Error terminating VM:", err);
        }
    }
});
