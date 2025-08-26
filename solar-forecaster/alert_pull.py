import requests
import json

# Alertmanager API endpoint
alertmanager_url = "http://10.67.67.22:9093/api/v2/alerts"

# Optional: Add filters
params = {
    'active': 'true',
    'silenced': 'false',
    'inhibited': 'false'
}

try:
    response = requests.get(alertmanager_url, params=params)
    response.raise_for_status()
    
    alerts = response.json()
    
    for alert in alerts:
        print(f"Alert: {alert['labels'].get('alertname', 'Unknown')}")
        print(f"Status: {alert['status']['state']}")
        print(f"Severity: {alert['labels'].get('severity', 'Unknown')}")
        print(f"Started: {alert['startsAt']}")
        print("-" * 50)
        
except requests.exceptions.RequestException as e:
    print(f"Error fetching alerts: {e}")