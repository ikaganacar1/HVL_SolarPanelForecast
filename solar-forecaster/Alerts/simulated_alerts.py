from flask import Flask, jsonify, request
from datetime import datetime, timedelta
import random
import threading
import time
import requests

app = Flask(__name__)
active_alerts = []

# Alert configuration
ALERT_CONFIGS = {
    "HighCPUUsage": {
        "severity": ["warning", "critical", "info"],
        "thresholds": {"info": 60, "warning": 80, "critical": 95},
        "instances": [
            "server01.example.com:9100", 
            "server02.example.com:9100",
            "web-app-prod-1.internal:9100",
            "web-app-prod-2.internal:9100",
            "api-gateway-1.internal:9100",
            "worker-node-alpha.cluster:9100",
            "worker-node-beta.cluster:9100",
            "k8s-master-node-1:9100",
            "elasticsearch-data-node-3:9100"
        ],
        "message": "CPU usage on {instance} is above {threshold}% (current: {value}%)"
    },
    "ServiceDown": {
        "severity": ["critical", "warning"],
        "services": [
            "payment-api", 
            "user-service", 
            "auth-service",
            "product-catalog-api",
            "shipping-calculator",
            "notification-service",
            "database-connector",
            "image-resizer-worker",
            "realtime-chat-service"
        ],
        "environments": ["production", "staging", "development", "qa"],
        "message": "{service} in {environment} has been down for {duration} minutes"
    },
    "DiskSpaceLow": {
        "severity": ["warning", "critical"],
        "thresholds": {"warning": 85, "critical": 95},
        "instances": [
            "database-server-01", 
            "app-server-01",
            "log-aggregator-main",
            "backup-storage-node",
            "ci-cd-runner-host",
            "prometheus-server"
        ],
        "mountpoints": [
            "/", 
            "/var/log", 
            "/data",
            "/home",
            "/mnt/backups",
            "/var/lib/docker",
            "/opt/data/postgres"
        ],
        "message": "Disk {mountpoint} on {instance} is {value}% full"
    },
    "HighMemoryUsage": {
        "severity": ["info", "warning", "critical"],
        "thresholds": {"info": 70, "warning": 85, "critical": 95},
        "instances": [
            "cache-server-01.example.com:9100",
            "database-replica-01.internal:9100",
            "analytics-processing-node.cluster:9100",
            "redis-master.internal:6379",
            "jvm-app-server-1:8080"
        ],
        "message": "Memory usage on {instance} is above {threshold}% (current: {value}%)"
    },
    "ApiLatencyHigh": {
        "severity": ["warning", "critical"],
        "thresholds": {"warning": 500, "critical": 1000}, # ms cinsinden
        "services": [
            "payment-api",
            "user-service",
            "product-catalog-api",
            "search-service"
        ],
        "environments": ["production", "staging"],
        "message": "P99 latency for {service} in {environment} is over {threshold}ms (current: {value}ms)"
    },
    "QueueSizeHigh": {
        "severity": ["warning", "critical"],
        "thresholds": {"warning": 1000, "critical": 10000},
        "instances": ["rabbitmq-cluster-01", "kafka-broker-prod"],
        "queues": ["payment_processing_queue", "email_notification_queue", "log_ingestion_topic"],
        "message": "Queue/Topic '{queue}' on {instance} has a backlog of {value} messages"
    },
    "DatabaseConnectionErrors": {
        "severity": ["warning", "critical"],
        "thresholds": {"warning": 10, "critical": 50}, # errors per minute
        "services": ["user-service", "payment-api", "product-catalog-api"],
        "environments": ["production"],
        "message": "{service} in {environment} is experiencing a high rate of database connection errors ({value} errors/min)"
    },
    "SSLCertificateExpiry": {
        "severity": ["info", "warning", "critical"],
        "thresholds": {"info": 30, "warning": 14, "critical": 3}, # days until expiry
        "instances": ["www.example.com", "api.example.com", "store.example.org", "internal-dashboard.net"],
        "message": "SSL certificate for {instance} will expire in {value} days"
    }
}


