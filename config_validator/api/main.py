import time
import grpc
import os
import json
import logging
from fastapi import FastAPI, Path
from typing import Dict
from google.protobuf.json_format import MessageToDict


# Import generated gRPC files (assuming you've generated them using `protoc`)
from pkg.clover import clover_pb2, clover_pb2_grpc

config_dir = os.path.expanduser("~/.config/config_validator")
METADATA_FILE = os.path.join(config_dir, "metadata.json")
print("Metada", METADATA_FILE)

def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return {}

metadata = load_metadata()
AUTH_TOKEN = metadata.get("access_token", None)
# Constants
timeout = 30
cv_server = "www.cv-staging.corp.arista.io:443"
# AUTH_TOKEN = os.getenv("ACCESS_TOKEN") 
from cvprac.cvp_client import CvpClient

# Initialize the CVP client
clnt = CvpClient()

# Connect to CVaaS using your API token
clnt.connect(
    nodes=['www.cv-staging.corp.arista.io'],  # Replace with your CVaaS endpoint
    username='',              # Username is ignored when using API token
    password='',              # Password is ignored when using API token
    is_cvaas=True,
    api_token=AUTH_TOKEN)

# Retrieve the device inventory
device_map: Dict[str, str] = {}
inventory = clnt.api.get_inventory()
for device in inventory:
    device_map[device.get('hostname').lower()] = device.get('serialNumber')


# Initialize FastAPI app
app = FastAPI()

# Metadata Plugin for Token Authentication
class AuthMetadataPlugin(grpc.AuthMetadataPlugin):
    def __call__(self, context, callback):
        callback((("authorization", f"Bearer {AUTH_TOKEN}"),), None)

# Setup gRPC connection with authentication
def get_grpc_client():
    ssl_creds = grpc.ssl_channel_credentials()
    auth_creds = grpc.metadata_call_credentials(AuthMetadataPlugin())
    creds = grpc.composite_channel_credentials(ssl_creds, auth_creds)

    channel = grpc.secure_channel(cv_server, creds)
    return clover_pb2_grpc.CloverStub(channel)

@app.get("/")
def home():
    return {"message": "Hello, World 👋!"}

@app.get("/{device_id}/flows")
def get_flows(device_id: str = Path(..., title="Device ID")):
    device_id = device_map.get(device_id.lower(), device_id)
    
    client = get_grpc_client()
    request = clover_pb2.BreakdownRequest(
        src_ip=True,
        dst_ip=True,
        src_port=True,
        dst_port=True,
        ingress_interface=True,
        egress_interface=True,
        application_name=True,
        aggregate_devices=True,
        protocol=True,
        # aggregate_devices=True,
        dps_path_group=True,
        deduplicate=True,
        app_category_name=True,
        app_service_name=True,
        src_app=True,
        dst_app=True,
        dpi_app=True,  # Add this line
        
        filter=clover_pb2.FlowFilter(
            device_id=device_id,
            start=int((time.time() - 300) * 1000),
            end=int(time.time() * 1000),
        ),
    )

    
    try:
        response = client.GetBreakdown(request)
        return MessageToDict(response, preserving_proto_field_name=True)
    except grpc.RpcError as e:
        logging.error(f"Error getting breakdown: {e}")
        return {"error": "Failed to fetch breakdown data"}

@app.get("/{device_id}/connection_stats")
def get_connection_stats(device_id: str = Path(..., title="Device ID")):
    device_id = device_map.get(device_id.lower(), device_id)
    client = get_grpc_client()
    
    request = clover_pb2.ConnectionStatsRequest(
        
        filter=clover_pb2.FlowFilter(
            device_id=device_id,
            start=int((time.time() - 86400) * 1000),
            end=int(time.time() * 1000),
        ),)
    try:
        response = client.GetConnectionStats(request)
        return MessageToDict(response, preserving_proto_field_name=True)
    except grpc.RpcError as e:
        logging.error(f"Error fetching connection stats: {e}")
        return {"error": "Failed to fetch connection stats"}

@app.get("/{device_id}/aggregate_time_series")
def get_aggregate_time_series(device_id: str = Path(..., title="Device ID")):
    device_id = device_map.get(device_id.lower(), device_id)
    client = get_grpc_client()
    
    request = clover_pb2.AggregateTimeSeriesRequest(
        aggregation_interval=200,
        src_ip=True,
        dst_ip=True,
        src_port=True,
        dst_port=True,
        ingress_interface=True,
        egress_interface=True,
        application_name=True,
        # aggregate_devices=True,
        protocol=True,
        is_private=True,
        tunnel_id=True,
        drop_reason=True,
        user_identity=True,
        vrf_name=True,
        # aggregate_devices=True,
        dps_path_group=True,
        # deduplicate=True,
        app_category_name=True,
        app_service_name=True,
        src_app=True,
        dst_app=True,
        dpi_app=True,
        avt_name=True,
        ip_class_of_service=True,
        filter=clover_pb2.FlowFilter(
            device_id=device_id,
            start=int((time.time() - 300) * 1000),
            end=int(time.time() * 1000),
        ),
    )
    try:
        response = client.GetAggregateTimeSeries(request)
        return MessageToDict(response, preserving_proto_field_name=True)
    except grpc.RpcError as e:
        logging.error(f"Error fetching aggregate time series: {e}")
        return {"error": "Failed to fetch aggregate time series data"}

