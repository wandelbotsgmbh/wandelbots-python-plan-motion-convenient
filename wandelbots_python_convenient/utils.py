import requests
from decouple import config
from requests.auth import HTTPBasicAuth
from wandelbots import Instance
from urllib.parse import urlparse

CELL_ID = config("CELL_ID", default="cell", cast=str)

def get_api_client() -> Instance:
    """Creates a new API client for the wandelbots API.
    """
    # if there is basic auth required (e.g. when running this service locally)
    basic_user = config("NOVA_USERNAME", default=None, cast=str)
    basic_pwd = config("NOVA_PASSWORD", default=None, cast=str)

    base_url = get_base_url(basic_user, basic_pwd)

    return create_instance(base_url=base_url, user=basic_user, password=basic_pwd)

def create_instance(base_url, user, password) -> Instance:
    parsed_url = urlparse(base_url)
    if parsed_url.scheme == "https://":
        return Instance(url=base_url, user=user, password=password)
    else:
        return Instance(url=base_url)
    
def get_base_url(basic_user, basic_pwd) -> str:
    # in-cluster it is the api-gateway service
    # when working with a remote instance one needs to provide the host via env variable
    api_host = config("WANDELAPI_BASE_URL", default="api-gateway:8080", cast=str)
    api_host = api_host.strip()
    api_host = api_host.replace("http://", "")
    api_host = api_host.replace("https://", "")
    api_host = api_host.rstrip("/")
    protocol = get_protocol(api_host, basic_user, basic_pwd)
    if protocol is None:
        msg = f"Could not determine protocol for host {api_host}. Make sure the host is reachable."
        raise Exception(msg)
    return f"{protocol}{api_host}"


# get the protocol of the host (http or https)
def get_protocol(host, basic_user, basic_pwd) -> str:
    api = f"/api/v1/cells/{CELL_ID}/controllers"
    auth = None
    if basic_user is not None and basic_pwd is not None:
        auth = HTTPBasicAuth(basic_user, basic_pwd)

    try:
        response = requests.get(f"https://{host}{api}", auth=auth, timeout=5)
        if response.status_code == 200:
            return "https://"
    except requests.RequestException:
        pass

    try:
        response = requests.get(f"http://{host}{api}", auth=auth, timeout=5)
        if response.status_code == 200:
            return "http://"
    except requests.RequestException:
        pass

    return None