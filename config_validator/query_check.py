import os
import yaml
import requests
import json
from rich import print

config_dir = os.path.expanduser("~/.config/config_validator")
print("config",config_dir)
METADATA_FILE = os.path.join(config_dir, "metadata.json")
PROTOCOLS = {1: "ICMP", 6: "TCP", 17: "UDP"}

def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return {}

def fetch_connection_stats(host):
    url = f"http://127.0.0.1:8000/{host}/connection_stats"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[red]Failed to retrieve flows for {host}, Status: {response.status_code}[/red]")
    except Exception as e:
        print(f"[red]Error fetching connection stats for host {host}: {e}[/red]")
    return None

def read_yaml_configs(directory, key):
    data = {}
    for file_name in os.listdir(directory):
        if file_name.endswith('.yaml') or file_name.endswith('.yml'):
            with open(os.path.join(directory, file_name), 'r') as f:
                yaml_data = yaml.safe_load(f)
                host_name = file_name.split('.')[0]
                data[host_name] = yaml_data.get(key, [])
    return data

def read_interface_data(directory):
    interfaces_data = {}
    for file_name in os.listdir(directory):
        if file_name.endswith('.yaml') or file_name.endswith('.yml'):
            full_path = os.path.join(directory, file_name)
            with open(full_path, 'r') as file:
                data = yaml.safe_load(file)
                host_name = file_name.split('.')[0]
                interfaces_data[host_name] = {
                    'port_channel_interfaces': data.get('port_channel_interfaces', []),
                    'ethernet_interfaces': data.get('ethernet_interfaces', [])
                }
    return interfaces_data

def is_flow_blocked(flow, acl_entry, protocol_name):
    if acl_entry['action'] != 'deny':
        return False
    acl_protocol = acl_entry.get('protocol', '').upper()
    if acl_protocol and acl_protocol != protocol_name:
        return False
    return any([
        flow['src_port'] in acl_entry.get('source_ports', []),
        flow['dst_port'] in acl_entry.get('destination_ports', []),
        flow['src_ip'] in acl_entry.get('source', []),
        flow['dst_ip'] in acl_entry.get('destination', [])
    ])

def check_flows_against_acls(host, acls):
    flows = fetch_connection_stats(host)
    if not flows:
        return []
    blocked_flows = []
    for flow in flows.get('connection_stats', []):
        protocol_name = PROTOCOLS.get(flow.get('protocol'), f"Unknown({flow.get('protocol')})")
        for acl in acls:
            for entry in acl['entries']:
                if is_flow_blocked(flow, entry, protocol_name):
                    blocked_flows.append((acl, entry, flow, protocol_name))
    return blocked_flows

def check_shutdown_impact(host, interfaces_data):
    shutdown_ports = []
    shutdown_affected_flows = []
    port_channels = interfaces_data.get(host, {}).get('port_channel_interfaces', [])
    ethernet_interfaces = interfaces_data.get(host, {}).get('ethernet_interfaces', [])

    for pc in port_channels:
        if pc.get('shutdown', False):
            shutdown_ports.append(pc['name'])
    for eth in ethernet_interfaces:
        if eth.get('shutdown', False):
            shutdown_ports.append(eth['name'])

    flows = fetch_connection_stats(host)
    if flows:
        for flow in flows.get('connection_stats', []):
            if flow['sub_device_id'] in shutdown_ports or flow['device_id'] in shutdown_ports:
                for app in flow.get('applications', {}):
                    shutdown_affected_flows.append((flow, app))
    return shutdown_affected_flows, shutdown_ports

def analyze_vlan_impact(host, vlan_list):
    flows = fetch_connection_stats(host)
    if not flows:
        return []

    affected = []
    for vlan in vlan_list:
        vlan_name = vlan.get('name')
        shutdown = vlan.get('shutdown', False)
        ip_subnet = vlan.get('ip_address', '')
        access_in = vlan.get('ip_access_group_in')
        access_out = vlan.get('ip_access_group_out')

        for flow in flows.get('connection_stats', []):
            src_ip = flow.get('src_ip')
            dst_ip = flow.get('dst_ip')

            if ip_subnet and ip_subnet.split('/')[0] in [src_ip, dst_ip]:
                if shutdown:
                    affected.append({
                        'reason': 'shutdown',
                        'vlan': vlan_name,
                        'flow': flow
                    })
                elif access_in or access_out:
                    affected.append({
                        'reason': 'acl',
                        'vlan': vlan_name,
                        'flow': flow,
                        'access_in': access_in,
                        'access_out': access_out
                    })

    return affected