@app.get("/{device_id}/sampling_rate")
def get_sampling_rate(device_id: str = Path(..., title="Device ID")):
    device_id = device_map.get(device_id.lower(), device_id)
    client = get_grpc_client()
    
    request = clover_pb2.SamplingRateRequest(
        filter=clover_pb2.FlowFilter(
            device_id=device_id,
            start=int((time.time() - 300) * 1000),
            end=int(time.time() * 1000),
        ),
    )
    try:
        response = client.GetSamplingRate(request)
        return MessageToDict(response, preserving_proto_field_name=True)
    except grpc.RpcError as e:
        logging.error(f"Error fetching sampling rate: {e}")
        return {"error": "Failed to fetch sampling rate"}

@app.get("/{device_id}/count")
def get_count(device_id: str = Path(..., title="Device ID")):
    device_id = device_map.get(device_id.lower(), device_id)
    client = get_grpc_client()
    
    request = clover_pb2.CountRequest(
        # src_ip=True,
        dst_ip=True,
        # user_identity=True,
        filter=clover_pb2.FlowFilter(
            device_id=device_id,
            start=int((time.time() - 300) * 1000),
            end=int(time.time() * 1000),
        ),
    )
    try:
        response = client.GetCount(request)
        return MessageToDict(response, preserving_proto_field_name=True)
    except grpc.RpcError as e:
        logging.error(f"Error fetching count: {e}")
        return {"error": "Failed to fetch count data"}

@app.get("/{device_id}/hostnames")
def get_hostnames(device_id: str = Path(..., title="Device ID")):
    device_id = device_map.get(device_id.lower(), device_id)
    client = get_grpc_client()
    
    request = clover_pb2.HostnamesRequest(device_id=device_id)
    try:
        response = client.GetHostnames(request)
        return MessageToDict(response, preserving_proto_field_name=True)
    except grpc.RpcError as e:
        logging.error(f"Error fetching hostnames: {e}")
        return {"error": "Failed to fetch hostnames"}

@app.get("/{device_id}/src_dst_app_stats")
def get_src_dst_app_stats(device_id: str = Path(..., title="Device ID")):
    device_id = device_map.get(device_id.lower(), device_id)
    client = get_grpc_client()
    
    request = clover_pb2.AppStatsRequest(
        # src_ip=True,
        # dst_ip=True,
        filter=clover_pb2.FlowFilter(
            device_id=device_id,
            start=int((time.time() - 300) * 1000),
            end=int(time.time() * 1000),
        ),)
    try:
        response = client.GetSrcDstAppStats(request)
        return MessageToDict(response, preserving_proto_field_name=True)
    except grpc.RpcError as e:
        logging.error(f"Error fetching src-dst app stats: {e}")
        return {"error": "Failed to fetch source-destination application stats"}

@app.get("/{device_id}/dapper_stats")
def get_dapper_stats(device_id: str = Path(..., title="Device ID")):
    device_id = device_map.get(device_id.lower(), device_id)
    client = get_grpc_client()
    
    request = clover_pb2.DapperStatsRequest(
        src_ip=True,
        dst_ip=True,
        src_port=True,
        dst_port=True,
        # ingress_interface=True,
        # egress_interface=True,
        application_name=True,
        # protocol=True,
        # dps_path_group=True,
        # deduplicate=True,
        app_category_name=True,
        app_service_name=True,
        src_app=True,
        dst_app=True,
        # dpi_app=True,  # Add this line
        filter=clover_pb2.DapperFlowFilter(
            start=int((time.time() - 300) * 1000),
            end=int(time.time() * 1000),
        ),
        )
    try:
        response = client.GetDapperStats(request)
        return MessageToDict(response, preserving_proto_field_name=True)
    except grpc.RpcError as e:
        logging.error(f"Error fetching dapper stats: {e}")
        return {"error": "Failed to fetch dapper stats"}

@app.get("/{device_id}/top_flows")
def stream_top_flows(device_id: str = Path(..., title="Device ID")):
    device_id = device_map.get(device_id.lower(), device_id)
    client = get_grpc_client()
    
    request = clover_pb2.BreakdownRequest(
        src_ip=True,
        dst_ip=True,
        src_port=True,
        dst_port=True,
        ingress_interface=True,
        egress_interface=True,
        application_name=True,
        # app_category_name=True,
        # app_service_name=True,
        # src_app=True,
        dst_app=True,
        # dpi_app=True,  # Add this line
        
        filter=clover_pb2.FlowFilter(
            # device_id=device_id,
            start=int((time.time() - 300) * 1000),
            end=int(time.time() * 1000),
        ),)
    try:
        response_stream = client.StreamTop(request)
        return [MessageToDict(response, preserving_proto_field_name=True) for response in response_stream]
    except grpc.RpcError as e:
        logging.error(f"Error streaming top flows: {e}")
        return {"error": "Failed to stream top flows"}



# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=3000)
