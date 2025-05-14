import os
import yaml
import requests
import json
from rich import print

config_dir = os.path.expanduser("~/.config/config_validator")
print("config", config_dir)
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
    if not directory or not os.path.exists(directory):
        return data
    for file_name in os.listdir(directory):
        if file_name.endswith('.yaml') or file_name.endswith('.yml'):
            with open(os.path.join(directory, file_name), 'r') as f:
                yaml_data = yaml.safe_load(f) or {}
                host_name = file_name.split('.')[0]
                data[host_name] = yaml_data.get(key, [])
    return data


def read_interface_data(directory):
    interfaces_data = {}
    if not directory or not os.path.exists(directory):
        return interfaces_data
    for file_name in os.listdir(directory):
        if file_name.endswith('.yaml') or file_name.endswith('.yml'):
            full_path = os.path.join(directory, file_name)
            with open(full_path, 'r') as file:
                data = yaml.safe_load(file) or {}
                host_name = file_name.split('.')[0]
                interfaces_data[host_name] = {
                    'port_channel_interfaces': data.get('port_channel_interfaces', []),
                    'ethernet_interfaces': data.get('ethernet_interfaces', [])
                }
    return interfaces_data


def is_flow_blocked(flow, acl_entry, protocol_name):
    if acl_entry.get('action') != 'deny':
        return False
    acl_protocol = acl_entry.get('protocol', '').upper()
    if acl_protocol and acl_protocol != protocol_name:
        return False
    return any([
        flow.get('src_port') in acl_entry.get('source_ports', []),
        flow.get('dst_port') in acl_entry.get('destination_ports', []),
        flow.get('src_ip') in acl_entry.get('source', []),
        flow.get('dst_ip') in acl_entry.get('destination', [])
    ])


def check_flows_against_acls(host, acls):
    flows = fetch_connection_stats(host)
    if not flows:
        return []
    blocked_flows = []
    for flow in flows.get('connection_stats', []):
        protocol_name = PROTOCOLS.get(flow.get('protocol'), f"Unknown({flow.get('protocol')})")
        for acl in acls:
            for entry in acl.get('entries', []):
                if is_flow_blocked(flow, entry, protocol_name):
                    for app in flow.get('applications', []):
                        blocked_flows.append((acl, entry, flow, protocol_name, app.get('app_service_name', 'unknown')))
    return blocked_flows


def check_shutdown_impact(host, interfaces_data):
    shutdown_ports = []
    shutdown_affected_flows = []
    port_channels = interfaces_data.get(host, {}).get('port_channel_interfaces', [])
    ethernet_interfaces = interfaces_data.get(host, {}).get('ethernet_interfaces', [])

    for pc in port_channels:
        if pc.get('shutdown', False):
            shutdown_ports.append(pc.get('name', 'unknown'))

    for eth in ethernet_interfaces:
        if eth.get('shutdown', False):
            shutdown_ports.append(eth.get('name', 'unknown'))

    flows = fetch_connection_stats(host)
    if flows:
        for flow in flows.get('connection_stats', []):
            if flow.get('ingress_interface') in shutdown_ports or flow.get('egress_interface') in shutdown_ports:
                for app in flow.get('applications', []):
                    shutdown_affected_flows.append((flow, app.get('app_service_name', 'unknown')))
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
                for app in flow.get('applications', []):
                    impact = {
                        'reason': 'shutdown' if shutdown else 'acl',
                        'vlan': vlan_name,
                        'flow': flow,
                        'app_name': app.get('app_service_name', 'unknown')
                    }
                    if not shutdown:
                        impact['access_in'] = access_in
                        impact['access_out'] = access_out
                    affected.append(impact)

    return affected


