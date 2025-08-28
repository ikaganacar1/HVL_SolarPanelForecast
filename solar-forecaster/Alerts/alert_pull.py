import requests
import json

def main(link='http://10.67.67.22:9093/api/v2/alerts?filter=severity="critical"&filter=brand="ABC"'):

    params = {
        'active': 'true',
        'silenced': 'false',
        'inhibited': 'false'
    }
    
    response = requests.get(link, params=params)
    response.raise_for_status()
    
    return {"alerts":response.json()}

print(main())
 