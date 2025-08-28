from datetime import datetime, timezone

def clean_alert_data(alerts_json):
    cleaned_alerts = []
    
    current_time = datetime.now(timezone.utc)

    for alert in alerts_json:
        try:
           
            starts_at_str = alert.get('startsAt', '')
            starts_at_time = datetime.fromisoformat(starts_at_str.replace('Z', '+00:00'))

            time_difference = current_time - starts_at_time
            
            total_seconds = int(time_difference.total_seconds())
            days, remainder = divmod(total_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            duration = ""
            if days > 0:
                duration += f"{days} days, "
            if hours > 0:
                duration += f"{hours} hours, "
            duration += f"{minutes} minutes ago"

            cleaned_alert = {
                'location': alert.get('labels', {}).get('location'),
                'severity': alert.get('labels', {}).get('severity'),
                'alertname': alert.get('labels', {}).get('alertname'),
                'state': alert.get('status', {}).get('state'),
                'description': alert.get('annotations', {}).get('description'),
                'duration': duration
            }
            cleaned_alerts.append(cleaned_alert)

        except (KeyError, ValueError) as e:
            print(f"Skipping a malformed alert. Error: {e}")
            continue
            
    return {"cleaned_alerts":cleaned_alerts}