def main():
    metadata = load_metadata()
    acls_config_dir = metadata.get("host_vars_path")
    intended_config_dir = metadata.get("intended_config_path")
    acl_policies = read_yaml_configs(acls_config_dir, 'ip_access_lists')
    interfaces_data = read_interface_data(intended_config_dir)
    vlan_configs = read_yaml_configs(intended_config_dir, 'vlan_interfaces')

    conflict = {
        'Acl': False,
        'Interface': False,
        'Vlan': False
    }

    print("\n[bold underline]Checking ACL Blocked Flows[/bold underline]")
    for host, acls in acl_policies.items():
        blocked_flows = check_flows_against_acls(host, acls)
        print(f"\nHost: [bold]{host}[/bold]")
        if not blocked_flows:
            print("[bold green]No protocol conflicts found for this host[/bold green]")
            continue
        for acl, entry, flow, protocol, app_service_name in blocked_flows:
            print(f'[bold red]WARNING: ACL "{acl.get("name", "unknown")}" blocks protocol {protocol}[/bold red]')
            print(f"\tFlow: {flow.get('src_ip')}:{flow.get('src_port')} -> {flow.get('dst_ip')}:{flow.get('dst_port')}")
            print(f"\tBlocked Ports: SRC {entry.get('source_ports', [])} -> DST {entry.get('destination_ports', [])}")
            print(f"\tInterface: {flow.get('ingress_interface')} -> {flow.get('egress_interface')}")
            app_name_split = app_service_name[37:].split("-")
            app_name = app_name_split[0] + ":" + "-".join(app_name_split[6:])
            if app_name_split[0] == '':
                app_name = 'unknown' + " : (UID -" + app_service_name + ")"
            print(f"\tAffected application: [bold red]{app_name}[/bold red]")
            conflict['Acl'] = True

    print("\n[bold underline]Checking Shutdown Impact[/bold underline]")
    for host in interfaces_data.keys():
        shutdown_affected_flows, shutdown_ports = check_shutdown_impact(host, interfaces_data)
        print(f"\nHost: [bold]{host}[/bold]")
        if shutdown_affected_flows:
            print(f"[bold red]WARNING: Shutting down these interfaces disrupts flows: {', '.join(shutdown_ports)}[/bold red]")
            for flow, app_service_name in shutdown_affected_flows:
                print(f"\tFlow: {flow.get('src_ip')}:{flow.get('src_port')} -> {flow.get('dst_ip')}:{flow.get('dst_port')}")
                print(f"\tShutdown Interface: {flow.get('ingress_interface')} -> {flow.get('egress_interface')}")
                app_name_split = app_service_name[37:].split("-")
                app_name = app_name_split[0] + ":" + "-".join(app_name_split[6:])
                if app_name_split[0] == '':
                    app_name = 'unknown' + " : (UID -" + app_service_name + ")"
                print(f"\tAffected application: [bold red]{app_name}[/bold red]")
            conflict['Interface'] = True
        else:
            print(f"[bold green]No disruptions found from shutting down interfaces on {host}.[/bold green]")

    print("\n[bold underline]Analyzing VLAN Config Impact[/bold underline]")
    for host, vlan_list in vlan_configs.items():
        print(f"\nHost: [bold]{host}[/bold]")
        impacts = analyze_vlan_impact(host, vlan_list)

        if not impacts:
            print("[green]No VLAN disruptions detected.[/green]")
            continue

        for impact in impacts:
            flow = impact['flow']
            reason = impact['reason']
            print(f'[bold red]WARNING: VLAN "{impact["vlan"]}" impact due to {reason}[/bold red]')
            print(f"\tFlow: {flow.get('src_ip')}:{flow.get('src_port')} -> {flow.get('dst_ip')}:{flow.get('dst_port')}")
            print(f"\tInterface: {flow.get('ingress_interface')} -> {flow.get('egress_interface')}")
            if reason == 'acl':
                print(f"\tInbound ACL: {impact.get('access_in')} | Outbound ACL: {impact.get('access_out')}")
            print(f"\tAffected VLAN: {impact['vlan']}")
            app_service_name = impact['app_name']
            app_name_split = app_service_name[37:].split("-")
            app_name = app_name_split[0] + ":" + "-".join(app_name_split[6:])
            if app_name_split[0] == '':
                app_name = 'unknown' + " : (UID -" + app_service_name + ")"
            print(f"\tAffected application: [bold red]{app_name}[/bold red]")
            conflict['Vlan'] = True

    for key, value in conflict.items():
        if value:
            print(f"\n[bold red]Conflicts found, please review the {key} before proceeding.[/bold red]")

    if not any(conflict.values()):
        print("\n[bold green]No conflicts found. Configuration appears safe to proceed.[/bold green]")


if __name__ == "__main__":
    main()
