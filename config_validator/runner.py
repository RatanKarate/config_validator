import subprocess
import time
import requests
import sys
import os
import json

config_dir = os.path.expanduser("~/.config/config_validator")
os.makedirs(config_dir, exist_ok=True)
METADATA_FILE = os.path.join(config_dir, "metadata.json")
print(METADATA_FILE)

def load_metadata():
    """Load metadata from metadata.json file."""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_metadata(metadata):
    """Save metadata (file path and access token) to metadata.json."""
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=4)

def get_user_input(metadata):
    """Prompt the user for host_vars file and access token if not present."""
    if "host_vars_path" not in metadata:
        metadata["host_vars_path"] = input("Enter the path to your host_vars file (e.g., /host_vars): ")

    if "intended_config_path" not in metadata:
        metadata["intended_config_path"] = input("Enter the path to your intended srtuctured_config_path file (e.g., intended/srtuctured_config): ")
    
    if "access_token" not in metadata:
        metadata["access_token"] = input("Enter the access token: ")

    save_metadata(metadata)

def wait_for_server(url: str, timeout: int = 15):
    """Wait for FastAPI server to be ready."""
    for _ in range(timeout):
        try:
            if requests.get(url).status_code == 200:
                return True
        except:
            time.sleep(1)
    return False

def main():
    metadata = load_metadata()

    # If metadata is missing, prompt user to input values
    if not metadata:
        print("No metadata found. Please provide the required values.")
        get_user_input(metadata)

    # If user provides new values via command line, update metadata
    if len(sys.argv) >= 3:
        metadata["host_vars_path"] = sys.argv[1]
        metadata["access_token"] = sys.argv[2]
        save_metadata(metadata)

    # Extract host_vars path and access token
    host_vars_path = metadata["host_vars_path"]
    access_token = metadata["access_token"]

    print(f"Using host_vars file: {host_vars_path}")
    print(f"Using access token: {access_token}")

    # Set the access token in the environment
    env = os.environ.copy()
    env["ACCESS_TOKEN"] = access_token

    # Start FastAPI server
    server = subprocess.Popen(
    [
        sys.executable, "-m", "uvicorn", "config_validator.api.main:app", "--port", "8000"
    ],
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
    )

    # Print stdout and stderr in real time
    while True:
        output = server.stdout.readline()
        error = server.stderr.readline()
        if output:
            print("STDOUT:", output.strip())
        if error:
            print("STDERR:", error.strip())
        if not output and not error and server.poll() is not None:
            break
    try:
        if not wait_for_server("http://localhost:8000/docs"):
            print("Server did not start.")
            server.terminate()
            sys.exit(1)

        # Run query_check with file
        subprocess.run([sys.executable, "-m", "config_validator.query_check", host_vars_path])
    finally:
        server.terminate()
        server.wait()

if __name__ == "__main__":
    main()