def main():
    metadata = load_metadata()
    acls_config_dir = metadata.get("host_vars_path")
    intended_config_dir = metadata.get("intended_config_path")
    acl_policies = read_yaml_configs(acls_config_dir, 'ip_access_lists')
    interfaces_data = read_interface_data(intended_config_dir )
    vlan_configs = read_yaml_configs(intended_config_dir , 'vlan_interfaces')

    conflict = False

    print("\n[bold underline]Checking ACL Blocked Flows[/bold underline]")
    for host, acls in acl_policies.items():
        blocked_flows = check_flows_against_acls(host, acls)
        print(f"\nHost: [bold]{host}[/bold]")
        if not blocked_flows:
            print("[bold green]No protocol conflicts found for this host[/bold green]")
            continue
        for acl, entry, flow, protocol in blocked_flows:
            print(f'[bold red]WARNING: ACL "{acl["name"]}" blocks protocol {protocol}[/bold red]')
            print(f"\tFlow: {flow['src_ip']}:{flow['src_port']} -> {flow['dst_ip']}:{flow['dst_port']}")
            print(f"\tBlocked Ports: SRC {entry.get('source_ports', [])} -> DST {entry.get('destination_ports', [])}")
            print(f"\tInterface: {flow['sub_device_id']} -> {flow['device_id']}")
            conflict = True

    print("\n[bold underline]Checking Shutdown Impact[/bold underline]")
    for host in interfaces_data.keys():
        shutdown_affected_flows, shutdown_ports = check_shutdown_impact(host, interfaces_data)
        print("-------------------------------------------------------------------------------")
        print(f"::shutdown_ports for {host}:: {shutdown_ports}")
        print("-------------------------------------------------------------------------------")
        if shutdown_affected_flows:
            print(f"\n[bold red]WARNING: Shutting down these interfaces disrupts flows on {host}: {', '.join(shutdown_ports)}[/bold red]")
            for flow, app in shutdown_affected_flows:
                print(f"\tFlow: {flow['src_ip']}:{flow['src_port']} -> {flow['dst_ip']}:{flow['dst_port']}")
                print(f"\tAffected application: [bold red]{flow.get('application_name', app.get('app_name', 'unknown'))}[/bold red]")
            conflict = True
        else:
            print(f"\n[bold green]No disruptions found from shutting down interfaces on {host}.[/bold green]")

    print("\n[bold underline]Analyzing VLAN Config Impact[/bold underline]")
    for host, vlan_list in vlan_configs.items():
        print(f"\n[bold blue]Analyzing VLANs for host: {host}[/bold blue]")
        impacts = analyze_vlan_impact(host, vlan_list)

        if not impacts:
            print("[green]No VLAN disruptions detected.[/green]")
            continue

        for impact in impacts:
            flow = impact['flow']
            if impact['reason'] == 'shutdown':
                print(f"🔴 [red]VLAN {impact['vlan']} is shut down[/red] — affects flow {flow['src_ip']}:{flow['src_port']} → {flow['dst_ip']}:{flow['dst_port']}")
            elif impact['reason'] == 'acl':
                print(f"🟠 [yellow]ACL on VLAN {impact['vlan']} may block flow[/yellow] {flow['src_ip']}:{flow['src_port']} → {flow['dst_ip']}:{flow['dst_port']}")
                print(f"     Inbound ACL: {impact.get('access_in')} | Outbound ACL: {impact.get('access_out')}")

            conflict = True

    if conflict:
        print("\n[bold red]Conflicts found, please review the ACLs, VLANs, and shutdown impact before proceeding.[/bold red]")
        exit(1)
    else:
        print("\n[bold green]No conflicts found. Configuration appears safe to proceed.[/bold green]")

if __name__ == "__main__":
    main()
