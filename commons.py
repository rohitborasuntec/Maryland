from dotenv import load_dotenv
import os

load_dotenv()

def get_ev():
    """Return a proxy URL from the PROXY_URL environment variable, or an
    empty string if none is configured."""
    return os.environ.get("PROXY_URL", "").strip()


def get_proxy_settings(isreq=False):

    proxy_url = get_ev()
    print("Proxy : ",proxy_url)
    proxy_settings = None
    if isreq and proxy_url:
        return proxy_url
    elif isreq:
        return {}        
    elif proxy_url:

        server = proxy_url.split("@")[-1].rstrip("/")
        user_name = proxy_url.split("@")[0].split("//")[-1].split(":")[0]
        password = proxy_url.split("@")[0].split("//")[-1].split(":")[-1]
        proxy_settings = {
                    "server": server,
                    "username": user_name,
                    "password": password
                }
        
    return proxy_settings

