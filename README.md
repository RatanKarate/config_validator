# 🔍 Config Validator

**Config Validator** is a CLI tool and FastAPI-powered backend that validates user-provided Ansible-generated configurations (e.g., ACLs, interface shutdowns) against real-time network flow data.

It ensures your changes won't accidentally disrupt live traffic or break critical protocols—**before you deploy**.

---

## 🚀 What It Does

- Fetches current flow and connection data via an internal FastAPI service (wrapping a gRPC API).
- Compares this against intended configs provided by the user (`host_vars`, `structured_config`, etc.).
- Flags any **conflicts, drops, or disruptions** in traffic or services (like BGP or ICMP).

---

## 🗂️ Folder Structure

```
config_validator/
├── config_validator/           # Python package for validation logic and server
│   ├── __init__.py
│   ├── runner.py               # CLI entry point (invoked by `validate-config`)
│   ├── query_check.py          # Core logic to validate user configs (ACLs, interfaces, VLANs, etc.)
│   └── api/                    # FastAPI server wrapper around gRPC live flow API
│       ├── __init__.py
│       └── main.py             # FastAPI app that exposes endpoints to access live flow data
├── pkg/                        # gRPC-generated protobuf client code
│   ├── __init__.py
│   └── clover/                 # Namespace for gRPC client implementation
│       ├── __init__.py
│       ├── clover_pb2_grpc.py  # gRPC service client bindings (auto-generated)
│       └── clover_pb2.py       # Protobuf message class definitions (auto-generated)
├── pyproject.toml              # Project metadata, dependencies, and entry points
└── README.md                   
```

---

## ⚙️ Installation

Create and activate Python virtual Enviroment:

```bash
python3 -m venv myvenv
source myvenv/bin/activate
```

## Installation

To install `config_validator` from source, follow the steps below:

```bash
# Clone the config_validator repository from GitHub
git clone https://github.com/RatanKarate/config_validator.git

# Navigate into the cloned repository directory
cd config_validator

# Install the package using pip
# The dot (.) refers to the current directory, which should contain pyproject.toml
pip install .
```

This will install the `validate-config` CLI tool.

---

## 🧪 Usage

### First Run

```bash
validate-config
```

You'll be prompted for:

- `host_vars` file path
- `structured_config` path
- `access token` (used by the FastAPI server to call the gRPC backend)

These values are saved to:

```bash
~/.config/config_validator/metadata.json
```

---

### 🔐 Providing the Access Token

The **Config Validator** requires an access token to authenticate API calls to the gRPC backend. You can provide this token in **one of three ways**, listed below in order of **priority**:

#### ✅ 1. Command-Line Argument (Highest Priority)

```bash
validate-config <access_token> <host_vars_path> <structured_config_path>
```

- Overrides all other sources.
- Saves values to `metadata.json`.

#### ✅ 2. `token.txt` File in Current Directory

- Create a file named `token.txt`:
  ```bash
  echo "your_token_here" > token.txt
  ```
- Single line, no spaces or breaks.
- If file exists but is **empty**, you'll be prompted.
- If valid, token is saved to `metadata.json`.

#### ✅ 3. Saved in Metadata File

If previously provided, the saved token from:

```bash
~/.config/config_validator/metadata.json
```

...will be used automatically.

#### ❌ No Token Provided?

If no valid token is found in any source, you'll be prompted to enter it manually. It will be saved for future use.

### 📌 Token Priority Summary

```
1. Command-line argument            ✅ Highest priority
2. token.txt in current directory  ✅ Used if CLI not given
3. metadata.json (saved token)     ✅ Used if above two are missing
4. Prompt user interactively        ⚠️ Fallback if all else fails
```

---

### Subsequent Runs

These saved values are reused. If you want to override them:

```bash
validate-config <new_access_token> <new_host_vars_path> <new_structured_config_path> 
```

---

## 🧠 Validation Logic

The validator performs checks like:

- 🔒 **ACL conflicts**: Flags drops or allows not intended in the new config.
- 🔌 **Interface shutdown impact**: Simulates interface state changes.
- 🌐 **Protocol behavior**: Detects whether protocols like BGP/OSPF/ICMP would break.
- 🧱 **VLAN shutdown impact**: Simulates shutdown scenarios on VLAN interfaces and checks for affected IP reachability.

---

## 📦 Dependencies

Managed via `pyproject.toml` (installed automatically):

- `fastapi`
- `uvicorn`
- `requests`
- `pyyaml`

---

## 🛠 Dev Notes

The FastAPI server runs internally to handle gRPC data fetches. You don’t need to start it manually — `runner.py` handles it.

You can extend `query_check.py` to add validation for other use cases.

---