def generate_alert(alert_type, config):
    """Generate a single alert based on type and configuration"""
    # 'info' seviyesi thresholds içinde olmayabilir, bu yüzden kontrol ekleyelim
    possible_severities = [s for s in config["severity"] if s in config.get("thresholds", {s:None})]
    if not possible_severities:
        possible_severities = config["severity"]
        
    severity = random.choice(possible_severities)
    
    alert = {
        "labels": {
            "alertname": alert_type,
            "severity": severity
        },
        "annotations": {},
        "startsAt": (datetime.utcnow() - timedelta(minutes=random.randint(1, 60))).isoformat() + "Z",
        "status": {"state": "active"}
    }
    
    # Generate specific alert data based on alert_type
    if alert_type in ["HighCPUUsage", "HighMemoryUsage"]:
        threshold = config["thresholds"][severity]
        alert["labels"]["instance"] = random.choice(config["instances"])
        alert["annotations"]["description"] = config["message"].format(
            instance=alert["labels"]["instance"],
            threshold=threshold,
            value=round(random.uniform(threshold, min(100, threshold + 15)), 1)
        )
    
    elif alert_type == "ServiceDown":
        alert["labels"]["service"] = random.choice(config["services"])
        alert["labels"]["environment"] = random.choice(config["environments"])
        alert["annotations"]["description"] = config["message"].format(
            service=alert["labels"]["service"],
            environment=alert["labels"]["environment"],
            duration=random.randint(1, 10)
        )
    
    elif alert_type == "DiskSpaceLow":
        threshold = config["thresholds"][severity]
        alert["labels"]["instance"] = random.choice(config["instances"])
        alert["labels"]["mountpoint"] = random.choice(config["mountpoints"])
        alert["annotations"]["description"] = config["message"].format(
            mountpoint=alert["labels"]["mountpoint"],
            instance=alert["labels"]["instance"],
            value=round(random.uniform(threshold, min(99, threshold + 10)), 1)
        )

    elif alert_type == "ApiLatencyHigh":
        threshold = config["thresholds"][severity]
        alert["labels"]["service"] = random.choice(config["services"])
        alert["labels"]["environment"] = random.choice(config["environments"])
        alert["annotations"]["description"] = config["message"].format(
            service=alert["labels"]["service"],
            environment=alert["labels"]["environment"],
            threshold=threshold,
            value=round(random.uniform(threshold, threshold + 200))
        )

    elif alert_type == "QueueSizeHigh":
        threshold = config["thresholds"][severity]
        alert["labels"]["instance"] = random.choice(config["instances"])
        alert["labels"]["queue"] = random.choice(config["queues"])
        alert["annotations"]["description"] = config["message"].format(
            queue=alert["labels"]["queue"],
            instance=alert["labels"]["instance"],
            value=random.randint(threshold, threshold + 5000)
        )

    elif alert_type == "DatabaseConnectionErrors":
        threshold = config["thresholds"][severity]
        alert["labels"]["service"] = random.choice(config["services"])
        alert["labels"]["environment"] = random.choice(config["environments"])
        alert["annotations"]["description"] = config["message"].format(
            service=alert["labels"]["service"],
            environment=alert["labels"]["environment"],
            value=random.randint(threshold, threshold + 40)
        )

    elif alert_type == "SSLCertificateExpiry":
        threshold = config["thresholds"][severity]
        alert["labels"]["instance"] = random.choice(config["instances"])
        alert["annotations"]["description"] = config["message"].format(
            instance=alert["labels"]["instance"],
            value=random.randint(1, threshold)
        )
    
    return alert

def update_alerts():
    """Background task to update alerts periodically"""
    global active_alerts
    while True:
        # Generate new alerts
        active_alerts = []
        for _ in range(random.randint(10, 30)):
            alert_type = random.choice(list(ALERT_CONFIGS.keys()))
            active_alerts.append(generate_alert(alert_type, ALERT_CONFIGS[alert_type]))
        
        # Randomly resolve some alerts
        for alert in active_alerts:
            if random.random() < 0.2:  # 20% chance to resolve
                alert["status"]["state"] = "resolved"
                alert["endsAt"] = datetime.utcnow().isoformat() + "Z"
        
        time.sleep(30)

