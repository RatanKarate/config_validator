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
    if "access_token" not in metadata:
        metadata["access_token"] = input("Enter the access token: ")

    if "host_vars_path" not in metadata:
        metadata["host_vars_path"] = input("Enter the path to your host_vars file (e.g., /host_vars): ")

    if "intended_config_path" not in metadata:
        metadata["intended_config_path"] = input("Enter the path to your intended srtuctured_config_path file (e.g., intended/srtuctured_config): ")
    

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

def print_usage():
   print("""
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           🛠️  USAGE: validate-config                               │
│                                                                                   │
│  Command format:                                                                  │
│      validate-config [access_token] [host_vars_path] [intended_structured_config] │
│                                                                                   │
│  Examples:                                                                        │
│      validate-config <access_token> ./host_vars ./intended/structured_config      │
│                                                                                   │
│      OR just run without arguments and you'll be prompted.                        │
│                                                                                   │
│  What it does:                                                                    │
│    ✅ Loads saved metadata from ~/.config/config_validator/metadata.json          │
│    🔐 If no access token in metadata, checks for token.txt in current directory   │
│    ⚠️  If token.txt exists but is empty, it will be ignored                        │
│    🧾 If no token is found in either place, you’ll be prompted for it             │
│                                                                                   │
│  📄 You can create a `token.txt` file in the current working directory and        │
│  place your access token there, or you can provide it directly in the command     │
│  line.                                                                            |
|                                                                                   │
│    🚀 Starts a FastAPI server for flow validation                                 │
│    🔎 Runs validation logic against your current config                           │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│           TO OVERWRITE SAVED VALUES IN metadata.json                         │
│                                                                              │
│  Run the command again with new arguments like below:                        │
│                                                                              │
│      validate-config <new_access_token> <new_host_vars_path>                 │
│                        <new_intended_structured_config>                      │
│                                                                              │
│  This will update the saved metadata values.                                 │
└──────────────────────────────────────────────────────────────────────────────┘
""")




def main():
    metadata = load_metadata()

    # Check for token.txt in current directory
    token_file_path = os.path.join(os.getcwd(), "token.txt")
    if os.path.exists(token_file_path):
        with open(token_file_path, "r") as f:
            token_from_file = f.read().strip()
            if token_from_file:  # Only use it if not empty
                if "access_token" not in metadata:
                    metadata["access_token"] = token_from_file
            else:
                print("⚠️  token.txt found but it's empty. Skipping.")

    # Show usage if no metadata and no CLI args
    if len(sys.argv) < 3:
        print_usage()

    # Prompt user if required values are missing
    required_keys = ["access_token", "host_vars_path", "intended_config_path"]
    if not all(key in metadata for key in required_keys):
        print("Missing required information. Please provide the following:")
        get_user_input(metadata)

    # If user provides new values via command line, update metadata
    if len(sys.argv) >= 4:
        metadata["access_token"] = sys.argv[1]
        metadata["host_vars_path"] = sys.argv[2]
        metadata["intended_config_path"] = sys.argv[3]
        save_metadata(metadata)

    # Start FastAPI server
    env = os.environ.copy()
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "config_validator.api.main:app", "--port", "8000"
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    # while True:
    #     output = server.stdout.readline()
    #     error = server.stderr.readline()
    #     if output:
    #         print("STDOUT:", output.strip())
    #     if error:
    #         print("STDERR:", error.strip())
    #     if not output and not error and server.poll() is not None:
    #         break
    try:
        if not wait_for_server("http://localhost:8000/docs"):
            print("Server did not start.")
            server.terminate()
            sys.exit(1)

        subprocess.run([sys.executable, "-m", "config_validator.query_check"])
    finally:
        server.terminate()
        server.wait()


if __name__ == "__main__":
    main()
