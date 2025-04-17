from flask import Flask, render_template, request, jsonify
import requests

import os
import sys

app = Flask(__name__)
API_URL = "http://localhost:8000"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/allocate", methods=["POST"])
def allocate():
    data = request.json
    ram_size = data.get("ram_size")
    print(f"📌 Forwarding allocate request for {ram_size} GB to FastAPI")
    response = requests.post(f"{API_URL}/allocate_ram/", json={"ram_size": ram_size})
    print(f"FastAPI response: {response.status_code} - {response.text}")
    if response.status_code == 200:
        return jsonify(response.json())
    else:
        return jsonify({"error": "Failed to allocate RAM", "details": response.text}), response.status_code

@app.route("/status")
def status():
    return render_template("status.html")

@app.route("/ram_usage")
def ram_usage():
    vm_ip = request.args.get("vm_ip")
    if not vm_ip:
        return jsonify({"error": "VM IP is required"}), 400
    try:
        print(f"Fetching RAM usage from http://{vm_ip}:5000/ram_usage")
        response = requests.get(f"http://{vm_ip}:5000/ram_usage", timeout=10)
        print(f"Response status: {response.status_code}, content: {response.text}")
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"error": f"Failed to fetch RAM usage from VM, status: {response.status_code}"}), response.status_code
    except requests.RequestException as e:
        print(f"Error connecting to VM: {str(e)}")
        return jsonify({"error": f"Failed to connect to VM: {str(e)}"}), 500

@app.route("/sync_notepad/", methods=["POST"])
def sync_notepad():
    data = request.json
    vm_ip = data.get("vm_ip")
    if not vm_ip:
        return jsonify({"error": "VM IP is required"}), 400
    try:
        response = requests.post(f"{API_URL}/sync_notepad/", json={"task_name": "notepad++.exe", "vm_ip": vm_ip})
        return jsonify(response.json()), response.status_code
    except requests.RequestException as e:
        print(f"❌ Error syncing Notepad++: {e}")
        return jsonify({"error": "Sync failed", "details": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)