# API Routes
@app.route('/api/v2/alerts', methods=['GET'])
def get_alerts():
    """Get all alerts, optionally filtered by state"""
    state_filter = request.args.get('active', 'true').lower() == 'true'
    
    if state_filter:
        return jsonify([a for a in active_alerts if a["status"]["state"] == "active"])
    else:
        return jsonify([a for a in active_alerts if a["status"]["state"] == "resolved"])

@app.route('/api/v2/alerts', methods=['POST'])
def create_alert():
    """Create a custom alert"""
    data = request.json
    if not data or 'alertname' not in data:
        return jsonify({"error": "alertname is required"}), 400
    
    alert = {
        "labels": {"alertname": data['alertname'], **data.get('labels', {})},
        "annotations": data.get('annotations', {}),
        "startsAt": datetime.utcnow().isoformat() + "Z",
        "status": {"state": "active"}
    }
    
    active_alerts.append(alert)
    return jsonify({"status": "created", "alert": alert}), 201

@app.route('/api/v2/alerts/stats', methods=['GET'])
def get_stats():
    """Get alert statistics"""
    stats = {
        "total": len(active_alerts),
        "active": sum(1 for a in active_alerts if a["status"]["state"] == "active"),
        "by_severity": {},
        "by_alertname": {}
    }
    
    for alert in active_alerts:
        severity = alert["labels"].get("severity", "unknown")
        alertname = alert["labels"].get("alertname", "unknown")
        
        stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
        stats["by_alertname"][alertname] = stats["by_alertname"].get(alertname, 0) + 1
    
    return jsonify(stats)

# Simple client for testing
class AlertClient:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
    
    def get_alerts(self):
        """Fetch and display alerts"""
        try:
            response = requests.get(f"{self.base_url}/api/v2/alerts")
            alerts = response.json()
            
            print(f"\n{'='*60}")
            print(f"ALERTS - Found {len(alerts)} active alerts")
            print(f"{'='*60}\n")
            
            # Group by severity
            by_severity = {}
            for alert in alerts:
                severity = alert['labels'].get('severity', 'unknown')
                by_severity.setdefault(severity, []).append(alert)
            
            # Display by severity
            for severity in ['critical', 'warning', 'info', 'unknown']:
                if severity in by_severity:
                    print(f"\n[{severity.upper()}] - {len(by_severity[severity])} alerts")
                    for alert in by_severity[severity]:
                        print(f"  • {alert['labels']['alertname']}")
                        print(f"    {alert['annotations'].get('description', 'No description')}")
                        print(f"    Started: {alert['startsAt']}")
                        print()
            
        except Exception as e:
            print(f"Error: {e}")
    
    def get_stats(self):
        """Get and display statistics"""
        try:
            response = requests.get(f"{self.base_url}/api/v2/alerts/stats")
            stats = response.json()
            
            print("\nAlert Statistics:")
            print(f"  Total: {stats['total']}")
            print(f"  Active: {stats['active']}")
            print(f"  By severity: {stats['by_severity']}")
            print(f"  By type: {stats['by_alertname']}")
            
        except Exception as e:
            print(f"Error: {e}")

def main():
    """Main function to run the server and client"""
    # Start background alert updater
    threading.Thread(target=update_alerts, daemon=True).start()
    
    # Initialize with some alerts
    for _ in range(5):
        alert_type = random.choice(list(ALERT_CONFIGS.keys()))
        active_alerts.append(generate_alert(alert_type, ALERT_CONFIGS[alert_type]))
    
    # Start Flask server in background
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False), daemon=True).start()    
    # Wait for server to start
    time.sleep(2)
    
    # Run client demo
    client = AlertClient()
    
    while True:
        print("\n" + "="*60)
        print("1. View alerts")
        print("2. View statistics")
        print("3. Exit")
        
        choice = input("\nSelect option: ")
        
        if choice == "1":
            client.get_alerts()
        elif choice == "2":
            client.get_stats()
        elif choice == "3":
            break
        
        time.sleep(1)

if __name__ == "__main__":
    main()
