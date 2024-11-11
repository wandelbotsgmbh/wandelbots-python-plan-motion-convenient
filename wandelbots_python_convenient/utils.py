import requests
from decouple import config
from requests.auth import HTTPBasicAuth
from wandelbots import Instance
from urllib.parse import urlparse

CELL_ID = config("CELL_ID", default="cell", cast=str)

def get_api_client() -> Instance:
    """Creates a new API client for the wandelbots API.
    """
    # if there is a token required for cloud access (e.g. when running this service locally)
    access_token = config("NOVA_ACCESS_TOKEN", default=None)
    basic_auth = get_basic_auth()

    base_url = get_base_url(access_token, basic_auth)

    return create_instance(base_url=base_url, access_token=access_token, basic_auth=basic_auth)

def create_instance(base_url, access_token, basic_auth) -> Instance:
    parsed_url = urlparse(base_url)
    if "https" in parsed_url.scheme:
        if access_token is not None:
            return Instance(url=base_url, access_token=access_token)
        elif basic_auth is not None:
            return Instance(url=base_url, user=basic_auth.username, password=basic_auth.password)
        else:
            raise Exception("Please provide access token or basic auth via env vars.")
    else:
        return Instance(url=base_url)
    
def get_base_url(access_token, basic_auth) -> str:
    # in-cluster it is the api-gateway service
    # when working with a remote instance one needs to provide the host via env variable
    api_host = config("WANDELAPI_BASE_URL", default="api-gateway:8080")
    api_host = api_host.strip()
    api_host = api_host.replace("http://", "")
    api_host = api_host.replace("https://", "")
    api_host = api_host.rstrip("/")
    protocol = get_protocol(api_host, access_token, basic_auth)
    if protocol is None:
        msg = f"Could not determine protocol for host {api_host}. Make sure the host is reachable."
        raise Exception(msg)
    return f"{protocol}{api_host}"


# get the protocol of the host (http or https)
def get_protocol(host, access_token, basic_auth) -> str:
    api = f"/api/v1/cells/{CELL_ID}/controllers"
    headers = None
    
    if access_token is not None:
        headers = {"Authorization": f"Bearer {access_token}"}
        basic_auth = None

    try:
        response = requests.get(f"https://{host}{api}", headers=headers, auth=basic_auth, timeout=5)
        if response.status_code == 200:
            return "https://"
    except requests.RequestException:
        pass

    try:
        response = requests.get(f"http://{host}{api}", timeout=5)
        if response.status_code == 200:
            return "http://"
    except requests.RequestException:
        pass

    return None

def get_basic_auth() -> dict[str, str]:
    basic_user = config("NOVA_USERNAME", default=None)
    basic_pwd = config("NOVA_PASSWORD", default=None)
    if basic_user is not None and basic_pwd is not None:
        return HTTPBasicAuth(basic_user, basic_pwd)
    return None
