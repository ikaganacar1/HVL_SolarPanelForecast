import requests

def main(link_head,link_created):
    

    full_url = f"{link_head.strip('/')}/{link_created.strip('/')}"
    response = requests.get(full_url,)
    response.raise_for_status()
    
    return {"alerts":str(response.json())}
        
 